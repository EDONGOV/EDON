"""Pre-governor preflight pipeline for /v1/action.

Extracts all pre-evaluation checks out of the v1_action hot path so that
file stays focused on request/response plumbing. Each step runs in order,
mutating ctx.req_context in place. A step may:
  - return None       → continue to the next step
  - return a response → short-circuit; v1_action returns it immediately
  - raise HTTPException → propagates directly (quota, PHI, device errors)

ML-signal invariant (enforced by convention, not code lock):
  Learned signals — causal chain, fleet learning, coordination, prediction,
  and session trust — may only RAISE estimated risk or add escalation context.
  They must never suppress policy evaluation, flip a BLOCK verdict to ALLOW,
  or fabricate authorization. Any step that would lower risk below what static
  policy already established is a bug and must not be merged.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .logging_config import get_logger

logger = get_logger(__name__)

_POLICY_RULES_CACHE: dict = {}
_POLICY_RULES_TTL_SEC = float(os.getenv("EDON_POLICY_RULES_TTL", "30"))


@dataclass
class PreflightContext:
    req: Any                              # V1ActionRequest
    tenant_id: Optional[str]
    action: Any                           # Action
    action_params: dict
    db: Any                               # Database
    start_time: float
    req_context: dict = field(default_factory=dict)
    tenant_rules: list = field(default_factory=list)
    prediction: Any = None


# ── Steps ─────────────────────────────────────────────────────────────────────

def _step_kill_switch(ctx: PreflightContext) -> Optional[Any]:
    if not ctx.tenant_id:
        return None
    try:
        from .routes.kill_switch import is_kill_switch_active
        if not is_kill_switch_active(ctx.tenant_id):
            return None
        from datetime import datetime, UTC
        from .schemas.v1_action import V1ActionResponse
        latency_ms = int((time.time() - ctx.start_time) * 1000)
        logger.warning(
            "[preflight] KILL SWITCH active: tenant=%s agent=%s action=%s — forcing BLOCK",
            ctx.tenant_id, ctx.req.agent_id, ctx.req.action_type,
        )
        return V1ActionResponse(  # type: ignore[call-arg]
            action_id=f"ks-{ctx.req.agent_id}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}",
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
    except Exception as exc:
        logger.warning("Kill switch check failed (non-blocking): %s", exc)
    return None


def _step_quota(ctx: PreflightContext) -> None:
    import json as _json
    from fastapi import HTTPException
    try:
        from .security.agent_quotas import check_agent_quota, record_agent_call
        payload_bytes = len(_json.dumps(ctx.req.action_payload or {}).encode())
        allowed, msg = check_agent_quota(
            db=ctx.db,
            tenant_id=ctx.tenant_id,
            agent_id=ctx.req.agent_id,
            payload_bytes=payload_bytes,
        )
        if not allowed:
            raise HTTPException(status_code=429, detail=f"Agent quota exceeded: {msg}")
        record_agent_call(ctx.tenant_id, ctx.req.agent_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Agent quota check failed (non-blocking): %s", exc)


def _step_phi(ctx: PreflightContext) -> None:
    if not ctx.tenant_id:
        return
    from fastapi import HTTPException
    try:
        from .security.phi_allowlist import check_params as phi_check_params
        allowed, url, reason = phi_check_params(
            tenant_id=ctx.tenant_id,
            params=ctx.action_params,
        )
        if not allowed:
            logger.warning(
                "[preflight] PHI allowlist block: agent=%s url=%s tenant=%s",
                ctx.req.agent_id, url, ctx.tenant_id,
            )
            raise HTTPException(
                status_code=403,
                detail=reason or "Action blocked — unauthorized endpoint (PHI-EXFIL-001).",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("PHI allowlist check failed (non-blocking): %s", exc)


def _step_intent(ctx: PreflightContext) -> None:
    try:
        from .intake.normalizer import normalize_intent
        norm = normalize_intent(
            stated_intent=ctx.req_context.get("stated_intent", ""),
            user_message=ctx.req_context.get("user_message", "") or ctx.req_context.get("prompt", ""),
            action_type=ctx.req.action_type,
            action_payload=ctx.action_params,
        )
        ctx.req_context["intent_alignment_score"] = norm.alignment_score
        ctx.req_context["intent_action_class"] = norm.action_class
        ctx.req_context["intent_inferred_class"] = norm.inferred_intent_class
        if norm.misalignment_flag:
            ctx.req_context["intent_misalignment_flag"] = True
            ctx.req_context["intent_gap_description"] = norm.gap_description or ""
            logger.warning(
                "[preflight] intent misalignment: agent=%s action=%s score=%.2f source=%s",
                ctx.req.agent_id, ctx.req.action_type, norm.alignment_score, norm.source,
            )
    except Exception as exc:
        logger.debug("[preflight/intent] failed (non-blocking): %s", exc)


def _step_causal(ctx: PreflightContext) -> None:
    if not ctx.tenant_id:
        return
    try:
        from .causal_chain import get_causal_chain, CausalRisk
        from .latency_guard import run_with_budget
        _fallback = CausalRisk(
            causal_score=0.5, credential_actions=0, data_actions=0,
            oldest_action_age_h=0.0, reason="causal_timeout_conservative",
        )
        declared = list(ctx.req.caused_by) if ctx.req.caused_by else []
        if declared:
            def _declared_eval():
                chain = get_causal_chain()
                contribs = chain.build_declared_contributions(declared, ctx.req.action_type)
                cred   = sum(1 for c in contribs if c.output_type == "credential")
                data   = sum(1 for c in contribs if c.output_type == "data")
                score  = min(1.0, sum(
                    c.contribution_weight * (0.30 if c.output_type == "credential" else 0.10)
                    for c in contribs
                ))
                oldest = max((c.age_h for c in contribs), default=0.0)
                return CausalRisk(
                    causal_score=round(score, 4),
                    credential_actions=cred, data_actions=data,
                    oldest_action_age_h=oldest,
                    reason=f"declared_lineage(n={len(contribs)})",
                    contributions=contribs,
                )
            causal, timed_out = run_with_budget("causal", _declared_eval, fallback=_fallback)
            ctx.req_context["causal_lineage_source"] = "declared"
        else:
            causal, timed_out = run_with_budget(
                "causal",
                lambda: get_causal_chain().evaluate(
                    tenant_id=ctx.tenant_id,
                    agent_id=ctx.req.agent_id,
                    action_type=ctx.req.action_type,
                ),
                fallback=_fallback,
            )
            ctx.req_context["causal_lineage_source"] = "inferred"

        ctx.req_context["causal_risk_score"]       = causal.causal_score
        ctx.req_context["causal_credential_count"] = causal.credential_actions
        ctx.req_context["causal_reason"]           = causal.reason
        ctx.req_context["causal_timed_out"]        = timed_out
        top = causal.top_cause()
        if top:
            ctx.req_context["causal_top_blame"] = {
                "action_id":           top.action_id,
                "action_type":         top.action_type,
                "age_h":               top.age_h,
                "contribution_weight": top.contribution_weight,
                "reason":              top.reason,
                "lineage_source":      ctx.req_context.get("causal_lineage_source", "inferred"),
            }
        if causal.causal_score > 0.50:
            ctx.req_context["risk_estimate"] = "critical"
        elif causal.causal_score > 0.25:
            if ctx.req_context.get("risk_estimate", "low") in ("low", "medium"):
                ctx.req_context["risk_estimate"] = "high"
    except Exception as exc:
        logger.debug("Causal chain check failed (non-blocking): %s", exc)


def _step_fleet(ctx: PreflightContext) -> None:
    if not ctx.tenant_id:
        return
    try:
        from .fleet.campaign_detector import get_campaign_detector, CampaignSignal
        from .latency_guard import run_with_budget
        _fallback = CampaignSignal(
            fingerprint="", threat_level="watch",
            matched_tenants=0, matched_agents=0,
            sample_action_seq=[], window_h=24.0,
            reason="fleet_timeout_conservative",
        )
        campaign, timed_out = run_with_budget(
            "fleet",
            lambda: get_campaign_detector().detect(
                tenant_id=ctx.tenant_id,
                agent_id=ctx.req.agent_id,
                action_type=ctx.req.action_type,
            ),
            fallback=_fallback,
        )
        try:
            get_campaign_detector().record(ctx.tenant_id, ctx.req.agent_id, ctx.req.action_type)
        except Exception:
            pass
        ctx.req_context["fleet_campaign_level"]  = campaign.threat_level
        ctx.req_context["fleet_matched_tenants"] = campaign.matched_tenants
        ctx.req_context["fleet_timed_out"]       = timed_out
        if campaign.threat_level in ("suspected", "confirmed"):
            current = ctx.req_context.get("risk_estimate", "low")
            if current not in ("critical",):
                ctx.req_context["risk_estimate"] = (
                    "critical" if campaign.threat_level == "confirmed" else "high"
                )
            logger.warning(
                "[preflight] fleet campaign signal: agent=%s action=%s level=%s tenants=%d",
                ctx.req.agent_id, ctx.req.action_type,
                campaign.threat_level, campaign.matched_tenants,
            )
            try:
                from .policy.proposals import get_proposal_store
                store    = get_proposal_store()
                affected = list({ctx.tenant_id} | set(campaign.top_tenants))
                for tid in affected:
                    if not tid:
                        continue
                    store.submit(
                        tenant_id=tid,
                        source="campaign_detector",
                        action="ESCALATE",
                        name=f"Campaign signal: {ctx.req.action_type} ({campaign.fingerprint[:8]})",
                        description=(
                            f"Action sequence '{ctx.req.action_type}' matched "
                            f"{campaign.matched_tenants} tenants in {campaign.window_h}h window "
                            "— possible coordinated attack."
                        ),
                        rationale=campaign.reason,
                        condition_tool=ctx.req.action_type.split(".")[0],
                        condition_op=(
                            ctx.req.action_type.split(".", 1)[1]
                            if "." in ctx.req.action_type else None
                        ),
                        priority=100,
                        evidence=(
                            f"tenants={campaign.matched_tenants} "
                            f"agents={campaign.matched_agents} "
                            f"level={campaign.threat_level} "
                            f"fingerprint={campaign.fingerprint}"
                        ),
                    )
            except Exception as exc:
                logger.debug("Cross-tenant proposal generation failed: %s", exc)
    except Exception as exc:
        logger.debug("Fleet campaign check failed (non-blocking): %s", exc)


def _step_coordination(ctx: PreflightContext) -> None:
    if not ctx.tenant_id:
        return
    try:
        from .coordination import get_coordination_graph, CoordinationRisk
        from .latency_guard import run_with_budget
        _fallback = CoordinationRisk(
            composite_score=0.3, unique_agents=1,
            data_flow_connections=0, credential_in_flow=False,
            multi_agent=False, reason="coord_timeout_conservative",
        )
        coord, timed_out = run_with_budget(
            "coordination",
            lambda: get_coordination_graph().evaluate_composite_risk(
                tenant_id=ctx.tenant_id,
                session_id=ctx.req_context["session_id"],
                agent_id=ctx.req.agent_id,
                action_type=ctx.req.action_type,
            ),
            fallback=_fallback,
        )
        ctx.req_context["coordination_composite_risk"] = coord.composite_score
        ctx.req_context["coordination_multi_agent"]    = coord.multi_agent
        ctx.req_context["coordination_reason"]         = coord.reason
        ctx.req_context["coordination_timed_out"]      = timed_out
        if coord.composite_score > 0.30:
            current = ctx.req_context.get("risk_estimate", "low")
            if coord.composite_score > 0.60 and current not in ("critical",):
                ctx.req_context["risk_estimate"] = "critical"
            elif coord.composite_score > 0.30 and current in ("low",):
                ctx.req_context["risk_estimate"] = "high"
    except Exception as exc:
        logger.debug("Coordination graph check failed (non-blocking): %s", exc)


def _step_prediction(ctx: PreflightContext) -> None:
    if not ctx.tenant_id:
        return
    try:
        from .fleet_learning import get_fleet_learning_engine
        estimated_risk = str(ctx.req_context.get("risk_estimate", "low"))
        ctx.prediction = get_fleet_learning_engine().predict_action(
            db=ctx.db,
            tenant_id=ctx.tenant_id,
            agent_id=ctx.req.agent_id,
            action_tool=ctx.action.tool.value,
            action_op=ctx.action.op,
            estimated_risk=estimated_risk,
        )
        ctx.req_context["predicted_oob_risk"]    = round(ctx.prediction.score, 4)
        ctx.req_context["predicted_oob_reasons"] = ctx.prediction.reasons
    except Exception as exc:
        logger.warning("Predictive OOB scoring failed (non-blocking): %s", exc)


def _step_policy_rules(ctx: PreflightContext) -> None:
    if not ctx.tenant_id:
        return
    try:
        cached = _POLICY_RULES_CACHE.get(ctx.tenant_id)
        if cached and cached[1] > time.time():
            ctx.tenant_rules = cached[0]
        else:
            ctx.tenant_rules = ctx.db.get_policy_rules(ctx.tenant_id, enabled_only=True)
            _POLICY_RULES_CACHE[ctx.tenant_id] = (
                ctx.tenant_rules, time.time() + _POLICY_RULES_TTL_SEC
            )
            now = time.time()
            for k in [k for k, v in _POLICY_RULES_CACHE.items() if v[1] <= now]:
                del _POLICY_RULES_CACHE[k]
    except Exception as exc:
        logger.warning("Failed to load tenant policy rules for %s: %s", ctx.tenant_id, exc)
    try:
        from .policy.defaults import SYSTEM_DEFAULT_RULES
        ctx.tenant_rules = ctx.tenant_rules + SYSTEM_DEFAULT_RULES
    except Exception as exc:
        logger.debug("System rules load failed (non-blocking): %s", exc)


def _step_trust(ctx: PreflightContext) -> Optional[Any]:
    if not ctx.tenant_id:
        return None
    try:
        from .trust import get_trust_engine
        te = get_trust_engine()
        if te.is_hard_blocked(ctx.req.action_type):
            from datetime import datetime, UTC
            from .schemas.v1_action import V1ActionResponse
            latency_ms = int((time.time() - ctx.start_time) * 1000)
            logger.warning(
                "[preflight] HARD BLOCK: agent=%s action=%s tenant=%s",
                ctx.req.agent_id, ctx.req.action_type, ctx.tenant_id,
            )
            return V1ActionResponse(  # type: ignore[call-arg]
                action_id=f"hb-{ctx.req.agent_id}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}",
                decision="BLOCK",
                decision_reason=(
                    f"Action type '{ctx.req.action_type}' is in the hard policy block list "
                    "and cannot be permitted regardless of trust or policy rules."
                ),
                policy_version="hard-policy-v1",
                processing_latency_ms=latency_ms,
                reason_code="HARD_POLICY_BLOCK",
            )
        trust = te.get_trust(ctx.tenant_id, ctx.req.agent_id, ctx.req.action_type)
        ctx.req_context["agent_trust_combined"]   = trust.combined_raw
        ctx.req_context["agent_trust_cold_start"] = trust.cold_start
        ctx.req_context["agent_trust_confidence"] = trust.action_confidence
        ctx.req_context["agent_trust_outcomes"]   = trust.action_outcomes
        if not trust.cold_start:
            try:
                thresholds = te.compute_adaptive_risk_thresholds(ctx.tenant_id)
                crit_t = thresholds["critical"]
                high_t = thresholds["high"]
                med_t  = thresholds["medium"]
                ctx.req_context["trust_adaptive_thresholds"] = thresholds
            except Exception:
                crit_t, high_t, med_t = 0.35, 0.50, 0.65
            if trust.combined_raw < crit_t:
                ctx.req_context["risk_estimate"] = "critical"
            elif trust.combined_raw < high_t:
                ctx.req_context["risk_estimate"] = "high"
            elif trust.combined_raw < med_t:
                ctx.req_context.setdefault("risk_estimate", "medium")
        entropy = getattr(trust, "behavioral_entropy", 1.0)
        ctx.req_context["behavioral_entropy"] = entropy
        if not trust.cold_start and entropy < 0.20:
            current = ctx.req_context.get("risk_estimate", "low")
            if current not in ("critical",):
                ctx.req_context["risk_estimate"] = "critical" if current == "high" else "high"
            logger.warning(
                "[preflight] low behavioral entropy: agent=%s entropy=%.3f",
                ctx.req.agent_id, entropy,
            )
        try:
            exploit = te.detect_exploitation_pattern(
                tenant_id=ctx.tenant_id,
                agent_id=ctx.req.agent_id,
                action_type=ctx.req.action_type,
                risk_bucket=ctx.req_context.get("risk_estimate", "default"),
            )
            ctx.req_context["exploitation_signal"] = exploit
            if exploit.get("exploitation_suspected"):
                ctx.req_context["risk_estimate"] = "critical"
                logger.warning(
                    "[preflight] exploitation pattern detected: agent=%s action=%s "
                    "run=%d trend=%.4f reason=%s",
                    ctx.req.agent_id, ctx.req.action_type,
                    exploit["positive_run"], exploit["trust_trend"], exploit["reason"],
                )
        except Exception as exc:
            logger.debug("Exploitation detection failed (non-blocking): %s", exc)
    except Exception as exc:
        logger.warning("Trust engine check failed (non-blocking): %s", exc)
    return None


# ── Pipeline ──────────────────────────────────────────────────────────────────

_STEPS = [
    _step_kill_switch,   # fastest O(1) — short-circuit before any computation
    _step_quota,         # fast fail — don't burn compute on over-quota agents
    _step_phi,           # fast fail — block unauthorized data paths early
    _step_intent,        # cheap normalization
    _step_causal,        # thread-pool, time-budgeted
    _step_fleet,         # thread-pool, time-budgeted
    _step_coordination,  # thread-pool, time-budgeted
    _step_prediction,    # ML inference
    _step_policy_rules,  # cached DB read
    _step_trust,         # trust scoring + hard-block check
]


def run_preflight(ctx: PreflightContext) -> Optional[Any]:
    """Run all preflight checks in order.

    Returns a V1ActionResponse to short-circuit (kill switch, hard block),
    or None if the request should proceed to the governor.

    Raises HTTPException for validation errors (quota exceeded, PHI blocked).
    Mutates ctx.req_context, ctx.tenant_rules, and ctx.prediction in place.
    """
    for step in _STEPS:
        result = step(ctx)
        if result is not None:
            return result
    return None
