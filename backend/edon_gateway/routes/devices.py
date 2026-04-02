"""Device registry API — physical device management, agent-device bindings, auth matrix."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..middleware.rbac import check_permission
from ..persistence import get_db
from ..tenancy import get_request_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/devices", tags=["devices"])

_VALID_STATUSES = {"available", "in_use", "maintenance", "locked", "offline"}
_VALID_PERMISSIONS = {"full_control", "read_only", "supervised"}


# ── Request models ─────────────────────────────────────────────────────────────

class DeviceRegisterRequest(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=100,
                           description="Stable unique ID, e.g. 'sr-001'")
    device_type: str = Field(..., min_length=1, max_length=100,
                             description="e.g. 'surgical_robot', 'iv_pump', 'mri_scanner'")
    name: str = Field(..., min_length=1, max_length=200,
                      description="Human-friendly name, e.g. 'Surgical Robot SR-001'")
    vendor_id: Optional[str] = Field(None, max_length=100)
    serial_number: Optional[str] = Field(None, max_length=200)
    make: Optional[str] = Field(None, max_length=100)
    model: Optional[str] = Field(None, max_length=100)
    department: Optional[str] = Field(None, max_length=100,
                                      description="e.g. 'surgery', 'radiology', 'pharmacy'")
    location: Optional[str] = Field(None, max_length=200,
                                    description="e.g. 'OR-3, Floor 4, North Wing'")
    requires_supervision: bool = Field(False,
        description="If true, any action on this device escalates to HUMAN_REQUIRED")
    metadata: Optional[dict] = None


class DeviceUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    vendor_id: Optional[str] = Field(None, max_length=100)
    serial_number: Optional[str] = Field(None, max_length=200)
    make: Optional[str] = Field(None, max_length=100)
    model: Optional[str] = Field(None, max_length=100)
    department: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=200)
    status: Optional[str] = None
    requires_supervision: Optional[bool] = None
    metadata: Optional[dict] = None


class BindingRequest(BaseModel):
    agent_id: str = Field(..., min_length=1)
    permission_level: str = Field("full_control",
        description="'full_control' | 'read_only' | 'supervised'")
    authorized_by: Optional[str] = None
    valid_from: Optional[str] = Field(None, description="ISO-8601 start of binding validity")
    valid_until: Optional[str] = Field(None, description="ISO-8601 expiry of binding")
    shift_start: Optional[str] = Field(None, description="HH:MM — earliest time agent may operate device")
    shift_end: Optional[str] = Field(None, description="HH:MM — latest time agent may operate device")
    requires_supervision: bool = Field(False,
        description="If true, actions escalate to HUMAN_REQUIRED even if device doesn't require it")


# ── Device CRUD ────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def register_device(request: Request, body: DeviceRegisterRequest):
    """Register a new physical device. Admin role required.

    Every device that any AI agent will ever command must be registered here
    before bindings can be created. This is your authoritative device inventory.
    """
    tenant_info = getattr(request.state, "tenant_info", None) or {}
    if not check_permission(tenant_info, "admin"):
        raise HTTPException(status_code=403, detail="Admin role required")

    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    # Check for duplicate
    existing = db.get_device(body.device_id, tenant_id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Device '{body.device_id}' already registered",
        )

    db.register_device(
        tenant_id=tenant_id,
        device_id=body.device_id,
        device_type=body.device_type,
        name=body.name,
        vendor_id=body.vendor_id,
        serial_number=body.serial_number,
        make=body.make,
        model=body.model,
        department=body.department,
        location=body.location,
        requires_supervision=body.requires_supervision,
        metadata=body.metadata,
    )
    device = db.get_device(body.device_id, tenant_id)
    logger.info("Device registered: device_id=%s tenant=%s type=%s",
                body.device_id, tenant_id, body.device_type)
    return device


@router.get("")
async def list_devices(
    request: Request,
    department: Optional[str] = Query(None),
    device_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    """List all registered devices with current status and controlling agent."""
    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    if status and status not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of: {sorted(_VALID_STATUSES)}")

    devices = db.list_devices(
        tenant_id=tenant_id,
        department=department,
        device_type=device_type,
        status=status,
    )
    return {"devices": devices, "count": len(devices)}


@router.get("/matrix")
async def get_authorization_matrix(request: Request):
    """Return the full agent × device authorization matrix for this tenant.

    Shows which agents are authorized for which devices, their permission level,
    shift windows, supervision requirements, and current lock status.
    """
    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    rows = db.get_authorization_matrix(tenant_id)

    # Pivot into a structured matrix: device → [authorized agents]
    matrix: dict = {}
    for row in rows:
        dev_id = row["device_id"]
        if dev_id not in matrix:
            matrix[dev_id] = {
                "device_id": dev_id,
                "device_name": row["device_name"],
                "device_type": row["device_type"],
                "department": row["department"],
                "location": row["location"],
                "status": row["status"],
                "current_agent_id": row["current_agent_id"],
                "device_vendor_id": row.get("device_vendor_id"),
                "authorized_agents": [],
            }
        if row.get("agent_id"):
            matrix[dev_id]["authorized_agents"].append({
                "agent_id": row["agent_id"],
                "agent_name": row.get("agent_name"),
                "agent_type": row.get("agent_type"),
                "vendor_id": row.get("agent_vendor_id"),
                "permission_level": row["permission_level"],
                "requires_supervision": bool(row["requires_supervision"]),
                "valid_until": row["valid_until"],
                "shift_start": row["shift_start"],
                "shift_end": row["shift_end"],
                "binding_enabled": bool(row["binding_enabled"]),
            })

    return {
        "matrix": list(matrix.values()),
        "device_count": len(matrix),
    }


@router.get("/vendors/summary")
async def get_vendor_summary(request: Request):
    """Per-vendor breakdown: action counts, block rate, devices controlled, last active.

    Answers: "What is each AI vendor doing in our hospital, and what devices do they control?"

    Returns one entry per vendor_id found on registered agents, with:
    - total_actions, allowed, blocked, escalated, block_rate_pct
    - last_action_at — last time any of this vendor's agents acted
    - distinct_agents — how many agents this vendor has registered
    - distinct_devices — how many distinct devices they've touched in audit trail
    - authorized_devices — full list of devices this vendor's agents are authorized for
    - currently_controlling — subset currently holding an active device lock
    """
    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    summaries = db.get_vendor_summary(tenant_id)
    return {"vendors": summaries, "count": len(summaries)}


@router.get("/{device_id}")
async def get_device(device_id: str, request: Request):
    """Get full details for a specific device including current lock status."""
    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    device = db.get_device(device_id=device_id, tenant_id=tenant_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device not found: {device_id}")
    return device


@router.patch("/{device_id}")
async def update_device(device_id: str, request: Request, body: DeviceUpdateRequest):
    """Update device metadata or status. Admin role required."""
    tenant_info = getattr(request.state, "tenant_info", None) or {}
    if not check_permission(tenant_info, "admin"):
        raise HTTPException(status_code=403, detail="Admin role required")

    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    if body.status and body.status not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of: {sorted(_VALID_STATUSES)}")

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updated = db.update_device(device_id=device_id, tenant_id=tenant_id, **updates)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Device not found: {device_id}")

    return db.get_device(device_id=device_id, tenant_id=tenant_id)


@router.delete("/{device_id}", status_code=204)
async def deregister_device(device_id: str, request: Request):
    """Deregister a device. Admin role required.

    Fails if device is currently in use (status='in_use').
    """
    tenant_info = getattr(request.state, "tenant_info", None) or {}
    if not check_permission(tenant_info, "admin"):
        raise HTTPException(status_code=403, detail="Admin role required")

    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    device = db.get_device(device_id=device_id, tenant_id=tenant_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device not found: {device_id}")
    if device.get("status") == "in_use":
        raise HTTPException(
            status_code=409,
            detail=f"Device '{device_id}' is currently in use by agent '{device.get('current_agent_id')}'. "
                   "Release the lock before deregistering.",
        )

    db.deregister_device(device_id=device_id, tenant_id=tenant_id)
    logger.info("Device deregistered: device_id=%s tenant=%s", device_id, tenant_id)


# ── Agent-Device Bindings ──────────────────────────────────────────────────────

@router.post("/{device_id}/agents")
async def create_binding(device_id: str, request: Request, body: BindingRequest):
    """Authorize an agent to control a device. Admin role required.

    The binding defines:
    - Which agent can command this device
    - At what permission level (full_control / read_only / supervised)
    - During which time window (shift_start–shift_end)
    - For how long (valid_until)
    - Whether a human must be present (requires_supervision)

    Only agents with an active binding can pass the device check at /v1/action.
    """
    tenant_info = getattr(request.state, "tenant_info", None) or {}
    if not check_permission(tenant_info, "admin"):
        raise HTTPException(status_code=403, detail="Admin role required")

    if body.permission_level not in _VALID_PERMISSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"permission_level must be one of: {sorted(_VALID_PERMISSIONS)}",
        )

    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    # Ensure device exists
    if not db.get_device(device_id=device_id, tenant_id=tenant_id):
        raise HTTPException(status_code=404, detail=f"Device not found: {device_id}")

    # authorized_by defaults to the caller's tenant/user id
    authorized_by = body.authorized_by or (
        (getattr(request.state, "tenant_info", None) or {}).get("key_id") or tenant_id
    )

    binding_id = db.create_device_binding(
        tenant_id=tenant_id,
        agent_id=body.agent_id,
        device_id=device_id,
        permission_level=body.permission_level,
        authorized_by=authorized_by,
        valid_from=body.valid_from,
        valid_until=body.valid_until,
        shift_start=body.shift_start,
        shift_end=body.shift_end,
        requires_supervision=body.requires_supervision,
    )
    logger.info(
        "Device binding created: agent=%s device=%s perm=%s tenant=%s authorized_by=%s",
        body.agent_id, device_id, body.permission_level, tenant_id, authorized_by,
    )
    return {
        "binding_id": binding_id,
        "agent_id": body.agent_id,
        "device_id": device_id,
        "permission_level": body.permission_level,
        "requires_supervision": body.requires_supervision,
        "valid_from": body.valid_from,
        "valid_until": body.valid_until,
        "shift_start": body.shift_start,
        "shift_end": body.shift_end,
        "authorized_by": authorized_by,
    }


@router.get("/{device_id}/agents")
async def list_device_bindings(device_id: str, request: Request):
    """List all agents authorized to control this device."""
    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    if not db.get_device(device_id=device_id, tenant_id=tenant_id):
        raise HTTPException(status_code=404, detail=f"Device not found: {device_id}")

    bindings = db.list_device_bindings(tenant_id=tenant_id, device_id=device_id)
    return {"device_id": device_id, "bindings": bindings, "count": len(bindings)}


@router.delete("/{device_id}/agents/{agent_id}", status_code=204)
async def revoke_binding(device_id: str, agent_id: str, request: Request):
    """Revoke an agent's authorization to control a device. Admin role required."""
    tenant_info = getattr(request.state, "tenant_info", None) or {}
    if not check_permission(tenant_info, "admin"):
        raise HTTPException(status_code=403, detail="Admin role required")

    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    revoked = db.revoke_device_binding(
        agent_id=agent_id, device_id=device_id, tenant_id=tenant_id
    )
    if not revoked:
        raise HTTPException(
            status_code=404,
            detail=f"No binding found: agent '{agent_id}' → device '{device_id}'",
        )
    logger.info("Binding revoked: agent=%s device=%s tenant=%s", agent_id, device_id, tenant_id)


# ── Lock Management ────────────────────────────────────────────────────────────

@router.post("/{device_id}/release")
async def force_release_device(device_id: str, request: Request):
    """Force-release a device lock. Admin role required.

    Use when an agent crashes or fails to release. All force-releases are
    logged in device_sessions with end_reason='force_released'.
    """
    tenant_info = getattr(request.state, "tenant_info", None) or {}
    if not check_permission(tenant_info, "admin"):
        raise HTTPException(status_code=403, detail="Admin role required")

    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    device = db.get_device(device_id=device_id, tenant_id=tenant_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device not found: {device_id}")
    if device.get("status") != "in_use":
        return {"device_id": device_id, "status": device.get("status"), "note": "Device was not locked"}

    releasing_agent = device.get("current_agent_id", "unknown")
    db.release_device_lock(
        device_id=device_id,
        tenant_id=tenant_id,
        agent_id=releasing_agent,
        end_reason="force_released",
        force=True,
    )
    logger.warning(
        "Device force-released: device_id=%s was_held_by=%s tenant=%s",
        device_id, releasing_agent, tenant_id,
    )
    return {
        "device_id": device_id,
        "status": "available",
        "released_from_agent": releasing_agent,
        "end_reason": "force_released",
    }


@router.get("/{device_id}/sessions")
async def list_device_sessions(
    device_id: str,
    request: Request,
    limit: int = Query(50, ge=1, le=500),
):
    """Session history for a device — who controlled it, for how long, and why it ended."""
    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    if not db.get_device(device_id=device_id, tenant_id=tenant_id):
        raise HTTPException(status_code=404, detail=f"Device not found: {device_id}")

    sessions = db.list_device_sessions(device_id=device_id, tenant_id=tenant_id, limit=limit)
    return {"device_id": device_id, "sessions": sessions, "count": len(sessions)}
