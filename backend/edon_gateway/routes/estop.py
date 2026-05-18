"""E-Stop routes — per-robot physical emergency halt.

POST   /v1/estop/{robot_id}   — trigger e-stop
DELETE /v1/estop/{robot_id}   — clear e-stop
GET    /v1/estop/{robot_id}   — get state for one robot
GET    /v1/estop              — list all active e-stops for tenant
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..estop import (
    trigger_estop,
    clear_estop,
    get_estop_state,
    list_active_estops,
)
from ..tenancy import get_request_tenant_id
from ..logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v1/estop", tags=["estop"])


class EStopTriggerBody(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    triggered_by: str = Field(default="api")


class EStopClearBody(BaseModel):
    cleared_by: str = Field(default="api")
    note: Optional[str] = Field(default=None, max_length=500)


@router.get("")
async def list_estops(request: Request):
    """Return all active e-stops for this tenant."""
    tenant_id = get_request_tenant_id(request)
    return {"estops": list_active_estops(tenant_id=tenant_id)}


@router.get("/{robot_id}")
async def get_estop(robot_id: str, request: Request):
    """Return the current e-stop state for a robot."""
    return get_estop_state(robot_id)


@router.post("/{robot_id}", status_code=200)
async def trigger(robot_id: str, body: EStopTriggerBody, request: Request):
    """Trigger an e-stop for a robot.

    All physical commands (execute, actuate, drive, fly, lift, etc.) for this
    robot_id will be hard-blocked by the governor until the e-stop is cleared.

    This does NOT automatically send a physical stop signal to the robot — that
    must be handled by the caller's control layer.  EDON's role is to ensure no
    further commands are issued while the e-stop is active.
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    state = trigger_estop(
        robot_id=robot_id,
        reason=body.reason,
        triggered_by=body.triggered_by,
        tenant_id=tenant_id,
    )
    return {
        **state,
        "message": (
            f"E-stop triggered for robot {robot_id}. "
            "All physical commands are now BLOCKED. "
            "Send a physical stop signal to the robot via your control layer. "
            "Clear at DELETE /v1/estop/{robot_id} when safe to resume."
        ),
    }


@router.delete("/{robot_id}", status_code=200)
async def clear(robot_id: str, body: EStopClearBody, request: Request):
    """Clear an e-stop — resume physical command governance for this robot.

    Only call this after confirming the robot is in a safe state.
    This action is logged with timestamp and operator identity.
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    state = clear_estop(
        robot_id=robot_id,
        cleared_by=body.cleared_by,
        note=body.note,
    )
    return {
        **state,
        "message": f"E-stop cleared for robot {robot_id}. Physical governance resumed.",
    }
