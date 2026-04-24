"""AI-powered policy suggestion engine.

Analyzes recent audit events to identify patterns and suggest new policy
rules that would improve governance. Runs as a background task.

Suggestions are surfaced via API but NEVER auto-applied — human approval
is always required before any rule takes effect.

Fail-open: all errors are caught and logged. Governance unaffected.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, UTC
from typing import Optional

from .client import call_advisory

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a governance policy engineer analyzing AI agent behavior patterns.

You receive a JSON object with:
- "total_events": total audit events analyzed
- "block_rate": fraction of events that were blocked (0.0–1.0)
- "escalate_rate": fraction escalated
- "top_blocked_tools": top 5 tool+op pairs most frequently blocked, with counts
- "top_reason_codes": top 5 block/escalate reason codes, with counts
- "agent_ids_analyzed": number of distinct agents
- "anomaly_rate": fraction of events that had anomaly detections
- "shadow_findings": list of shadow-mode findings (tool, op, severity, description) \
  — these are actions that PASSED governance but shadow replay flagged as risky. \
  High-severity shadow findings are the most important signal.

Based on these patterns, suggest 1–3 specific policy rules that would reduce
unnecessary blocks OR catch more genuine threats. Each suggestion must include:
- "name": short rule name (snake_case)
- "description": one sentence explaining the rule
- "condition_tool": tool name to match (or null for any)
- "condition_op": operation to match (or null for any)
- "action": "BLOCK", "ESCALATE", or "ALLOW"
- "rationale": why this pattern warrants this rule (one sentence)
- "confidence": float 0.0–1.0 (your confidence this is a good suggestion)

Prioritize shadow_findings with severity "critical" or "high" — these represent
actual policy blind spots confirmed by replay, not just block-rate noise.

Return ONLY a JSON object: {"suggestions": [...]}
If you see no actionable patterns, return: {"suggestions": []}
"""


def _build_shadow_findings_payload(trace_store) -> list:
    """Pull recent shadow findings from TraceStore and format for the AI prompt."""
    try:
        raw = trace_store.recent_findings(limit=20)
        out = []
        for f in raw:
            out.append({
                "tool": f.get("tool") or f.get("action_tool", "unknown"),
                "op": f.get("op") or f.get("action_op", "unknown"),
                "severity": f.get("severity", "unknown"),
                "description": str(f.get("description") or f.get("finding_type", ""))[:120],
            })
        return out
    except Exception as exc:
        logger.debug("Shadow findings fetch failed: %s", exc)
        return []


def _build_stats_payload(events: list, shadow_findings: list | None = None) -> dict:
    """Summarize audit events into aggregate statistics for the AI prompt."""
    if not events:
        return {}

    total = len(events)
    blocked = sum(1 for e in events if (e.get("decision") or {}).get("verdict") == "BLOCK")
    escalated = sum(1 for e in events if (e.get("decision") or {}).get("verdict") == "ESCALATE")
    anomaly = sum(1 for e in events if (e.get("context") or {}).get("anomaly_result"))

    # Count tool+op pairs in blocked/escalated events
    tool_op_counts: dict = {}
    for e in events:
        verdict = (e.get("decision") or {}).get("verdict", "")
        if verdict in ("BLOCK", "ESCALATE"):
            tool = (e.get("action") or {}).get("tool", "unknown")
            op = (e.get("action") or {}).get("op", "unknown")
            key = f"{tool}.{op}"
            tool_op_counts[key] = tool_op_counts.get(key, 0) + 1

    top_blocked = sorted(tool_op_counts.items(), key=lambda x: -x[1])[:5]

    reason_counts: dict = {}
    for e in events:
        rc = (e.get("decision") or {}).get("reason_code", "unknown")
        verdict = (e.get("decision") or {}).get("verdict", "")
        if verdict in ("BLOCK", "ESCALATE"):
            reason_counts[rc] = reason_counts.get(rc, 0) + 1

    top_reasons = sorted(reason_counts.items(), key=lambda x: -x[1])[:5]

    agent_ids = {(e.get("action") or {}).get("agent_id") for e in events if e.get("action")}

    return {
        "total_events": total,
        "block_rate": round(blocked / total, 3) if total else 0,
        "escalate_rate": round(escalated / total, 3) if total else 0,
        "top_blocked_tools": [{"tool_op": t, "count": c} for t, c in top_blocked],
        "top_reason_codes": [{"reason": r, "count": c} for r, c in top_reasons],
        "agent_ids_analyzed": len(agent_ids),
        "anomaly_rate": round(anomaly / total, 3) if total else 0,
        "shadow_findings": shadow_findings or [],
    }


def generate_policy_suggestions(events: list, shadow_findings: list | None = None) -> list:
    """Analyze audit events and return a list of policy suggestions.

    Args:
        events: List of audit event dicts from the database.

    Returns:
        List of suggestion dicts, empty list on failure or no patterns.
    """
    import json as _json

    stats = _build_stats_payload(events, shadow_findings=shadow_findings)
    if not stats or stats.get("total_events", 0) < 10:
        return []

    payload = _json.dumps(stats, separators=(",", ":"))
    result = call_advisory(_SYSTEM_PROMPT, payload, max_tokens=1024)

    if result is None:
        return []

    try:
        suggestions = result.get("suggestions", [])
        if not isinstance(suggestions, list):
            return []

        # Validate and sanitize each suggestion
        valid = []
        for s in suggestions[:5]:  # Cap at 5 suggestions
            if not isinstance(s, dict):
                continue
            name = str(s.get("name", ""))[:64]
            action = str(s.get("action", "")).upper()
            if not name or action not in ("BLOCK", "ESCALATE", "ALLOW"):
                continue
            confidence = max(0.0, min(1.0, float(s.get("confidence", 0.5))))
            valid.append({
                "name": name,
                "description": str(s.get("description", ""))[:200],
                "condition_tool": s.get("condition_tool"),
                "condition_op": s.get("condition_op"),
                "action": action,
                "rationale": str(s.get("rationale", ""))[:200],
                "confidence": confidence,
                "source": "ai_policy_suggester",
                "generated_at": datetime.now(UTC).isoformat(),
                "status": "pending_review",
                # auto_escalate=True means this suggestion is shown in the one-click
                # approval queue — still requires a human click, never auto-applied.
                "auto_escalate": confidence >= 0.85,
            })
        return valid

    except Exception as exc:
        logger.debug("Policy suggestion parsing failed: %s", exc)
        return []


# ── Background Task ───────────────────────────────────────────────────────────

_suggestion_cache: list = []
_suggestion_cache_ts: Optional[datetime] = None
_SUGGESTION_INTERVAL_SEC = int(__import__("os").getenv("EDON_AI_SUGGEST_INTERVAL", "3600"))


async def run_policy_suggestion_loop(db_getter) -> None:
    """Background asyncio task: generate policy suggestions hourly.

    Args:
        db_getter: Callable returning the database instance.
    """
    global _suggestion_cache, _suggestion_cache_ts

    while True:
        await asyncio.sleep(_SUGGESTION_INTERVAL_SEC)
        try:
            db = db_getter()
            # Analyze last 500 audit events + shadow findings
            events = db.query_audit_events(limit=500)
            shadow_findings: list = []
            try:
                from ..shadow.trace_capture import TraceStore
                ts = TraceStore()
                shadow_findings = _build_shadow_findings_payload(ts)
            except Exception as _sf_err:
                logger.debug("[policy_suggester] Shadow findings unavailable: %s", _sf_err)
            suggestions = await asyncio.get_event_loop().run_in_executor(
                None, lambda: generate_policy_suggestions(events, shadow_findings=shadow_findings)
            )
            if suggestions:
                _suggestion_cache = suggestions
                _suggestion_cache_ts = datetime.now(UTC)
                logger.info(
                    "[policy_suggester] Generated %d suggestions from %d events",
                    len(suggestions), len(events)
                )
        except Exception as exc:
            logger.debug("[policy_suggester] Background task error (fail-open): %s", exc)


def get_cached_suggestions() -> dict:
    """Return the latest cached policy suggestions."""
    return {
        "suggestions": _suggestion_cache,
        "generated_at": _suggestion_cache_ts.isoformat() if _suggestion_cache_ts else None,
        "count": len(_suggestion_cache),
    }
