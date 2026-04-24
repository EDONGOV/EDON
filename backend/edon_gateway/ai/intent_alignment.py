"""AI-powered semantic intent alignment.

Replaces keyword matching in governor._check_intent_alignment() with
a semantic similarity score from Claude. The score is ADVISORY — the
governor still runs deterministic scope checks; this module enriches
the meta and can lower the alignment threshold.

Fail-open: if AI unavailable, returns None and governor falls back to
the existing keyword-matching logic unchanged.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from typing import Optional

from .client import call_advisory_float

logger = logging.getLogger(__name__)

# ── Alignment score cache ─────────────────────────────────────────────────────
# Keyed by sha256(objective + "|" + tool + "|" + op). Scores are stable for a
# given (objective, tool, op) triple — no need to call Claude on every action.
# TTL defaults to 5 minutes; set EDON_AI_ALIGN_CACHE_TTL_SEC=0 to disable.

_CACHE_TTL: float = float(os.getenv("EDON_AI_ALIGN_CACHE_TTL_SEC", "300"))
_cache: dict[str, tuple[float, float]] = {}  # key → (score, expires_at)
_cache_lock = threading.Lock()


def _cache_key(objective: str, tool: str, op: str) -> str:
    raw = f"{objective[:300]}|{tool[:64]}|{op[:64]}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_get(key: str) -> Optional[float]:
    if _CACHE_TTL <= 0:
        return None
    with _cache_lock:
        entry = _cache.get(key)
        if entry and time.monotonic() < entry[1]:
            return entry[0]
        if entry:
            del _cache[key]
    return None


def _cache_set(key: str, score: float) -> None:
    if _CACHE_TTL <= 0:
        return
    with _cache_lock:
        # Evict entries over 1 000 to bound memory
        if len(_cache) >= 1000:
            now = time.monotonic()
            expired = [k for k, (_, exp) in _cache.items() if exp <= now]
            for k in expired[:200]:
                del _cache[k]
        _cache[key] = (score, time.monotonic() + _CACHE_TTL)

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

    safe_objective = str(intent_objective)[:300]
    tool_str = str(action_tool)[:64]
    op_str = str(action_op)[:64]

    # Cache hit — skip the Claude call entirely
    ck = _cache_key(safe_objective, tool_str, op_str)
    cached = _cache_get(ck)
    if cached is not None:
        logger.debug("AI intent alignment (cached): tool=%s op=%s score=%.2f", tool_str, op_str, cached)
        return cached

    payload = _json.dumps({
        "intent_objective": safe_objective,
        "intent_scope_tools": [str(t) for t in (intent_scope_tools or [])[:20]],
        "action_tool": tool_str,
        "action_op": op_str,
    }, separators=(",", ":"))

    score = call_advisory_float(_SYSTEM_PROMPT, payload, key="score")
    if score is not None:
        logger.debug("AI intent alignment: tool=%s op=%s score=%.2f", tool_str, op_str, score)
        _cache_set(ck, score)
    return score


# Threshold: below this score, flag as potential misalignment advisory
MISALIGNMENT_THRESHOLD = float(__import__("os").getenv("EDON_AI_ALIGNMENT_THRESHOLD", "0.25"))
