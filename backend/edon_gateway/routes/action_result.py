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
from ..observation import observe
from ..fleet_learning import get_fleet_learning_engine
from ..ai.goal_evaluator import evaluate_goal_achievement

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

    # ── Causal chain record ───────────────────────────────────────────────────
    # Record every executed action in the persistent causal chain so future
    # requests by this agent carry cross-session context.
    if recorded:
        try:
            from ..causal_chain import get_causal_chain
            get_causal_chain().record(
                tenant_id=tenant_id or "",
                agent_id=req.agent_id,
                action_id=req.action_id,
                action_type=req.action_type,
            )
        except Exception as _cc_err:
            logger.debug("[action/result] causal chain record failed: %s", _cc_err)

    # ── Independent Observation Layer ────────────────────────────────────────
    # Run the VerifierRegistry — agent-independent truth source.
    # VerificationResult replaces all agent-provided confidence values.
    # source_type="agent_claim" inputs never update trust.
    _verification = None
    if recorded:
        try:
            from ..verification import get_verifier_registry
            from ..trust import get_trust_engine as _get_te
            _reg = get_verifier_registry()
            _vt  = _get_te().get_verifier_trusts(tenant_id or "")
            _verification = _reg.verify(
                tenant_id=tenant_id or "",
                action_type=req.action_type,
                result_payload=req.result_payload,
                verifier_trusts=_vt,
            )
        except Exception as _vr_err:
            logger.warning("[action/result] verification failed (non-blocking): %s", _vr_err)

    # ── Fleet learning: correlate execution outcome ───────────────────────────
    if recorded:
        try:
            parts = req.action_type.split(".", 1)
            _tool, _op = parts[0].lower(), (parts[1].lower() if len(parts) > 1 else "")
            # Prefer verification result; fall back to legacy observe() for fleet labels
            _verified: bool
            if _verification is not None:
                _verified = _verification.verified
            else:
                obs = observe(
                    tool=_tool, op=_op,
                    execution_result=req.result_payload or {"outcome": req.outcome},
                    params={}, tenant_id=tenant_id,
                )
                _verified = obs.get("verified", True) if obs else True
            learning_label = "oob" if (req.outcome in ("failure", "partial", "timeout") or not _verified) else "safe"
            get_fleet_learning_engine().record_feedback(
                tenant_id=tenant_id,
                agent_id=req.agent_id,
                action_tool=_tool,
                action_op=_op,
                label=learning_label,
                source="execution_outcome",
                notes=f"outcome={req.outcome} verified={_verified}",
            )
        except Exception as _obs_err:
            logger.warning("[action/result] observation/learning failed (non-blocking): %s", _obs_err)

    # ── Trust update via VerificationResult ──────────────────────────────────
    # Uses record_outcome_from_verification() which enforces epistemic boundary:
    # agent_claim inputs never contribute to verification_confidence.
    if recorded:
        try:
            from ..trust import get_trust_engine
            te = get_trust_engine()
            if _verification is not None:
                te.record_outcome_from_verification(
                    tenant_id=tenant_id or "",
                    agent_id=req.agent_id,
                    action_type=req.action_type,
                    outcome=req.outcome,
                    verification=_verification,
                    action_id=req.action_id,
                    schedule_delayed=(_verification.deferred),
                )
            else:
                # No verifier registered — use legacy path with low default confidence
                te.record_outcome(
                    tenant_id=tenant_id or "",
                    agent_id=req.agent_id,
                    action_type=req.action_type,
                    outcome=req.outcome,
                    verification_confidence=0.20,
                )
        except Exception as _trust_err:
            logger.warning("[action/result] trust update failed (non-blocking): %s", _trust_err)

    # Goal achievement scoring — did this action advance the agent's objective?
    # Requires goal_context in the request; silent no-op if absent.
    if recorded and req.goal_context:
        try:
            parts = req.action_type.split(".", 1)
            _g_tool = parts[0].lower()
            _g_op = parts[1].lower() if len(parts) > 1 else ""
            goal_score = evaluate_goal_achievement(
                intent_objective=req.goal_context,
                action_type=req.action_type,
                action_params=req.result_payload,
                execution_outcome=req.outcome,
                result_summary=req.result_summary,
            )
            if goal_score is not None:
                get_fleet_learning_engine().record_goal_score(
                    tenant_id=tenant_id,
                    agent_id=req.agent_id,
                    action_tool=_g_tool,
                    action_op=_g_op,
                    score=goal_score,
                    execution_outcome=req.outcome,
                )
        except Exception as _goal_err:
            logger.warning("[action/result] goal scoring failed (non-blocking): %s", _goal_err)

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
