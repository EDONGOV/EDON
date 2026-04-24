"""Intervention intelligence engine.

Moves EDON from guardrail to co-pilot. Instead of only BLOCK/DEGRADE with
predefined static alternatives, this generates context-aware strategies:

  REWRITE      — modify the action params or prompt to make it safe
  INJECT       — prepend reasoning steps the agent should run first
  REPLAN       — suggest an alternative tool sequence to achieve the goal
  ACCEPT_BLOCK — no viable alternative (truly dangerous, block stands)

Called when verdict is BLOCK or DEGRADE and a better outcome is possible.
The strategy is returned in the API response so the agent/orchestrator can
act on it — EDON does not execute on behalf of the agent.

Fail-open: returns None on any error. Original verdict stands.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .client import call_advisory

logger = logging.getLogger(__name__)

_STRATEGY_TYPES = {"REWRITE", "INJECT", "REPLAN", "ACCEPT_BLOCK"}

_SYSTEM_PROMPT = """\
You are an AI governance co-pilot. An agent tried to take an action that \
was blocked or flagged as risky. Your job is to generate a SAFER ALTERNATIVE \
STRATEGY that achieves the same goal without the risk.

You receive a JSON object with:
- "intent_objective": what the agent session is trying to accomplish
- "action_type": the blocked/risky tool.operation (e.g. "email.send")
- "action_params": key parameters (sanitized)
- "verdict": why it was flagged (BLOCK, DEGRADE, ESCALATE)
- "reason_code": governance reason code
- "risk_factors": list of what made it risky

Choose ONE strategy type and return a JSON response:

REWRITE — the action can proceed with modified parameters:
{"type":"REWRITE","params":{"<key>":"<safe_value>"},"rationale":"<one sentence>"}

INJECT — add reasoning steps before the agent acts:
{"type":"INJECT","steps":["<step1>","<step2>","<step3>"],"rationale":"<one sentence>"}

REPLAN — use a different tool sequence to achieve the goal:
{"type":"REPLAN","sequence":["<tool.op1>","<tool.op2>"],"rationale":"<one sentence>"}

ACCEPT_BLOCK — no safe alternative exists:
{"type":"ACCEPT_BLOCK","rationale":"<one sentence why this cannot be made safe>"}

Rules:
- If the action is destructive (delete, drop, truncate) with no recovery: ACCEPT_BLOCK
- If the action can be scoped down safely: REWRITE
- If the agent needs to think before acting: INJECT
- If a different tool sequence achieves the goal: REPLAN
- Keep steps and sequences short (max 4 items)
- Never suggest actions that bypass security controls
"""


@dataclass
class InterventionStrategy:
    type: str                          # REWRITE | INJECT | REPLAN | ACCEPT_BLOCK
    rationale: str = ""
    rewrite_params: Dict[str, Any] = field(default_factory=dict)   # for REWRITE
    inject_steps: List[str] = field(default_factory=list)           # for INJECT
    replan_sequence: List[str] = field(default_factory=list)        # for REPLAN

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"type": self.type, "rationale": self.rationale}
        if self.type == "REWRITE" and self.rewrite_params:
            out["rewrite_params"] = self.rewrite_params
        if self.type == "INJECT" and self.inject_steps:
            out["steps"] = self.inject_steps
        if self.type == "REPLAN" and self.replan_sequence:
            out["sequence"] = self.replan_sequence
        return out

    @property
    def actionable(self) -> bool:
        return self.type != "ACCEPT_BLOCK"


def generate_intervention(
    *,
    intent_objective: str,
    action_type: str,
    action_params: Optional[dict] = None,
    verdict: str,
    reason_code: Optional[str] = None,
    risk_factors: Optional[List[str]] = None,
) -> Optional[InterventionStrategy]:
    """Generate a safer alternative strategy for a blocked/risky action.

    Returns None if AI unavailable — caller falls back to original verdict.
    Never raises.

    Args:
        intent_objective: Agent session goal.
        action_type:      "tool.op" string of the blocked action.
        action_params:    Sanitised action parameters.
        verdict:          BLOCK | DEGRADE | ESCALATE
        reason_code:      Governor reason code string.
        risk_factors:     Human-readable list of what made it risky.
    """
    safe_params: dict = {}
    if action_params:
        for k, v in list(action_params.items())[:8]:
            if isinstance(v, (str, int, float, bool)) and not _looks_sensitive(str(k)):
                safe_params[str(k)[:64]] = str(v)[:128]

    payload = json.dumps({
        "intent_objective": str(intent_objective)[:300],
        "action_type": str(action_type)[:64],
        "action_params": safe_params,
        "verdict": verdict,
        "reason_code": str(reason_code or "")[:64],
        "risk_factors": [str(r)[:100] for r in (risk_factors or [])[:5]],
    }, separators=(",", ":"))

    result = call_advisory(_SYSTEM_PROMPT, payload, max_tokens=512)
    if result is None:
        return None

    try:
        strategy_type = str(result.get("type", "ACCEPT_BLOCK")).upper()
        if strategy_type not in _STRATEGY_TYPES:
            strategy_type = "ACCEPT_BLOCK"

        strategy = InterventionStrategy(
            type=strategy_type,
            rationale=str(result.get("rationale", ""))[:300],
        )

        if strategy_type == "REWRITE":
            raw_params = result.get("params") or {}
            if isinstance(raw_params, dict):
                strategy.rewrite_params = {
                    str(k)[:64]: str(v)[:256]
                    for k, v in list(raw_params.items())[:10]
                }

        elif strategy_type == "INJECT":
            raw_steps = result.get("steps") or []
            if isinstance(raw_steps, list):
                strategy.inject_steps = [str(s)[:200] for s in raw_steps[:4]]

        elif strategy_type == "REPLAN":
            raw_seq = result.get("sequence") or []
            if isinstance(raw_seq, list):
                strategy.replan_sequence = [str(s)[:64] for s in raw_seq[:4]]

        logger.info(
            "[intervention] action=%s verdict=%s → strategy=%s actionable=%s",
            action_type, verdict, strategy_type, strategy.actionable,
        )
        return strategy

    except Exception as exc:
        logger.debug("[intervention] parse failed: %s", exc)
        return None


def _looks_sensitive(key: str) -> bool:
    _SENSITIVE = {"password", "token", "secret", "key", "auth", "credential", "ssn", "dob"}
    return any(s in key.lower() for s in _SENSITIVE)
