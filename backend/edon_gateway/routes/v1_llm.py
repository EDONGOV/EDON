"""LLM proxy endpoint — POST /v1/llm

Drop-in governance proxy for LLM calls. Full runtime governance loop:

    1. Predict OOB risk via fleet learning (prev actions + sequence signal)
    2. Score multi-turn conversation context through sequence scorer
    3. Govern the full conversation through the policy engine
    4. Forward to provider if ALLOW
    5. Scan output through output filter
    6. Record outcome into fleet learning (closes the loop)

Supports OpenAI and Anthropic. Provider key via X-Provider-Key header or env.
"""

from __future__ import annotations

import os
import time
import hashlib
import json as _json_stdlib
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from ..fleet_learning import get_fleet_learning_engine
from ..logging_config import get_logger
from ..security.output_filter import filter_output
from ..state.sequence_scorer import get_scorer
from ..tenancy import get_request_tenant_id
from ..governance_records import build_decision_record, build_execution_token, verify_execution_token

logger = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["v1-llm"])

_OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
_ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
_SUPPORTED_PROVIDERS = {"openai", "anthropic"}

_LLM_TOOL = "llm"
_LLM_OP = "generate"


class LLMMessage(BaseModel):
    role: str
    content: str


class V1LLMRequest(BaseModel):
    provider: str = Field(default="openai", description="openai | anthropic")
    model: str = Field(..., description="e.g. gpt-4o or claude-sonnet-4-6")
    messages: List[LLMMessage]
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, gt=0)
    agent_id: str = Field(default="llm-proxy-agent")
    intent_id: Optional[str] = None
    stated_intent: Optional[str] = None
    extra: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Extra provider params forwarded verbatim (e.g. top_p, stream=false)",
    )


class V1LLMResponse(BaseModel):
    verdict: str
    content: Optional[str] = None
    findings: List[dict] = []
    redacted: bool = False
    provider_response: Optional[dict] = None
    oob_prediction: Optional[dict] = None
    sequence_score: Optional[float] = None
    governance_latency_ms: int = 0
    provider_latency_ms: int = 0
    decision_record: Optional[Dict[str, Any]] = None
    execution_token: Optional[Dict[str, Any]] = None


@router.post("/llm", response_model=V1LLMResponse)
async def llm_proxy(
    request: Request,
    body: V1LLMRequest,
    x_provider_key: Optional[str] = Header(default=None, alias="X-Provider-Key"),
):
    """Govern an LLM request and proxy it to the provider."""
    start = time.time()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    if body.provider not in _SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider '{body.provider}'. Use: {sorted(_SUPPORTED_PROVIDERS)}")
    if not body.messages:
        raise HTTPException(status_code=400, detail="messages must not be empty")

    user_messages = [m for m in body.messages if m.role == "user"]
    last_user_msg = user_messages[-1].content if user_messages else ""
    # Multi-turn context: concatenate all user messages for full-conversation governance
    full_context = " | ".join(m.content[:500] for m in user_messages)[:2000]

    # ── 1. Fleet learning — OOB prediction ────────────────────────────────────
    prediction = None
    if tenant_id:
        try:
            from ..persistence import get_db
            prediction = get_fleet_learning_engine().predict_action(
                db=get_db(),
                tenant_id=tenant_id,
                agent_id=body.agent_id,
                action_tool=_LLM_TOOL,
                action_op=_LLM_OP,
                estimated_risk="low",
            )
        except Exception as _pred_err:
            logger.debug("[v1/llm] OOB prediction failed (non-blocking): %s", _pred_err)

    # ── 2. Sequence scorer — multi-turn session context ────────────────────────
    # Each message in the conversation is scored as an llm.generate action so
    # the scorer can detect patterns like: read_data → llm.generate → write_comms
    seq_score = 0.0
    seq_chain: Optional[str] = None
    try:
        scorer = get_scorer()
        for _ in user_messages:
            seq_score, seq_chain = scorer.record_and_score(
                tenant_id=tenant_id,
                agent_id=body.agent_id,
                intent_id=body.intent_id,
                tool_val=_LLM_TOOL,
                op=_LLM_OP,
            )
        scorer.record_cross_intent(
            tenant_id=tenant_id,
            agent_id=body.agent_id,
            tool_val=_LLM_TOOL,
            op=_LLM_OP,
        )
    except Exception as _seq_err:
        logger.debug("[v1/llm] sequence scoring failed (non-blocking): %s", _seq_err)

    # ── 3. Governance ──────────────────────────────────────────────────────────
    gov_verdict, gov_explanation, gov_question, gov_decision_id, gov_record, gov_token = await _govern_input(
        tenant_id=tenant_id,
        agent_id=body.agent_id,
        intent_id=body.intent_id,
        stated_intent=body.stated_intent,
        model=body.model,
        conversation_context=full_context,
        oob_score=prediction.score if prediction else 0.0,
        seq_score=seq_score,
    )
    governance_latency_ms = int((time.time() - start) * 1000)
    provider_latency_ms = 0

    oob_dict = prediction.to_dict() if prediction else None

    if gov_verdict == "BLOCK":
        _record_llm_feedback(tenant_id, body.agent_id, "blocked", prediction)
        _record_llm_execution_result(tenant_id, body.agent_id, gov_decision_id, "failure", provider_latency_ms)
        raise HTTPException(
            status_code=403,
            detail=gov_explanation or "LLM request blocked by governance policy.",
        )
    if gov_verdict in ("ESCALATE", "PAUSE"):
        _record_llm_feedback(tenant_id, body.agent_id, "incident", prediction)
        return V1LLMResponse(
            verdict="ESCALATE",
            content=None,
            oob_prediction=oob_dict,
            sequence_score=round(seq_score, 4),
            governance_latency_ms=governance_latency_ms,
            provider_response={"escalation_question": gov_question or gov_explanation},
            decision_record=gov_record,
            execution_token=gov_token,
        )

    try:
        verify_execution_token(gov_token or {}, tenant_id=tenant_id, action_type="llm.generate")
    except Exception as exc:
        logger.error("[v1/llm] execution token verification failed: %s", exc)
        raise HTTPException(status_code=403, detail="Valid EDON execution token required before provider forwarding")

    # ── 4. Forward to provider ─────────────────────────────────────────────────
    provider_key = (
        x_provider_key
        or (os.getenv("OPENAI_API_KEY") if body.provider == "openai" else None)
        or (os.getenv("ANTHROPIC_API_KEY") if body.provider == "anthropic" else None)
    )
    if not provider_key:
        raise HTTPException(
            status_code=400,
            detail="No provider API key. Pass X-Provider-Key header or set OPENAI_API_KEY / ANTHROPIC_API_KEY.",
        )

    provider_start = time.time()
    try:
        raw_response = await _call_provider(body, provider_key)
    except httpx.TimeoutException:
        _record_llm_feedback(tenant_id, body.agent_id, "oob", prediction)
        raise HTTPException(status_code=504, detail="Provider request timed out.")
    except httpx.HTTPStatusError as exc:
        _record_llm_feedback(tenant_id, body.agent_id, "oob", prediction)
        raise HTTPException(status_code=exc.response.status_code, detail=f"Provider error: {exc.response.text[:500]}")
    provider_latency_ms = int((time.time() - provider_start) * 1000)

    # ── 5. Scan output ─────────────────────────────────────────────────────────
    response_text = _extract_content(raw_response, body.provider)
    scan_result = filter_output(
        {"content": response_text},
        action_tool=_LLM_TOOL,
        action_op=_LLM_OP,
    )
    redacted = scan_result.verdict in ("REDACT", "BLOCK")
    final_content = scan_result.redacted_text if (redacted and scan_result.redacted_text) else response_text

    if scan_result.verdict == "BLOCK":
        _record_llm_feedback(tenant_id, body.agent_id, "blocked", prediction)
        return V1LLMResponse(
            verdict="BLOCK",
            content="[LLM response blocked by output governance policy]",
            findings=[{"category": f.category, "pattern": f.pattern_name} for f in scan_result.findings],
            redacted=True,
            oob_prediction=oob_dict,
            sequence_score=round(seq_score, 4),
            governance_latency_ms=governance_latency_ms,
            provider_latency_ms=provider_latency_ms,
            decision_record=gov_record,
            execution_token=gov_token,
        )

    # ── 6. Record outcome into fleet learning ──────────────────────────────────
    _record_llm_feedback(tenant_id, body.agent_id, "safe", prediction)
    _record_llm_execution_result(tenant_id, body.agent_id, gov_decision_id, "success", provider_latency_ms)

    return V1LLMResponse(
        verdict="ALLOW",
        content=final_content,
        findings=[{"category": f.category, "pattern": f.pattern_name} for f in scan_result.findings],
        redacted=redacted,
        provider_response=raw_response,
        oob_prediction=oob_dict,
        sequence_score=round(seq_score, 4),
        governance_latency_ms=governance_latency_ms,
        provider_latency_ms=provider_latency_ms,
        decision_record=gov_record,
        execution_token=gov_token,
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _record_llm_feedback(
    tenant_id: Optional[str],
    agent_id: str,
    label: str,
    prediction: Any,
) -> None:
    try:
        engine = get_fleet_learning_engine()
        engine.record_feedback(
            tenant_id=tenant_id,
            agent_id=agent_id,
            action_tool=_LLM_TOOL,
            action_op=_LLM_OP,
            label=label,
            predicted_risk=prediction.score if prediction else None,
            source="llm_proxy",
        )
        # Sequence bigram: record prev_action → llm.generate transition
        prev = prediction.prev_action if prediction else None
        if prev:
            engine.record_sequence_feedback(
                tenant_id=tenant_id,
                agent_id=agent_id,
                prev_tool=prev[0],
                prev_op=prev[1],
                curr_tool=_LLM_TOOL,
                curr_op=_LLM_OP,
                label=label,
                source="llm_proxy",
            )
    except Exception as _fb_err:
        logger.debug("[v1/llm] fleet learning feedback failed: %s", _fb_err)


async def _govern_input(
    tenant_id: Optional[str],
    agent_id: str,
    intent_id: Optional[str],
    stated_intent: Optional[str],
    model: str,
    conversation_context: str,
    oob_score: float,
    seq_score: float,
) -> tuple[str, str, str, str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Run the full conversation context through the governor."""
    try:
        from ..governor import EDONGovernor
        from ..schemas import Action, Tool, RiskLevel, ActionSource, IntentContract
        from ..persistence import get_db

        # Elevate estimated risk if OOB or sequence scores are high
        if oob_score >= 0.70 or seq_score >= 0.75:
            estimated_risk = RiskLevel.HIGH
        elif oob_score >= 0.45 or seq_score >= 0.50:
            estimated_risk = RiskLevel.MEDIUM
        else:
            estimated_risk = RiskLevel.LOW

        db = get_db()
        governor = EDONGovernor(db=db)
        action = Action(
            tool=Tool.CUSTOM,
            op=_LLM_OP,
            params={"conversation": conversation_context, "model": model},
            estimated_risk=estimated_risk,
            source=ActionSource.AGENT,
        )
        intent = IntentContract(
            objective=stated_intent or "LLM inference",
            scope={"custom": [_LLM_OP]},
            constraints={},
            risk_level=RiskLevel.MEDIUM,
            approved_by_user=True,
        )
        context: dict = {
            "agent_id": agent_id,
            "stated_intent": stated_intent or "",
            "prompt": conversation_context,
            "predicted_oob_risk": round(oob_score, 4),
            "sequence_drift_score": round(seq_score, 4),
        }
        if intent_id:
            context["intent_id"] = intent_id

        decision = governor.evaluate(action=action, intent=intent, context=context, tenant_id=tenant_id)
        verdict = decision.verdict.value if hasattr(decision.verdict, "value") else str(decision.verdict)
        from datetime import datetime, UTC
        created_at = datetime.now(UTC).isoformat()
        decision_id = f"dec-{action.id}-{created_at}"
        request_hash = hashlib.sha256(
            _json_stdlib.dumps(action.params, sort_keys=True).encode()
        ).hexdigest()
        context["request_hash"] = request_hash
        record = build_decision_record(
            decision_id=decision_id,
            tenant_id=tenant_id or "",
            actor_id=agent_id,
            agent_id=agent_id,
            action_type="llm.generate",
            risk_tier=estimated_risk.value.lower() if hasattr(estimated_risk, "value") else str(estimated_risk).lower(),
            verdict=verdict,
            context={
                **context,
                "data_class": "confidential",
                "connector_scope": ["llm.prompt.route", "llm.output.audit", "llm.action.authorize"],
            },
            policy_version=decision.policy_version,
            reason_code=decision.reason_code.value if decision.reason_code else None,
            issued_at=created_at,
            request_hash=request_hash,
        )
        execution_token = build_execution_token(record)
        try:
            db.save_audit_event(
                action=action.to_dict(),
                decision=decision.to_dict(),
                intent_id=intent_id,
                agent_id=agent_id,
                context={
                    **context,
                    "decision_record": record.to_dict(),
                    "execution_token_key_id": execution_token["key_id"],
                },
                customer_id=tenant_id,
                action_summary=f"{action.tool.value}.{action.op}",
                request_hash=request_hash,
                decision_id_override=decision_id,
                created_at_override=created_at,
            )
        except Exception as audit_err:
            logger.warning("[v1/llm] audit write failed: %s", audit_err)
            raise RuntimeError("Unable to persist governed LLM decision to audit trail") from audit_err
        return verdict, decision.explanation or "", decision.escalation_question or "", decision_id, record.to_dict(), execution_token
    except Exception as exc:
        # Fail-closed: governance errors must never grant access in a clinical/control-plane context.
        logger.error("[v1/llm] governance failed (fail-closed — blocking): %s", exc)
        return "BLOCK", "Governance error - request blocked for safety", "", "", None, None


def _record_llm_execution_result(
    tenant_id: Optional[str],
    agent_id: str,
    decision_id: str,
    outcome: str,
    latency_ms: int,
) -> None:
    if not decision_id:
        return
    try:
        from datetime import datetime, UTC
        from ..shadow.trace_capture import ActionResult, get_trace_store
        result = ActionResult.build(
            action_id=decision_id,
            agent_id=agent_id,
            tenant_id=tenant_id,
            action_type="llm.generate",
            outcome=outcome,
            latency_ms=max(0, latency_ms),
            result_summary=f"LLM provider outcome: {outcome}",
            executed_at=datetime.now(UTC).isoformat(),
        )
        get_trace_store().save_action_result(result)
    except Exception as exc:
        logger.debug("[v1/llm] execution receipt write failed: %s", exc)


async def _call_provider(body: V1LLMRequest, provider_key: str) -> dict:
    extra = body.extra or {}
    async with httpx.AsyncClient(timeout=60.0) as client:
        if body.provider == "openai":
            payload: dict = {
                "model": body.model,
                "messages": [m.model_dump() for m in body.messages],
                **extra,
            }
            if body.temperature is not None:
                payload["temperature"] = body.temperature
            if body.max_tokens is not None:
                payload["max_tokens"] = body.max_tokens
            resp = await client.post(
                _OPENAI_CHAT_URL,
                headers={"Authorization": f"Bearer {provider_key}", "Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

        # Anthropic
        payload = {
            "model": body.model,
            "messages": [m.model_dump() for m in body.messages],
            "max_tokens": body.max_tokens or 1024,
            **extra,
        }
        if body.temperature is not None:
            payload["temperature"] = body.temperature
        resp = await client.post(
            _ANTHROPIC_MESSAGES_URL,
            headers={
                "x-api-key": provider_key,
                "anthropic-version": _ANTHROPIC_VERSION,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


def _extract_content(raw: dict, provider: str) -> str:
    try:
        if provider == "openai":
            return raw["choices"][0]["message"]["content"] or ""
        blocks = raw.get("content", [])
        return " ".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    except (KeyError, IndexError, TypeError):
        return ""
