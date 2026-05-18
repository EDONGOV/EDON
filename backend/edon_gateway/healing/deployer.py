"""EDON Self-Healing Deployer.

Takes rule_ready rules that passed regression validation and:
  1. Deploys them to the live policy_rules table (enabled=True)
  2. Marks the source proposal as "deployed" in the fix pipeline
  3. Re-runs Impact Engine C validation with the new rules active
  4. Marks failure states as "mitigated" when the new rule blocks the exploit

This is the last mile of the self-healing loop:

  shadow trace → fix proposal → rule_ready → regression OK → [THIS] deploy + verify → mitigated

All steps are fail-open. Errors are logged and returned, never re-raised.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, UTC
from typing import Optional

from ..logging_config import get_logger

logger = get_logger(__name__)

_PRIORITY_MAP = {"critical": 90, "high": 70, "medium": 50, "low": 30, "advisory": 20}


def deploy_rule(
    rule: dict,
    tenant_id: str,
    db,
    canary: bool = True,
    canary_fraction: float = 0.10,
    baseline_block_rate: float = 0.05,
) -> Optional[str]:
    """Insert a rule_ready rule into the live policy_rules table.

    Returns the new rule_id, or None on failure.
    Sets enabled=True so it takes effect on the next action evaluation.
    """
    try:
        rule_id = db.create_policy_rule(
            tenant_id=tenant_id,
            name=(rule.get("description") or rule.get("rationale") or "Auto-hardening rule")[:100],
            description=rule.get("description") or "",
            action=rule.get("action", "BLOCK"),
            condition_tool=rule.get("tool") or None,
            condition_op=rule.get("operation") or None,
            condition_risk_level=None,
            condition_tags=["auto_hardening", rule.get("perturbation_type", "unknown")],
            priority=_PRIORITY_MAP.get(rule.get("priority", "medium"), 50),
            enabled=True,
        )
        logger.info(
            "[healing/deployer] deployed rule: id=%s tool=%s op=%s action=%s tenant=%s canary=%s",
            rule_id, rule.get("tool"), rule.get("operation"), rule.get("action"), tenant_id, canary,
        )

        # Register with canary watchdog (default: 10% of traffic)
        if canary and rule_id:
            try:
                from .canary import register_canary
                register_canary(
                    rule_id=rule_id,
                    tenant_id=tenant_id,
                    fraction=canary_fraction,
                    baseline_block_rate=baseline_block_rate,
                )
            except Exception as _can_err:
                logger.debug("[healing/deployer] canary registration failed (non-blocking): %s", _can_err)

        try:
            from ..alerts import fire_healing_alert
            fire_healing_alert(
                tenant_id=tenant_id,
                rule_name=(rule.get("description") or rule.get("rationale") or "Auto-hardening rule")[:80],
                action=rule.get("action", "BLOCK"),
                tool=rule.get("tool"),
                op=rule.get("operation"),
            )
        except Exception:
            pass

        # Mark proposal as deployed in fix pipeline
        proposal_id = rule.get("proposal_id")
        if proposal_id:
            try:
                from ..shadow.fix_pipeline import _proposals, _persist, _lock
                with _lock:
                    if proposal_id in _proposals:
                        _proposals[proposal_id]["status"] = "deployed"
                        _proposals[proposal_id]["deployed_rule_id"] = rule_id
                        _proposals[proposal_id]["deployed_at"] = datetime.now(UTC).isoformat()
                        _persist()
            except Exception as _pipe_err:
                logger.debug("[healing/deployer] fix_pipeline update failed (non-blocking): %s", _pipe_err)

        return rule_id
    except Exception as exc:
        logger.warning("[healing/deployer] deploy_rule failed: %s", exc)
        return None


def _rule_now_blocks(failure_state_dict: dict, edges: list, governor, tenant_rules: list) -> bool:
    """Re-run the governor check with new tenant_rules active.

    Returns True if the new rules now block the previously-confirmed exploit.
    Mirrors the logic in impact/validator.py _check_policy_violation, but passes
    tenant_rules instead of an empty list.
    """
    if governor is None:
        return False

    from ..schemas import Action, Tool, IntentContract, RiskLevel, ActionSource

    path = failure_state_dict.get("path") or []
    tool_name: Optional[str] = None
    operation: Optional[str] = None
    agent_id: Optional[str] = None

    for element in path:
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
        return False

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
        tags=["healing_verification"],
    )
    intent = IntentContract(
        objective="Healing verification",
        scope={},
        constraints={},
        risk_level=RiskLevel.HIGH,
        approved_by_user=False,
    )
    context = {
        "agent_id": agent_id or "healing-verifier",
        "_shadow": True,
        "_shadow_mode": "healing_verification",
    }

    try:
        decision = governor.evaluate(
            action=action,
            intent=intent,
            context=context,
            tenant_rules=tenant_rules,
        )
        return decision.verdict.value != "ALLOW"
    except Exception as exc:
        logger.debug("[healing/deployer] governor re-check failed: %s", exc)
        return False


def verify_healing_pass(
    deployed_rule_ids: list[str],
    tenant_id: Optional[str],
    db,
    governor,
    impact_store,
) -> dict:
    """Re-validate confirmed failure states with newly deployed rules.

    For each confirmed (verified=True) failure state that hasn't been mitigated:
      - Re-run the governor check with the full live rule set
      - If the new rules now block the exploit, mark the state as mitigated

    Returns a summary dict.
    """
    if not deployed_rule_ids or governor is None:
        return {"verified": 0, "mitigated": 0, "skipped_no_governor": governor is None}

    summary = {"verified": 0, "mitigated": 0, "mitigated_ids": []}

    # Fetch the live rule set (includes newly deployed rules)
    try:
        tenant_rules = db.get_policy_rules(tenant_id or "tenant_edon_internal", enabled_only=True)
    except Exception as exc:
        logger.warning("[healing/deployer] could not load tenant_rules for verification: %s", exc)
        return {**summary, "error": str(exc)}

    # Only test confirmed, not-yet-mitigated failure states
    confirmed = impact_store.get_failure_states(
        tenant_id=tenant_id,
        verified_only=True,
        limit=200,
    )

    edges = impact_store.get_edges(tenant_id=tenant_id)

    for fs_dict in confirmed:
        if fs_dict.get("mitigated_at"):
            continue  # already healed

        summary["verified"] += 1
        try:
            now_blocked = _rule_now_blocks(fs_dict, edges, governor, tenant_rules)
            if now_blocked:
                impact_store.mark_mitigated(fs_dict["failure_state_id"])
                summary["mitigated"] += 1
                summary["mitigated_ids"].append(fs_dict["failure_state_id"])
                logger.info(
                    "[healing/deployer] mitigated failure_state=%s",
                    fs_dict["failure_state_id"][:16],
                )
        except Exception as exc:
            logger.warning(
                "[healing/deployer] verification failed for fs=%s: %s",
                fs_dict["failure_state_id"][:12], exc,
            )

    return summary


async def verify_healing_pass_async(
    deployed_rule_ids: list[str],
    tenant_id: Optional[str],
    db,
    governor,
    impact_store,
) -> dict:
    """Async wrapper for verify_healing_pass."""
    return await asyncio.to_thread(
        verify_healing_pass,
        deployed_rule_ids, tenant_id, db, governor, impact_store,
    )
