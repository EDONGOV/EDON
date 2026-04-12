"""EDON Incident Response Agent — detects anomalies and auto-generates incident reports.

Runs every 5 minutes. Compares live gateway metrics against a rolling baseline.
When something breaks — latency spike, error surge, decision anomaly, policy engine
failure, CAV degradation — it:

  1. Detects the anomaly (with thresholds)
  2. Collects all available context (logs, health, timeseries, recent decisions)
  3. Uses Claude Opus to identify probable root cause
  4. Generates a structured incident report
  5. Opens a P0/P1 GitHub issue
  6. Fires a webhook (Slack/Discord/PagerDuty) if configured

Maintains a baseline file so it can detect relative changes, not just absolute thresholds.

Usage:
    ANTHROPIC_API_KEY=xxx EDON_API_TOKEN=xxx python -m agents.incident_agent

    # With Slack webhook
    ANTHROPIC_API_KEY=xxx EDON_API_TOKEN=xxx \\
      INCIDENT_WEBHOOK_URL=https://hooks.slack.com/... python -m agents.incident_agent

GitHub Actions: .github/workflows/incident_agent.yml — runs every 5 minutes.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import requests
import anthropic

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GATEWAY_URL = os.environ.get("EDON_GATEWAY_URL", "https://edon-gateway.fly.dev").rstrip("/")
API_TOKEN = os.environ.get("EDON_API_TOKEN", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "EDONGOV/EDON")
WEBHOOK_URL = os.environ.get("INCIDENT_WEBHOOK_URL", "")   # Slack / Discord / custom
ADMIN_TENANT = os.environ.get("EDON_ADMIN_TENANT_ID", "tenant_dev")

BASELINE_FILE = Path(__file__).parent / "incident_baseline.json"

# Thresholds — tune these once you know your normal numbers
THRESHOLDS = {
    "latency_p99_ms": 200,        # SLO is 100ms — alert at 2x
    "error_rate_pct": 5.0,        # > 5% errors = incident
    "volume_drop_pct": 50,        # decision volume drops >50% WoW = incident
    "block_rate_spike_pct": 40,   # block rate jumps >40% above baseline = anomaly
    "health_degraded": True,      # any degraded component = incident
}


# ── Gateway fetchers ──────────────────────────────────────────────────────────

def _h() -> dict[str, str]:
    h = {"Content-Type": "application/json", "X-Tenant-ID": ADMIN_TENANT}
    if API_TOKEN:
        h["X-EDON-TOKEN"] = API_TOKEN
    return h


def _get(path: str, params: dict | None = None) -> Any:
    try:
        r = requests.get(f"{GATEWAY_URL}{path}", headers=_h(), params=params or {}, timeout=10)
        return r.json() if r.status_code == 200 else {"_error": r.status_code, "_text": r.text[:200]}
    except Exception as exc:
        return {"_error": str(exc)}


def collect_snapshot() -> dict[str, Any]:
    health = _get("/health")
    timeseries = _get("/timeseries", {"days": 2})
    block_reasons = _get("/block-reasons", {"days": 1})
    decisions = _get("/decisions/query", {"limit": 50})
    security = _get("/security/anti-bypass")
    compliance = _get("/compliance/health")

    ts_list: list[dict] = timeseries if isinstance(timeseries, list) else []

    today_vol = sum(
        p.get("allowed", 0) + p.get("blocked", 0) + p.get("confirm", 0)
        for p in ts_list[-1:]
    )
    yesterday_vol = sum(
        p.get("allowed", 0) + p.get("blocked", 0) + p.get("confirm", 0)
        for p in ts_list[-2:-1]
    )
    total_today = max(today_vol, 1)
    block_today = sum(p.get("blocked", 0) for p in ts_list[-1:])
    block_rate = round(block_today / total_today * 100, 1)

    components = health.get("components", {}) if isinstance(health, dict) else {}
    degraded = [k for k, v in components.items() if isinstance(v, dict) and v.get("status") != "healthy"]

    slo = components.get("latency_slo", {})
    p99 = slo.get("p99_ms") if isinstance(slo, dict) else None

    return {
        "ts": datetime.now(UTC).isoformat(),
        "overall_status": health.get("status", "unknown") if isinstance(health, dict) else "unknown",
        "degraded_components": degraded,
        "p99_ms": p99,
        "today_volume": today_vol,
        "yesterday_volume": yesterday_vol,
        "block_rate_pct": block_rate,
        "security_score": (security.get("bypass_resistance", {}) or {}).get("score") if isinstance(security, dict) else None,
        "compliance_status": compliance.get("status", "unknown") if isinstance(compliance, dict) else "unknown",
        "raw": {
            "health": health,
            "block_reasons": block_reasons,
            "recent_decisions": decisions,
        }
    }


# ── Baseline management ───────────────────────────────────────────────────────

def load_baseline() -> dict[str, Any]:
    if BASELINE_FILE.exists():
        return json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    return {}


def save_baseline(snapshot: dict[str, Any]) -> None:
    # Only persist non-raw fields as baseline
    baseline = {k: v for k, v in snapshot.items() if k != "raw"}
    BASELINE_FILE.write_text(json.dumps(baseline, indent=2), encoding="utf-8")


# ── Anomaly detection ─────────────────────────────────────────────────────────

def detect_anomalies(snapshot: dict[str, Any], baseline: dict[str, Any]) -> list[dict[str, Any]]:
    anomalies = []

    # Gateway health degraded
    degraded = snapshot.get("degraded_components", [])
    if degraded:
        anomalies.append({
            "type": "health_degraded",
            "severity": "P0",
            "detail": f"Degraded components: {', '.join(degraded)}",
        })

    # Latency SLO breach
    p99 = snapshot.get("p99_ms")
    if p99 and p99 > THRESHOLDS["latency_p99_ms"]:
        anomalies.append({
            "type": "latency_spike",
            "severity": "P1",
            "detail": f"p99 latency {p99}ms exceeds threshold {THRESHOLDS['latency_p99_ms']}ms",
        })

    # Decision volume drop
    today = snapshot.get("today_volume", 0)
    yesterday = snapshot.get("yesterday_volume", 0)
    if yesterday > 10 and today < yesterday * (1 - THRESHOLDS["volume_drop_pct"] / 100):
        drop_pct = round((yesterday - today) / yesterday * 100)
        anomalies.append({
            "type": "volume_drop",
            "severity": "P1",
            "detail": f"Decision volume dropped {drop_pct}% vs yesterday ({today} vs {yesterday})",
        })

    # Block rate spike vs baseline
    current_block_rate = snapshot.get("block_rate_pct", 0)
    baseline_block_rate = baseline.get("block_rate_pct", 0)
    if baseline_block_rate > 0 and current_block_rate > baseline_block_rate + THRESHOLDS["block_rate_spike_pct"]:
        anomalies.append({
            "type": "block_rate_spike",
            "severity": "P1",
            "detail": f"Block rate {current_block_rate}% vs baseline {baseline_block_rate}% (+{current_block_rate - baseline_block_rate:.1f}%)",
        })

    # Compliance degraded
    if snapshot.get("compliance_status") not in ("healthy", "compliant", "unknown"):
        anomalies.append({
            "type": "compliance_degraded",
            "severity": "P1",
            "detail": f"Compliance health: {snapshot.get('compliance_status')}",
        })

    return anomalies


# ── Incident analysis ─────────────────────────────────────────────────────────

def analyse_incident(snapshot: dict[str, Any], anomalies: list[dict[str, Any]]) -> dict[str, Any]:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    anomaly_summary = "\n".join(f"- [{a['severity']}] {a['type']}: {a['detail']}" for a in anomalies)
    highest_sev = "P0" if any(a["severity"] == "P0" for a in anomalies) else "P1"

    health_raw = json.dumps(snapshot["raw"].get("health", {}), indent=2)[:1500]
    decisions_raw = json.dumps(snapshot["raw"].get("recent_decisions", {}), indent=2)[:1000]
    block_reasons_raw = json.dumps(snapshot["raw"].get("block_reasons", {}), indent=2)[:500]

    prompt = f"""You are the incident response system for EDON, an AI governance platform.
An anomaly has been detected. Analyse it and generate a structured incident report.

## Detected Anomalies
{anomaly_summary}

## Current snapshot ({snapshot['ts']})
- Gateway status: {snapshot['overall_status']}
- Degraded components: {snapshot['degraded_components']}
- p99 latency: {snapshot.get('p99_ms', 'unknown')}ms
- Decision volume today: {snapshot['today_volume']} (yesterday: {snapshot['yesterday_volume']})
- Block rate: {snapshot['block_rate_pct']}%
- Compliance: {snapshot['compliance_status']}

## Raw health data
{health_raw}

## Recent decisions
{decisions_raw}

## Block reasons
{block_reasons_raw}

Respond as JSON:
{{
  "severity": "P0|P1|P2",
  "title": "<short incident title>",
  "probable_cause": "<most likely root cause — be specific>",
  "confidence": "high|medium|low",
  "impact": "<what is broken and who is affected>",
  "immediate_actions": ["<action 1>", "<action 2>", "<action 3>"],
  "investigation_steps": ["<step 1>", "<step 2>"],
  "estimated_resolution": "minutes|hours|unknown",
  "runbook": "<which runbook applies, if any>"
}}"""

    msg = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = str(getattr(msg.content[0], "text", msg.content[0]))
    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        return json.loads(clean.strip())
    except Exception:
        return {
            "severity": highest_sev,
            "title": f"Anomaly detected: {', '.join(a['type'] for a in anomalies)}",
            "probable_cause": raw[:300],
            "confidence": "low",
            "impact": "Unknown — analysis parse failed",
            "immediate_actions": ["Check /health endpoint manually"],
            "investigation_steps": ["Review raw health data"],
            "estimated_resolution": "unknown",
            "runbook": "",
        }


# ── Notifications ─────────────────────────────────────────────────────────────

def _gh_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}


def _find_open_incident(anomaly_types: list[str]) -> dict[str, Any] | None:
    """Return an existing open incident issue that covers any of the same anomaly types."""
    if not GITHUB_TOKEN:
        return None
    try:
        r = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/issues",
            headers=_gh_headers(),
            params={"state": "open", "labels": "incident", "per_page": 20},
            timeout=10,
        )
        if r.status_code != 200:
            return None
        for issue in r.json():
            title = issue.get("title", "").lower()
            if any(atype.lower().replace("_", " ") in title or atype.lower() in title for atype in anomaly_types):
                return issue
    except Exception as exc:
        print(f"[incident] Dedup check failed: {exc}", file=sys.stderr)
    return None


def _add_incident_comment(issue_number: int, report: dict[str, Any], anomalies: list[dict[str, Any]]) -> None:
    """Append a recurrence comment to an existing incident issue instead of opening a duplicate."""
    anomaly_list = "\n".join(f"- [{a['severity']}] **{a['type']}**: {a['detail']}" for a in anomalies)
    comment = (
        f"### Recurrence — {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        f"**Probable cause:** {report.get('probable_cause', '')}\n\n"
        f"**Anomalies this run:**\n{anomaly_list}\n\n"
        f"*Auto-appended by EDON Incident Agent*"
    )
    try:
        requests.post(
            f"https://api.github.com/repos/{GITHUB_REPO}/issues/{issue_number}/comments",
            headers=_gh_headers(),
            json={"body": comment},
            timeout=10,
        )
        print(f"[incident] Appended recurrence comment to existing issue #{issue_number}")
    except Exception as exc:
        print(f"[incident] Comment failed: {exc}", file=sys.stderr)


def open_incident_issue(report: dict[str, Any], anomalies: list[dict[str, Any]]) -> str | None:
    if not GITHUB_TOKEN:
        return None

    anomaly_types = [a["type"] for a in anomalies]

    # Dedup: if the same incident is already open, comment on it instead
    existing = _find_open_incident(anomaly_types)
    if existing:
        _add_incident_comment(existing["number"], report, anomalies)
        return existing.get("html_url")

    sev = report.get("severity", "P1")
    title = f"[INCIDENT {sev}] {report.get('title', 'Anomaly detected')}"
    actions = "\n".join(f"- {a}" for a in report.get("immediate_actions", []))
    steps = "\n".join(f"- {s}" for s in report.get("investigation_steps", []))
    anomaly_list = "\n".join(f"- [{a['severity']}] **{a['type']}**: {a['detail']}" for a in anomalies)

    body = f"""## {sev} Incident — {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}

**Probable cause:** {report.get('probable_cause', '')}
**Confidence:** {report.get('confidence', '')}
**Estimated resolution:** {report.get('estimated_resolution', '')}

## Impact
{report.get('impact', '')}

## Detected Anomalies
{anomaly_list}

## Immediate Actions
{actions}

## Investigation Steps
{steps}

---
*Auto-generated by EDON Incident Agent — {datetime.now(UTC).isoformat()}*"""

    labels = ["incident", f"severity-{sev.lower()}", "automated"]
    r = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPO}/issues",
        headers=_gh_headers(),
        json={"title": title, "body": body, "labels": labels},
        timeout=10,
    )
    return r.json().get("html_url") if r.status_code == 201 else None


def fire_webhook(report: dict[str, Any], anomalies: list[dict[str, Any]], issue_url: str | None) -> None:
    if not WEBHOOK_URL:
        return
    sev = report.get("severity", "P1")
    colour = 0xFF0000 if sev == "P0" else 0xFF8C00

    # Discord-compatible payload (also works for many other webhooks)
    payload = {
        "embeds": [{
            "title": f"🚨 [{sev}] {report.get('title', 'Incident detected')}",
            "color": colour,
            "description": report.get("probable_cause", ""),
            "fields": [
                {"name": "Impact", "value": report.get("impact", "")[:200], "inline": False},
                {"name": "Anomalies", "value": "\n".join(f"• {a['type']}: {a['detail']}" for a in anomalies[:3])[:500], "inline": False},
                {"name": "Immediate action", "value": (report.get("immediate_actions") or ["Check /health"])[0], "inline": False},
            ],
            "footer": {"text": f"EDON Incident Agent • {datetime.now(UTC).strftime('%H:%M UTC')}"},
        }]
    }
    if issue_url:
        payload["embeds"][0]["url"] = issue_url

    try:
        requests.post(WEBHOOK_URL, json=payload, timeout=5)
    except Exception as exc:
        print(f"[incident] Webhook failed: {exc}", file=sys.stderr)


# ── Entrypoint ────────────────────────────────────────────────────────────────

def main() -> int:
    print(f"[incident] EDON Incident Agent — {datetime.now(UTC).isoformat()}")

    baseline = load_baseline()
    snapshot = collect_snapshot()
    anomalies = detect_anomalies(snapshot, baseline)

    if not anomalies:
        print(f"[incident] All clear — status={snapshot['overall_status']} "
              f"p99={snapshot.get('p99_ms', '?')}ms volume={snapshot['today_volume']}")
        save_baseline(snapshot)
        return 0

    print(f"[incident] {len(anomalies)} anomaly/anomalies detected:")
    for a in anomalies:
        print(f"  [{a['severity']}] {a['type']}: {a['detail']}")

    print("[incident] Analysing with Claude Opus...")
    report = analyse_incident(snapshot, anomalies)

    print(f"\n[incident] Incident: {report.get('title')}")
    print(f"[incident] Cause: {report.get('probable_cause')}")
    print(f"[incident] Actions: {report.get('immediate_actions', [])}")

    issue_url = open_incident_issue(report, anomalies)
    if issue_url:
        print(f"[incident] Issue filed: {issue_url}")

    fire_webhook(report, anomalies, issue_url)

    out = {"run_at": datetime.now(UTC).isoformat(), "anomalies": anomalies, "report": report, "issue_url": issue_url}
    (Path(__file__).parent / "last_incident.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    # Don't update baseline on anomaly — preserve pre-incident state for comparison
    return 1 if any(a["severity"] == "P0" for a in anomalies) else 0


if __name__ == "__main__":
    sys.exit(main())
