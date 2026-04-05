"""EDON Ops Agent — daily system health, pain point detection, and fix suggestions.

Monitors everything: gateway health, latency SLOs, compliance gaps, security posture,
CI failures, open issues, code debt, and business metrics across all tenants.

Uses Claude Opus to reason about what actually matters (not just noise), prioritise
by business impact, and suggest specific fixes. Opens GitHub issues for anything
that needs action so nothing gets lost.

Usage:
    ANTHROPIC_API_KEY=xxx EDON_API_TOKEN=xxx GITHUB_TOKEN=xxx \\
      python -m agents.ops_agent

GitHub Actions: see .github/workflows/ops_agent.yml — runs daily at 7am UTC.
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
GITHUB_REPO = os.environ.get("GITHUB_REPO", "GHOSTCODERRRRAHAHA/edongov")
ADMIN_TENANT_ID = os.environ.get("EDON_ADMIN_TENANT_ID", "tenant_dev")

REPO_ROOT = Path(__file__).resolve().parents[2]


# ── Gateway data ──────────────────────────────────────────────────────────────

def _headers(tenant_id: str = ADMIN_TENANT_ID) -> dict[str, str]:
    h = {"Content-Type": "application/json", "X-Tenant-ID": tenant_id}
    if API_TOKEN:
        h["X-EDON-TOKEN"] = API_TOKEN
    return h


def _fetch(path: str, params: dict | None = None) -> dict[str, Any]:
    try:
        r = requests.get(
            f"{GATEWAY_URL}{path}",
            headers=_headers(),
            params=params or {},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            return data if isinstance(data, dict) else {"_list": data}
        return {"_error": r.status_code, "_text": r.text[:200]}
    except Exception as exc:
        return {"_error": str(exc)}


def collect_gateway_metrics() -> dict[str, Any]:
    print("[ops] Collecting gateway metrics...")
    return {
        "health": _fetch("/health"),
        "health_dependencies": _fetch("/health/dependencies"),
        "security": _fetch("/security/anti-bypass"),
        "compliance": _fetch("/compliance/health"),
        "timeseries_14d": _fetch("/timeseries", {"days": 14}),
        "block_reasons_7d": _fetch("/block-reasons", {"days": 7}),
        "agents": _fetch("/agents"),
    }


# ── GitHub data ───────────────────────────────────────────────────────────────

def _gh_get(path: str) -> Any:
    if not GITHUB_TOKEN:
        return {"_skipped": "no GITHUB_TOKEN"}
    try:
        r = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}{path}",
            headers={
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json",
            },
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
        return {"_error": r.status_code}
    except Exception as exc:
        return {"_error": str(exc)}


def collect_github_metrics() -> dict[str, Any]:
    print("[ops] Collecting GitHub metrics...")

    # Recent CI runs
    runs_raw = _gh_get("/actions/runs?per_page=20")
    runs = []
    if isinstance(runs_raw, dict) and "workflow_runs" in runs_raw:
        for run in runs_raw["workflow_runs"][:20]:
            runs.append({
                "name": run.get("name"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "created_at": run.get("created_at"),
                "html_url": run.get("html_url"),
            })

    # Open issues (not PRs)
    issues_raw = _gh_get("/issues?state=open&per_page=20")
    issues = []
    if isinstance(issues_raw, list):
        for issue in issues_raw:
            if "pull_request" not in issue:
                issues.append({
                    "number": issue.get("number"),
                    "title": issue.get("title"),
                    "labels": [l.get("name") for l in issue.get("labels", [])],
                    "created_at": issue.get("created_at"),
                })

    failed_runs = [r for r in runs if r.get("conclusion") == "failure"]

    return {
        "recent_runs": runs,
        "failed_runs": failed_runs,
        "open_issues": issues,
        "ci_health": "failing" if failed_runs else "passing",
    }


# ── Code health scan ──────────────────────────────────────────────────────────

def scan_code_health() -> dict[str, Any]:
    print("[ops] Scanning codebase for pain points...")

    # Count TODO/FIXME/HACK/BROKEN markers in backend
    todo_counts: dict[str, int] = {}
    markers = ["TODO", "FIXME", "HACK", "BROKEN", "XXX", "NOSONAR"]
    backend_path = REPO_ROOT / "backend" / "edon_gateway"

    all_todos: list[str] = []
    for py_file in backend_path.rglob("*.py"):
        try:
            lines = py_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            for i, line in enumerate(lines, 1):
                for marker in markers:
                    if marker in line.upper() and not line.strip().startswith("#!"):
                        rel = str(py_file.relative_to(REPO_ROOT))
                        all_todos.append(f"{rel}:{i}: {line.strip()[:100]}")
                        todo_counts[marker] = todo_counts.get(marker, 0) + 1
        except Exception:
            pass

    # Check for large files (complexity signal)
    large_files = []
    for py_file in backend_path.rglob("*.py"):
        try:
            lines = py_file.read_text(encoding="utf-8", errors="ignore").count("\n")
            if lines > 600:
                large_files.append({
                    "file": str(py_file.relative_to(REPO_ROOT)),
                    "lines": lines,
                })
        except Exception:
            pass

    # Check requirements for pinning issues
    req_file = REPO_ROOT / "backend" / "requirements.gateway.txt"
    unpinned = []
    if req_file.exists():
        for line in req_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "==" not in line and ">=" not in line:
                unpinned.append(line)

    return {
        "todo_counts": todo_counts,
        "total_todos": sum(todo_counts.values()),
        "sample_todos": all_todos[:15],
        "large_files": sorted(large_files, key=lambda x: x["lines"], reverse=True)[:5],
        "unpinned_deps": unpinned,
    }


# ── Business metrics ──────────────────────────────────────────────────────────

def collect_business_metrics(gateway: dict[str, Any]) -> dict[str, Any]:
    ts = gateway.get("timeseries_14d", {}).get("_list") or []
    if not isinstance(ts, list):
        ts = []

    if ts:
        total_decisions = sum(
            p.get("allowed", 0) + p.get("blocked", 0) + p.get("confirm", 0)
            for p in ts
        )
        week1_vol = sum(
            p.get("allowed", 0) + p.get("blocked", 0) + p.get("confirm", 0)
            for p in ts[:7]
        )
        week2_vol = sum(
            p.get("allowed", 0) + p.get("blocked", 0) + p.get("confirm", 0)
            for p in ts[7:]
        )
        total_blocks = sum(p.get("blocked", 0) for p in ts)
        block_rate = round(total_blocks / total_decisions * 100, 1) if total_decisions else 0
        volume_change_pct = round((week2_vol - week1_vol) / max(week1_vol, 1) * 100, 1)
    else:
        total_decisions = week1_vol = week2_vol = total_blocks = 0
        block_rate = volume_change_pct = 0.0

    agents_raw = gateway.get("agents", {})
    agent_list = agents_raw.get("agents", []) if isinstance(agents_raw, dict) else []
    active_agents = sum(1 for a in agent_list if a.get("status") == "active")
    paused_agents = sum(1 for a in agent_list if a.get("status") == "paused")

    block_reasons = gateway.get("block_reasons_7d", {}).get("_list") or []

    return {
        "total_decisions_14d": total_decisions,
        "week_over_week_change_pct": volume_change_pct,
        "block_rate_pct": block_rate,
        "active_agents": active_agents,
        "paused_agents": paused_agents,
        "top_block_reasons": block_reasons[:5] if isinstance(block_reasons, list) else [],
    }


# ── Claude analysis ───────────────────────────────────────────────────────────

def analyse_with_claude(
    gateway: dict[str, Any],
    github: dict[str, Any],
    code: dict[str, Any],
    business: dict[str, Any],
) -> dict[str, Any]:
    print("[ops] Running Claude Opus analysis...")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    health = gateway.get("health", {})
    components = health.get("components", {})
    security = gateway.get("security", {})
    compliance = gateway.get("compliance", {})

    prompt = f"""You are the CTO agent for EDON, a solo-founder AI governance startup in healthtech.
Your job is to do a daily ops review: find real pain points, prioritise by business impact, and suggest concrete fixes.

Today is {datetime.now(UTC).strftime('%Y-%m-%d')}.

## System Health

Gateway components:
{json.dumps(components, indent=2)[:800]}

Security posture:
- Bypass resistance score: {security.get('bypass_resistance', {}).get('score', 'unknown')}
- Secure: {security.get('secure', 'unknown')}

Compliance health:
{json.dumps(compliance, indent=2)[:600]}

## Business Metrics (last 14 days)
- Total decisions: {business['total_decisions_14d']}
- Week-over-week volume change: {business['week_over_week_change_pct']:+.1f}%
- Block rate: {business['block_rate_pct']}%
- Active agents: {business['active_agents']}  |  Paused agents: {business['paused_agents']}
- Top block reasons: {json.dumps(business['top_block_reasons'])[:300]}

## CI / GitHub
- CI status: {github['ci_health']}
- Failed runs: {len(github['failed_runs'])}
{chr(10).join(f"  - {r['name']} ({r.get('created_at','?')[:10]}): {r['html_url']}" for r in github['failed_runs'][:5])}
- Open issues: {len(github['open_issues'])}
{chr(10).join(f"  - #{i['number']}: {i['title']}" for i in github['open_issues'][:8])}

## Code Health
- Total TODOs/FIXMEs/HACKs: {code['total_todos']}
{chr(10).join(f"  {t}" for t in code['sample_todos'][:8])}
- Large files (complexity risk): {json.dumps(code['large_files'])[:300]}
- Unpinned dependencies: {code['unpinned_deps'][:10]}

---

Analyse this as a sharp CTO would. Your output must be a JSON object:

{{
  "overall_health_score": <0-100>,
  "health_summary": "<one sentence>",
  "pain_points": [
    {{
      "id": "PP-001",
      "title": "<specific problem>",
      "severity": "critical|high|medium|low",
      "category": "reliability|security|compliance|performance|code_quality|business",
      "impact": "<what breaks or who suffers if not fixed>",
      "fix": "<specific actionable fix — file, line, command, or config change>",
      "effort": "minutes|hours|days"
    }}
  ],
  "metrics_flags": [
    "<anything anomalous in the business metrics — volume drops, high block rates, etc>"
  ],
  "auto_fixable": [
    "<pain_point id that could be fixed automatically by an agent>"
  ],
  "weekly_priority": "<the single most important thing to do this week>"
}}

Only surface real problems. Do not pad with low-value observations. Max 8 pain points."""

    msg = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2000,
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
            "overall_health_score": None,
            "health_summary": "Parse error",
            "pain_points": [{"id": "PARSE-ERR", "title": raw[:300], "severity": "low",
                              "category": "code_quality", "impact": "", "fix": "", "effort": "minutes"}],
            "metrics_flags": [],
            "auto_fixable": [],
            "weekly_priority": "Fix ops agent parse error",
        }


# ── GitHub issues ─────────────────────────────────────────────────────────────

def _open_issue(title: str, body: str, labels: list[str]) -> str | None:
    if not GITHUB_TOKEN:
        return None
    r = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPO}/issues",
        headers={"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"},
        json={"title": title, "body": body, "labels": labels},
        timeout=10,
    )
    return r.json().get("html_url") if r.status_code == 201 else None


def file_pain_point_issues(analysis: dict[str, Any]) -> None:
    """Open a GitHub issue for each critical/high pain point."""
    pain_points = analysis.get("pain_points", [])
    critical_high = [p for p in pain_points if p.get("severity") in ("critical", "high")]

    for pp in critical_high:
        title = f"[{pp['severity'].upper()}] {pp['title']}"
        body = f"""**Category:** {pp.get('category', '?')}
**Impact:** {pp.get('impact', '')}
**Effort:** {pp.get('effort', '?')}

## Suggested Fix

{pp.get('fix', 'See ops agent analysis.')}

---
*Filed automatically by EDON Ops Agent — {datetime.now(UTC).strftime('%Y-%m-%d')}*"""

        labels = ["ops-agent", "automated", pp.get("severity", "medium")]
        url = _open_issue(title, body, labels)
        if url:
            print(f"  [ops] Issue filed: {url}")


# ── Report ────────────────────────────────────────────────────────────────────

def print_report(analysis: dict[str, Any], business: dict[str, Any]) -> None:
    score = analysis.get("overall_health_score", "?")
    print("\n" + "=" * 65)
    print(f"EDON OPS REPORT — {datetime.now(UTC).strftime('%Y-%m-%d')}")
    print("=" * 65)
    print(f"Health score: {score}/100")
    print(f"Summary: {analysis.get('health_summary', '')}")
    print(f"\nBusiness: {business['total_decisions_14d']} decisions (14d), "
          f"vol {business['week_over_week_change_pct']:+.1f}% WoW, "
          f"block rate {business['block_rate_pct']}%")

    flags = analysis.get("metrics_flags", [])
    if flags:
        print("\nMetrics flags:")
        for f in flags:
            print(f"  ! {f}")

    print(f"\nPriority this week: {analysis.get('weekly_priority', '')}")

    pain_points = analysis.get("pain_points", [])
    if pain_points:
        print(f"\nPain points ({len(pain_points)}):")
        for pp in pain_points:
            sev = pp.get("severity", "?").upper()
            print(f"\n  [{sev}] {pp.get('id', '?')} — {pp.get('title', '')}")
            print(f"  Impact: {pp.get('impact', '')}")
            print(f"  Fix: {pp.get('fix', '')}")
            print(f"  Effort: {pp.get('effort', '?')}")

    auto = analysis.get("auto_fixable", [])
    if auto:
        print(f"\nAuto-fixable by agents: {', '.join(auto)}")

    print("=" * 65)


# ── Entrypoint ────────────────────────────────────────────────────────────────

def main() -> int:
    print(f"[ops] EDON Ops Agent — {datetime.now(UTC).isoformat()}")
    print(f"[ops] Gateway: {GATEWAY_URL}\n")

    gateway = collect_gateway_metrics()
    github = collect_github_metrics()
    code = scan_code_health()
    business = collect_business_metrics(gateway)

    analysis = analyse_with_claude(gateway, github, code, business)

    print_report(analysis, business)

    # File GitHub issues for critical/high pain points
    if GITHUB_TOKEN:
        print("\n[ops] Filing GitHub issues for critical/high pain points...")
        file_pain_point_issues(analysis)

    # Write full report artifact
    report = {
        "run_at": datetime.now(UTC).isoformat(),
        "analysis": analysis,
        "business": business,
        "code_health": code,
        "ci": {
            "status": github["ci_health"],
            "failed_runs": github["failed_runs"],
            "open_issues_count": len(github["open_issues"]),
        },
    }
    out_path = Path(__file__).parent / "ops_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n[ops] Full report saved to {out_path}")

    critical = [p for p in analysis.get("pain_points", []) if p.get("severity") == "critical"]
    return 1 if critical else 0


if __name__ == "__main__":
    sys.exit(main())
