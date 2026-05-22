"""API key management routes — create, list, revoke, rotate."""

import base64
import json
import secrets
from datetime import UTC, datetime, timedelta
from fastapi import APIRouter, Request, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional

from ..config import config
from ..persistence import get_db
from ..tenancy import get_request_tenant_id
from ..security.hashing import hash_api_key_fast
from ..security.signing import get_key_id, sign_canonical_payload
from ..logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api-keys", tags=["api-keys"])

ADMIN_ROLES = {"admin", "super_admin", "governance_admin", "security_admin"}


class CreateKeyRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=100, description="Optional name for the key")
    role: str = Field(
        "viewer",
        description="RBAC role: super_admin, governance_admin, security_admin, operator, auditor, developer, viewer",
    )
    department: Optional[str] = Field(None, max_length=120, description="Owning department")
    scope_group: Optional[str] = Field(None, max_length=80, description="Credential scope group")
    purpose: Optional[str] = Field(None, max_length=140, description="Credential purpose")
    scope: Optional[str] = Field(None, max_length=240, description="Runtime scope expression")
    environment: Optional[str] = Field(None, max_length=60, description="Deployment environment")
    expires_in_days: Optional[int] = Field(None, ge=1, le=365, description="Credential expiry window.")


class RotateKeyRequest(BaseModel):
    overlap_hours: int = Field(
        24, ge=1, le=168,
        description="How long (hours) the old key stays valid after rotation. Default 24h, max 168h (7 days)."
    )
    name: Optional[str] = Field(None, max_length=100, description="Optional name for the new key")


class RuntimeSessionRequest(BaseModel):
    ttl_minutes: int = Field(15, ge=1, le=60, description="Short-lived runtime token TTL.")


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
        "department": tenant_info.get("department"),
        "scope_group": tenant_info.get("scope_group"),
        "purpose": tenant_info.get("purpose"),
        "scope": tenant_info.get("scope"),
        "environment": tenant_info.get("environment"),
    }


@router.post("/runtime-session", status_code=201)
async def exchange_runtime_session(request: Request, body: RuntimeSessionRequest):
    """Exchange a runtime credential for a short-lived signed session token.

    This is only the runtime's identity/session artifact. It does not authorize
    clinical execution by itself; downstream actions still need the governed
    per-action execution token emitted by /v1/action.
    """
    tenant_info = getattr(request.state, 'tenant_info', None) or {}
    tenant_id = tenant_info.get("tenant_id") or get_request_tenant_id(request)
    key_id = tenant_info.get("api_key_id")
    if not tenant_id or not key_id:
        raise HTTPException(status_code=401, detail="Runtime API key context required")
    if tenant_info.get("role") in {"auditor", "viewer"}:
        raise HTTPException(status_code=403, detail="Runtime session requires an operator or runtime credential")

    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=body.ttl_minutes)
    payload = {
        "token_type": "edon.runtime_session",
        "tenant_id": tenant_id,
        "api_key_id": key_id,
        "role": tenant_info.get("role", "operator"),
        "department": tenant_info.get("department"),
        "scope_group": tenant_info.get("scope_group"),
        "purpose": tenant_info.get("purpose"),
        "scope": tenant_info.get("scope"),
        "environment": tenant_info.get("environment"),
        "issued_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "key_id": get_key_id(),
    }
    signature = sign_canonical_payload(payload)
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    token = f"{encoded}.{signature}"
    return {
        "token": token,
        "token_type": payload["token_type"],
        "expires_at": payload["expires_at"],
        "ttl_minutes": body.ttl_minutes,
        "payload": payload,
        "message": "Short-lived runtime session issued. Governed actions still require per-action execution tokens.",
    }


@router.patch("/me/vertical", status_code=200)
async def set_vertical(request: Request):
    """Set the industry vertical for this tenant (admin only)."""
    tenant_info = getattr(request.state, 'tenant_info', None) or {}
    if tenant_info.get("role") not in ADMIN_ROLES:
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
    requester_role = (getattr(request.state, "tenant_info", None) or {}).get("role", "viewer")

    enterprise_roles = {
        "super_admin",
        "governance_admin",
        "security_admin",
        "operator",
        "auditor",
        "developer",
        "viewer",
    }
    allowed_roles = enterprise_roles if config.ENTERPRISE_MODE else enterprise_roles | {"admin", "user", "agent", "read_only"}
    if body.role not in allowed_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role '{body.role}'. Valid: {sorted(allowed_roles)}")
    if config.ENTERPRISE_MODE and requester_role not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required to create API keys in enterprise mode")
    if not config.ENTERPRISE_MODE and body.role != "viewer" and requester_role not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required to create elevated access keys")
    if body.role in {"operator", "developer"} and not body.department:
        raise HTTPException(status_code=400, detail="Department is required for runtime/operator credentials")
    if body.role in {"operator", "developer"} and not body.scope:
        raise HTTPException(status_code=400, detail="Scope is required for runtime/operator credentials")

    plaintext = f"edon-{secrets.token_urlsafe(32)}"
    key_hash = hash_api_key_fast(plaintext)
    expires_in_days = body.expires_in_days or (90 if body.role in {"operator", "developer"} else None)
    expires_at = (datetime.now(UTC) + timedelta(days=expires_in_days)).isoformat() if expires_in_days else None

    key_id = db.create_api_key(
        tenant_id=tenant_id,
        key_hash=key_hash,
        name=body.name,
        role=body.role,
        department=body.department,
        scope_group=body.scope_group,
        purpose=body.purpose,
        scope=body.scope,
        environment=body.environment,
        expires_at=expires_at,
    )

    logger.info(f"[api-keys] Created key {key_id} for tenant {tenant_id} (name={body.name!r})")

    return {
        "key_id": key_id,
        "key": plaintext,
        "name": body.name,
        "role": body.role,
        "department": body.department,
        "scope_group": body.scope_group,
        "purpose": body.purpose,
        "scope": body.scope,
        "environment": body.environment,
        "expires_at": expires_at,
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
