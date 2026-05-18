"""EDON Self-Healing Routes.

GET  /v1/healing/status          — last healing pass result + config
POST /v1/healing/run             — trigger a healing pass manually
POST /v1/healing/deploy/{rule_key} — manually deploy a single rule_ready rule
"""

from __future__ import annotations

import os
from fastapi import APIRouter, Query, Request, HTTPException

from ..tenancy import get_request_tenant_id
from ..logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v1/healing", tags=["healing"])

_last_healing: dict[str, dict] = {}


@router.get("/status")
async def get_healing_status(request: Request):
    """Return last healing pass result and configuration."""
    tenant_id = get_request_tenant_id(request)
    last = _last_healing.get(tenant_id or "__global__")

    return {
        "last_run": last,
        "auto_enabled": os.getenv("EDON_HEALING_AUTO_ENABLED", "true").lower() == "true",
        "config": {
            "auto_deploy_on_apply":  os.getenv("EDON_HEALING_AUTO_ENABLED", "true") == "true",
            "verify_after_deploy":   True,
            "mark_mitigated":        True,
        },
    }


@router.post("/run")
async def run_healing(
    request: Request,
    force: bool = Query(False, description="Bypass EDON_HEALING_AUTO_ENABLED gate"),
):
    """Manually trigger a healing pass.

    Reads rule_ready rules from the last hardening run, deploys those
    with recommendation='apply', re-validates affected failure states,
    and marks healed states as mitigated.

    Set force=true to run even when EDON_HEALING_AUTO_ENABLED=false.
    """
    from ..creao.engine import get_creao_engine
    from ..routes.hardening import get_last_hardening_result

    tenant_id = get_request_tenant_id(request)
    governor = getattr(request.app.state, "governor", None)

    hardening_result = get_last_hardening_result(tenant_id)
    if not hardening_result:
        try:
            from ..persistence import get_db
            hardening_result = get_db().get_hardening_result(tenant_id or "__global__") or {}
        except Exception:
            pass
    if not hardening_result:
        raise HTTPException(
            status_code=400,
            detail=(
                "No hardening result found for this tenant. "
                "Run POST /v1/hardening/run first to generate rule_ready rules."
            ),
        )

    engine = get_creao_engine()
    cycle = await engine.run_cycle(
        hardening_result=hardening_result,
        governor=governor,
        tenant_id=tenant_id,
        force=force,
    )

    result = {
        "creao_mode":       cycle.mode,
        "rules_deployed":   cycle.rules_deployed,
        "states_mitigated": cycle.states_mitigated,
        "proposals_queued": cycle.proposals_queued,
        "skipped_suggest":  cycle.skipped_suggest,
        "blocked_by_policy": cycle.blocked_by_policy,
        "errors":           cycle.errors,
        "tenant_id":        tenant_id,
    }
    _last_healing[tenant_id or "__global__"] = result
    return result


@router.post("/deploy/{proposal_id}")
async def deploy_single_rule(
    proposal_id: str,
    request: Request,
):
    """Manually deploy a single rule_ready rule by proposal_id.

    Use this to deploy a specific rule without running a full healing pass.
    The rule must already be in rule_ready status from a previous hardening run.

    After deployment, re-validation of affected failure states runs automatically.
    """
    from ..routes.hardening import get_last_hardening_result
    from ..healing.deployer import deploy_rule, verify_healing_pass_async
    from ..impact.store import get_impact_store
    from ..persistence.database import Database

    tenant_id = get_request_tenant_id(request)
    governor = getattr(request.app.state, "governor", None)

    hardening_result = get_last_hardening_result(tenant_id)
    if not hardening_result:
        try:
            from ..persistence import get_db as _get_db
            hardening_result = _get_db().get_hardening_result(tenant_id or "__global__") or {}
        except Exception:
            pass
    policy_result = (hardening_result.get("policy") or {})
    rules = policy_result.get("rules") or []
    rule = next((r for r in rules if r.get("proposal_id") == proposal_id), None)

    if rule is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No rule_ready rule found for proposal_id='{proposal_id}'. "
                "Run POST /v1/hardening/run to generate rules first."
            ),
        )

    # Deploy
    try:
        import os as _os
        db = Database(_os.getenv("EDON_DATABASE_PATH", "edon_gateway.db"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DB init failed: {exc}")

    rule_id = deploy_rule(rule, tenant_id or "tenant_edon_internal", db)
    if not rule_id:
        raise HTTPException(status_code=500, detail="Rule deployment failed — check logs")

    # Verify
    verify_result = await verify_healing_pass_async(
        deployed_rule_ids=[rule_id],
        tenant_id=tenant_id,
        db=db,
        governor=governor,
        impact_store=get_impact_store(),
    )

    return {
        "deployed": True,
        "rule_id": rule_id,
        "proposal_id": proposal_id,
        "rule": rule,
        "verification": verify_result,
    }
