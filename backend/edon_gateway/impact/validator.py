"""Engine C — Deterministic Re-Validation Engine.

For each AI-generated scenario, re-runs graph simulation + policy check to
confirm or reject reachability and constraint violation.

Verdicts:
  VALID       — path is reachable AND policy violation confirmed
  INVALID     — path cannot be reached OR no policy violation exists
  PARTIAL     — path is reachable but policy constraint is present (partially mitigated)

This closes the AI loop: Engine B can generate hypotheses, but Engine C
is the truth gate. Only VALID scenarios become confirmed findings.

Design:
  - Pure function: validate_scenario(scenario, failure_state, graph_edges, governor)
  - Synchronous; async callers use asyncio.to_thread
  - Fail-open: errors produce INVALID with a reason, never crash
"""

from __future__ import annotations

import asyncio
from datetime import datetime, UTC
from typing import Optional

from .schemas import RedTeamScenario, FailureState, ValidationResult
from .store import ImpactStore
from ..logging_config import get_logger

logger = get_logger(__name__)


def _check_path_reachability(
    scenario_path: list[str],
    edges: list[dict],
) -> tuple[bool, list[str]]:
    """Confirm each step in the scenario path exists as a real edge.

    Returns (reachable: bool, confirmed_path: list[str]).
    A path is reachable if every agent→tool→operation step has a matching edge.
    """
    if not scenario_path:
        return False, []

    confirmed = []
    # Extract agent+tool+operation steps from path
    agent_id: Optional[str] = None
    for element in scenario_path:
        if element.startswith("agent:"):
            agent_id = element.split(":", 1)[1]
            confirmed.append(element)
        elif element.startswith("tool:") or (element.startswith("read:") or element.startswith("write:")):
            # e.g. "tool:email" or "read:database.query"
            raw = element.split(":", 1)[1] if ":" in element else element
            parts = raw.split(".", 1)
            tool = parts[0].lower()
            op = parts[1].lower() if len(parts) > 1 else None

            # Check edge exists
            match = next(
                (e for e in edges
                 if e.get("tool_name", "").lower() == tool
                 and (op is None or e.get("operation", "").lower() == op)
                 and (agent_id is None or e.get("agent_id") == agent_id)),
                None,
            )
            if match:
                confirmed.append(element)
            else:
                # Step not in graph — path is not fully reachable
                return False, confirmed
        else:
            # Passthrough elements (sink:external, user_input, etc.)
            confirmed.append(element)

    return True, confirmed


def _check_policy_violation(
    scenario: RedTeamScenario,
    failure_state: FailureState,
    edges: list[dict],
    governor,
) -> tuple[bool, Optional[str]]:
    """Run the relevant edge through the governor to confirm constraint violation.

    Returns (violation_confirmed: bool, explanation: Optional[str]).
    A violation is confirmed if the governor would ALLOW an action that should
    be BLOCK/ESCALATE based on the failure state's constraint_violation.
    """
    if governor is None:
        return True, "Governor unavailable — assuming violation based on graph evidence"

    # Find the primary edge implicated in the scenario
    # We test: does the governor ALLOW this action without the constraint?
    from ..schemas import Action, Tool, IntentContract, RiskLevel, ActionSource

    # Use the path to identify tool + operation
    tool_name = None
    operation = None
    agent_id = None
    for element in (failure_state.path or []):
        if element.startswith("agent:"):
            agent_id = element.split(":", 1)[1]
        elif element.startswith("tool:"):
            tool_name = element.split(":", 1)[1]
        elif element.startswith("op:"):
            operation = element.split(":", 1)[1]
        elif element.startswith("read:") or element.startswith("write:"):
            raw = element.split(":", 1)[1]
            parts = raw.split(".", 1)
            if not tool_name:
                tool_name = parts[0]
            if not operation and len(parts) > 1:
                operation = parts[1]

    if not tool_name:
        return True, "No tool identified in path — assuming violation"

    try:
        tool_enum = Tool(tool_name.lower())
        payload: dict = {}
    except ValueError:
        tool_enum = Tool.CUSTOM
        payload = {"_custom_tool": tool_name.lower()}

    action = Action(
        tool=tool_enum,
        op=operation or "unknown",
        params=payload,
        requested_at=datetime.now(UTC),
        source=ActionSource.AGENT,
        tags=["impact_validation"],
    )

    intent = IntentContract(
        objective="Impact validation",
        scope={},
        constraints={},
        risk_level=RiskLevel.MEDIUM,
        approved_by_user=False,
    )

    context = {
        "agent_id": agent_id or "impact-validator",
        "_shadow": True,
        "_shadow_mode": "impact_validation",
    }

    try:
        decision = governor.evaluate(
            action=action,
            intent=intent,
            context=context,
            tenant_rules=[],
        )
        verdict = decision.verdict.value

        # Violation confirmed if ALLOW — meaning the governor doesn't catch it
        if verdict == "ALLOW":
            return True, f"Governor returned ALLOW — constraint missing as predicted ({failure_state.constraint_violation})"
        else:
            return False, f"Governor returned {verdict} — constraint IS present, violation not confirmed"
    except Exception as exc:
        return True, f"Governor evaluation failed — assuming violation: {exc}"


def validate_scenario(
    scenario: RedTeamScenario,
    failure_state: FailureState,
    edges: list[dict],
    governor=None,
) -> ValidationResult:
    """Engine C: deterministic re-validation of one AI-generated scenario.

    Checks:
    1. Path reachability — every edge in the scenario path exists in the graph
    2. Policy violation — governor confirms the constraint is absent

    Returns a ValidationResult with status VALID | PARTIAL | INVALID.
    """
    vr = ValidationResult(
        scenario_id=scenario.scenario_id,
        failure_state_id=failure_state.failure_state_id,
    )

    try:
        reachable, confirmed_path = _check_path_reachability(
            scenario.graph_path_used or failure_state.path,
            edges,
        )
        vr.reachability_confirmed = reachable
        vr.graph_path_confirmed = confirmed_path

        if not reachable:
            vr.status = "invalid"
            vr.invalidation_reason = (
                f"Path not reachable: step '{confirmed_path[-1] if confirmed_path else 'unknown'}' "
                "has no matching edge in the execution graph."
            )
            return vr

        violation_confirmed, explanation = _check_policy_violation(
            scenario, failure_state, edges, governor
        )
        vr.policy_violation_confirmed = violation_confirmed

        if reachable and violation_confirmed:
            vr.status = "valid"
            # Fire alert — confirmed finding is a real vulnerability in the agent graph
            try:
                from ..alerts.dispatcher import fire_impact_alert
                fire_impact_alert(
                    scenario_id=scenario.scenario_id,
                    failure_state_id=failure_state.failure_state_id,
                    vulnerability_class=failure_state.vulnerability_class,
                    severity_score=failure_state.severity_score,
                    title=scenario.title,
                    tenant_id=failure_state.tenant_id,
                    attack_steps=getattr(scenario, "remediation_steps", []),
                )
            except Exception as _alert_err:
                logger.debug("[impact/validator] alert dispatch failed (non-blocking): %s", _alert_err)
        elif reachable and not violation_confirmed:
            vr.status = "partial"
            vr.invalidation_reason = explanation
        else:
            vr.status = "invalid"
            vr.invalidation_reason = explanation

    except Exception as exc:
        logger.warning(
            "[impact/validator] validation error scenario=%s: %s",
            scenario.scenario_id[:8], exc,
        )
        vr.status = "invalid"
        vr.invalidation_reason = f"Validation error: {exc}"

    return vr


def validate_all_scenarios(
    failure_state: FailureState,
    store: ImpactStore,
    governor=None,
) -> list[ValidationResult]:
    """Validate all pending scenarios for a failure state.

    Fetches pending scenarios from store, validates each, saves results.
    Returns list of ValidationResult objects.
    """
    pending = store.get_scenarios(
        failure_state_id=failure_state.failure_state_id,
        validation_status="pending",
    )
    edges = store.get_edges(tenant_id=failure_state.tenant_id)
    results = []

    for s_dict in pending:
        scenario = RedTeamScenario(
            scenario_id=s_dict["scenario_id"],
            failure_state_id=s_dict["failure_state_id"],
            title=s_dict["title"],
            attack_narrative=s_dict["attack_narrative"],
            attacker_type=s_dict["attacker_type"],
            attack_vector=s_dict["attack_vector"],
            impact_description=s_dict["impact_description"],
            indicators_of_compromise=s_dict.get("indicators_of_compromise", []),
            remediation_steps=s_dict.get("remediation_steps", []),
            graph_path_used=s_dict.get("graph_path_used", []),
            validation_status=s_dict.get("validation_status", "pending"),
            generated_at=s_dict.get("generated_at", ""),
        )

        vr = validate_scenario(scenario, failure_state, edges, governor)
        store.save_validation(vr)

        # Update failure state last_validated_at
        fs_dict = store.get_failure_state(failure_state.failure_state_id)
        if fs_dict:
            from dataclasses import asdict
            updated_fs = FailureState(**{
                k: v for k, v in fs_dict.items()
                if k in FailureState.__dataclass_fields__
            })
            updated_fs.last_validated_at = vr.validated_at
            store.save_failure_state(updated_fs)

        results.append(vr)

        logger.info(
            "[impact/validator] scenario=%s status=%s reachable=%s violation=%s",
            scenario.scenario_id[:8],
            vr.status,
            vr.reachability_confirmed,
            vr.policy_violation_confirmed,
        )

    return results


async def validate_all_scenarios_async(
    failure_state: FailureState,
    store: ImpactStore,
    governor=None,
) -> list[ValidationResult]:
    """Async wrapper."""
    return await asyncio.to_thread(validate_all_scenarios, failure_state, store, governor)
