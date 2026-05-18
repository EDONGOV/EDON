"""EDON Self-Healing Runner.

Orchestrates the full healing pass:

  1. Read rule_ready rules from the last hardening run that have
     regression_recommendation="apply"
  2. Deploy each qualifying rule via deployer.deploy_rule()
  3. Run verify_healing_pass() to re-check confirmed failure states
  4. Fire a healing alert if any states were mitigated
  5. Return a structured summary

Gated by EDON_HEALING_AUTO_ENABLED (default: true).
Can be called:
  - From hardening/runner.py (Agent 4, automatic)
  - From POST /v1/healing/run (manual trigger)

Fail-open: errors are logged and returned, never raised.
"""

from __future__ import annotations

import os
from datetime import datetime, UTC
from typing import Optional

from ..logging_config import get_logger

logger = get_logger(__name__)

_AUTO_ENABLED = os.getenv("EDON_HEALING_AUTO_ENABLED", "true").lower() == "true"


async def run_healing_pass(
    *,
    hardening_result: dict,
    governor,
    tenant_id: Optional[str] = None,
    db=None,
    impact_store=None,
    force: bool = False,
) -> dict:
    """Deploy qualifying rules and verify healing.

    Args:
        hardening_result:  The dict returned by hardening/runner.run() — must
                           contain "policy" and "regression" sub-results.
        governor:          EDONGovernor used for re-validation.
        tenant_id:         Scope to this tenant.
        db:                Database instance. If None, loaded from app state.
        impact_store:      ImpactStore. If None, loaded via get_impact_store().
        force:             Ignore _AUTO_ENABLED gate and run anyway.

    Returns:
        Healing summary dict.
    """
    from .deployer import deploy_rule, verify_healing_pass_async
    from ..impact.store import get_impact_store

    summary: dict = {
        "agent": "healing",
        "tenant_id": tenant_id,
        "started_at": datetime.now(UTC).isoformat(),
        "auto_enabled": _AUTO_ENABLED,
        "rules_deployed": 0,
        "deployed_rule_ids": [],
        "states_verified": 0,
        "states_mitigated": 0,
        "mitigated_ids": [],
        "skipped": False,
        "errors": [],
    }

    if not _AUTO_ENABLED and not force:
        summary["skipped"] = True
        summary["reason"] = (
            "EDON_HEALING_AUTO_ENABLED=false — set to true to enable autonomous deployment, "
            "or call POST /v1/healing/run?force=true"
        )
        return summary

    # Resolve dependencies
    _store = impact_store or get_impact_store()
    if db is None:
        try:
            from ..persistence.database import Database
            import os as _os
            _db_path = _os.getenv("EDON_DATABASE_PATH", "edon_gateway.db")
            db = Database(_db_path)
        except Exception as exc:
            summary["errors"].append(f"db_init: {exc}")
            summary["skipped"] = True
            summary["reason"] = "could not initialize DB"
            return summary

    # Collect qualifying rules from regression output
    policy_result = hardening_result.get("policy") or {}
    regression_result = hardening_result.get("regression") or {}

    rules = policy_result.get("rules") or []
    regression_reports = {
        r.get("rule", {}).get("proposal_id"): r
        for r in (regression_result.get("reports") or [])
    }

    # Deploy rules where regression says "apply"
    for rule in rules:
        proposal_id = rule.get("proposal_id")
        reg = regression_reports.get(proposal_id, {})
        recommendation = reg.get("recommendation", "inconclusive")

        if recommendation != "apply":
            logger.debug(
                "[healing/runner] skipping rule proposal=%s recommendation=%s",
                (proposal_id or "")[:8], recommendation,
            )
            continue

        try:
            rule_id = deploy_rule(rule, tenant_id or "tenant_edon_internal", db)
            if rule_id:
                summary["rules_deployed"] += 1
                summary["deployed_rule_ids"].append(rule_id)
        except Exception as exc:
            logger.warning("[healing/runner] deploy failed for proposal=%s: %s", proposal_id, exc)
            summary["errors"].append(f"deploy:{proposal_id}: {exc}")

    # Verify healing — re-run Engine C with new rules active
    if summary["deployed_rule_ids"]:
        try:
            verify_result = await verify_healing_pass_async(
                deployed_rule_ids=summary["deployed_rule_ids"],
                tenant_id=tenant_id,
                db=db,
                governor=governor,
                impact_store=_store,
            )
            summary["states_verified"] = verify_result.get("verified", 0)
            summary["states_mitigated"] = verify_result.get("mitigated", 0)
            summary["mitigated_ids"] = verify_result.get("mitigated_ids", [])
        except Exception as exc:
            logger.warning("[healing/runner] verify pass failed: %s", exc)
            summary["errors"].append(f"verify: {exc}")

        # Fire healing alert
        if summary["states_mitigated"] > 0:
            try:
                from ..alerts.dispatcher import _dispatch
                _dispatch("healing.mitigated", {
                    "rules_deployed": summary["rules_deployed"],
                    "states_mitigated": summary["states_mitigated"],
                    "tenant_id": tenant_id or "global",
                })
            except Exception as _alert_err:
                logger.debug("[healing/runner] alert failed (non-blocking): %s", _alert_err)

    summary["completed_at"] = datetime.now(UTC).isoformat()
    logger.info(
        "[healing/runner] complete: tenant=%s deployed=%d mitigated=%d errors=%d",
        tenant_id, summary["rules_deployed"], summary["states_mitigated"], len(summary["errors"]),
    )
    return summary
