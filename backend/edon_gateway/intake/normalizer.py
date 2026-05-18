"""Intent Normalization Layer.

Every agent action arrives with two intent signals that may disagree:
  - stated_intent: what the agent says it is doing ("send a weekly report")
  - user_message:  what the user actually asked  ("delete all old records")
  - action_type:   what the agent is actually doing (database.delete)

Without reconciling these, the governor is evaluating the stated_intent,
not the actual task. This is the primary vector for social engineering of
the governance layer.

This module:
  1. Structurally scores alignment between intent signals and action (O(n), no AI)
  2. Optionally calls Claude to classify the true intent from combined signals
  3. Flags misalignment above configured threshold
  4. Returns a NormalizedIntent that feeds into the governor context

Integration point (v1_action.py, before governor.evaluate):
    from ..intake.normalizer import normalize_intent, MISALIGNMENT_THRESHOLD
    norm = normalize_intent(
        stated_intent=req_context.get("stated_intent", ""),
        user_message=req_context.get("user_message", ""),
        action_type=req.action_type,
        action_payload=action_params,
    )
    req_context["intent_alignment_score"] = norm.alignment_score
    req_context["intent_misalignment_flag"] = norm.misalignment_flag
    if norm.misalignment_flag:
        req_context["intent_gap_description"] = norm.gap_description

Fail-open: any error returns a neutral NormalizedIntent (score=0.5, no flag).
Never raises. Never blocks governance.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional

from ..logging_config import get_logger

logger = get_logger(__name__)

MISALIGNMENT_THRESHOLD = float(os.getenv("EDON_INTENT_MISALIGNMENT_THRESHOLD", "0.35"))
_AI_NORMALIZATION_ENABLED = os.getenv("EDON_INTENT_AI_ENABLED", "true").strip().lower() == "true"
_AI_THRESHOLD = float(os.getenv("EDON_INTENT_AI_THRESHOLD", "0.50"))  # only call AI when structural score < this


# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class NormalizedIntent:
    """Output of the intent normalization layer."""

    # Core alignment signal
    alignment_score: float          # 0.0 = total mismatch, 1.0 = perfect alignment
    misalignment_flag: bool         # True when score < MISALIGNMENT_THRESHOLD

    # Inferred intent (may differ from stated_intent when signals conflict)
    inferred_intent_class: str      # "read" | "write" | "delete" | "execute" | "send" | "unknown"
    inferred_risk_signal: str       # "low" | "medium" | "high" — based on action class alone
    gap_description: Optional[str]  # human-readable description of the gap, if any

    # Component scores (for audit trail)
    structural_score: float = 1.0   # deterministic structural alignment
    semantic_score: Optional[float] = None  # AI-derived semantic alignment (None if not called)

    # Source signals (preserved for audit)
    stated_intent_class: str = "unknown"
    action_class: str = "unknown"

    # Advisory — never used as sole basis for BLOCK
    source: str = "structural"      # "structural" | "ai_assisted"


# ── Action classification ──────────────────────────────────────────────────────

_WRITE_OPS = frozenset({
    "send", "write", "create", "update", "upsert", "insert", "post",
    "publish", "push", "upload", "submit", "put", "patch",
})
_DELETE_OPS = frozenset({
    "delete", "remove", "drop", "truncate", "purge", "clear", "destroy",
    "revoke", "ban", "disable",
})
_EXECUTE_OPS = frozenset({
    "exec", "execute", "run", "invoke", "call", "deploy", "trigger",
    "start", "stop", "restart", "kill",
})
_READ_OPS = frozenset({
    "read", "get", "fetch", "list", "query", "search", "find",
    "retrieve", "load", "download", "export",
})
_SEND_OPS = frozenset({"send", "email", "message", "notify", "alert", "broadcast"})

_HIGH_RISK_TOOLS = frozenset({"shell", "database", "vehicle", "robot", "drone", "forklift"})
_EXTERNAL_TOOLS = frozenset({"email", "slack", "discord", "twitter", "gmail", "http", "browser"})


def _classify_operation(action_type: str) -> tuple[str, str]:
    """Return (action_class, risk_signal) from action_type string."""
    parts = action_type.lower().split(".", 1)
    tool = parts[0]
    op = parts[1] if len(parts) > 1 else ""

    if op in _DELETE_OPS:
        action_class = "delete"
    elif op in _EXECUTE_OPS:
        action_class = "execute"
    elif op in _WRITE_OPS or op in _SEND_OPS:
        action_class = "write" if tool not in _EXTERNAL_TOOLS else "send"
    elif op in _READ_OPS:
        action_class = "read"
    else:
        action_class = "unknown"

    if tool in _HIGH_RISK_TOOLS or action_class in ("delete", "execute"):
        risk = "high"
    elif action_class in ("send", "write") or tool in _EXTERNAL_TOOLS:
        risk = "medium"
    else:
        risk = "low"

    return action_class, risk


# ── Intent signal extraction ───────────────────────────────────────────────────

# Word sets that indicate each intent class in natural language
_INTENT_SIGNALS: dict[str, frozenset[str]] = {
    "read":    frozenset({"read", "get", "fetch", "check", "view", "see", "look", "find",
                          "retrieve", "show", "display", "list", "search", "query", "review",
                          "report", "summarize", "summary", "audit"}),
    "write":   frozenset({"write", "create", "add", "update", "save", "store", "record",
                          "insert", "set", "change", "edit", "modify", "upload"}),
    "delete":  frozenset({"delete", "remove", "clear", "clean", "purge", "drop",
                          "erase", "wipe", "destroy"}),
    "execute": frozenset({"run", "execute", "start", "trigger", "invoke", "launch",
                          "deploy", "process", "perform"}),
    "send":    frozenset({"send", "email", "message", "notify", "alert", "share",
                          "deliver", "forward", "broadcast", "post"}),
}


def _classify_intent_text(text: str) -> str:
    """Return intent class from free-text using token overlap."""
    if not text:
        return "unknown"
    tokens = set(re.findall(r"\b\w+\b", text.lower()))
    scores = {cls: len(tokens & words) for cls, words in _INTENT_SIGNALS.items()}
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "unknown"


# ── Alignment scoring ──────────────────────────────────────────────────────────

# How compatible is stated_intent_class with action_class?
# 1.0 = perfect, 0.0 = direct contradiction
_COMPATIBILITY: dict[tuple[str, str], float] = {
    # Perfect match
    ("read",    "read"):    1.0,
    ("write",   "write"):   1.0,
    ("write",   "send"):    0.9,
    ("send",    "send"):    1.0,
    ("send",    "write"):   0.8,
    ("delete",  "delete"):  1.0,
    ("execute", "execute"): 1.0,
    # Partial overlap
    ("read",    "write"):   0.4,
    ("read",    "send"):    0.5,
    ("read",    "execute"): 0.3,
    ("write",   "read"):    0.6,
    ("write",   "delete"):  0.2,
    ("send",    "read"):    0.5,
    ("send",    "delete"):  0.1,
    ("execute", "read"):    0.5,
    ("execute", "write"):   0.7,
    # Direct contradictions
    ("read",    "delete"):  0.0,
    ("delete",  "read"):    0.2,
    ("delete",  "write"):   0.3,
    ("delete",  "send"):    0.1,
    ("delete",  "execute"): 0.4,
    ("execute", "delete"):  0.6,
}


def _structural_alignment(
    stated_intent: str,
    user_message: str,
    action_class: str,
) -> tuple[float, str, Optional[str]]:
    """Deterministic alignment score from signal classification.

    Returns (score, stated_intent_class, gap_description).
    """
    # Use user_message if stated_intent is absent or generic
    intent_text = stated_intent.strip() if stated_intent.strip() else user_message.strip()
    if not intent_text:
        # No intent signal at all — neutral score
        return 0.7, "unknown", None

    # If both are provided, weight user_message more heavily (it's the raw ask)
    if stated_intent.strip() and user_message.strip():
        si_class = _classify_intent_text(stated_intent)
        um_class = _classify_intent_text(user_message)
        # Take the lower-compatibility class as the binding intent
        si_compat = _COMPATIBILITY.get((si_class, action_class), 0.5)
        um_compat = _COMPATIBILITY.get((um_class, action_class), 0.5)

        # If user_message is significantly more misaligned → use it as primary
        if um_compat < si_compat - 0.2:
            stated_class = um_class
            score = um_compat * 0.7 + si_compat * 0.3   # weight user_message
        else:
            stated_class = si_class
            score = si_compat * 0.5 + um_compat * 0.5
    else:
        stated_class = _classify_intent_text(intent_text)
        score = _COMPATIBILITY.get((stated_class, action_class), 0.5)

    gap = None
    if score < MISALIGNMENT_THRESHOLD:
        gap = (
            f"Intent signals '{stated_class}' but action performs '{action_class}'. "
            f"Alignment score: {score:.2f}. "
            f"Stated: '{stated_intent[:80]}'. "
            f"User message: '{user_message[:80]}'."
        )

    return round(score, 4), stated_class, gap


# ── AI-assisted normalization ──────────────────────────────────────────────────

_AI_SYSTEM = """\
You are an intent alignment classifier for an AI governance system.

You receive structured input about an AI agent action and must determine:
1. Whether the stated intent matches what the action actually does
2. The true intent class of the combined signals

Input fields:
- stated_intent: what the agent says it is doing
- user_message: what the user actually requested
- action_type: tool.operation being executed (e.g. "email.send", "database.delete")
- action_class: pre-classified action category

Return ONLY valid JSON, no commentary:
{
  "alignment_score": <float 0.0-1.0>,
  "true_intent_class": "<read|write|delete|execute|send|unknown>",
  "gap_detected": <true|false>,
  "gap_summary": "<one sentence or null>"
}

alignment_score meaning:
  1.0 = stated intent and action are perfectly consistent
  0.5 = ambiguous — intent could plausibly match
  0.0 = intent and action are directly contradictory (e.g. intent says "read data", action deletes records)

Be strict about contradictions. Social engineering typically looks like:
  stated_intent="generate weekly summary" + user_message="delete all old records" + action=database.delete
"""


def _ai_alignment(
    stated_intent: str,
    user_message: str,
    action_type: str,
    action_class: str,
) -> Optional[tuple[float, Optional[str]]]:
    """Call Claude for deeper semantic alignment analysis.

    Returns (score, gap_summary) or None on any failure.
    """
    try:
        from ..ai.client import call_advisory
        import json

        user_msg = json.dumps({
            "stated_intent": stated_intent[:200],
            "user_message": user_message[:200],
            "action_type": action_type,
            "action_class": action_class,
        })

        result = call_advisory(
            system_prompt=_AI_SYSTEM,
            user_message=user_msg,
            max_tokens=256,
            timeout=6.0,
            expect_json=True,
        )

        if not result or not isinstance(result, dict):
            return None

        score = float(result.get("alignment_score", 0.5))
        gap: Optional[str] = result.get("gap_summary") if result.get("gap_detected") else None
        return round(score, 4), gap

    except Exception as exc:
        logger.debug("[normalizer] AI alignment call failed (fail-open): %s", exc)
        return None


# ── Public API ─────────────────────────────────────────────────────────────────


def normalize_intent(
    *,
    stated_intent: str = "",
    user_message: str = "",
    action_type: str = "",
    action_payload: Optional[dict] = None,
    use_ai: Optional[bool] = None,
) -> NormalizedIntent:
    """Normalize and score the alignment between intent signals and action.

    Always returns a NormalizedIntent — never raises.

    Args:
        stated_intent:  req_context.get("stated_intent", "")
        user_message:   req_context.get("user_message", "") or req_context.get("prompt", "")
        action_type:    req.action_type (e.g. "email.send")
        action_payload: req.action_payload (unused in structural check, reserved for future)
        use_ai:         Force AI on/off. None = use _AI_NORMALIZATION_ENABLED setting.

    Returns:
        NormalizedIntent with alignment_score, misalignment_flag, and gap_description.
    """
    try:
        action_class, risk_signal = _classify_operation(action_type)

        # Structural pass (always runs, O(n), no AI)
        structural_score, stated_class, gap = _structural_alignment(
            stated_intent, user_message, action_class
        )

        ai_score: Optional[float] = None
        ai_gap: Optional[str] = None
        source = "structural"

        # AI pass (optional — only when structural score is ambiguous)
        should_ai = use_ai if use_ai is not None else _AI_NORMALIZATION_ENABLED
        if should_ai and structural_score < _AI_THRESHOLD and (stated_intent or user_message):
            ai_result = _ai_alignment(stated_intent, user_message, action_type, action_class)
            if ai_result is not None:
                ai_score, ai_gap = ai_result
                source = "ai_assisted"

        # Final score: blend structural + AI when both available
        if ai_score is not None:
            final_score = structural_score * 0.4 + ai_score * 0.6
            final_gap = ai_gap or gap
        else:
            final_score = structural_score
            final_gap = gap

        final_score = round(final_score, 4)
        flag = final_score < MISALIGNMENT_THRESHOLD

        if flag:
            logger.warning(
                "[normalizer] INTENT MISALIGNMENT: action=%s score=%.2f stated='%s' user='%s'",
                action_type, final_score,
                (stated_intent or "")[:60], (user_message or "")[:60],
            )

        return NormalizedIntent(
            alignment_score=final_score,
            misalignment_flag=flag,
            inferred_intent_class=stated_class,
            inferred_risk_signal=risk_signal,
            gap_description=final_gap,
            structural_score=structural_score,
            semantic_score=ai_score,
            stated_intent_class=stated_class,
            action_class=action_class,
            source=source,
        )

    except Exception as exc:
        logger.warning("[normalizer] normalization failed (fail-open): %s", exc)
        return NormalizedIntent(
            alignment_score=0.5,
            misalignment_flag=False,
            inferred_intent_class="unknown",
            inferred_risk_signal="medium",
            gap_description=None,
            structural_score=0.5,
            source="structural",
        )
