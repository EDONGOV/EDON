"""AI-powered audit trail anomaly mining.

Runs a nightly background task that mines the audit trail for patterns
that may indicate coordinated attacks, drift in agent behavior, or
emerging threat vectors.

Findings are stored as structured JSON in memory and surfaced via API.
They are NEVER automatically acted upon — they are reports for human review.

Fail-open: all errors caught and logged. Governance unaffected.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, UTC
from typing import Optional

from .client import call_advisory

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a security analyst reviewing AI agent audit logs for anomalous patterns.

You receive a JSON object with aggregate statistics about agent behavior over a
time period. Identify concerning patterns that may indicate:
- Coordinated multi-agent attacks
- Gradual scope creep (agent behavior drifting beyond its intent)
- Injection campaign attempts (repeated injection blocks from one agent)
- Time-of-day anomalies (unusual activity outside normal hours)
- Tool combination sequences that suggest reconnaissance or exfiltration

Return ONLY a JSON object:
{
  "findings": [
    {
      "severity": "low"|"medium"|"high"|"critical",
      "pattern": "<short pattern name>",
      "description": "<one sentence describing the finding>",
      "affected_agents": ["agent_id1", ...],
      "recommendation": "<one sentence response recommendation>",
      "confidence": <float 0.0-1.0>
    }
  ],
  "analysis_period_summary": "<one sentence summary of the period>"
}

Return empty findings array if no concerning patterns detected.
Cap at 5 findings. Prioritize by severity descending.
"""


def _build_mining_payload(events: list, period_hours: int = 24) -> dict:
    """Build an aggregate statistics payload for the audit miner."""
    if not events:
        return {}

    total = len(events)

    # Per-agent stats
    agent_stats: dict = {}
    for e in events:
        aid = (e.get("action") or {}).get("agent_id") or e.get("agent_id") or "unknown"
        if aid not in agent_stats:
            agent_stats[aid] = {"total": 0, "blocked": 0, "injections": 0, "anomalies": 0}
        agent_stats[aid]["total"] += 1
        verdict = (e.get("decision") or {}).get("verdict", "")
        if verdict == "BLOCK":
            agent_stats[aid]["blocked"] += 1
        rc = (e.get("decision") or {}).get("reason_code", "")
        if "INJECTION" in rc:
            agent_stats[aid]["injections"] += 1
        if (e.get("context") or {}).get("anomaly_result"):
            agent_stats[aid]["anomalies"] += 1

    # Identify high-block agents (potential bad actors)
    high_block_agents = [
        {"agent_id": aid[:32], "block_rate": round(s["blocked"] / max(s["total"], 1), 2),
         "injection_count": s["injections"], "anomaly_count": s["anomalies"]}
        for aid, s in agent_stats.items()
        if s["blocked"] / max(s["total"], 1) > 0.3 or s["injections"] > 2
    ][:10]

    # Tool sequence patterns
    tool_sequences: dict = {}
    for e in events:
        tool = (e.get("action") or {}).get("tool", "")
        op = (e.get("action") or {}).get("op", "")
        if tool and op:
            key = f"{tool}.{op}"
            tool_sequences[key] = tool_sequences.get(key, 0) + 1

    top_tools = sorted(tool_sequences.items(), key=lambda x: -x[1])[:10]

    return {
        "period_hours": period_hours,
        "total_events": total,
        "unique_agents": len(agent_stats),
        "overall_block_rate": round(
            sum(1 for e in events if (e.get("decision") or {}).get("verdict") == "BLOCK") / max(total, 1), 3
        ),
        "high_block_rate_agents": high_block_agents,
        "top_tool_ops": [{"tool_op": t, "count": c} for t, c in top_tools],
        "injection_events": sum(
            1 for e in events
            if "INJECTION" in str((e.get("decision") or {}).get("reason_code", ""))
        ),
        "anomaly_events": sum(
            1 for e in events if (e.get("context") or {}).get("anomaly_result")
        ),
    }


def mine_audit_trail(events: list, period_hours: int = 24) -> dict:
    """Analyze audit events for security patterns and anomalies.

    Args:
        events: Audit event dicts from the database.
        period_hours: Time period these events cover.

    Returns:
        Dict with "findings" list and "analysis_period_summary" string.
    """
    import json as _json

    stats = _build_mining_payload(events, period_hours)
    if not stats or stats.get("total_events", 0) < 5:
        return {"findings": [], "analysis_period_summary": "Insufficient data for analysis."}

    payload = _json.dumps(stats, separators=(",", ":"))
    result = call_advisory(_SYSTEM_PROMPT, payload, max_tokens=1024)

    if result is None:
        return {"findings": [], "analysis_period_summary": "AI analysis unavailable."}

    try:
        findings = result.get("findings", [])
        if not isinstance(findings, list):
            findings = []

        # Validate findings
        valid_findings = []
        for f in findings[:5]:
            if not isinstance(f, dict):
                continue
            severity = str(f.get("severity", "low")).lower()
            if severity not in ("low", "medium", "high", "critical"):
                severity = "low"
            valid_findings.append({
                "severity": severity,
                "pattern": str(f.get("pattern", ""))[:64],
                "description": str(f.get("description", ""))[:300],
                "affected_agents": [str(a)[:64] for a in (f.get("affected_agents") or [])[:5]],
                "recommendation": str(f.get("recommendation", ""))[:200],
                "confidence": max(0.0, min(1.0, float(f.get("confidence", 0.5)))),
            })

        return {
            "findings": valid_findings,
            "analysis_period_summary": str(result.get("analysis_period_summary", ""))[:300],
            "stats": stats,
            "analyzed_at": datetime.now(UTC).isoformat(),
        }

    except Exception as exc:
        logger.debug("Audit mining result parsing failed: %s", exc)
        return {"findings": [], "analysis_period_summary": "Result parsing failed."}


# ── Background Task ───────────────────────────────────────────────────────────

_mining_cache: dict = {}
_mining_cache_ts: Optional[datetime] = None
_MINING_INTERVAL_SEC = int(__import__("os").getenv("EDON_AI_MINING_INTERVAL", "86400"))


async def run_audit_mining_loop(db_getter) -> None:
    """Background asyncio task: mine audit trail nightly.

    Args:
        db_getter: Callable returning the database instance.
    """
    global _mining_cache, _mining_cache_ts

    while True:
        await asyncio.sleep(_MINING_INTERVAL_SEC)
        try:
            db = db_getter()
            events = db.query_audit_events(limit=2000)
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: mine_audit_trail(events)
            )
            _mining_cache = result
            _mining_cache_ts = datetime.now(UTC)
            n = len(result.get("findings", []))
            logger.info(
                "[audit_miner] Completed: %d findings from %d events",
                n, len(events)
            )
        except Exception as exc:
            logger.debug("[audit_miner] Background task error (fail-open): %s", exc)


def get_cached_mining_report() -> dict:
    """Return the latest cached audit mining report."""
    return {
        "report": _mining_cache,
        "generated_at": _mining_cache_ts.isoformat() if _mining_cache_ts else None,
        "finding_count": len(_mining_cache.get("findings", [])),
    }
