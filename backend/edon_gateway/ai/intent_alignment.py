"""AI-powered semantic intent alignment.

Replaces keyword matching in governor._check_intent_alignment() with
a semantic similarity score from Claude. The score is ADVISORY — the
governor still runs deterministic scope checks; this module enriches
the meta and can lower the alignment threshold.

Fail-open: if AI unavailable, returns None and governor falls back to
the existing keyword-matching logic unchanged.
"""

from __future__ import annotations

import logging
from typing import Optional

from .client import call_advisory_float

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a governance alignment classifier. You evaluate whether a proposed \
agent action is semantically consistent with an intent contract.

You receive a JSON object with:
- "intent_objective": the declared goal of the agent session (string)
- "intent_scope_tools": list of tool names the intent allows
- "action_tool": the tool the agent wants to use (string)
- "action_op": the operation within that tool (string)

Return ONLY a JSON object with a single key "score" (float 0.0–1.0):
- 1.0 = the action is clearly aligned with the intent objective
- 0.5 = ambiguous / neutral
- 0.0 = the action is clearly misaligned with the intent objective

Do NOT explain. Do NOT add commentary. Output ONLY: {"score": <float>}
"""


def score_intent_alignment(
    intent_objective: str,
    intent_scope_tools: list,
    action_tool: str,
    action_op: str,
) -> Optional[float]:
    """Return semantic alignment score 0.0–1.0 for the proposed action.

    Returns None if AI is unavailable — caller should fall back to
    deterministic keyword logic in that case.

    Args:
        intent_objective: Human-readable goal of the agent session.
        intent_scope_tools: List of tool names declared in the intent scope.
        action_tool: Tool name being invoked.
        action_op: Operation within the tool.

    Returns:
        Float in [0.0, 1.0] or None on failure.
    """
    import json as _json

    # Truncate objective to avoid leaking large agent-controlled blobs
    safe_objective = str(intent_objective)[:300]

    payload = _json.dumps({
        "intent_objective": safe_objective,
        "intent_scope_tools": [str(t) for t in (intent_scope_tools or [])[:20]],
        "action_tool": str(action_tool)[:64],
        "action_op": str(action_op)[:64],
    }, separators=(",", ":"))

    score = call_advisory_float(_SYSTEM_PROMPT, payload, key="score")
    if score is not None:
        logger.debug(
            "AI intent alignment: tool=%s op=%s score=%.2f",
            action_tool, action_op, score,
        )
    return score


# Threshold: below this score, flag as potential misalignment advisory
MISALIGNMENT_THRESHOLD = float(__import__("os").getenv("EDON_AI_ALIGNMENT_THRESHOLD", "0.25"))
