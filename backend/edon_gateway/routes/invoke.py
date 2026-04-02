"""POST /agent/invoke — proxy any registered agent through governance.

Any backend (not just Clawdbot) can be invoked through this endpoint.
The governor evaluates the action first; if ALLOW the request is forwarded
to the registered agent's endpoint with the gateway's credentials.
"""

import time
import uuid
from datetime import datetime, UTC
from typing import Any, Optional

import requests as http_requests
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

from ..schemas import Action, IntentContract, Tool, RiskLevel, ActionSource
from ..persistence import get_db
from ..tenancy import get_request_tenant_id
from ..logging_config import get_logger
from ..fleet_learning import get_fleet_learning_engine

logger = get_logger(__name__)

router = APIRouter(prefix="/agent", tags=["agent-invoke"])


# ── Request / Response models ──────────────────────────────────────────────────

class AgentInvokeRequest(BaseModel):
    agent_id: str = Field(..., description="Registered agent ID to invoke")
    action_type: str = Field(..., description="tool.operation e.g. agent.run")
    action_payload: dict = Field(default_factory=dict, description="Payload forwarded to the agent backend")
    timestamp: str = Field(..., description="ISO-8601 request timestamp")
    context: dict = Field(default_factory=dict, description="Governance context (intent_id, etc.)")


class AgentInvokeResponse(BaseModel):
    action_id: str
    decision: str
    decision_reason: str
    agent_response: Optional[Any] = None
    forwarded: bool = False
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


def _forward_to_agent(agent_row: dict, action_type: str, payload: dict, timeout: int = 15) -> Any:
    """Forward request to the agent's registered endpoint."""
    endpoint = (agent_row.get("metadata") or {}).get("endpoint")
    if not endpoint:
        raise ValueError(f"Agent '{agent_row['agent_id']}' has no registered endpoint in metadata")

    headers = {"Content-Type": "application/json"}
    # Inject agent secret/token if stored in metadata
    agent_token = (agent_row.get("metadata") or {}).get("token")
    if agent_token:
        headers["Authorization"] = f"Bearer {agent_token}"

    resp = http_requests.post(
        endpoint,
        json={"action_type": action_type, "payload": payload},
        headers=headers,
        timeout=timeout,
    )
    resp.raise_for_status()
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}


# ── Route ──────────────────────────────────────────────────────────────────────

@router.post("/invoke", response_model=AgentInvokeResponse)
async def invoke_agent(request: Request, req: AgentInvokeRequest):
    """Evaluate governance then forward to any registered agent backend.

    Looks up the agent in the registry to find its endpoint. The full governor
    pipeline runs first — same as /v1/action. Only on ALLOW is the request
    forwarded. The governance decision and agent response are both returned.
    """
    start = time.time()

    if not req.agent_id.strip():
        raise HTTPException(status_code=400, detail="agent_id is required")

    try:
        tool_str, operation = _parse_action_type(req.action_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        requested_at = datetime.fromisoformat(req.timestamp.replace("Z", "+00:00"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid timestamp: {exc}")

    tenant_id = get_request_tenant_id(request)
    db = get_db()

    # ── Look up registered agent ────────────────────────────────────────────
    agent_row = db.get_agent(req.agent_id, tenant_id)
    if not agent_row:
        raise HTTPException(status_code=404, detail=f"Agent not found: {req.agent_id}")

    if agent_row.get("status") == "paused":
        raise HTTPException(status_code=403, detail=f"Agent '{req.agent_id}' is paused")

    # ── Load intent ─────────────────────────────────────────────────────────
    intent_id = req.context.get("intent_id")
    intent_contract = None

    if intent_id:
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
        except Exception as exc:
            logger.warning("Failed to load intent %s: %s", intent_id, exc)

    if not intent_contract:
        try:
            active = db.get_active_policy_preset()
            if active and active.get("preset_name"):
                from ..policy_packs import get_policy_pack
                pack = get_policy_pack(active["preset_name"])
                d = pack.to_intent_dict()
                intent_contract = IntentContract(
                    objective=d["objective"],
                    scope=d["scope"],
                    constraints=d.get("constraints", {}),
                    risk_level=RiskLevel(d.get("risk_level", "LOW")),
                    approved_by_user=bool(d.get("approved_by_user", False)),
                )
        except Exception as exc:
            logger.warning("Failed to load active preset: %s", exc)

    if not intent_contract:
        intent_contract = IntentContract(
            objective="Default intent",
            scope={},
            constraints={},
            risk_level=RiskLevel.MEDIUM,
            approved_by_user=False,
        )

    # ── Build Action ────────────────────────────────────────────────────────
    try:
        tool = Tool(tool_str.lower())
    except ValueError:
        tool = Tool.AGENT  # type: ignore[attr-defined]

    action = Action(
        tool=tool,
        op=operation,
        params=dict(req.action_payload),
        requested_at=requested_at,
        source=ActionSource.AGENT,
        tags=[],
    )

    # ── Tenant policy rules ─────────────────────────────────────────────────
    tenant_rules = []
    if tenant_id:
        try:
            tenant_rules = db.get_policy_rules(tenant_id, enabled_only=True)
        except Exception as exc:
            logger.warning("Failed to load tenant rules: %s", exc)

    # ── Governor evaluation ─────────────────────────────────────────────────
    governor = getattr(request.app.state, "governor", None)
    if governor is None:
        from ..governor import EDONGovernor
        governor = EDONGovernor(db=db)

    req_context = dict(req.context)

    # ── Auto session_id ──────────────────────────────────────────────────────
    if "session_id" not in req_context:
        hour_bucket = datetime.now(UTC).strftime("%Y%m%d%H")
        req_context["session_id"] = f"auto:{req.agent_id}:{hour_bucket}"

    try:
        decision = governor.evaluate(
            action=action,
            intent=intent_contract,
            context={"agent_id": req.agent_id, "tenant_id": tenant_id, **req_context},
            tenant_rules=tenant_rules,
        )
    except Exception as exc:
        logger.exception("Governor error in /agent/invoke: %s", exc)
        raise HTTPException(status_code=500, detail="Internal error during action evaluation")

    latency_ms = int((time.time() - start) * 1000)
    verdict_str = decision.verdict.value

    # ── Audit ───────────────────────────────────────────────────────────────
    try:
        decision_id = db.save_audit_event(
            action=action.to_dict(),
            decision=decision.to_dict(),
            intent_id=intent_id,
            agent_id=req.agent_id,
            context={"agent_id": req.agent_id, "tenant_id": tenant_id, **req_context},
            customer_id=tenant_id,
            processing_latency_ms=latency_ms,
            action_summary=f"{action.tool.value}.{action.op}",
        )
    except Exception as exc:
        logger.exception("Audit write failed in /agent/invoke: %s", exc)
        decision_id = f"invoke-{action.id}"

    # ── Auto-label for fleet learning ───────────────────────────────────────
    try:
        label = "safe" if verdict_str == "ALLOW" else ("blocked" if verdict_str in {"BLOCK", "ERROR"} else "incident")
        get_fleet_learning_engine().record_feedback(
            tenant_id=tenant_id,
            agent_id=req.agent_id,
            action_tool=action.tool.value,
            action_op=action.op,
            label=label,
            source="auto_invoke",
            notes=f"decision={verdict_str}",
        )
    except Exception:
        pass

    # ── Forward to agent backend (only on ALLOW) ────────────────────────────
    forwarded = False
    agent_response = None

    if verdict_str == "ALLOW":
        try:
            agent_response = _forward_to_agent(agent_row, req.action_type, req.action_payload)
            forwarded = True
            logger.info("[/agent/invoke] ALLOW+forwarded agent=%s action=%s", req.agent_id, req.action_type)
            # ── Scan agent response for indirect injection ───────────────────
            try:
                from ..security.prompt_injection import scan_output
                _out_injection = scan_output(agent_response)
                if _out_injection:
                    logger.warning(
                        "[/agent/invoke] Indirect injection in agent response: pattern=%s field=%s agent=%s",
                        _out_injection.pattern_name, _out_injection.field, req.agent_id,
                    )
                    req_context["output_injection_detected"] = _out_injection.to_dict()
            except Exception:
                pass
        except ValueError as exc:
            # No endpoint registered — ALLOW but can't forward
            agent_response = {"warning": str(exc)}
            logger.info("[/agent/invoke] ALLOW but no endpoint for %s: %s", req.agent_id, exc)
        except Exception as exc:
            agent_response = {"error": str(exc)}
            logger.warning("[/agent/invoke] Forward error for %s: %s", req.agent_id, exc)

    return AgentInvokeResponse(
        action_id=decision_id,
        decision=_map_verdict(verdict_str),
        decision_reason=decision.explanation,
        agent_response=agent_response,
        forwarded=forwarded,
        processing_latency_ms=latency_ms,
        reason_code=decision.reason_code.value if decision.reason_code else None,
    )
