"""Routes for adaptive fleet learning and predictive governance."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..fleet_learning import get_fleet_learning_engine
from ..persistence import get_db
from ..tenancy import get_request_tenant_id


router = APIRouter(prefix="/learning", tags=["learning"])


class PredictRequest(BaseModel):
    agent_id: str = Field(..., min_length=1)
    action_type: str = Field(..., min_length=3, description="Format: tool.operation")
    estimated_risk: str = Field(default="low", description="low|medium|high|critical")


class FeedbackRequest(BaseModel):
    agent_id: Optional[str] = None
    action_type: str = Field(..., min_length=3, description="Format: tool.operation")
    label: str = Field(..., description="safe|oob|incident|blocked")
    predicted_risk: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    oob_type: Optional[str] = None
    notes: Optional[str] = None
    source: str = Field(default="operator")


class FederatedOptInRequest(BaseModel):
    opt_in: bool


def _parse_action_type(action_type: str) -> tuple[str, str]:
    parts = action_type.split(".", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError("Invalid action_type. Expected format 'tool.operation'")
    return parts[0].strip().lower(), parts[1].strip().lower()


@router.post("/predict")
async def predict_oob_risk(request: Request, body: PredictRequest) -> Dict[str, Any]:
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        action_tool, action_op = _parse_action_type(body.action_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    db = get_db()
    engine = get_fleet_learning_engine()
    prediction = engine.predict_action(
        db=db,
        tenant_id=tenant_id,
        agent_id=body.agent_id,
        action_tool=action_tool,
        action_op=action_op,
        estimated_risk=body.estimated_risk,
    )
    return {
        "tenant_id": tenant_id,
        "agent_id": body.agent_id,
        "action_type": body.action_type,
        "prediction": prediction.to_dict(),
    }


@router.post("/feedback")
async def record_feedback(request: Request, body: FeedbackRequest) -> Dict[str, Any]:
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        action_tool, action_op = _parse_action_type(body.action_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    normalized_label = body.label.strip().lower()
    if normalized_label not in {"safe", "oob", "incident", "blocked"}:
        raise HTTPException(status_code=400, detail="label must be one of: safe|oob|incident|blocked")

    engine = get_fleet_learning_engine()
    engine.record_feedback(
        tenant_id=tenant_id,
        agent_id=body.agent_id,
        action_tool=action_tool,
        action_op=action_op,
        predicted_risk=body.predicted_risk,
        label=normalized_label,
        oob_type=body.oob_type,
        notes=body.notes,
        source=body.source,
    )
    return {"ok": True}


@router.post("/federated-opt-in")
async def set_federated_opt_in(request: Request, body: FederatedOptInRequest) -> Dict[str, Any]:
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    db = get_db()
    engine = get_fleet_learning_engine()
    engine.set_federated_opt_in(db=db, tenant_id=tenant_id, opt_in=body.opt_in)
    return {"tenant_id": tenant_id, "federated_opt_in": body.opt_in}


@router.get("/model/summary")
async def get_model_summary(request: Request) -> Dict[str, Any]:
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    engine = get_fleet_learning_engine()
    return engine.model_summary(tenant_id=tenant_id)

