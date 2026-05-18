"""POST /execute — evaluate + execute an action through governance.

Governance evaluation happens first (identical to /v1/action). Only if the
verdict is ALLOW does the gateway actually invoke the appropriate connector.
Credentials live in the gateway; agents never touch them directly.
"""

import time
import hashlib
import json as _json_stdlib
from datetime import datetime, UTC
from typing import Any, Optional

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

from ..schemas import Action, Tool, ActionSource, Verdict, ReasonCode
from ..persistence import get_db
from ..tenancy import get_request_tenant_id
from ..logging_config import get_logger
from ..fleet_learning import get_fleet_learning_engine
from ..services.governance import load_intent
from ..schemas.v1_action import V1ActionRequest
from ..preflight import PreflightContext, run_preflight

logger = get_logger(__name__)

router = APIRouter(prefix="/execute", tags=["execute"])


# ── Request / Response models ──────────────────────────────────────────────────

class ExecuteRequest(BaseModel):
    agent_id: str = Field(..., description="Agent identifier")
    action_type: str = Field(..., description="tool.operation e.g. email.send")
    action_payload: dict = Field(default_factory=dict, description="Tool-specific parameters")
    timestamp: str = Field(..., description="ISO-8601 request timestamp")
    context: dict = Field(default_factory=dict, description="Optional context (intent_id, etc.)")


class ExecuteResponse(BaseModel):
    action_id: str
    decision: str
    decision_reason: str
    executed: bool = False
    execution_result: Optional[Any] = None
    execution_error: Optional[str] = None
    processing_latency_ms: int
    reason_code: Optional[str] = None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_action_type(action_type: str) -> tuple[str, str]:
    parts = action_type.split(".", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid action_type '{action_type}'. Expected tool.operation")
    return parts[0], parts[1]


def _map_verdict(verdict: str) -> str:
    if verdict == "ESCALATE":
        return "HUMAN_REQUIRED"
    if verdict == "ERROR":
        return "BLOCK"
    return verdict


def _run_connector(tool: str, op: str, params: dict) -> Any:
    """Dispatch to the appropriate connector after ALLOW verdict.

    Each connector has its own method API; we route by (tool, op) and pass
    params as keyword arguments where the connector method signature allows it.
    """
    tool = tool.lower()

    if tool == "email":
        from ..connectors.email_connector import email_connector
        # EmailConnector.send(recipients, subject, body, ...)
        return email_connector.send(**params)

    if tool == "filesystem":
        from ..connectors.filesystem_connector import filesystem_connector
        method = getattr(filesystem_connector, f"{op}_file", None) or getattr(filesystem_connector, op, None)
        if method is None:
            raise NotImplementedError(f"filesystem connector has no op '{op}'")
        return method(**params)

    if tool == "brave_search":
        from ..connectors.brave_search_connector import BraveSearchConnector
        return BraveSearchConnector().search(**params)

    if tool == "memory":
        from ..connectors.memory_connector import MemoryConnector
        conn = MemoryConnector()
        method = getattr(conn, op, None)
        if method is None:
            raise NotImplementedError(f"memory connector has no op '{op}'")
        return method(**params)

    if tool in ("agent", "clawdbot"):
        from ..connectors.clawdbot_connector import get_clawdbot_connector
        connector = get_clawdbot_connector()
        if connector is None:
            raise RuntimeError("Agent/Clawdbot connector not configured")
        return connector.invoke(tool=params.get("tool", op), action=op, args=params)

    logger.warning("[execute] No connector registered for tool '%s'", tool)
    return {
        "status": "error",
        "reason": "connector_not_registered",
        "connector_type": tool,
        "message": (
            f"No connector registered for tool '{tool}'. "
            "Register a backend via /agents/register with an endpoint in metadata, "
            "or use a built-in connector (email, filesystem, memory, brave_search, agent)."
        ),
    }


# ── Route ──────────────────────────────────────────────────────────────────────

@router.post("", response_model=ExecuteResponse)
async def execute_action(request: Request, req: ExecuteRequest):
    """Evaluate and (if ALLOW) execute an agent action.

    The full governor pipeline runs first — identical to /v1/action. The
    connector is only invoked when the verdict is ALLOW. The response includes
    both the governance decision and the connector's execution result.
    """
    start = time.time()

    if not req.agent_id.strip():
        raise HTTPException(status_code=400, detail="agent_id is required")
    if not req.action_type.strip():
        raise HTTPException(status_code=400, detail="action_type is required")

    try:
        tool_str, operation = _parse_action_type(req.action_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        tool = Tool(tool_str.lower())
        custom_tool_name = None
    except ValueError:
        tool = Tool.CUSTOM  # type: ignore[attr-defined]
        custom_tool_name = tool_str.lower()

    try:
        requested_at = datetime.fromisoformat(req.timestamp.replace("Z", "+00:00"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid timestamp: {exc}")

    tenant_id = get_request_tenant_id(request)
    db = get_db()

    # ── Load intent ─────────────────────────────────────────────────────────
    intent_id = req.context.get("intent_id")
    intent_contract, intent_id = load_intent(db, intent_id, tenant_id)

    # ── Build Action ────────────────────────────────────────────────────────
    action_params = dict(req.action_payload)
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

    req_context = dict(req.context)

    # ── Auto session_id ──────────────────────────────────────────────────────
    if "session_id" not in req_context:
        hour_bucket = datetime.now(UTC).strftime("%Y%m%d%H")
        req_context["session_id"] = f"auto:{req.agent_id}:{hour_bucket}"

    _v1_req = V1ActionRequest(
        agent_id=req.agent_id,
        action_type=req.action_type,
        action_payload=req.action_payload,
        timestamp=req.timestamp,
        context=req_context,
    )
    _pf_ctx = PreflightContext(
        req=_v1_req,
        tenant_id=tenant_id,
        action=action,
        action_params=action_params,
        db=db,
        start_time=start,
        req_context=req_context,
    )
    _pf_hard = run_preflight(_pf_ctx)
    if _pf_hard is not None:
        return ExecuteResponse(
            action_id=_pf_hard.action_id,
            decision=_map_verdict(_pf_hard.decision),
            decision_reason=_pf_hard.decision_reason,
            executed=False,
            processing_latency_ms=_pf_hard.processing_latency_ms,
            reason_code=_pf_hard.reason_code,
        )
    req_context = _pf_ctx.req_context
    tenant_rules = _pf_ctx.tenant_rules

    # ── Tenant policy rules ─────────────────────────────────────────────────
    if tenant_id and not tenant_rules:
        try:
            tenant_rules = db.get_policy_rules(tenant_id, enabled_only=True)
        except Exception as exc:
            logger.warning("Failed to load tenant rules: %s", exc)

    # ── Governor evaluation ─────────────────────────────────────────────────
    governor = getattr(request.app.state, "governor", None)
    if governor is None:
        from ..governor import EDONGovernor
        governor = EDONGovernor(db=db)

    try:
        _policy_eval_start = time.time()
        decision = governor.evaluate(
            action=action,
            intent=intent_contract,
            context={"agent_id": req.agent_id, **req_context},
            tenant_rules=tenant_rules,
            tenant_id=tenant_id,
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
    except Exception as exc:
        logger.exception("Governor error in /execute: %s", exc)
        raise HTTPException(status_code=500, detail="Internal error during action evaluation")

    latency_ms = int((time.time() - start) * 1000)
    verdict_str = decision.verdict.value
    _created_at = datetime.now(UTC).isoformat()
    decision_id = f"dec-{action.id}-{_created_at}"
    _request_hash = hashlib.sha256(
        _json_stdlib.dumps(action_params, sort_keys=True).encode()
    ).hexdigest()

    # ── Audit ───────────────────────────────────────────────────────────────
    try:
        decision_id = db.save_audit_event(
            action=action.to_dict(),
            decision=decision.to_dict(),
            intent_id=intent_id,
            agent_id=req.agent_id,
            context={"agent_id": req.agent_id, "tenant_id": tenant_id, "request_hash": _request_hash, **req_context},
            customer_id=tenant_id,
            processing_latency_ms=latency_ms,
            action_summary=f"{action.tool.value}.{action.op}",
            request_hash=_request_hash,
            decision_id_override=decision_id,
            created_at_override=_created_at,
        )
    except Exception as exc:
        logger.exception("Audit write failed in /execute: %s", exc)
        decision_id = f"exec-{action.id}"

    # ── Auto-label for fleet learning ───────────────────────────────────────
    try:
        label = "safe" if verdict_str == "ALLOW" else ("blocked" if verdict_str in {"BLOCK", "ERROR"} else "incident")
        get_fleet_learning_engine().record_feedback(
            tenant_id=tenant_id,
            agent_id=req.agent_id,
            action_tool=action.tool.value,
            action_op=action.op,
            label=label,
            source="auto_execute",
            notes=f"decision={verdict_str}",
        )
    except Exception:
        pass

    # ── Execute connector (only on ALLOW) ───────────────────────────────────
    executed = False
    execution_result = None
    execution_error = None

    if verdict_str == "ALLOW":
        try:
            execution_result = _run_connector(tool_str, operation, action_params)
            executed = True
            try:
                from ..shadow.trace_capture import ActionResult, get_trace_store
                _result = ActionResult.build(
                    action_id=decision_id,
                    agent_id=req.agent_id,
                    tenant_id=tenant_id,
                    action_type=req.action_type,
                    outcome="success",
                    latency_ms=max(0, int((time.time() - start) * 1000) - latency_ms),
                    result_summary="Connector executed successfully",
                    executed_at=datetime.now(UTC).isoformat(),
                )
                get_trace_store().save_action_result(_result)
            except Exception as _receipt_err:
                logger.warning("[/execute] execution receipt write failed: %s", _receipt_err)
            logger.info("[/execute] ALLOW+executed agent=%s action=%s", req.agent_id, req.action_type)
            # ── Scan tool output for indirect injection ──────────────────────
            try:
                from ..security.prompt_injection import scan_output
                _out_injection = scan_output(execution_result)
                if _out_injection:
                    logger.warning(
                        "[/execute] Indirect injection in tool output: pattern=%s field=%s agent=%s",
                        _out_injection.pattern_name, _out_injection.field, req.agent_id,
                    )
                    req_context["output_injection_detected"] = _out_injection.to_dict()
            except Exception:
                pass
        except NotImplementedError as exc:
            execution_error = str(exc)
            logger.info("[/execute] ALLOW but no connector for %s: %s", tool_str, exc)
        except Exception as exc:
            execution_error = str(exc)
            try:
                from ..shadow.trace_capture import ActionResult, get_trace_store
                _result = ActionResult.build(
                    action_id=decision_id,
                    agent_id=req.agent_id,
                    tenant_id=tenant_id,
                    action_type=req.action_type,
                    outcome="failure",
                    latency_ms=max(0, int((time.time() - start) * 1000) - latency_ms),
                    error=execution_error[:1000],
                    result_summary="Connector execution failed",
                    executed_at=datetime.now(UTC).isoformat(),
                )
                get_trace_store().save_action_result(_result)
            except Exception as _receipt_err:
                logger.warning("[/execute] failure receipt write failed: %s", _receipt_err)
            logger.warning("[/execute] Connector error for %s: %s", req.action_type, exc)

    return ExecuteResponse(
        action_id=decision_id,
        decision=_map_verdict(verdict_str),
        decision_reason=decision.explanation,
        executed=executed,
        execution_result=execution_result,
        execution_error=execution_error,
        processing_latency_ms=latency_ms,
        reason_code=decision.reason_code.value if decision.reason_code else None,
    )
