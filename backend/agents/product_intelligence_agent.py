"""EDON Product Intelligence Agent — learns from usage to drive product and revenue.

Analyzes decision logs across all tenants weekly to surface:

  - Most blocked tool/op combinations → friction customers haven't reported
  - New tool types appearing that have no policy rules → product gap
  - Tenants repeatedly hitting the same rules → education or product opportunity
  - Tenants on lower plans with enterprise-level usage → upsell signals
  - Regulation coverage gaps → compliance risk for customers
  - Common escalation patterns → human-in-the-loop UX improvements

Outputs a weekly product intelligence report and opens GitHub issues
for each actionable finding tagged "product".

Usage:
    ANTHROPIC_API_KEY=xxx EDON_API_TOKEN=xxx python -m agents.product_intelligence_agent

GitHub Actions: .github/workflows/product_intelligence.yml — runs weekly.
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
ADMIN_TENANT = os.environ.get("EDON_ADMIN_TENANT_ID", "tenant_dev")

REPO_ROOT = Path(__file__).resolve().parents[2]


def _h(tenant_id: str = "") -> dict[str, str]:
    h = {"Content-Type": "application/json", "X-Tenant-ID": tenant_id or ADMIN_TENANT}
    if API_TOKEN:
        h["X-EDON-TOKEN"] = API_TOKEN
    return h


def _get(path: str, tenant_id: str = "", params: dict | None = None) -> Any:
    try:
        r = requests.get(f"{GATEWAY_URL}{path}", headers=_h(tenant_id), params=params or {}, timeout=10)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}


# ── Data collection ───────────────────────────────────────────────────────────

def collect_usage_data() -> dict[str, Any]:
    print("[product] Collecting usage data...")

    decisions = _get("/decisions/query", params={"limit": 1000})
    audit = _get("/audit/query", params={"limit": 500})
    agents_data = _get("/agents")
    compliance = _get("/compliance/health")
    block_reasons = _get("/block-reasons", params={"days": 30})
    timeseries = _get("/timeseries", params={"days": 30})

    decision_list = decisions.get("decisions", decisions.get("items", [])) if isinstance(decisions, dict) else []
    audit_list = audit.get("events", audit.get("items", [])) if isinstance(audit, dict) else []
    agent_list = agents_data.get("agents", []) if isinstance(agents_data, dict) else []

    return {
        "decisions": decision_list if isinstance(decision_list, list) else [],
        "audit_events": audit_list if isinstance(audit_list, list) else [],
        "agents": agent_list if isinstance(agent_list, list) else [],
        "compliance": compliance,
        "block_reasons": block_reasons if isinstance(block_reasons, list) else [],
        "timeseries": timeseries if isinstance(timeseries, list) else [],
    }


# ── Analysis functions ────────────────────────────────────────────────────────

def analyse_block_patterns(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    tool_block_counts: dict[str, int] = defaultdict(int)
    tool_total_counts: dict[str, int] = defaultdict(int)
    reason_counts: dict[str, int] = defaultdict(int)

    for d in decisions:
        action_type = d.get("action_type", "")
        verdict = d.get("verdict", "").upper()
        reason = d.get("reason_code", "")

        if action_type:
            tool = action_type.split(".")[0]
            tool_total_counts[tool] += 1
            if verdict in ("BLOCK", "HUMAN_REQUIRED", "ESCALATE"):
                tool_block_counts[tool] += 1

        if reason:
            reason_counts[reason] += 1

    # Block rate per tool
    tool_block_rates = {}
    for tool, total in tool_total_counts.items():
        if total >= 5:
            block_rate = round(tool_block_counts[tool] / total * 100, 1)
            tool_block_rates[tool] = {"total": total, "blocked": tool_block_counts[tool], "block_rate_pct": block_rate}

    return {
        "tool_block_rates": dict(sorted(tool_block_rates.items(), key=lambda x: x[1]["block_rate_pct"], reverse=True)[:10]),
        "top_reason_codes": dict(sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
    }


def detect_unknown_tools(decisions: list[dict[str, Any]]) -> list[str]:
    """Tools customers are using that don't have explicit policy rules."""
    schema_path = REPO_ROOT / "backend" / "edon_gateway" / "schemas.py"
    known_tools = set()
    try:
        src = schema_path.read_text(encoding="utf-8")
        for line in src.splitlines():
            if '= "' in line and "Tool" in src[:src.find(line)].split("\n")[-10:][0] if src.find(line) > 0 else False:
                pass
        # Simpler: extract Tool enum values
        import re
        matches = re.findall(r'\w+\s*=\s*"([^"]+)"', src)
        known_tools = {m.lower() for m in matches}
    except Exception:
        pass

    seen_tools = {d.get("action_type", "").split(".")[0].lower() for d in decisions if d.get("action_type")}
    return sorted(seen_tools - known_tools - {""})


def find_upsell_signals(agents: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    signals = []
    agent_decision_counts: dict[str, int] = defaultdict(int)
    for d in decisions:
        agent_id = d.get("agent_id", "")
        if agent_id:
            agent_decision_counts[agent_id] += 1

    for agent in agents:
        agent_id = agent.get("id", "")
        tenant_id = agent.get("tenant_id", "")
        count = agent_decision_counts.get(agent_id, 0)
        # High usage agents on basic plans
        if count > 200:
            signals.append({
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "signal": f"High volume: {count} decisions — candidate for enterprise plan conversation",
            })

    return signals[:10]


def identify_product_gaps(block_patterns: dict[str, Any], unknown_tools: list[str]) -> list[str]:
    gaps = []
    for tool, stats in block_patterns.get("tool_block_rates", {}).items():
        if stats["block_rate_pct"] > 60 and stats["total"] > 20:
            gaps.append(f"Tool '{tool}' has {stats['block_rate_pct']}% block rate — customers may need a pre-built policy pack for this use case")

    for tool in unknown_tools:
        gaps.append(f"Tool '{tool}' is being used by customers but has no SDK documentation or policy example")

    return gaps


# ── Claude synthesis ──────────────────────────────────────────────────────────

def synthesise_intelligence(
    block_patterns: dict[str, Any],
    unknown_tools: list[str],
    upsell_signals: list[dict[str, Any]],
    product_gaps: list[str],
    usage: dict[str, Any],
) -> dict[str, Any]:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    ts = usage.get("timeseries", [])
    total_decisions = sum(
        p.get("allowed", 0) + p.get("blocked", 0) + p.get("confirm", 0)
        for p in ts if isinstance(p, dict)
    )
    active_agents = len([a for a in usage.get("agents", []) if a.get("status") == "active"])

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        messages=[{"role": "user", "content": f"""You are the product intelligence analyst for EDON, an AI governance platform.
Analyse this week's usage data and surface the most actionable insights for a solo founder.

## Usage Summary
- Total decisions (30d): {total_decisions}
- Active agents: {active_agents}

## Block Patterns (top tools by block rate)
{json.dumps(block_patterns.get('tool_block_rates', {}), indent=2)[:600]}

## Top Block Reason Codes
{json.dumps(block_patterns.get('top_reason_codes', {}), indent=2)[:400]}

## Unknown Tools (used by customers, no built-in support)
{unknown_tools[:10]}

## Upsell Signals
{json.dumps(upsell_signals[:5], indent=2)[:400]}

## Product Gaps Identified
{chr(10).join(f'- {g}' for g in product_gaps[:8])}

Return JSON:
{{
  "top_insights": [
    {{"insight": "<specific finding>", "action": "<what to do about it>", "priority": "high|medium|low"}}
  ],
  "feature_requests_implied": ["<feature customers clearly need but don't have>"],
  "upsell_this_week": "<which tenant/segment to prioritise for upsell conversation>",
  "product_health_score": <0-100>,
  "one_line_summary": "<the single most important thing this data is telling you>"
}}

Max 6 insights. Be specific and actionable."""}],
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
        return {"top_insights": [], "one_line_summary": raw[:200], "product_health_score": None}


def _open_issue(title: str, body: str) -> str | None:
    if not GITHUB_TOKEN:
        return None
    r = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPO}/issues",
        headers={"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"},
        json={"title": title, "body": body, "labels": ["product", "automated"]},
        timeout=10,
    )
    return r.json().get("html_url") if r.status_code == 201 else None


def main() -> int:
    print(f"[product] EDON Product Intelligence — {datetime.now(UTC).isoformat()}")

    usage = collect_usage_data()
    decisions = usage["decisions"]
    agents = usage["agents"]

    print(f"[product] Analysing {len(decisions)} decisions, {len(agents)} agents...")

    block_patterns = analyse_block_patterns(decisions)
    unknown_tools = detect_unknown_tools(decisions)
    upsell_signals = find_upsell_signals(agents, decisions)
    product_gaps = identify_product_gaps(block_patterns, unknown_tools)

    print("[product] Synthesising with Claude...")
    intelligence = synthesise_intelligence(block_patterns, unknown_tools, upsell_signals, product_gaps, usage)

    print(f"\n[product] Score: {intelligence.get('product_health_score', '?')}/100")
    print(f"[product] Summary: {intelligence.get('one_line_summary', '')}")
    print(f"\n[product] Top insights:")
    for ins in intelligence.get("top_insights", []):
        print(f"  [{ins.get('priority','?').upper()}] {ins.get('insight','')}")
        print(f"    → {ins.get('action','')}\n")

    # Open issues for high-priority insights
    high_priority = [i for i in intelligence.get("top_insights", []) if i.get("priority") == "high"]
    for ins in high_priority[:3]:
        body = f"""**Insight:** {ins.get('insight', '')}

**Recommended action:** {ins.get('action', '')}

---
*Auto-generated by EDON Product Intelligence Agent — {datetime.now(UTC).isoformat()}*"""
        url = _open_issue(f"[Product Intelligence] {ins.get('insight', '')[:80]}", body)
        if url:
            print(f"  [product] Issue: {url}")

    report = {
        "run_at": datetime.now(UTC).isoformat(),
        "intelligence": intelligence,
        "block_patterns": block_patterns,
        "unknown_tools": unknown_tools,
        "upsell_signals": upsell_signals,
        "product_gaps": product_gaps,
    }
    out_path = Path(__file__).parent / "product_intelligence_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n[product] Full report: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
