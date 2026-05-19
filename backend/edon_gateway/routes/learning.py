"""Routes for adaptive fleet learning and predictive governance."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

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


@router.get("/precision")
async def get_precision_stats(request: Request) -> Dict[str, Any]:
    """Return per-tool.op block precision (what fraction of blocks were correct).

    Requires operators to submit 'false_positive' labels via POST /learning/feedback
    when a block was wrong. Without those corrections the precision is unknown (1.0).
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    engine = get_fleet_learning_engine()
    stats = engine.precision_stats(tenant_id=tenant_id)
    return {
        "tenant_id": tenant_id,
        "tool_ops": stats,
        "overall_false_positive_count": sum(s["false_positives"] for s in stats),
    }


@router.get("/drift/{agent_id}")
async def get_agent_drift(agent_id: str, request: Request) -> Dict[str, Any]:
    """Compare an agent's current-week behaviour to its 4-week rolling baseline.

    Returns drift=True with signals if volume, block rate, or tool usage shifted
    significantly. Requires at least 10 baseline events to produce a result.
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    db = get_db()
    engine = get_fleet_learning_engine()
    return engine.detect_agent_drift(db=db, tenant_id=tenant_id, agent_id=agent_id)


@router.get("/suggestions")
async def get_policy_suggestions(request: Request) -> Dict[str, Any]:
    """Return all AI-generated policy suggestions from the background analysis loop."""
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    from ..ai.policy_suggester import get_cached_suggestions
    return get_cached_suggestions(tenant_id)


@router.get("/suggestions/pending")
async def get_pending_suggestions(request: Request) -> Dict[str, Any]:
    """Return only high-confidence suggestions (auto_escalate=True) for one-click approval.

    These are suggestions with confidence >= 0.85. They still require a human
    to explicitly approve via POST /learning/suggestions/approve.
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    from ..ai.policy_suggester import get_cached_suggestions
    all_s = get_cached_suggestions(tenant_id)
    pending = [s for s in (all_s.get("suggestions") or []) if s.get("auto_escalate")]
    return {
        "pending": pending,
        "count": len(pending),
        "generated_at": all_s.get("generated_at"),
    }


class ApproveSuggestionRequest(BaseModel):
    name: str = Field(..., description="Suggestion name to approve (from /suggestions/pending)")
    priority: Optional[int] = Field(default=500, ge=0, le=1000)


@router.post("/suggestions/approve")
async def approve_suggestion(
    request: Request, body: ApproveSuggestionRequest
) -> Dict[str, Any]:
    """One-click approve: submit a pending suggestion as a live policy rule.

    Finds the named suggestion in the cache and creates it as an enabled policy
    rule for this tenant. The suggestion must exist and have auto_escalate=True.
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    from ..ai.policy_suggester import get_cached_suggestions
    from ..persistence import get_db

    all_s = get_cached_suggestions(tenant_id)
    match = next(
        (s for s in (all_s.get("suggestions") or [])
         if s.get("name") == body.name and s.get("auto_escalate")),
        None,
    )
    if not match:
        raise HTTPException(
            status_code=404,
            detail=f"No high-confidence pending suggestion named '{body.name}'. "
                   "Check GET /learning/suggestions/pending for available names.",
        )

    db = get_db()
    rule_id = db.create_policy_rule(
        tenant_id=tenant_id,
        name=match["name"],
        description=f"{match['description']} [approved from AI suggestion: {match['rationale']}]",
        action=match["action"],
        condition_tool=match.get("condition_tool"),
        condition_op=match.get("condition_op"),
        priority=body.priority or 500,
        enabled=True,
    )
    return {
        "approved": True,
        "rule_id": rule_id,
        "name": match["name"],
        "action": match["action"],
        "condition_tool": match.get("condition_tool"),
        "condition_op": match.get("condition_op"),
        "source_confidence": match.get("confidence"),
    }


@router.get("/threshold-suggestions")
async def get_threshold_suggestions(request: Request) -> Dict[str, Any]:
    """Return threshold tuning suggestions derived from block precision stats.

    over_sensitive: tool.op blocks with <60% precision — threshold too tight.
    well_calibrated: tool.op blocks with >95% precision — working correctly.
    auto_escalate=True entries need attention (precision <40%, 20+ blocks).
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    engine = get_fleet_learning_engine()
    suggestions = engine.suggest_threshold_adjustments(tenant_id=tenant_id)
    needs_attention = [s for s in suggestions if s.get("auto_escalate")]
    return {
        "tenant_id": tenant_id,
        "suggestions": suggestions,
        "needs_attention": needs_attention,
        "count": len(suggestions),
    }

