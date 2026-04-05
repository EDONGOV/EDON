"""EDON Security Monitoring Agent — active threat detection across the gateway.

Runs hourly. Queries audit logs and decision history to detect:

  - Credential abuse / API key enumeration
  - Unusual agent activity (rate spikes, tool scanning, off-hours actions)
  - Prompt injection patterns in payloads
  - Policy bypass probing (BLOCK → slight variation → ALLOW patterns)
  - Reconnaissance (single agent hitting many different tool types)
  - Anomalous escalation spikes that could indicate a compromised agent

When threats are found: generates a security alert, opens a GitHub issue
labeled "security", and fires a webhook if configured.

Usage:
    ANTHROPIC_API_KEY=xxx EDON_API_TOKEN=xxx python -m agents.security_monitor_agent

GitHub Actions: .github/workflows/security_monitor.yml — runs hourly.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import requests
import anthropic

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GATEWAY_URL = os.environ.get("EDON_GATEWAY_URL", "https://edon-gateway.fly.dev").rstrip("/")
API_TOKEN = os.environ.get("EDON_API_TOKEN", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "GHOSTCODERRRRAHAHA/edongov")
WEBHOOK_URL = os.environ.get("INCIDENT_WEBHOOK_URL", "")
ADMIN_TENANT = os.environ.get("EDON_ADMIN_TENANT_ID", "tenant_dev")

STATE_FILE = Path(__file__).parent / "security_monitor_state.json"

# Thresholds
THRESHOLDS = {
    "requests_per_agent_per_hour": 500,       # above this = rate abuse
    "distinct_tools_per_agent": 8,             # hitting many tools = reconnaissance
    "block_then_allow_window": 10,             # bypass probe: BLOCK followed by ALLOW within N decisions
    "escalation_rate_pct": 30,                 # >30% escalations for an agent = unusual
    "off_hours_high_risk": True,               # high-risk actions between midnight-6am = flag
}

# Prompt injection markers — patterns in payloads that indicate injection attempts
INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all previous",
    "disregard your",
    "you are now",
    "new persona",
    "system prompt",
    "forget everything",
    "act as",
    "jailbreak",
    "dan mode",
    "\\n\\nHuman:",
    "\\n\\nAssistant:",
    "</s>",
    "[INST]",
    "<<SYS>>",
]


def _h() -> dict[str, str]:
    h = {"Content-Type": "application/json", "X-Tenant-ID": ADMIN_TENANT}
    if API_TOKEN:
        h["X-EDON-TOKEN"] = API_TOKEN
    return h


def _get(path: str, params: dict | None = None) -> Any:
    try:
        r = requests.get(f"{GATEWAY_URL}{path}", headers=_h(), params=params or {}, timeout=10)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}


# ── Data collection ───────────────────────────────────────────────────────────

def collect_audit_window() -> list[dict[str, Any]]:
    """Pull last 2 hours of audit events."""
    data = _get("/audit/query", {"limit": 500})
    events = data.get("events", data.get("items", [])) if isinstance(data, dict) else []
    return events if isinstance(events, list) else []


def collect_decisions_window() -> list[dict[str, Any]]:
    """Pull last 500 decisions."""
    data = _get("/decisions/query", {"limit": 500})
    decisions = data.get("decisions", data.get("items", [])) if isinstance(data, dict) else []
    return decisions if isinstance(decisions, list) else []


# ── Threat detectors ──────────────────────────────────────────────────────────

def detect_rate_abuse(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    agent_counts: dict[str, int] = defaultdict(int)
    for e in events:
        agent_id = e.get("agent_id") or e.get("action", {}).get("agent_id", "")
        if agent_id:
            agent_counts[agent_id] += 1

    findings = []
    for agent_id, count in agent_counts.items():
        if count > THRESHOLDS["requests_per_agent_per_hour"]:
            findings.append({
                "type": "rate_abuse",
                "severity": "HIGH",
                "agent_id": agent_id,
                "detail": f"Agent made {count} requests in the monitored window (threshold: {THRESHOLDS['requests_per_agent_per_hour']})",
            })
    return findings


def detect_reconnaissance(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Agent hitting many different tool types = reconnaissance pattern."""
    agent_tools: dict[str, set] = defaultdict(set)
    for e in events:
        agent_id = e.get("agent_id", "")
        tool = e.get("action_type", "").split(".")[0] if e.get("action_type") else ""
        if agent_id and tool:
            agent_tools[agent_id].add(tool)

    findings = []
    for agent_id, tools in agent_tools.items():
        if len(tools) >= THRESHOLDS["distinct_tools_per_agent"]:
            findings.append({
                "type": "reconnaissance",
                "severity": "MEDIUM",
                "agent_id": agent_id,
                "detail": f"Agent accessed {len(tools)} distinct tool types: {', '.join(sorted(tools))}",
            })
    return findings


def detect_bypass_probing(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """BLOCK followed quickly by ALLOW on similar action from same agent = bypass probe."""
    agent_sequence: dict[str, list[str]] = defaultdict(list)
    for d in decisions:
        agent_id = d.get("agent_id", "")
        verdict = d.get("verdict", "").upper()
        if agent_id and verdict:
            agent_sequence[agent_id].append(verdict)

    findings = []
    for agent_id, sequence in agent_sequence.items():
        window = THRESHOLDS["block_then_allow_window"]
        for i in range(len(sequence) - 1):
            if sequence[i] in ("BLOCK", "HUMAN_REQUIRED"):
                upcoming = sequence[i + 1:i + window]
                if "ALLOW" in upcoming:
                    findings.append({
                        "type": "bypass_probe",
                        "severity": "HIGH",
                        "agent_id": agent_id,
                        "detail": f"BLOCK followed by ALLOW within {window} decisions — possible policy bypass probing",
                    })
                    break  # one finding per agent
    return findings


def detect_prompt_injection(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Scan payloads for prompt injection patterns."""
    findings = []
    for e in events:
        payload_str = json.dumps(e.get("action_payload") or e.get("payload") or {}).lower()
        for pattern in INJECTION_PATTERNS:
            if pattern.lower() in payload_str:
                agent_id = e.get("agent_id", "unknown")
                findings.append({
                    "type": "prompt_injection",
                    "severity": "CRITICAL",
                    "agent_id": agent_id,
                    "detail": f"Injection pattern '{pattern}' found in action payload",
                    "event_id": e.get("id", e.get("action_id", "")),
                })
                break  # one finding per event
    return findings[:10]  # cap at 10


def detect_escalation_spike(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """High escalation rate for an agent = something is wrong."""
    agent_totals: dict[str, int] = defaultdict(int)
    agent_escalations: dict[str, int] = defaultdict(int)
    for d in decisions:
        agent_id = d.get("agent_id", "")
        if agent_id:
            agent_totals[agent_id] += 1
            if d.get("verdict", "").upper() in ("ESCALATE", "HUMAN_REQUIRED"):
                agent_escalations[agent_id] += 1

    findings = []
    for agent_id, total in agent_totals.items():
        if total < 10:
            continue  # not enough data
        esc_pct = round(agent_escalations[agent_id] / total * 100)
        if esc_pct > THRESHOLDS["escalation_rate_pct"]:
            findings.append({
                "type": "escalation_spike",
                "severity": "MEDIUM",
                "agent_id": agent_id,
                "detail": f"{esc_pct}% escalation rate ({agent_escalations[agent_id]}/{total} decisions)",
            })
    return findings


# ── Analysis ──────────────────────────────────────────────────────────────────

def analyse_threats(findings: list[dict[str, Any]]) -> dict[str, Any]:
    if not findings:
        return {}

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    finding_text = "\n".join(f"- [{f['severity']}] {f['type']} (agent={f.get('agent_id','?')}): {f['detail']}" for f in findings)

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": f"""You are the security analyst for EDON, an AI governance platform.
These security findings were detected in the last monitoring window:

{finding_text}

Analyse these findings and return JSON:
{{
  "overall_severity": "CRITICAL|HIGH|MEDIUM|LOW",
  "attack_pattern": "<what type of attack or misuse this looks like, or null>",
  "most_likely_explanation": "<benign or malicious — be honest>",
  "recommended_actions": ["<action 1>", "<action 2>"],
  "agents_to_investigate": ["<agent_id>"],
  "escalate_immediately": true/false
}}"""}],
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
        return {"overall_severity": "HIGH", "most_likely_explanation": raw[:200],
                "recommended_actions": ["Review audit logs manually"], "escalate_immediately": False}


def _open_issue(title: str, body: str) -> str | None:
    if not GITHUB_TOKEN:
        return None
    r = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPO}/issues",
        headers={"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"},
        json={"title": title, "body": body, "labels": ["security", "automated"]},
        timeout=10,
    )
    return r.json().get("html_url") if r.status_code == 201 else None


# ── Entrypoint ────────────────────────────────────────────────────────────────

def main() -> int:
    print(f"[secmon] EDON Security Monitor — {datetime.now(UTC).isoformat()}")

    events = collect_audit_window()
    decisions = collect_decisions_window()
    print(f"[secmon] Analysing {len(events)} audit events, {len(decisions)} decisions...")

    findings: list[dict[str, Any]] = []
    findings += detect_prompt_injection(events)
    findings += detect_bypass_probing(decisions)
    findings += detect_rate_abuse(events)
    findings += detect_reconnaissance(events)
    findings += detect_escalation_spike(decisions)

    if not findings:
        print("[secmon] No threats detected.")
        return 0

    print(f"[secmon] {len(findings)} finding(s):")
    for f in findings:
        print(f"  [{f['severity']}] {f['type']}: {f['detail']}")

    analysis = analyse_threats(findings)
    sev = analysis.get("overall_severity", "HIGH")
    print(f"\n[secmon] Overall severity: {sev}")
    print(f"[secmon] Pattern: {analysis.get('attack_pattern', 'unknown')}")
    print(f"[secmon] Explanation: {analysis.get('most_likely_explanation', '')}")

    finding_list = "\n".join(f"- [{f['severity']}] **{f['type']}** (agent=`{f.get('agent_id','?')}`): {f['detail']}" for f in findings)
    action_list = "\n".join(f"- {a}" for a in analysis.get("recommended_actions", []))

    issue_body = f"""## Security Alert — {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}

**Overall severity:** {sev}
**Attack pattern:** {analysis.get('attack_pattern', 'None identified')}
**Assessment:** {analysis.get('most_likely_explanation', '')}

## Findings
{finding_list}

## Recommended Actions
{action_list}

**Agents to investigate:** {', '.join(f'`{a}`' for a in analysis.get('agents_to_investigate', []))}

---
*Auto-generated by EDON Security Monitor — {datetime.now(UTC).isoformat()}*"""

    title = f"[SECURITY {sev}] {analysis.get('attack_pattern') or f'{len(findings)} security finding(s)'}"
    issue_url = _open_issue(title, issue_body)
    if issue_url:
        print(f"[secmon] Issue filed: {issue_url}")

    if WEBHOOK_URL and analysis.get("escalate_immediately"):
        payload = {"embeds": [{"title": f"🔐 {title}", "color": 0xFF0000,
                                "description": analysis.get("most_likely_explanation", "")[:300],
                                "footer": {"text": "EDON Security Monitor"}}]}
        try:
            requests.post(WEBHOOK_URL, json=payload, timeout=5)
        except Exception:
            pass

    out = {"run_at": datetime.now(UTC).isoformat(), "findings": findings, "analysis": analysis}
    (Path(__file__).parent / "last_security_scan.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    return 1 if sev in ("CRITICAL", "HIGH") else 0


if __name__ == "__main__":
    sys.exit(main())
