"""AI-powered escalation summarizer for human review queue.

Generates a concise, human-readable summary of why an action was escalated
and what the reviewer should focus on. Makes the review queue actionable.

Fail-open: if AI unavailable, returns a structured fallback summary.
Never touches verdicts. Only enriches text shown to human reviewers.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .client import call_advisory

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a concise AI governance assistant writing summaries for human reviewers.

You receive a JSON object describing an AI agent action that was escalated for
human review. Write a 2–4 sentence plain-English summary that:
1. States what the agent tried to do (tool + operation)
2. Explains the specific governance concern that triggered review
3. Highlights the key risk factor the reviewer should assess

Be direct and factual. Use no markdown, no bullet points, no headers.
Do NOT recommend a decision. Do NOT add caveats or disclaimers.
Output ONLY the plain-text summary paragraph.
"""


def summarize_escalation(
    action_tool: str,
    action_op: str,
    reason_code: str,
    explanation: str,
    agent_id: str,
    context_keys: Optional[list] = None,
    anomaly_pattern: Optional[str] = None,
) -> str:
    """Generate a reviewer-focused summary for an escalated action.

    Args:
        action_tool: Tool name that was invoked.
        action_op: Operation within the tool.
        reason_code: Governance reason code (e.g. ANOMALY_DETECTED).
        explanation: Existing deterministic explanation from the governor.
        agent_id: ID of the agent that triggered the escalation.
        context_keys: List of context key names present (never values).
        anomaly_pattern: Anomaly pattern name if applicable.

    Returns:
        Plain-text summary string. Falls back to structured text on AI failure.
    """
    import json as _json

    safe_explanation = str(explanation)[:400]
    safe_agent = str(agent_id)[:64]

    payload = _json.dumps({
        "action_tool": str(action_tool)[:64],
        "action_op": str(action_op)[:64],
        "reason_code": str(reason_code)[:64],
        "governance_explanation": safe_explanation,
        "agent_id": safe_agent,
        "context_fields_present": [str(k)[:32] for k in (context_keys or [])[:15]],
        "anomaly_pattern": str(anomaly_pattern)[:64] if anomaly_pattern else None,
    }, separators=(",", ":"))

    result = call_advisory(_SYSTEM_PROMPT, payload, expect_json=False, max_tokens=256)

    if result and isinstance(result, str) and len(result.strip()) > 10:
        return result.strip()

    # Fallback: structured text summary (no AI required)
    return (
        f"Agent '{safe_agent}' attempted {action_tool}.{action_op} and was escalated "
        f"for human review. Governance reason: {reason_code}. "
        f"Details: {safe_explanation[:200]}"
        + (f" Detected pattern: {anomaly_pattern}." if anomaly_pattern else "")
    )


async def enrich_review_item(item: dict) -> dict:
    """Add AI-generated summary to a review queue item dict.

    Called asynchronously; item is returned with an added "ai_summary" key.
    Fails silently and returns the item unchanged on any error.

    Args:
        item: Review queue item dict from the database.

    Returns:
        Item dict with "ai_summary" key added.
    """
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        context = item.get("context") or {}
        summary = await loop.run_in_executor(
            None,
            lambda: summarize_escalation(
                action_tool=item.get("action_type", "").split(".")[0] if "." in str(item.get("action_type", "")) else str(item.get("action_type", "")),
                action_op=item.get("action_type", "").split(".", 1)[1] if "." in str(item.get("action_type", "")) else "",
                reason_code=item.get("reason", ""),
                explanation=item.get("reason", ""),
                agent_id=item.get("agent_id", ""),
                context_keys=list(context.keys()) if isinstance(context, dict) else [],
                anomaly_pattern=context.get("anomaly_result", {}).get("pattern_name") if isinstance(context, dict) else None,
            )
        )
        item = dict(item)
        item["ai_summary"] = summary
    except Exception as exc:
        logger.debug("Failed to enrich review item with AI summary: %s", exc)
    return item
