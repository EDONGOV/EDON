"""Legacy /decisions/* query endpoints.

These predate the /audit/* router. Kept at their original paths for
backward-compat with any SDK clients using them directly.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..governance_records import (
    build_decision_record,
    build_execution_token,
    build_policy_replay_bundle,
)
from ..tenancy import get_request_tenant_id

router = APIRouter(tags=["decisions"])


class DecisionQueryResponse(BaseModel):
    decisions: List[Dict[str, Any]]
    total: int
    limit: int


def _get_enriched_decision_row(request: Request, decision_id: str) -> tuple[dict, dict]:
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    db = request.app.state.db
    decision = db.get_decision(decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")
    decision_row = decision
    action_id = decision.get("action_id")
    if action_id:
        try:
            enriched = db.query_decisions(action_id=action_id, customer_id=tenant_id, limit=1)
            if enriched:
                decision_row = enriched[0]
            else:
                raise HTTPException(status_code=404, detail="Decision not found")
        except Exception:
            raise
    return decision, decision_row


def _build_canonical_record_from_row(decision_id: str, decision: dict, decision_row: dict) -> dict:
    action = decision_row.get("action") or {}
    context = dict(decision_row.get("context") or {})
    if isinstance(context, str):
        try:
            import json as _json
            context = _json.loads(context)
        except Exception:
            context = {}
    tenant_id = (
        decision_row.get("customer_id")
        or decision_row.get("tenant_id")
        or context.get("tenant_id")
        or "unknown"
    )
    agent_id = decision_row.get("agent_id") or context.get("agent_id") or ""
    actor_id = context.get("actor_id") or context.get("user_id") or agent_id or ""
    action_type = decision_row.get("action_summary") or ""
    if not action_type and action:
        tool = action.get("tool") or ""
        op = action.get("op") or ""
        action_type = f"{tool}.{op}".strip(".")
    if not action_type:
        action_type = context.get("action_type") or "unknown.unknown"
    risk_tier = (
        action.get("computed_risk")
        or action.get("estimated_risk")
        or context.get("risk_tier")
        or "low"
    )
    connector_scope = context.get("connector_scope") or action.get("connector_scope") or []
    verdict = str(decision_row.get("verdict") or decision.get("verdict") or "")
    approval_state = context.get("approval_state") or (
        "approved" if verdict == "ALLOW" else
        "pending_review" if verdict in {"ESCALATE", "PAUSE"} else
        "blocked" if verdict == "BLOCK" else
        "degraded" if verdict == "DEGRADE" else
        "unknown"
    )
    rollback_mode = context.get("rollback_mode") or "standard"
    record = build_decision_record(
        decision_id=decision_id,
        tenant_id=str(tenant_id),
        actor_id=str(actor_id),
        agent_id=str(agent_id),
        action_type=str(action_type),
        risk_tier=str(risk_tier),
        verdict=verdict,
        context={
            **context,
            "data_class": context.get("data_class") or action.get("data_class") or "internal",
            "connector_scope": connector_scope,
            "approval_state": approval_state,
            "rollback_mode": rollback_mode,
            "actor_role": context.get("actor_role"),
            "approval_chain": context.get("approval_chain") or context.get("approvals") or [],
            "request_hash": decision_row.get("request_hash") or context.get("request_hash"),
            "policy_snapshot_hash": context.get("policy_snapshot_hash"),
            "break_glass": context.get("break_glass"),
            "break_glass_reason": context.get("break_glass_reason"),
            "kill_switch_scope": context.get("kill_switch_scope"),
            "kill_switch_target": context.get("kill_switch_target"),
        },
        policy_version=str(decision_row.get("policy_version") or decision.get("policy_version") or ""),
        reason_code=str(decision_row.get("reason_code") or decision.get("reason_code") or ""),
        issued_at=str(decision_row.get("created_at") or decision.get("created_at") or ""),
        request_hash=decision_row.get("request_hash") or context.get("request_hash"),
        audit_id=decision_row.get("id") or decision_row.get("audit_id") or decision_row.get("action_id"),
    )
    return record.to_dict()


@router.get("/decisions/query", response_model=DecisionQueryResponse)
async def query_decisions(
    request: Request,
    action_id: Optional[str] = None,
    verdict: Optional[str] = None,
    intent_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    limit: int = 100,
):
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 1000")
    db = request.app.state.db
    decisions = db.query_decisions(
        action_id=action_id,
        verdict=verdict,
        intent_id=intent_id,
        agent_id=agent_id,
        customer_id=tenant_id,
        limit=limit,
    )
    return DecisionQueryResponse(decisions=decisions, total=len(decisions), limit=limit)


@router.get("/decisions/{decision_id}")
async def get_decision(decision_id: str, request: Request):
    decision, _decision_row = _get_enriched_decision_row(request, decision_id)
    return decision


@router.get("/decisions/{decision_id}/record")
async def get_decision_record(decision_id: str, request: Request):
    decision, decision_row = _get_enriched_decision_row(request, decision_id)
    return {
        "decision_record": _build_canonical_record_from_row(decision_id, decision, decision_row),
    }


@router.get("/decisions/{decision_id}/execution-token")
async def get_decision_execution_token(decision_id: str, request: Request):
    decision, decision_row = _get_enriched_decision_row(request, decision_id)
    record_dict = _build_canonical_record_from_row(decision_id, decision, decision_row)
    from ..governance_records import DecisionRecord

    record = DecisionRecord(**record_dict)
    record.signature = record_dict.get("signature", record.signature)
    token = build_execution_token(record)
    return {
        "decision_record": record.to_dict(),
        "execution_token": token,
    }


@router.get("/decisions/{decision_id}/replay")
async def get_decision_replay(decision_id: str, request: Request):
    decision, decision_row = _get_enriched_decision_row(request, decision_id)
    record_dict = _build_canonical_record_from_row(decision_id, decision, decision_row)
    from ..governance_records import DecisionRecord

    record = DecisionRecord(**record_dict)
    record.signature = record_dict.get("signature", record.signature)
    return {
        "replay": build_policy_replay_bundle(
            record=record,
            decision_row=decision_row,
        )
    }
