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
from ..security.phi_allowlist import check_params as phi_check_params
from ..security.audit_reason_formatter import format_reason as fmt_audit_reason

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

    # ── Cross-session causal risk ────────────────────────────────────────────
    # Two paths:
    #   1. Declared lineage (req.caused_by set): agent explicitly names which
    #      prior actions caused this one → precise blame attribution, no inference.
    #   2. Heuristic inference: scan full 7-day history, time-weighted scoring.
    # Attribution: top_cause() names the specific prior action driving risk.
    if tenant_id:
        try:
            from ..causal_chain import get_causal_chain, CausalRisk
            from ..latency_guard import run_with_budget
            _causal_fallback = CausalRisk(
                causal_score=0.5, credential_actions=0, data_actions=0,
                oldest_action_age_h=0.0, reason="causal_timeout_conservative",
            )

            _declared_lineage = list(req.caused_by) if req.caused_by else []

            if _declared_lineage:
                # Declared path — lookup those specific action_ids
                def _declared_eval():
                    chain = get_causal_chain()
                    contribs = chain.build_declared_contributions(
                        _declared_lineage, req.action_type
                    )
                    # Synthesize a CausalRisk from declared contributions
                    cred = sum(1 for c in contribs if c.output_type == "credential")
                    data = sum(1 for c in contribs if c.output_type == "data")
                    score = min(1.0, sum(c.contribution_weight * (0.30 if c.output_type == "credential" else 0.10) for c in contribs))
                    oldest = max((c.age_h for c in contribs), default=0.0)
                    r = CausalRisk(
                        causal_score=round(score, 4),
                        credential_actions=cred, data_actions=data,
                        oldest_action_age_h=oldest,
                        reason=f"declared_lineage(n={len(contribs)})",
                        contributions=contribs,
                    )
                    return r
                _causal, _causal_timed_out = run_with_budget(
                    "causal", _declared_eval, fallback=_causal_fallback,
                )
                req_context["causal_lineage_source"] = "declared"
            else:
                # Heuristic path
                _causal, _causal_timed_out = run_with_budget(
                    "causal",
                    lambda: get_causal_chain().evaluate(
                        tenant_id=tenant_id,
                        agent_id=req.agent_id,
                        action_type=req.action_type,
                    ),
                    fallback=_causal_fallback,
                )
                req_context["causal_lineage_source"] = "inferred"

            req_context["causal_risk_score"]       = _causal.causal_score
            req_context["causal_credential_count"] = _causal.credential_actions
            req_context["causal_reason"]           = _causal.reason
            req_context["causal_timed_out"]        = _causal_timed_out
            # Attribution: surface the specific prior action driving risk
            _top_cause = _causal.top_cause()
            if _top_cause:
                req_context["causal_top_blame"] = {
                    "action_id":           _top_cause.action_id,
                    "action_type":         _top_cause.action_type,
                    "age_h":               _top_cause.age_h,
                    "contribution_weight": _top_cause.contribution_weight,
                    "reason":              _top_cause.reason,
                    "lineage_source":      req_context.get("causal_lineage_source", "inferred"),
                }
            if _causal.causal_score > 0.50:
                req_context["risk_estimate"] = "critical"
            elif _causal.causal_score > 0.25:
                current = req_context.get("risk_estimate", "low")
                if current in ("low", "medium"):
                    req_context["risk_estimate"] = "high"
        except Exception as _causal_err:
            logger.debug("Causal chain check failed (non-blocking): %s", _causal_err)

    # ── Fleet campaign detection ─────────────────────────────────────────────
    # Cross-tenant fingerprint matching — detects coordinated attacks at scale.
    # "10 tenants seeing the same action sequence" = campaign signal.
    if tenant_id:
        try:
            from ..fleet.campaign_detector import get_campaign_detector, CampaignSignal
            from ..latency_guard import run_with_budget
            _campaign_fallback = CampaignSignal(
                fingerprint="", threat_level="watch",
                matched_tenants=0, matched_agents=0,
                sample_action_seq=[], window_h=24.0,
                reason="fleet_timeout_conservative",
            )
            _campaign, _fleet_timed_out = run_with_budget(
                "fleet",
                lambda: get_campaign_detector().detect(
                    tenant_id=tenant_id,
                    agent_id=req.agent_id,
                    action_type=req.action_type,
                ),
                fallback=_campaign_fallback,
            )
            # Record this action into the global fingerprint store
            try:
                get_campaign_detector().record(tenant_id, req.agent_id, req.action_type)
            except Exception:
                pass
            req_context["fleet_campaign_level"]   = _campaign.threat_level
            req_context["fleet_matched_tenants"]  = _campaign.matched_tenants
            req_context["fleet_timed_out"]        = _fleet_timed_out
            if _campaign.threat_level in ("suspected", "confirmed"):
                current = req_context.get("risk_estimate", "low")
                if current not in ("critical",):
                    req_context["risk_estimate"] = "critical" if _campaign.threat_level == "confirmed" else "high"
                logger.warning(
                    "[/v1/action] fleet campaign signal: agent=%s action=%s level=%s tenants=%d",
                    req.agent_id, req.action_type,
                    _campaign.threat_level, _campaign.matched_tenants,
                )
                # Cross-tenant proposal generation: submit an ESCALATE proposal for
                # every affected tenant so they each get the campaign finding surfaced
                # in their review queue without waiting for the attack to hit them.
                try:
                    from ..policy.proposals import get_proposal_store
                    _store = get_proposal_store()
                    # Current tenant already gets a proposal
                    _affected_tenants = list({tenant_id} | set(_campaign.top_tenants))
                    for _affected_tid in _affected_tenants:
                        if not _affected_tid:
                            continue
                        _store.submit(
                            tenant_id=_affected_tid,
                            source="campaign_detector",
                            action="ESCALATE",
                            name=f"Campaign signal: {req.action_type} ({_campaign.fingerprint[:8]})",
                            description=(
                                f"Action sequence '{req.action_type}' matched {_campaign.matched_tenants} "
                                f"tenants in {_campaign.window_h}h window — possible coordinated attack."
                            ),
                            rationale=_campaign.reason,
                            condition_tool=req.action_type.split(".")[0],
                            condition_op=req.action_type.split(".", 1)[1] if "." in req.action_type else None,
                            priority=100,  # high priority — cross-tenant signal
                            evidence=(
                                f"tenants={_campaign.matched_tenants} "
                                f"agents={_campaign.matched_agents} "
                                f"level={_campaign.threat_level} "
                                f"fingerprint={_campaign.fingerprint}"
                            ),
                        )
                except Exception as _prop_err:
                    logger.debug("Cross-tenant proposal generation failed: %s", _prop_err)
        except Exception as _fleet_err:
            logger.debug("Fleet campaign check failed (non-blocking): %s", _fleet_err)

    # ── Multi-agent coordination risk (Fix 2) ───────────────────────────────
    # Score composite risk from prior actions in this session before evaluation.
    # Detects cross-agent data hand-offs and credential propagation paths.
    if tenant_id:
        try:
            from ..coordination import get_coordination_graph, CoordinationRisk
            from ..latency_guard import run_with_budget
            _coord_fallback = CoordinationRisk(
                composite_score=0.3, unique_agents=1,
                data_flow_connections=0, credential_in_flow=False,
                multi_agent=False, reason="coord_timeout_conservative",
            )
            _coord_risk, _coord_timed_out = run_with_budget(
                "coordination",
                lambda: get_coordination_graph().evaluate_composite_risk(
                    tenant_id=tenant_id,
                    session_id=req_context["session_id"],
                    agent_id=req.agent_id,
                    action_type=req.action_type,
                ),
                fallback=_coord_fallback,
            )
            req_context["coordination_composite_risk"] = _coord_risk.composite_score
            req_context["coordination_multi_agent"]    = _coord_risk.multi_agent
            req_context["coordination_reason"]         = _coord_risk.reason
            req_context["coordination_timed_out"]      = _coord_timed_out
            if _coord_risk.composite_score > 0.30:
                current = req_context.get("risk_estimate", "low")
                if _coord_risk.composite_score > 0.60 and current not in ("critical",):
                    req_context["risk_estimate"] = "critical"
                elif _coord_risk.composite_score > 0.30 and current in ("low",):
                    req_context["risk_estimate"] = "high"
        except Exception as _coord_err:
            logger.debug("Coordination graph check failed (non-blocking): %s", _coord_err)

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

    # ── PHI endpoint allowlist check ────────────────────────────────────────────
    # Block any action that tries to send data to an unauthorized URL.
    # Runs before the governor so it never hits policy evaluation.
    if tenant_id:
        try:
            _phi_allowed, _phi_url, _phi_reason = phi_check_params(
                tenant_id=tenant_id,
                params=action_params,
            )
            if not _phi_allowed:
                latency_ms = int((time.time() - start_time) * 1000)
                logger.warning(
                    "[/v1/action] PHI allowlist block: agent=%s url=%s tenant=%s",
                    req.agent_id, _phi_url, tenant_id,
                )
                raise HTTPException(
                    status_code=403,
                    detail=_phi_reason or "Action blocked — unauthorized endpoint (PHI-EXFIL-001).",
                )
        except HTTPException:
            raise
        except Exception as _phi_err:
            logger.warning("PHI allowlist check failed (non-blocking): %s", _phi_err)

    # ── Intent normalization ────────────────────────────────────────────────────
    # Reconcile stated_intent, user_message, and action_type before the governor
    # sees the context. Misalignment score is advisory — it feeds into the
    # governor context and is audit-logged, but never sole basis for BLOCK.
    try:
        from ..intake.normalizer import normalize_intent
        _norm = normalize_intent(
            stated_intent=req_context.get("stated_intent", ""),
            user_message=req_context.get("user_message", "") or req_context.get("prompt", ""),
            action_type=req.action_type,
            action_payload=action_params,
        )
        req_context["intent_alignment_score"] = _norm.alignment_score
        req_context["intent_action_class"] = _norm.action_class
        req_context["intent_inferred_class"] = _norm.inferred_intent_class
        if _norm.misalignment_flag:
            req_context["intent_misalignment_flag"] = True
            req_context["intent_gap_description"] = _norm.gap_description or ""
            logger.warning(
                "[/v1/action] intent misalignment: agent=%s action=%s score=%.2f source=%s",
                req.agent_id, req.action_type, _norm.alignment_score, _norm.source,
            )
    except Exception as _norm_err:
        logger.debug("[normalizer] failed (non-blocking): %s", _norm_err)

    # ── Kill switch check ───────────────────────────────────────────────────────
    # O(1) in-memory check. If active, every action for this tenant is BLOCK.
    # The governor still runs in shadow to preserve the audit trail.
    if tenant_id:
        try:
            from ..routes.kill_switch import is_kill_switch_active
            if is_kill_switch_active(tenant_id):
                latency_ms = int((time.time() - start_time) * 1000)
                logger.warning(
                    "[/v1/action] KILL SWITCH active: tenant=%s agent=%s action=%s — forcing BLOCK",
                    tenant_id, req.agent_id, req.action_type,
                )
                return V1ActionResponse(  # type: ignore[call-arg]
                    action_id=f"ks-{req.agent_id}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}",
                    decision="BLOCK",
                    decision_reason=(
                        "Emergency kill switch is active for this tenant. "
                        "All AI agent actions are halted. "
                        "Contact your administrator to resume operations."
                    ),
                    policy_version="kill-switch",
                    processing_latency_ms=latency_ms,
                    reason_code="KILL_SWITCH",
                )
        except Exception as _ks_err:
            logger.warning("Kill switch check failed (non-blocking): %s", _ks_err)

    # ── Trust engine ────────────────────────────────────────────────────────────
    # Hard blocks fire here — before the governor, before OOB prediction.
    # For non-cold-start agents, trust score is injected into context so the
    # governor sees risk_estimate adjusted to the agent's real track record.
    _trust_score = None
    if tenant_id:
        try:
            from ..trust import get_trust_engine
            _te = get_trust_engine()

            if _te.is_hard_blocked(req.action_type):
                latency_ms = int((time.time() - start_time) * 1000)
                logger.warning(
                    "[/v1/action] HARD BLOCK: agent=%s action=%s tenant=%s",
                    req.agent_id, req.action_type, tenant_id,
                )
                return V1ActionResponse(  # type: ignore[call-arg]
                    action_id=f"hb-{req.agent_id}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}",
                    decision="BLOCK",
                    decision_reason=(
                        f"Action type '{req.action_type}' is in the hard policy block list "
                        "and cannot be permitted regardless of trust or policy rules."
                    ),
                    policy_version="hard-policy-v1",
                    processing_latency_ms=latency_ms,
                    reason_code="HARD_POLICY_BLOCK",
                )

            _trust_score = _te.get_trust(tenant_id, req.agent_id, req.action_type)
            req_context["agent_trust_combined"]    = _trust_score.combined
            req_context["agent_trust_cold_start"]  = _trust_score.cold_start
            req_context["agent_trust_confidence"]  = _trust_score.action_confidence
            req_context["agent_trust_outcomes"]    = _trust_score.action_outcomes

            # For known agents (past cold-start), skew estimated_risk toward trust.
            # Thresholds are adaptive: calibrated from the per-tenant trust distribution
            # (p10/p25/p50 of all agent scores for this tenant). Falls back to fixed
            # defaults (0.35/0.50/0.65) if < 50 agents are enrolled.
            if not _trust_score.cold_start:
                try:
                    _risk_thresholds = _te.compute_adaptive_risk_thresholds(tenant_id)
                    _crit_t = _risk_thresholds["critical"]
                    _high_t = _risk_thresholds["high"]
                    _med_t  = _risk_thresholds["medium"]
                    req_context["trust_adaptive_thresholds"] = _risk_thresholds
                except Exception:
                    _crit_t, _high_t, _med_t = 0.35, 0.50, 0.65
                if _trust_score.combined < _crit_t:
                    req_context["risk_estimate"] = "critical"
                elif _trust_score.combined < _high_t:
                    req_context["risk_estimate"] = "high"
                elif _trust_score.combined < _med_t:
                    req_context.setdefault("risk_estimate", "medium")

            # Behavioral entropy: low diversity = possible probing pattern.
            # Computed inside get_trust() — read here, elevate risk if needed.
            _entropy = getattr(_trust_score, "behavioral_entropy", 1.0)
            req_context["behavioral_entropy"] = _entropy
            if not _trust_score.cold_start and _entropy < 0.20:
                current = req_context.get("risk_estimate", "low")
                if current not in ("critical",):
                    req_context["risk_estimate"] = "critical" if current == "high" else "high"
                logger.warning(
                    "[/v1/action] low behavioral entropy: agent=%s entropy=%.3f",
                    req.agent_id, _entropy,
                )

            # Patch E: exploitation detection — trust-building into high-risk action.
            # Runs after basic risk skewing so it can override to "critical" when needed.
            try:
                _risk_bucket = req_context.get("risk_estimate", "default")
                _exploit = _te.detect_exploitation_pattern(
                    tenant_id=tenant_id,
                    agent_id=req.agent_id,
                    action_type=req.action_type,
                    risk_bucket=_risk_bucket,
                )
                req_context["exploitation_signal"] = _exploit
                if _exploit.get("exploitation_suspected"):
                    req_context["risk_estimate"] = "critical"
                    logger.warning(
                        "[/v1/action] exploitation pattern detected: agent=%s action=%s "
                        "run=%d trend=%.4f reason=%s",
                        req.agent_id, req.action_type,
                        _exploit["positive_run"], _exploit["trust_trend"],
                        _exploit["reason"],
                    )
            except Exception as _exp_err:
                logger.debug("Exploitation detection failed (non-blocking): %s", _exp_err)

        except Exception as _trust_err:
            logger.warning("Trust engine check failed (non-blocking): %s", _trust_err)

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

    # ── Shadow execution — probabilistic adversarial replay ──────────────────
    # Capture this trace and, at the configured sample rate, re-run it through
    # the governor under adversarial perturbation (async, never blocks response).
    try:
        import asyncio as _asyncio
        from ..shadow import capture_trace as _capture_trace, shadow_should_sample, shadow_run_trace
        _shadow_trace = _capture_trace(
            agent_id=req.agent_id,
            tenant_id=tenant_id,
            action_type=req.action_type,
            action_payload=dict(req.action_payload or {}),
            context=req_context,
            timestamp=req.timestamp,
            intent_id=effective_intent_id,
            verdict=verdict_str,
            reason=decision.explanation or "",
            latency_ms=latency_ms,
            meta=decision.meta or {},
        )
        if shadow_should_sample():
            _asyncio.create_task(
                shadow_run_trace(_shadow_trace, governor=governor, db=db)
            )
    except Exception as _shadow_err:
        logger.debug("[shadow] capture/dispatch failed (non-blocking): %s", _shadow_err)

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
        engine = get_fleet_learning_engine()
        engine.record_feedback(
            tenant_id=tenant_id,
            agent_id=req.agent_id,
            action_tool=action.tool.value,
            action_op=action.op,
            label=auto_label,
            predicted_risk=(prediction.score if prediction else None),
            source="auto_decision",
            notes=f"decision={verdict_str}",
        )
        # Sequence (bigram) transition label — records (prev_action → this_action) outcome
        # so the model learns which action pairs are risky, not just individual actions.
        _prev = prediction.prev_action if prediction else None
        if _prev:
            prev_tool, prev_op = _prev
        else:
            prev_tool = prev_op = ""
        if prev_tool and prev_op:
            engine.record_sequence_feedback(
                tenant_id=tenant_id,
                agent_id=req.agent_id,
                prev_tool=prev_tool,
                prev_op=prev_op,
                curr_tool=action.tool.value,
                curr_op=action.op,
                label=auto_label,
                source="auto_decision",
            )
    except Exception as _learning_err:
        logger.warning("auto learning feedback failed (non-blocking): %s", _learning_err)

    # ── Audit-ready reason formatting ────────────────────────────────────────
    # Rewrite the explanation into regulation-mapped, auditor-friendly language.
    try:
        decision.explanation = fmt_audit_reason(
            verdict=verdict_str,
            reason_code=decision.reason_code.value if decision.reason_code else None,
            decision_id=decision_id,
            agent_id=req.agent_id,
            original_explanation=decision.explanation or "",
        )
    except Exception:
        pass  # Never block on formatter failure

    # ── Dispatch governance event webhooks (non-blocking) ────────────────────
    if tenant_id:
        try:
            import asyncio as _asyncio
            from ..webhooks import dispatch_event
            from ..services.webhook_delivery import deliver_webhook as _deliver_webhook
            _verdict = decision.verdict.value
            _legacy_event = (
                "action.blocked" if _verdict in ("BLOCK", "ERROR")
                else "action.escalated" if _verdict in ("ESCALATE", "PAUSE")
                else "action.allowed"
            )
            _decision_data = {
                "action_id": decision_id,
                "action_type": req.action_type,
                "agent_id": req.agent_id,
                "verdict": _verdict,
                "reason": decision.explanation,
                "escalation_question": decision.escalation_question or "",
                "escalation_options": decision.escalation_options or [],
                "review_url": "https://console.edoncore.com",
            }
            # Legacy synchronous dispatcher (keeps existing alert rules working)
            dispatch_event(
                event_type=_legacy_event,
                payload=_decision_data,
                tenant_id=tenant_id,
                db=db,
            )
            # New async deliver_webhook — fires per the new /webhooks route events
            if _verdict in ("BLOCK", "ERROR"):
                _asyncio.create_task(_deliver_webhook(tenant_id, "decision.blocked", _decision_data, db))
            elif _verdict in ("ESCALATE", "PAUSE"):
                _asyncio.create_task(_deliver_webhook(tenant_id, "decision.escalated", _decision_data, db))
            # risk.high — fire whenever risk_score > 0.7 (from prediction or anomaly)
            _risk_score = (decision.meta or {}).get("predictive_oob_risk") or 0.0
            if not _risk_score:
                _anomaly = (decision.meta or {}).get("anomaly", {})
                _risk_score = (_anomaly.get("score") or 0.0) if _anomaly else 0.0
            if _risk_score > 0.7:
                _asyncio.create_task(_deliver_webhook(tenant_id, "risk.high", _decision_data, db))
        except Exception as _wh_err:
            logger.warning("Webhook dispatch failed (non-blocking): %s", _wh_err)

    # ── Enqueue HUMAN_REQUIRED escalations for review + Telegram notify ──────
    if verdict_str in ("ESCALATE", "PAUSE") and tenant_id:
        try:
            from .review_queue import enqueue_escalation, notify_escalation_async
            _record = {
                "decision_id": decision_id,
                "tenant_id": tenant_id,
                "agent_id": req.agent_id,
                "action_type": req.action_type,
                "action_payload": dict(req.action_payload or {}),
                "escalation_question": decision.escalation_question or "Human review required.",
                "explanation": decision.explanation,
                "meta": decision.meta or {},
            }
            enqueue_escalation(**_record)
            notify_escalation_async(_record)
        except Exception as _esq_err:
            logger.warning("Escalation enqueue failed (non-blocking): %s", _esq_err)

    # ── Anomaly Telegram alert ────────────────────────────────────────────────
    # If anomaly score is high (>= 75), send Telegram alert immediately.
    # This is advisory — we alert, we don't claim to detect every threat.
    _anomaly_meta_v = (decision.meta or {}).get("anomaly", {})
    _anomaly_score_v = _anomaly_meta_v.get("score", 0.0) if _anomaly_meta_v else 0.0
    if _anomaly_score_v >= 0.75 and tenant_id:
        try:
            import threading as _thr
            def _send_anomaly_alert() -> None:
                import os as _os, requests as _rq
                _bot = _os.getenv("TELEGRAM_BOT_TOKEN", "")
                _chat = _os.getenv("TELEGRAM_OWNER_CHAT_ID", "") or _os.getenv("TELEGRAM_CHAT_ID", "")
                if not _bot or not _chat:
                    return
                _pattern = _anomaly_meta_v.get("pattern_name", "unknown")
                _msg = (
                    f"⚠️ *Anomaly Detected*\n\n"
                    f"*Agent:* `{req.agent_id}`\n"
                    f"*Action:* `{req.action_type}`\n"
                    f"*Pattern:* `{_pattern}`\n"
                    f"*Score:* `{round(_anomaly_score_v * 100)}/100`\n"
                    f"*Verdict:* `{verdict_str}`\n"
                    f"*Tenant:* `{tenant_id}`\n"
                    f"*Decision:* `{decision_id}`\n\n"
                    f"_This is an advisory alert — review at console.edoncore.com_"
                )
                try:
                    _rq.post(
                        f"https://api.telegram.org/bot{_bot}/sendMessage",
                        json={"chat_id": _chat, "text": _msg, "parse_mode": "Markdown"},
                        timeout=8,
                    )
                except Exception:
                    pass
            _thr.Thread(target=_send_anomaly_alert, daemon=True).start()
        except Exception as _anom_err:
            logger.warning("Anomaly alert failed (non-blocking): %s", _anom_err)

    # ── Evaluate anomaly/threshold alert rules (non-blocking, fire-and-forget) ─
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

    # ── Sandbox / Shadow Mode override ──────────────────────────────────────
    # Two ways observe-only mode can be active:
    #   1. Key-level: key.is_sandbox=True (hardcoded, cannot be bypassed)
    #   2. Tenant-level: shadow mode setting (admin-controlled)
    # Either triggers the same behaviour: log real verdict, respond ALLOW.
    _key_is_sandbox = bool((getattr(request.state, 'tenant_info', None) or {}).get('is_sandbox', False))
    _shadow_mode_active = _key_is_sandbox
    if not _shadow_mode_active and tenant_id:
        try:
            _shadow_mode_active = db.get_shadow_mode(tenant_id) if hasattr(db, "get_shadow_mode") else False
        except Exception as _sm_err:
            logger.warning("Shadow mode check failed (non-blocking): %s", _sm_err)

    if _shadow_mode_active and verdict_str not in ("ALLOW",):
        logger.info(
            "[/v1/action] shadow_mode override: agent=%s action=%s original_verdict=%s -> ALLOW",
            req.agent_id, req.action_type, verdict_str,
        )
        verdict_str = "ALLOW"

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

    # Intervention strategy — when blocked/degraded, generate a co-pilot strategy.
    # Returned as advisory: the agent/orchestrator decides whether to act on it.
    if verdict_str in ("BLOCK", "DEGRADE", "ESCALATE"):
        try:
            from ..ai.intervention_engine import generate_intervention
            _intent_obj = req_context.get("stated_intent") or req_context.get("user_message") or ""
            _risk_factors = (decision.meta or {}).get("predictive_oob_reasons") or []
            _strategy = generate_intervention(
                intent_objective=_intent_obj,
                action_type=req.action_type,
                action_params=dict(req.action_payload or {}),
                verdict=verdict_str,
                reason_code=decision.reason_code.value if decision.reason_code else None,
                risk_factors=_risk_factors,
            )
            if _strategy:
                response.intervention = _strategy.to_dict()
        except Exception as _iv_err:
            logger.debug("Intervention generation failed (non-blocking): %s", _iv_err)

    if _shadow_mode_active:
        response.shadow_mode = True

    predictive_meta = decision.meta or {}
    predictive_risk = predictive_meta.get("predictive_oob_risk")
    if predictive_risk is not None:
        response.predicted_oob_risk = float(predictive_risk)
        response.predicted_oob_reasons = predictive_meta.get("predictive_oob_reasons", [])
        response.predicted_oob_breakdown = predictive_meta.get("predictive_oob_breakdown", {})

    # ── Record in coordination graph (Fix 2) ────────────────────────────────
    # Only record when the action wasn't blocked — blocked actions didn't execute.
    if tenant_id and response_decision == "ALLOW":
        try:
            from ..coordination import get_coordination_graph as _gcg
            _gcg().record_action(
                tenant_id=tenant_id,
                session_id=req_context.get("session_id", ""),
                agent_id=req.agent_id,
                action_id=decision_id,
                action_type=req.action_type,
            )
        except Exception as _coord_rec_err:
            logger.debug("Coordination record failed (non-blocking): %s", _coord_rec_err)

    logger.info(
        f"[/v1/action] agent_id={req.agent_id} action={req.action_type} "
        f"decision={response_decision} latency={latency_ms}ms"
    )

    return response
