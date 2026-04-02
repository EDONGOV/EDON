"""AI-powered independent risk classification.

Provides a second opinion on action risk level, independent of the
deterministic policy engine. The score is ADVISORY — it is stored in
audit meta and can trigger escalation when the AI score materially
disagrees with the computed risk level, but never issues verdicts.

Fail-open: returns None on any error.
"""

from __future__ import annotations

import logging
from typing import Optional

from .client import call_advisory_float

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a governance risk classifier for AI agent actions. You assess the \
potential harm of a proposed action based on its structural features.

You receive a JSON object with:
- "tool": the agent tool being used (e.g. "email", "shell", "filesystem")
- "op": the operation (e.g. "send", "exec", "delete")
- "param_keys": list of parameter key names (NOT values — no content)
- "param_count": number of parameters

Return ONLY a JSON object with two keys:
- "risk_score": float 0.0–1.0 (0=minimal risk, 1=critical risk)
- "risk_label": one of "low", "medium", "high", "critical"

Do NOT explain. Do NOT add commentary. Output ONLY:
{"risk_score": <float>, "risk_label": "<label>"}
"""


def classify_action_risk(
    tool: str,
    op: str,
    param_keys: list,
) -> Optional[dict]:
    """Return AI risk assessment for the proposed action.

    Inputs are structural metadata only (keys, not values).
    Returns dict with "risk_score" float and "risk_label" str, or None.

    Args:
        tool: Tool name (e.g. "shell", "email").
        op: Operation name.
        param_keys: List of parameter key names (never values).

    Returns:
        {"risk_score": float, "risk_label": str} or None on failure.
    """
    import json as _json

    payload = _json.dumps({
        "tool": str(tool)[:64],
        "op": str(op)[:64],
        "param_keys": [str(k)[:64] for k in (param_keys or [])[:20]],
        "param_count": len(param_keys or []),
    }, separators=(",", ":"))

    result = __import__("edon_gateway.ai.client", fromlist=["call_advisory"]).call_advisory(
        _SYSTEM_PROMPT, payload
    )
    if result is None:
        return None

    try:
        score = max(0.0, min(1.0, float(result.get("risk_score", 0.0))))
        label = str(result.get("risk_label", "low"))
        if label not in ("low", "medium", "high", "critical"):
            label = "medium"
        logger.debug("AI risk: tool=%s op=%s score=%.2f label=%s", tool, op, score, label)
        return {"risk_score": score, "risk_label": label}
    except Exception:
        return None


# If AI risk score exceeds this and computed_risk is LOW, flag for escalation advisory
AI_RISK_ESCALATION_THRESHOLD = float(__import__("os").getenv("EDON_AI_RISK_THRESHOLD", "0.75"))
