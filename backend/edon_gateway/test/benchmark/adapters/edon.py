"""EDON adapter for the vendor-neutral GovernanceProtocol.

Translates GovernanceInput → EDON types, calls EDONGovernor.evaluate(),
and translates the result back to GovernanceOutput.
"""

from __future__ import annotations

from edon_gateway.governor import EDONGovernor
from edon_gateway.policy.engine import PolicyConfig
from edon_gateway.schemas import (
    Action, IntentContract, RiskLevel, Tool,
)

from ..protocol import GovernanceInput, GovernanceOutput, GovernanceProtocol

_RISK_MAP = {
    "low": RiskLevel.LOW,
    "medium": RiskLevel.MEDIUM,
    "high": RiskLevel.HIGH,
    "critical": RiskLevel.CRITICAL,
}


def _to_tool(tool_str: str) -> Tool:
    """Map a string tool name to a Tool enum value, falling back to CUSTOM."""
    try:
        return Tool(tool_str.lower())
    except ValueError:
        return Tool.CUSTOM


class EDONAdapter(GovernanceProtocol):
    """Wraps EDONGovernor behind the vendor-neutral GovernanceProtocol."""

    def __init__(self, policy_config: PolicyConfig | None = None):
        self._governor = EDONGovernor(policy_config=policy_config)

    def evaluate(self, inp: GovernanceInput) -> GovernanceOutput:
        action = Action(
            tool=_to_tool(inp.action_tool),
            op=inp.action_op,
            params=inp.action_params,
            estimated_risk=_RISK_MAP.get(inp.action_risk.lower(), RiskLevel.LOW),
        )

        intent = IntentContract(
            objective=inp.intent_objective,
            scope=inp.intent_scope,
            constraints={},
            risk_level=RiskLevel.LOW,
            approved_by_user=inp.intent_approved,
        )
        intent.revoked = inp.intent_revoked
        intent.expires_at = inp.intent_expires_at

        context = dict(inp.context)
        context.setdefault("agent_id", inp.agent_id)
        context.setdefault("session_id", inp.session_id)

        decision = self._governor.evaluate(
            action=action,
            intent=intent,
            context=context,
            tenant_id=inp.tenant_id,
        )

        return GovernanceOutput(
            verdict=decision.verdict.value.upper(),
            reason=decision.explanation or str(decision.reason_code),
            latency_ms=0.0,  # filled in by scorer
        )
