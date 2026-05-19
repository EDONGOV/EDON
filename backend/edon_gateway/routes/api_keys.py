"""API key management routes — create, list, revoke, rotate."""

import secrets
from fastapi import APIRouter, Request, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional

from ..config import config
from ..persistence import get_db
from ..tenancy import get_request_tenant_id
from ..security.hashing import hash_api_key_fast
from ..logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


class CreateKeyRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=100, description="Optional name for the key")
    role: str = Field(
        "viewer",
        description="RBAC role: super_admin, governance_admin, security_admin, operator, auditor, developer, viewer",
    )


class RotateKeyRequest(BaseModel):
    overlap_hours: int = Field(
        24, ge=1, le=168,
        description="How long (hours) the old key stays valid after rotation. Default 24h, max 168h (7 days)."
    )
    name: Optional[str] = Field(None, max_length=100, description="Optional name for the new key")


@router.get("/me", status_code=200)
async def get_me(request: Request):
    """Return identity info for the current API key."""
    tenant_info = getattr(request.state, 'tenant_info', None) or {}
    tenant_id = tenant_info.get("tenant_id", "")
    db = get_db()
    vertical = db.get_tenant_vertical(tenant_id) if tenant_id and hasattr(db, "get_tenant_vertical") else None
    return {
        "tenant_id": tenant_id,
        "key_id": tenant_info.get("api_key_id", None),
        "key_name": tenant_info.get("key_name", None),
        "role": tenant_info.get("role", "viewer"),
        "plan": tenant_info.get("plan", ""),
        "is_admin": tenant_info.get("role") in {"admin", "super_admin", "governance_admin", "security_admin"},
        "is_sandbox": tenant_info.get("is_sandbox", False),
        "vertical": vertical,
    }


@router.patch("/me/vertical", status_code=200)
async def set_vertical(request: Request):
    """Set the industry vertical for this tenant (admin only)."""
    tenant_info = getattr(request.state, 'tenant_info', None) or {}
    if tenant_info.get("role") not in {"admin", "super_admin", "governance_admin"}:
        raise HTTPException(status_code=403, detail="Admin role required to set vertical")
    tenant_id = tenant_info.get("tenant_id", "")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    body = await request.json()
    vertical = body.get("vertical")
    allowed = {"healthcare", "banking", "general", None}
    if vertical not in allowed:
        raise HTTPException(status_code=422, detail=f"vertical must be one of: {', '.join(str(v) for v in allowed if v)}")
    db = get_db()
    if hasattr(db, "set_tenant_vertical"):
        db.set_tenant_vertical(tenant_id, vertical)
    return {"vertical": vertical}


@router.post("/{key_id}/rotate", status_code=201)
async def rotate_api_key(key_id: str, request: Request, body: RotateKeyRequest):
    """Rotate an API key with zero-downtime overlap.

    Creates a new API key and marks the current key as **rotating** (still valid
    for `overlap_hours`). During the overlap window both keys authenticate
    successfully so you can deploy the new key without any auth failures.

    After `overlap_hours` the old key automatically stops being accepted.

    Returns the **new plaintext key** — store it securely, it is shown only once.
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    db = get_db()

    # Verify the key exists and belongs to this tenant
    existing = db.get_api_key(key_id, tenant_id) if hasattr(db, "get_api_key") else None
    if existing is None:
        # Fallback: check via list
        keys = db.list_api_keys(tenant_id) if hasattr(db, "list_api_keys") else []
        existing = next((k for k in keys if k["id"] == key_id), None)
    if not existing:
        raise HTTPException(status_code=404, detail="API key not found")
    if existing.get("status") not in ("active", "rotating"):
        raise HTTPException(status_code=400, detail=f"Key status '{existing.get('status')}' cannot be rotated")

    # Generate new key
    new_plaintext = f"edon-{secrets.token_urlsafe(32)}"
    new_hash = hash_api_key_fast(new_plaintext)
    new_name = body.name or (f"{existing.get('name', 'key')} (rotated)")

    result = db.rotate_api_key(
        api_key_id=key_id,
        tenant_id=tenant_id,
        new_key_hash=new_hash,
        new_key_name=new_name,
        overlap_hours=body.overlap_hours,
        role=existing.get("role", "user"),
    )

    logger.info(
        f"[api-keys] Rotated key {key_id} for tenant {tenant_id}. "
        f"New key id={result['new_key_id']}, old expires={result['old_expires_at']}"
    )

    return {
        "new_key_id": result["new_key_id"],
        "new_key": new_plaintext,
        "new_key_name": new_name,
        "old_key_id": key_id,
        "old_key_expires_at": result["old_expires_at"],
        "overlap_hours": body.overlap_hours,
        "message": f"New key active immediately. Old key valid until {result['old_expires_at']}.",
    }


@router.post("", status_code=201)
async def create_api_key(request: Request, body: CreateKeyRequest):
    """Create a new API key for the current tenant.

    Returns the **plaintext key** once — it is never stored and cannot be retrieved again.
    Store it securely immediately.
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    db = get_db()

    enterprise_roles = {
        "super_admin",
        "governance_admin",
        "security_admin",
        "operator",
        "auditor",
        "developer",
        "viewer",
    }
    legacy_roles = {"admin", "user", "agent", "read_only"}
    allowed_roles = enterprise_roles if config.ENTERPRISE_MODE else enterprise_roles | legacy_roles
    if body.role not in allowed_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role '{body.role}'. Valid: {sorted(allowed_roles)}")

    plaintext = f"edon-{secrets.token_urlsafe(32)}"
    key_hash = hash_api_key_fast(plaintext)

    key_id = db.create_api_key(
        tenant_id=tenant_id,
        key_hash=key_hash,
        name=body.name,
        role=body.role,
    )

    logger.info(f"[api-keys] Created key {key_id} for tenant {tenant_id} (name={body.name!r})")

    return {
        "key_id": key_id,
        "key": plaintext,
        "name": body.name,
        "role": body.role,
        "message": "API key created. Store the key value securely — it will not be shown again.",
    }


@router.get("", status_code=200)
async def list_api_keys(request: Request):
    """List API keys for the current tenant.

    Never returns the plaintext key or its hash — only metadata.
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    db = get_db()
    keys = db.list_api_keys(tenant_id) if hasattr(db, "list_api_keys") else []

    # Strip key_hash from results before returning
    safe_keys = [
        {k: v for k, v in key.items() if k != "key_hash"}
        for key in keys
    ]

    return {"keys": safe_keys, "count": len(safe_keys)}


@router.delete("/{key_id}", status_code=200)
async def delete_api_key(key_id: str, request: Request):
    """Revoke/delete an API key for the current tenant.

    Verifies tenant ownership before revoking. Revoked keys are immediately rejected.
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    db = get_db()

    # Verify the key exists and belongs to this tenant
    keys = db.list_api_keys(tenant_id) if hasattr(db, "list_api_keys") else []
    existing = next((k for k in keys if k["id"] == key_id), None)
    if not existing:
        raise HTTPException(status_code=404, detail="API key not found")

    revoked = db.revoke_api_key(key_id) if hasattr(db, "revoke_api_key") else False

    logger.info(f"[api-keys] Revoked key {key_id} for tenant {tenant_id}")

    return {"key_id": key_id, "status": "revoked", "revoked": revoked}
