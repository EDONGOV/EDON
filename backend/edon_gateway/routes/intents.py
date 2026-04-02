"""Intent management routes: set, get, list intent contracts.

Intent contracts define what an agent is allowed to do (objective, scope,
constraints, risk level). The governor loads the active intent on every
/v1/action call; without these endpoints operators cannot update that contract
programmatically.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, Field

from ..persistence import get_db
from ..tenancy import get_request_tenant_id
from ..logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/intent", tags=["intent"])


# ── Request / Response models ──────────────────────────────────────────────────

class IntentSetRequest(BaseModel):
    intent_id: Optional[str] = Field(
        None,
        description="Intent ID; auto-generated as intent_<uuid4> if omitted",
    )
    objective: str = Field(..., description="Human-readable description of the agent's goal")
    scope: dict = Field(
        default_factory=dict,
        description='Allowed tool→operations map, e.g. {"email": ["send", "read"]}',
    )
    constraints: dict = Field(
        default_factory=dict,
        description="Constraint flags: work_hours_only, drafts_only, max_recipients, etc.",
    )
    risk_level: str = Field(
        "medium",
        pattern="^(low|medium|high|critical)$",
        description="Maximum risk level the intent tolerates",
    )
    approved_by_user: bool = Field(
        False,
        description="Whether a human operator has explicitly approved this intent",
    )
    set_as_active: bool = Field(
        False,
        description="If true, also persist this intent as the tenant's active preset",
    )


class IntentResponse(BaseModel):
    intent_id: str
    objective: str
    scope: dict
    constraints: dict
    risk_level: str
    approved_by_user: bool
    created_at: str
    updated_at: str


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/set", response_model=IntentResponse, status_code=201)
async def set_intent(request: Request, body: IntentSetRequest):
    """Create or replace an intent contract.

    If `intent_id` is omitted a new one is generated. Pass `set_as_active=true`
    to also activate this intent as the tenant's default policy preset so that
    /v1/action calls without an explicit intent_id use it automatically.
    """
    db = get_db()
    tenant_id = get_request_tenant_id(request)

    intent_id = (body.intent_id or f"intent_{uuid.uuid4().hex[:12]}").strip()

    try:
        db.save_intent(
            intent_id=intent_id,
            objective=body.objective,
            scope=body.scope,
            constraints=body.constraints,
            risk_level=body.risk_level,
            approved_by_user=body.approved_by_user,
            customer_id=tenant_id,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if body.set_as_active:
        try:
            db.set_active_policy_preset(
                preset_name=intent_id,
                applied_by=tenant_id or "api",
            )
        except Exception as exc:
            logger.warning("set_as_active failed (non-blocking): %s", exc)

    intent = db.get_intent(intent_id, customer_id=tenant_id)
    if not intent:
        raise HTTPException(status_code=500, detail="Intent saved but could not be retrieved")

    # Update edon_active_intents Prometheus gauge
    try:
        from ..main import prometheus_active_intents
        from ..config import config as _cfg
        if _cfg.METRICS_ENABLED and prometheus_active_intents is not None:
            prometheus_active_intents.set(len(db.list_intents()))
    except Exception:
        pass

    logger.info("[intent/set] tenant=%s intent_id=%s", tenant_id, intent_id)
    return IntentResponse(**intent)


@router.get("/get", response_model=IntentResponse)
async def get_intent(
    request: Request,
    intent_id: Optional[str] = Query(None, description="Specific intent ID; omit to get the active/latest intent"),
):
    """Retrieve an intent contract by ID, or the most-recently-updated intent if no ID given."""
    db = get_db()
    tenant_id = get_request_tenant_id(request)

    if intent_id:
        intent = db.get_intent(intent_id, customer_id=tenant_id)
        if not intent:
            raise HTTPException(status_code=404, detail=f"Intent not found: {intent_id}")
    else:
        # Try active preset first
        intent = None
        try:
            active = db.get_active_policy_preset()
            if active and active.get("preset_name"):
                intent = db.get_intent(active["preset_name"], customer_id=tenant_id)
        except Exception:
            pass
        if not intent:
            intent = db.get_latest_intent(customer_id=tenant_id)
        if not intent:
            raise HTTPException(status_code=404, detail="No intents found. Create one via POST /intent/set")

    return IntentResponse(**intent)


@router.get("/list")
async def list_intents(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
):
    """List all intent contracts for this tenant, newest first."""
    db = get_db()
    tenant_id = get_request_tenant_id(request)
    intents = db.list_intents(limit=limit, customer_id=tenant_id)

    # Surface which intent is currently active
    active_intent_id = None
    try:
        active = db.get_active_policy_preset()
        if active:
            active_intent_id = active.get("preset_name")
    except Exception:
        pass

    return {
        "intents": intents,
        "count": len(intents),
        "active_intent_id": active_intent_id,
    }


@router.delete("/{intent_id}", status_code=204)
async def delete_intent(intent_id: str, request: Request):
    """Delete an intent contract by ID."""
    db = get_db()
    tenant_id = get_request_tenant_id(request)
    existing = db.get_intent(intent_id, customer_id=tenant_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Intent not found: {intent_id}")

    try:
        with db._get_connection() as conn:
            if tenant_id is not None:
                conn.execute(
                    "DELETE FROM intents WHERE intent_id = ? AND customer_id = ?",
                    (intent_id, tenant_id),
                )
            else:
                conn.execute("DELETE FROM intents WHERE intent_id = ?", (intent_id,))
            conn.commit()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete intent: {exc}")

    # Update edon_active_intents Prometheus gauge
    try:
        from ..main import prometheus_active_intents
        from ..config import config as _cfg
        if _cfg.METRICS_ENABLED and prometheus_active_intents is not None:
            prometheus_active_intents.set(len(db.list_intents()))
    except Exception:
        pass

    logger.info("[intent/delete] intent_id=%s", intent_id)
