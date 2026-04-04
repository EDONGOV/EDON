"""REST API routes for /v1/action endpoint.

This module implements the /v1/action endpoint which is the primary interface
for agent action evaluation and governance. It validates requests, evaluates
actions through the policy engine, logs to audit trail, and returns decisions.
"""

from fastapi import APIRouter, Request, HTTPException
from datetime import datetime, UTC
import time
import os

from ..schemas.v1_action import V1ActionRequest, V1ActionResponse
from ..schemas import (
    Action,
    Tool,
    IntentContract,
    RiskLevel,
    ActionSource,
    Decision,
    Verdict,
    ReasonCode,
)
from ..persistence import get_db
from ..logging_config import get_logger
from ..tenancy import get_request_tenant_id
from ..monitoring.metrics import metrics as metrics_collector
from ..fleet_learning import get_fleet_learning_engine

# Simple TTL cache for per-tenant policy rules.
# Rules are loaded from DB at most once per TTL window per tenant,
# preventing a round-trip to RDS on every single /v1/action call.
_policy_rules_cache: dict = {}  # {tenant_id: (rules_list, expires_at_float)}
_POLICY_RULES_TTL_SEC = float(os.getenv("EDON_POLICY_RULES_TTL", "30"))
_PREDICTIVE_OOB_ESCALATE_THRESHOLD = float(os.getenv("EDON_PREDICTIVE_OOB_ESCALATE_THRESHOLD", "0.82"))
_PREDICTIVE_OOB_ADVISORY_THRESHOLD = float(os.getenv("EDON_PREDICTIVE_OOB_ADVISORY_THRESHOLD", "0.60"))

logger = get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["v1"])


def _parse_action_type(action_type: str) -> tuple[str, str]:
    """Parse action_type string into (tool, operation).

    Args:
        action_type: Action type string in format "tool.operation" (e.g., "email.send")

    Returns:
        Tuple of (tool, operation)

    Raises:
        ValueError: If action_type format is invalid
    """
    parts = action_type.split(".", 1)
    if len(parts) != 2:
        raise ValueError(
            f"Invalid action_type format: '{action_type}'. "
            "Expected format: 'tool.operation' (e.g., 'email.send')"
        )
    return parts[0], parts[1]


def _map_verdict_to_decision(verdict: str) -> str:
    """Map internal verdict enum to v1/action decision type.

    Args:
        verdict: Internal verdict value (ALLOW, BLOCK, ESCALATE, DEGRADE, PAUSE, ERROR)

    Returns:
        Decision type for v1/action response (ALLOW, BLOCK, HUMAN_REQUIRED, DEGRADE, PAUSE)
    """
    # Map ESCALATE to HUMAN_REQUIRED for v1 API
    if verdict == "ESCALATE":
        return "HUMAN_REQUIRED"
    # ERROR maps to BLOCK
    elif verdict == "ERROR":
        return "BLOCK"
    # All others pass through
    return verdict


@router.post("/action", response_model=V1ActionResponse)
async def evaluate_action(request: Request, req: V1ActionRequest):
    """Evaluate an agent action through the governance engine.

    This is the primary endpoint for agent action evaluation. It:
    1. Validates the request
    2. Parses action_type into tool and operation
    3. Loads the relevant intent contract (from context or active policy)
    4. Evaluates the action through the policy engine
    5. Logs the decision to the audit trail
    6. Returns the governance decision with latency metrics

    Args:
        request: FastAPI request object (for tenant context)
        req: V1ActionRequest containing action details

    Returns:
        V1ActionResponse with governance decision and metadata

    Raises:
        HTTPException:
            - 400: Invalid request format or action_type
            - 500: Internal error during evaluation
    """
    start_time = time.time()

    # Validate agent_id
    if not req.agent_id or not req.agent_id.strip():
        raise HTTPException(
            status_code=400,
            detail="agent_id is required and cannot be empty"
        )

    # Validate action_type
    if not req.action_type or not req.action_type.strip():
        raise HTTPException(
            status_code=400,
            detail="action_type is required and cannot be empty"
        )

    # Parse action_type
    try:
        tool_str, operation = _parse_action_type(req.action_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Resolve tool — known tools get their enum, unknown tools become CUSTOM.
    # This lets tenants govern any tool name (e.g. "myrobot", "erp_system")
    # without needing a code change. The original name is preserved in the
    # action params so audit logs and custom policy rules can match on it.
    try:
        tool = Tool(tool_str.lower())
        custom_tool_name = None
    except ValueError:
        tool = Tool.CUSTOM  # type: ignore[attr-defined]
        custom_tool_name = tool_str.lower()

    # Parse timestamp
    try:
        requested_at = datetime.fromisoformat(req.timestamp.replace("Z", "+00:00"))
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timestamp format: {req.timestamp}. Expected ISO 8601 format. Error: {str(e)}"
        )

    # Get tenant context
    tenant_id = get_request_tenant_id(request)

    # Get database
    db = get_db()

    # Enforce max_agents per plan
    if tenant_id:
        try:
            from ..billing.plans import get_plan_limits
            tenant_obj = db.get_tenant(tenant_id)
            tenant_plan = (tenant_obj or {}).get("plan", "free")
            plan_limits = get_plan_limits(tenant_plan)
            if plan_limits.max_agents != -1:
                current_count = db.get_agent_count(tenant_id)
                if current_count >= plan_limits.max_agents:
                    is_new = db.register_agent(tenant_id, req.agent_id)
                    if is_new:
                        raise HTTPException(
                            status_code=403,
                            detail=f"Agent limit reached ({plan_limits.max_agents} agents on {tenant_plan} plan). Upgrade at edoncore.com to add more agents."
                        )
                else:
                    db.register_agent(tenant_id, req.agent_id)
            else:
                db.register_agent(tenant_id, req.agent_id)
        except HTTPException:
            raise
        except Exception as _agent_err:
            logger.warning(f"Agent limit check failed (non-blocking): {_agent_err}")

    # ── Device binding + mutex check ────────────────────────────────────────────
    # If the action targets a specific physical device, enforce:
    #   1. Agent must have a valid binding for that device.
    #   2. Device must not be locked by a different agent (mutex).
    #   3. If binding or device requires supervision → override verdict to ESCALATE.
    # This runs before policy evaluation so it can short-circuit the entire request.
    _device_id = req.device_id
    _device_requires_supervision = False
    if _device_id and tenant_id:
        try:
            _check = db.check_device_binding_valid(
                agent_id=req.agent_id,
                device_id=_device_id,
                tenant_id=tenant_id,
            )
            if not _check.get("allowed"):
                raise HTTPException(
                    status_code=403,
                    detail=f"Device access denied — {_check.get('reason')}",
                )
            # Check device mutex
            _device = db.get_device(device_id=_device_id, tenant_id=tenant_id)
            if _device is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Device '{_device_id}' not found in registry",
                )
            if (
                _device.get("status") == "in_use"
                and _device.get("current_agent_id")
                and _device["current_agent_id"] != req.agent_id
            ):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Device '{_device_id}' is currently controlled by "
                        f"agent '{_device['current_agent_id']}'. "
                        "Wait for it to be released or request a force-release via admin."
                    ),
                )
            if _device.get("status") in ("maintenance", "offline", "locked"):
                raise HTTPException(
                    status_code=409,
                    detail=f"Device '{_device_id}' is not available (status={_device['status']})",
                )
            # Flag if supervision is required (affects verdict below)
            _device_requires_supervision = (
                bool(_check.get("requires_supervision"))
                or bool(_device.get("requires_supervision"))
            )
        except HTTPException:
            raise
        except Exception as _dev_err:
            logger.warning("Device check error (non-blocking): %s", _dev_err)

    # Load intent contract
    intent_id = req.context.get("intent_id") if req.context else None
    intent_contract = None

    if intent_id:
        # Try to load specific intent
        try:
            intent_data = db.get_intent(intent_id, customer_id=tenant_id)
            if intent_data:
                intent_contract = IntentContract(
                    objective=intent_data["objective"],
                    scope=intent_data["scope"],
                    constraints=intent_data.get("constraints", {}),
                    risk_level=RiskLevel(intent_data.get("risk_level", "MEDIUM")),
                    approved_by_user=bool(intent_data.get("approved_by_user", False)),
                )
        except Exception as e:
            logger.warning(f"Failed to load intent {intent_id}: {e}")

    # Fallback to active policy preset if no intent specified
    if not intent_contract:
        try:
            active_preset = db.get_active_policy_preset()
            if active_preset and active_preset.get("preset_name"):
                from ..policy_packs import get_policy_pack
                preset_name = active_preset["preset_name"]
                pack = get_policy_pack(preset_name)
                intent_dict = pack.to_intent_dict()
                intent_contract = IntentContract(
                    objective=intent_dict["objective"],
                    scope=intent_dict["scope"],
                    constraints=intent_dict.get("constraints", {}),
                    risk_level=RiskLevel(intent_dict.get("risk_level", "LOW")),
                    approved_by_user=bool(intent_dict.get("approved_by_user", False)),
                )
                # Auto-resolve intent_id from the active preset so audit records
                # always have an intent_id even when none was passed in context.
                if not intent_id:
                    try:
                        all_intents = db.list_intents(customer_id=tenant_id)
                        matching = [i for i in all_intents if preset_name.lower() in i.get("intent_id", "").lower()]
                        if matching:
                            intent_id = matching[0]["intent_id"]
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Failed to load active policy preset: {e}")

    # Final fallback to default intent
    if not intent_contract:
        intent_contract = IntentContract(
            objective="Default intent",
            scope={},
            constraints={},
            risk_level=RiskLevel.MEDIUM,
            approved_by_user=False,
        )

    # Create Action object
    # For custom tools, inject the original tool name into params so policy
    # rules and audit logs can match/filter on it.
    action_params = dict(req.action_payload or {})
    if custom_tool_name:
        action_params["_custom_tool"] = custom_tool_name

    action = Action(
        tool=tool,
        op=operation,
        params=action_params,
        requested_at=requested_at,
        source=ActionSource.AGENT,
        tags=[],
    )

    req_context: dict = dict(req.context or {})

    # ── Auto session_id ──────────────────────────────────────────────────────
    # Group actions by agent + hour so session risk accumulates automatically
    # even when callers don't supply a session_id.
    if "session_id" not in req_context:
        hour_bucket = datetime.now(UTC).strftime("%Y%m%d%H")
        req_context["session_id"] = f"auto:{req.agent_id}:{hour_bucket}"

    # ── Per-agent resource quota check ──────────────────────────────────────
    try:
        from ..security.agent_quotas import check_agent_quota, record_agent_call
        import json as _json
        _payload_bytes = len(_json.dumps(req.action_payload or {}).encode("utf-8"))
        _quota_allowed, _quota_msg = check_agent_quota(
            db=db,
            tenant_id=tenant_id,
            agent_id=req.agent_id,
            payload_bytes=_payload_bytes,
        )
        if not _quota_allowed:
            raise HTTPException(status_code=429, detail=f"Agent quota exceeded: {_quota_msg}")
        record_agent_call(tenant_id, req.agent_id)
    except HTTPException:
        raise
    except Exception as _quota_err:
        logger.warning("Agent quota check failed (non-blocking): %s", _quota_err)

    # Pre-action out-of-bounds risk prediction (per-agent + fleet signals).
    prediction = None
    if tenant_id:
        try:
            estimated_risk = str(req_context.get("risk_estimate", "low"))
            prediction = get_fleet_learning_engine().predict_action(
                db=db,
                tenant_id=tenant_id,
                agent_id=req.agent_id,
                action_tool=action.tool.value,
                action_op=action.op,
                estimated_risk=estimated_risk,
            )
            req_context["predicted_oob_risk"] = round(prediction.score, 4)
            req_context["predicted_oob_reasons"] = prediction.reasons
        except Exception as pred_err:
            logger.warning("Predictive OOB scoring failed (non-blocking): %s", pred_err)

    # Load tenant-specific custom policy rules (cached per tenant, TTL=30s)
    tenant_rules = []
    if tenant_id:
        try:
            cached = _policy_rules_cache.get(tenant_id)
            if cached and cached[1] > time.time():
                tenant_rules = cached[0]
            else:
                tenant_rules = db.get_policy_rules(tenant_id, enabled_only=True)
                _policy_rules_cache[tenant_id] = (tenant_rules, time.time() + _POLICY_RULES_TTL_SEC)
                # Evict expired entries to prevent unbounded growth with many tenants
                now = time.time()
                expired = [k for k, v in _policy_rules_cache.items() if v[1] <= now]
                for k in expired:
                    del _policy_rules_cache[k]
        except Exception as e:
            logger.warning(f"Failed to load tenant policy rules for {tenant_id}: {e}")

    # Evaluate action through governor (use shared module-level instance for loop detection).
    # Fall back to a fresh instance in test environments where startup event hasn't fired.
    governor = getattr(request.app.state, "governor", None)
    if governor is None:
        from ..governor import EDONGovernor
        governor = EDONGovernor(db=db)

    predictive_override_allowed = bool(req_context.get("allow_predicted_risk_override", False))
    decision: Decision
    if (
        prediction
        and prediction.score >= _PREDICTIVE_OOB_ESCALATE_THRESHOLD
        and not predictive_override_allowed
    ):
        decision = Decision(
            verdict=Verdict.ESCALATE,
            reason_code=ReasonCode.NEED_CONFIRMATION,
            explanation=(
                "Predicted out-of-bounds risk is high. "
                f"Score={prediction.score:.2f}. Human confirmation required."
            ),
            escalation_question=(
                "This action is predicted to be high-risk based on agent and fleet behavior. "
                "Do you want to proceed once?"
            ),
            escalation_options=[
                {"id": "allow_once", "label": "Allow once"},
                {"id": "block", "label": "Block"},
            ],
            meta={
                "predictive_oob_risk": round(prediction.score, 4),
                "predictive_oob_reasons": prediction.reasons,
                "predictive_oob_breakdown": prediction.signal_breakdown,
            },
        )
    else:
        try:
            _policy_eval_start = time.time()
            decision = governor.evaluate(
                action=action,
                intent=intent_contract,
                context={
                    "agent_id": req.agent_id,
                    "tenant_id": tenant_id,
                    **req_context,
                },
                tenant_rules=tenant_rules,
            )
            _policy_eval_ms = (time.time() - _policy_eval_start) * 1000.0
            # Record policy evaluation time for Prometheus (Phase 6.4)
            try:
                from ..main import prometheus_policy_eval_time_ms
                from ..config import config as _cfg
                if _cfg.METRICS_ENABLED and prometheus_policy_eval_time_ms is not None:
                    prometheus_policy_eval_time_ms.labels(
                        verdict=decision.verdict.value
                    ).observe(_policy_eval_ms)
            except Exception:
                pass
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Policy engine error during /v1/action evaluation: {e}")
            raise HTTPException(
                status_code=500,
                detail="Internal error during action evaluation. Please try again or contact support."
            )

    if prediction and prediction.score >= _PREDICTIVE_OOB_ADVISORY_THRESHOLD:
        decision.meta["predictive_oob_risk"] = round(prediction.score, 4)
        decision.meta["predictive_oob_reasons"] = prediction.reasons
        decision.meta["predictive_oob_breakdown"] = prediction.signal_breakdown

    # Override verdict to ESCALATE when device supervision is required
    if _device_requires_supervision and decision.verdict.value == "ALLOW":
        decision = Decision(
            verdict=Verdict.ESCALATE,
            reason_code=decision.reason_code,
            explanation=(
                f"Device '{_device_id}' requires human supervisor present. "
                "Please confirm supervision before proceeding."
            ),
            policy_version=decision.policy_version,
            meta={**(decision.meta or {}), "device_supervision_required": True},
        )

    # Calculate latency
    latency_ms = int((time.time() - start_time) * 1000)

    # Record metrics
    verdict_str = decision.verdict.value
    metrics_collector.increment_counter(
        "edon_decisions_total",
        {"verdict": verdict_str, "endpoint": "/v1/action"}
    )
    metrics_collector.observe_histogram(
        "edon_decision_latency_ms",
        latency_ms,
        {"endpoint": "/v1/action"}
    )

    # Persist to audit trail
    try:
        # Prefer intent_id from the request context if not already resolved
        effective_intent_id = intent_id or req.context.get("intent_id")
        audit_context: dict = {
            "agent_id": req.agent_id,
            "tenant_id": tenant_id,
            "request_timestamp": req.timestamp,
            **req_context,
        }
        # Include MAG signal in audit trail when present
        mag_verdict_for_audit = (decision.meta or {}).get("mag_verdict")
        if mag_verdict_for_audit is not None:
            audit_context["mag_verdict"] = mag_verdict_for_audit
        predictive_risk_for_audit = (decision.meta or {}).get("predictive_oob_risk")
        if predictive_risk_for_audit is not None:
            audit_context["predictive_oob_risk"] = predictive_risk_for_audit
            audit_context["predictive_oob_reasons"] = (decision.meta or {}).get("predictive_oob_reasons", [])
            audit_context["predictive_oob_breakdown"] = (decision.meta or {}).get("predictive_oob_breakdown", {})
        if decision.policy_snapshot_hash:
            audit_context["policy_snapshot_hash"] = decision.policy_snapshot_hash
        if decision.invariant_results:
            audit_context["invariant_results"] = decision.invariant_results
        # Include device_id and vendor_id in audit context when present
        if _device_id:
            audit_context["device_id"] = _device_id
        if tenant_id:
            try:
                _vendor_id = db.get_agent_vendor_id(req.agent_id, tenant_id)
                if _vendor_id:
                    audit_context["vendor_id"] = _vendor_id
            except Exception:
                pass
        # Extract anomaly score (0–100 scale) from decision meta for audit
        _anomaly_meta = (decision.meta or {}).get("anomaly", {})
        _anomaly_score_raw = _anomaly_meta.get("score")
        _anomaly_score_100 = round(_anomaly_score_raw * 100) if _anomaly_score_raw is not None else None
        # Persist to audit trail (async — returns immediately, write happens in background)
        from ..audit_queue import AuditTask, enqueue_audit
        _audit_task = AuditTask(
            action=action.to_dict(),
            decision=decision.to_dict(),
            intent_id=effective_intent_id,
            agent_id=req.agent_id,
            context=audit_context,
            customer_id=tenant_id,
            processing_latency_ms=latency_ms,
            anomaly_score=_anomaly_score_100,
            stated_intent=req.context.get("stated_intent"),
            user_message=req.context.get("user_message") or req.context.get("prompt"),
            action_summary=f"{action.tool.value}.{action.op}",
            policy_rule_id=decision.policy_rule_id or (decision.meta or {}).get("policy_rule_id"),
        )
        decision_id = await enqueue_audit(_audit_task, db) or f"async-{action.id}"
    except Exception as e:
        logger.exception(f"Failed to persist decision to audit trail: {e}")
        # Generate fallback decision_id
        decision_id = f"dec-{action.id}-{datetime.now(UTC).isoformat()}"

    # Acquire device lock on ALLOW (non-blocking; never raises)
    if _device_id and tenant_id and verdict_str == "ALLOW":
        try:
            _session_id = db.acquire_device_lock(
                device_id=_device_id,
                tenant_id=tenant_id,
                agent_id=req.agent_id,
                action_id=decision_id,
            )
            if _session_id is None:
                # Race: another agent grabbed it between our check and now — log but don't fail
                logger.warning(
                    "Device lock race condition: device=%s agent=%s tenant=%s",
                    _device_id, req.agent_id, tenant_id,
                )
            else:
                logger.debug(
                    "Device lock acquired: device=%s agent=%s session=%s",
                    _device_id, req.agent_id, _session_id,
                )
        except Exception as _lock_err:
            logger.warning("Device lock acquire failed (non-blocking): %s", _lock_err)

    # Update per-agent verdict counters (non-blocking; never raises)
    try:
        db.update_agent_stats(req.agent_id, verdict_str, tenant_id=tenant_id)
    except Exception as _stats_err:
        logger.warning("update_agent_stats failed (non-blocking): %s", _stats_err)

    # Continuous learning signal: auto-label outcome for this tool/op.
    # Human feedback can later override/correct this label via /learning/feedback.
    try:
        auto_label = "safe"
        if verdict_str in {"BLOCK", "ERROR"}:
            auto_label = "blocked"
        elif verdict_str in {"ESCALATE", "PAUSE"}:
            auto_label = "incident"
        get_fleet_learning_engine().record_feedback(
            tenant_id=tenant_id,
            agent_id=req.agent_id,
            action_tool=action.tool.value,
            action_op=action.op,
            label=auto_label,
            predicted_risk=(prediction.score if prediction else None),
            source="auto_decision",
            notes=f"decision={verdict_str}",
        )
    except Exception as _learning_err:
        logger.warning("auto learning feedback failed (non-blocking): %s", _learning_err)

    # Dispatch governance event webhooks (non-blocking)
    if tenant_id:
        try:
            from ..webhooks import dispatch_event
            _verdict = decision.verdict.value
            _event_type = (
                "action.blocked" if _verdict in ("BLOCK", "ERROR")
                else "action.escalated" if _verdict in ("ESCALATE", "PAUSE")
                else "action.allowed"
            )
            dispatch_event(
                event_type=_event_type,
                payload={
                    "action_id": decision_id,
                    "action_type": req.action_type,
                    "agent_id": req.agent_id,
                    "verdict": _verdict,
                    "reason": decision.explanation,
                },
                tenant_id=tenant_id,
                db=db,
            )
        except Exception as _wh_err:
            logger.warning("Webhook dispatch failed (non-blocking): %s", _wh_err)

    # Evaluate anomaly/threshold alert rules (non-blocking, fire-and-forget)
    if tenant_id:
        try:
            import asyncio as _asyncio
            from .alerts import evaluate_and_fire_alerts
            _asyncio.create_task(evaluate_and_fire_alerts(tenant_id))
        except Exception as _alert_err:
            logger.warning("Alert evaluation dispatch failed (non-blocking): %s", _alert_err)

    # Record decision for billing metering (fire-and-forget)
    try:
        import asyncio as _asyncio
        from ..billing.metering import record_decision_async
        _asyncio.create_task(record_decision_async(
            customer_id=tenant_id or "",
            verdict=decision.verdict.value,
            action_type=req.action_type,
        ))
    except Exception as _meter_err:
        logger.debug("Metering record dispatch failed (non-blocking): %s", _meter_err)

    # Build response
    response_decision = _map_verdict_to_decision(verdict_str)

    response = V1ActionResponse(  # type: ignore[call-arg]
        action_id=decision_id,
        decision=response_decision,
        decision_reason=decision.explanation,
        policy_version=decision.policy_version,
        processing_latency_ms=latency_ms,
        reason_code=decision.reason_code.value if decision.reason_code else None,
    )

    # Add optional fields if present
    if decision.safe_alternative:
        response.safe_alternative = {
            "action_type": f"{decision.safe_alternative.tool.value}.{decision.safe_alternative.op}",
            "action_payload": decision.safe_alternative.params,
        }

    if decision.escalation_question:
        response.escalation_question = decision.escalation_question

    if decision.escalation_options:
        response.escalation_options = decision.escalation_options

    predictive_meta = decision.meta or {}
    predictive_risk = predictive_meta.get("predictive_oob_risk")
    if predictive_risk is not None:
        response.predicted_oob_risk = float(predictive_risk)
        response.predicted_oob_reasons = predictive_meta.get("predictive_oob_reasons", [])
        response.predicted_oob_breakdown = predictive_meta.get("predictive_oob_breakdown", {})

    logger.info(
        f"[/v1/action] agent_id={req.agent_id} action={req.action_type} "
        f"decision={response_decision} latency={latency_ms}ms"
    )

    return response
