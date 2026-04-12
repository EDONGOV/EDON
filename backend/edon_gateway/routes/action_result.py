"""POST /v1/action/result — agent-reported execution outcomes.

After executing a tool action, agents call this endpoint to report what
actually happened. EDON correlates the outcome with:

  1. The original governance decision (via action_id)
  2. Shadow execution findings — did a shadow "critical bypass" finding
     correspond to an action that actually succeeded in the real world?

This closes the feedback loop for the governance proxy: EDON knows what
it decided AND whether the execution succeeded or failed.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException

from ..schemas.action_result import ActionResultRequest, ActionResultResponse
from ..tenancy import get_request_tenant_id
from ..logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["v1"])


@router.post("/action/result", response_model=ActionResultResponse)
async def record_action_result(request: Request, req: ActionResultRequest):
    """Record an execution outcome for a previously evaluated action.

    Called by agents after a tool runs. Links the governance decision
    (action_id) to the real-world outcome (success / failure / timeout).

    Returns the assigned result_id for the caller's records.
    """
    if not req.action_id.strip():
        raise HTTPException(status_code=400, detail="action_id is required")

    if not req.agent_id.strip():
        raise HTTPException(status_code=400, detail="agent_id is required")

    tenant_id = get_request_tenant_id(request)

    from ..shadow.trace_capture import ActionResult, get_trace_store

    result = ActionResult.build(
        action_id=req.action_id,
        agent_id=req.agent_id,
        tenant_id=tenant_id,
        action_type=req.action_type,
        outcome=req.outcome,
        latency_ms=req.latency_ms,
        error=req.error,
        result_summary=req.result_summary,
        executed_at=req.executed_at,
    )

    try:
        get_trace_store().save_action_result(result)
        recorded = True
        logger.info(
            "[action/result] agent=%s action=%s outcome=%s latency=%dms",
            req.agent_id, req.action_id, req.outcome, req.latency_ms,
        )
    except Exception as exc:
        logger.exception("[action/result] failed to save: %s", exc)
        recorded = False

    # Non-blocking: flag to shadow system if outcome contradicts a critical finding
    if recorded and req.outcome == "success":
        try:
            import asyncio
            asyncio.create_task(
                _check_critical_correlation(req.action_id, tenant_id)
            )
        except Exception:
            pass

    return ActionResultResponse(
        result_id=result.result_id,
        action_id=result.action_id,
        recorded=recorded,
        outcome=result.outcome,
    )


@router.get("/action/result/{action_id}")
async def get_action_result(action_id: str, request: Request):
    """Look up the recorded execution outcome for a specific action_id."""
    from ..shadow.trace_capture import get_trace_store
    row = get_trace_store().get_action_result(action_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"No result recorded for action_id '{action_id}'")
    return row


@router.get("/action/result-stats")
async def get_outcome_stats(request: Request):
    """Return outcome counts by type — useful for policy tuning.

    High failure rates on allowed actions may indicate the policy is too
    permissive. High success rates on shadow-critical findings mean those
    bypasses are real and worth fixing.
    """
    from ..shadow.trace_capture import get_trace_store
    tenant_id = get_request_tenant_id(request)
    stats = get_trace_store().outcome_stats(tenant_id=tenant_id)
    total = sum(stats.values())
    return {
        "outcomes": stats,
        "total": total,
        "failure_rate": round(stats["failure"] / total, 4) if total else 0.0,
        "success_rate": round(stats["success"] / total, 4) if total else 0.0,
    }


# ── Internal correlation task ──────────────────────────────────────────────────

async def _check_critical_correlation(action_id: str, tenant_id: str | None) -> None:
    """If a critical shadow finding exists for this action AND the real execution
    succeeded, persist a confirmed bypass record. A critical finding + real
    success = the bypass is real, not theoretical.
    """
    try:
        from ..shadow.trace_capture import get_trace_store
        store = get_trace_store()

        # Look up the action result we just saved
        result_row = store.get_action_result(action_id)
        if not result_row:
            return

        # Find critical shadow findings for this action's trace
        # The trace was captured before the audit write, so action_id is in the context
        findings = store.recent_findings(severity="critical", limit=1000)
        for f in findings:
            # Match on action_id embedded in trace context or agent_id+action_type
            if (
                f.get("action_type") == result_row.get("action_type")
                and f.get("agent_id") == result_row.get("agent_id")
            ):
                store.save_confirmed_bypass(
                    action_id=action_id,
                    trace_id=f["trace_id"],
                    agent_id=result_row["agent_id"],
                    tenant_id=tenant_id,
                    action_type=result_row["action_type"],
                    perturbation_name=f["perturbation_name"],
                    perturbation_type=f["perturbation_type"],
                    original_verdict=f.get("trace_original_verdict", "UNKNOWN"),
                    shadow_verdict=f["shadow_verdict"],
                    real_outcome=result_row["outcome"],
                )
                logger.warning(
                    "[shadow/bypass] CONFIRMED: action_id=%s agent=%s action=%s "
                    "perturbation=%s original=%s shadow=%s real_outcome=%s",
                    action_id,
                    result_row["agent_id"],
                    result_row["action_type"],
                    f["perturbation_name"],
                    f.get("trace_original_verdict"),
                    f["shadow_verdict"],
                    result_row["outcome"],
                )
    except Exception as exc:
        logger.debug("[shadow/correlation] error: %s", exc)
