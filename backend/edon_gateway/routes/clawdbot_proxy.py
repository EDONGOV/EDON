"""Clawdbot connector proxy: /clawdbot/invoke and /edon/invoke.

Governs the request through the full EDON pipeline before forwarding to the
Clawdbot connector. /edon/invoke is an alias kept for backward-compat.
"""
from __future__ import annotations

import os
import time
import hashlib
import json as _json_stdlib
from datetime import datetime, UTC
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..schemas import Action, Tool, Verdict, ActionSource
from ..tenancy import get_request_tenant_id
from ..logging_config import get_logger
from ..services.governance import load_intent
from ..schemas.v1_action import V1ActionRequest
from ..preflight import PreflightContext, run_preflight

logger = get_logger(__name__)

router = APIRouter(tags=["clawdbot"])


class ClawdbotInvokeRequest(BaseModel):
    tool: str
    action: str = "json"
    args: Dict[str, Any] = {}
    sessionKey: Optional[str] = None
    decision_id: Optional[str] = None
    decision_bundle: Optional[Dict[str, Any]] = None
    credential_id: Optional[str] = Field(
        default=None,
        description="Optional Clawdbot credential_id to use for this invoke (tenant-scoped). "
        "If omitted, uses DEFAULT_CLAWDBOT_CREDENTIAL_ID.",
    )


class ClawdbotInvokeResponse(BaseModel):
    ok: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    edon_verdict: Optional[str] = None
    edon_explanation: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


@router.post("/edon/invoke", response_model=ClawdbotInvokeResponse)
async def edon_invoke_alias(
    http_request: Request,
    payload: ClawdbotInvokeRequest,
    x_agent_id: Optional[str] = Header(None, alias="X-Agent-ID"),
    x_edon_agent_id: Optional[str] = Header(None, alias="X-EDON-Agent-ID"),
    x_intent_id: Optional[str] = Header(None, alias="X-Intent-ID"),
):
    return await clawdbot_invoke_proxy(
        http_request=http_request,
        payload=payload,
        x_agent_id=x_agent_id,
        x_edon_agent_id=x_edon_agent_id,
        x_intent_id=x_intent_id,
    )


@router.post("/clawdbot/invoke", response_model=ClawdbotInvokeResponse)
async def clawdbot_invoke_proxy(
    http_request: Request,
    payload: ClawdbotInvokeRequest,
    x_agent_id: Optional[str] = Header(None, alias="X-Agent-ID"),
    x_edon_agent_id: Optional[str] = Header(None, alias="X-EDON-Agent-ID"),
    x_intent_id: Optional[str] = Header(None, alias="X-Intent-ID"),
):
    start = time.time()
    agent_id = x_edon_agent_id or x_agent_id or "clawdbot-agent"
    tenant_id = get_request_tenant_id(http_request)
    governor = http_request.app.state.governor
    db = http_request.app.state.db

    action = Action(
        tool=Tool.CLAWDBOT,
        op="invoke",
        params={
            "tool": payload.tool,
            "action": payload.action,
            "args": payload.args,
            "sessionKey": payload.sessionKey,
        },
        requested_at=datetime.now(UTC),
        source=ActionSource.CLAWDBOT,
        tags=["clawdbot-proxy"],
    )

    req_context = {"intent_id": x_intent_id, "source": "clawdbot"}
    _v1_req = V1ActionRequest(
        agent_id=agent_id,
        action_type="clawdbot.invoke",
        action_payload=dict(action.params),
        timestamp=datetime.now(UTC).isoformat(),
        context=req_context,
    )
    _pf_ctx = PreflightContext(
        req=_v1_req,
        tenant_id=tenant_id,
        action=action,
        action_params=action.params,
        db=db,
        start_time=start,
        req_context=req_context,
    )
    _pf_hard = run_preflight(_pf_ctx)
    if _pf_hard is not None:
        return ClawdbotInvokeResponse(
            ok=False,
            result=None,
            error=_pf_hard.decision_reason,
            edon_verdict=_pf_hard.decision,
            edon_explanation=_pf_hard.decision_reason,
        )
    req_context = _pf_ctx.req_context
    tenant_rules = _pf_ctx.tenant_rules

    # ── Governance ─────────────────────────────────────────────────────────────
    intent_contract, x_intent_id = load_intent(db, x_intent_id, tenant_id)
    try:
        decision = governor.evaluate(
            action=action,
            intent=intent_contract,
            context={"agent_id": agent_id, "source": "clawdbot", **req_context},
            tenant_rules=tenant_rules,
            tenant_id=tenant_id,
        )
    except Exception as e:
        logger.exception("Decision evaluation failed")
        return ClawdbotInvokeResponse(
            ok=False,
            result=None,
            error=str(e),
            edon_verdict=Verdict.ERROR.value,
            edon_explanation="Decision engine error",
        )

    # ── Persist decision + audit ────────────────────────────────────────────────
    persist_decisions = (
        os.getenv("EDON_PERSIST_DECISIONS", "true").strip().lower() in ("true", "1", "yes")
    )
    decision_id = f"dec-{action.id}-{datetime.now(UTC).isoformat()}"
    if not persist_decisions:
        logger.warning(
            "EDON_PERSIST_DECISIONS is disabled; clawdbot invoke audit records will not be persisted"
        )
    else:
        try:
            _created_at = datetime.now(UTC).isoformat()
            decision_id = f"dec-{action.id}-{_created_at}"
            _request_hash = hashlib.sha256(
                _json_stdlib.dumps(action.params, sort_keys=True).encode()
            ).hexdigest()
            payload_dict = payload.model_dump()
            stated_intent = payload_dict.get("stated_intent") or payload_dict.get("intent")
            user_message = payload_dict.get("user_message") or payload_dict.get("prompt")
            decision_id = db.save_audit_event(
                action=action.to_dict(),
                decision=decision.to_dict(),
                intent_id=x_intent_id,
                agent_id=agent_id,
                context={
                    "agent_id": agent_id,
                    "source": "clawdbot",
                    "stated_intent": stated_intent,
                    "user_message": user_message,
                    "request_hash": _request_hash,
                    **req_context,
                },
                customer_id=tenant_id,
                stated_intent=stated_intent,
                user_message=user_message,
                action_summary=f"{action.tool.value}.{action.op}",
                policy_rule_id=decision.policy_rule_id or (decision.meta or {}).get("policy_rule_id"),
                request_hash=_request_hash,
                decision_id_override=decision_id,
                created_at_override=_created_at,
            )
        except Exception as e:
            logger.exception("Failed to persist decision/audit for clawdbot invoke")
            return ClawdbotInvokeResponse(
                ok=False,
                result=None,
                error="Internal error persisting audit record.",
                edon_verdict=decision.verdict.value,
                edon_explanation=decision.explanation or "Decision recorded but DB write failed",
            )

    # ── Enforce verdict ─────────────────────────────────────────────────────────
    if decision.verdict not in (Verdict.ALLOW, Verdict.DEGRADE):
        return ClawdbotInvokeResponse(
            ok=False,
            result=None,
            error=decision.explanation or f"Blocked: {decision.verdict.value}",
            edon_verdict=decision.verdict.value,
            edon_explanation=decision.explanation,
        )

    # ── Execute ─────────────────────────────────────────────────────────────────
    from ..config import config as app_config

    credential_id = payload.credential_id or app_config.DEFAULT_CLAWDBOT_CREDENTIAL_ID
    _is_dev = (
        os.getenv("ENVIRONMENT") != "production" and os.getenv("EDON_ENV") != "production"
    )

    try:
        from ..connectors.clawdbot_connector import ClawdbotConnector

        connector = ClawdbotConnector(credential_id=credential_id, tenant_id=tenant_id)
        result = connector.invoke(
            tool=payload.tool,
            action=payload.action,
            args=payload.args,
            sessionKey=payload.sessionKey,
        )
        try:
            from ..shadow.trace_capture import ActionResult, get_trace_store
            _result = ActionResult.build(
                action_id=decision_id,
                agent_id=agent_id,
                tenant_id=tenant_id,
                action_type="clawdbot.invoke",
                outcome="success" if result.get("success") else "failure",
                latency_ms=int((time.time() - start) * 1000),
                error=None if result.get("success") else str(result.get("error", ""))[:1000],
                result_summary="Clawdbot connector completed",
                executed_at=datetime.now(UTC).isoformat(),
            )
            get_trace_store().save_action_result(_result)
        except Exception as _receipt_err:
            logger.warning("[clawdbot] execution receipt write failed: %s", _receipt_err)

        _details = {"used_credential_id": credential_id} if _is_dev else None

        if result.get("success"):
            return ClawdbotInvokeResponse(
                ok=True,
                result=result.get("result", {}),
                edon_verdict=decision.verdict.value,
                edon_explanation=decision.explanation,
                details=_details,
            )

        if result.get("downstream_unavailable"):
            body = ClawdbotInvokeResponse(
                ok=False,
                error=result.get("error", "Unknown Clawdbot execution error"),
                edon_verdict=Verdict.ERROR.value,
                edon_explanation="Clawdbot execution failed",
                details=_details,
            )
            return JSONResponse(status_code=503, content=body.model_dump())

        return ClawdbotInvokeResponse(
            ok=False,
            error=result.get("error", "Unknown Clawdbot execution error"),
            edon_verdict=Verdict.ERROR.value,
            edon_explanation="Clawdbot execution failed",
            details=_details,
        )
    except Exception as e:
        logger.error("Clawdbot proxy error", exc_info=True)
        try:
            from ..shadow.trace_capture import ActionResult, get_trace_store
            _result = ActionResult.build(
                action_id=decision_id,
                agent_id=agent_id,
                tenant_id=tenant_id,
                action_type="clawdbot.invoke",
                outcome="failure",
                latency_ms=int((time.time() - start) * 1000),
                error=str(e)[:1000],
                result_summary="Clawdbot connector raised an exception",
                executed_at=datetime.now(UTC).isoformat(),
            )
            get_trace_store().save_action_result(_result)
        except Exception as _receipt_err:
            logger.warning("[clawdbot] failure receipt write failed: %s", _receipt_err)
        _details = {"used_credential_id": credential_id} if _is_dev else None
        error_msg = str(e)
        if "HTTP error 401" in error_msg:
            body = ClawdbotInvokeResponse(
                ok=False,
                error="Execution failed: authentication error.",
                edon_verdict=Verdict.ERROR.value,
                edon_explanation="Internal execution error",
                details=_details,
            )
            return JSONResponse(status_code=401, content=body.model_dump())
        return ClawdbotInvokeResponse(
            ok=False,
            error="Execution failed. Please try again or contact support.",
            edon_verdict=Verdict.ERROR.value,
            edon_explanation="Internal execution error",
            details=_details,
        )
