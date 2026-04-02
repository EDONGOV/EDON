"""Admin bootstrap routes — protected by EDON_BOOTSTRAP_SECRET.

These endpoints are NOT protected by the normal auth middleware (they are added
to PUBLIC_ENDPOINTS in auth.py via the exclusion set).  They are instead
protected by a separate shared secret (`X-Bootstrap-Secret` header) so that
operators can provision the very first API key before any tenant exists.

Intended for one-time provisioning and CI bootstrap only.
"""

import os
import uuid
import secrets
import time
import ipaddress
from collections import defaultdict
from datetime import datetime, UTC

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List

from ..persistence import get_db
from ..security.hashing import hash_api_key_fast
from ..logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

# The bootstrap secret is set via env var.  If not set, the endpoint is disabled.
_BOOTSTRAP_SECRET = os.getenv("EDON_BOOTSTRAP_SECRET", "").strip()

_bootstrap_attempts: dict = defaultdict(list)
_BOOTSTRAP_MAX_ATTEMPTS = 5
_BOOTSTRAP_WINDOW_SEC = 300  # 5 minutes


def _check_bootstrap_rate_limit(ip: str) -> None:
    """Raise 429 if the IP has exceeded the bootstrap secret attempt threshold."""
    now = time.time()
    attempts = [t for t in _bootstrap_attempts[ip] if now - t < _BOOTSTRAP_WINDOW_SEC]
    if len(attempts) >= _BOOTSTRAP_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many bootstrap attempts. Try again later.")
    attempts.append(now)
    _bootstrap_attempts[ip] = attempts


def _check_bootstrap_secret(request: Request):
    """Raise 403 if X-Bootstrap-Secret header is missing or wrong."""
    client_ip = request.client.host if request.client else "unknown"
    _check_bootstrap_rate_limit(client_ip)
    if not _BOOTSTRAP_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Bootstrap endpoint is disabled. Set EDON_BOOTSTRAP_SECRET env var to enable.",
        )
    provided = request.headers.get("X-Bootstrap-Secret", "").strip()
    if not secrets.compare_digest(provided, _BOOTSTRAP_SECRET):
        logger.warning("bootstrap_secret_mismatch: ip=%s", client_ip)
        raise HTTPException(status_code=403, detail="Invalid bootstrap secret")


class BootstrapKeyRequest(BaseModel):
    token: str = Field(..., min_length=8, description="Plaintext API token to provision")
    tenant_id: str = Field(..., min_length=1, max_length=100, description="Tenant ID to create or use")
    name: Optional[str] = Field(None, max_length=100, description="Human-readable key name")
    role: str = Field("admin", description="RBAC role for this key (admin/operator/user/read_only)")
    plan: str = Field("enterprise", description="Billing plan to set on the tenant (free/starter/pro/enterprise)")
    email: Optional[str] = Field(None, description="Email address for the provisioned user/tenant")


@router.post("/bootstrap-api-key", status_code=201)
async def bootstrap_api_key(request: Request, body: BootstrapKeyRequest):
    """Provision an API key for a tenant, creating the tenant if needed.

    Protected by `X-Bootstrap-Secret` header (matches `EDON_BOOTSTRAP_SECRET` env var).

    This is idempotent: if the tenant already has a key with the same hash,
    returns the existing key's metadata without creating a duplicate.
    """
    _check_bootstrap_secret(request)

    valid_roles = {"admin", "operator", "user", "agent", "read_only"}
    if body.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role '{body.role}'. Valid: {sorted(valid_roles)}")

    db = get_db()
    tenant_id = body.tenant_id
    now = datetime.now(UTC).isoformat()

    # --- Ensure tenant exists ---
    tenant = db.get_tenant(tenant_id)
    if not tenant:
        # Create a synthetic user first (required FK)
        user_id = f"user_{uuid.uuid4().hex[:16]}"
        email = body.email or f"{tenant_id}@provisioned.edoncore.com"
        db.create_user(
            user_id=user_id,
            email=email,
            auth_provider="bootstrap",
            auth_subject=f"bootstrap:{tenant_id}",
            role="admin",
        )
        db.create_tenant(tenant_id=tenant_id, user_id=user_id)
        tenant = db.get_tenant(tenant_id)
        logger.info("bootstrap: created tenant=%s user=%s", tenant_id, user_id)

    # Upgrade plan/status to requested values (always idempotent update)
    try:
        with db._get_connection() as conn:
            conn.execute(
                "UPDATE tenants SET plan = ?, status = 'active', updated_at = ? WHERE id = ?",
                (body.plan, now, tenant_id),
            )
            conn.commit()
    except Exception as e:
        logger.warning("bootstrap: could not update tenant plan: %s", e)

    # --- Check if token already provisioned ---
    key_hash = hash_api_key_fast(body.token)
    existing_key = db.get_api_key_by_hash(key_hash)
    if existing_key:
        logger.info(
            "bootstrap: token already exists for tenant=%s key_id=%s",
            tenant_id, existing_key["id"],
        )
        return {
            "key_id": existing_key["id"],
            "tenant_id": tenant_id,
            "status": "already_exists",
            "message": "Token was already provisioned. No changes made.",
        }

    # --- Create API key ---
    key_name = body.name or f"{tenant_id}-bootstrap-key"
    key_id = db.create_api_key(
        tenant_id=tenant_id,
        key_hash=key_hash,
        name=key_name,
        role=body.role,
    )

    logger.info(
        "bootstrap: provisioned key_id=%s tenant=%s role=%s plan=%s",
        key_id, tenant_id, body.role, body.plan,
    )

    return {
        "key_id": key_id,
        "tenant_id": tenant_id,
        "name": key_name,
        "role": body.role,
        "plan": body.plan,
        "status": "created",
        "message": "API key provisioned. The token you supplied is now active.",
    }


# ---------------------------------------------------------------------------
# IP Allowlist management (Phase 2.3)
# ---------------------------------------------------------------------------

class IPAllowlistRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=100, description="Tenant ID")
    cidr: str = Field(..., min_length=7, max_length=50, description="CIDR notation (e.g. 203.0.113.0/24 or 10.0.0.1/32)")


def _validate_cidr(cidr: str) -> str:
    """Raise HTTPException 400 if cidr is not a valid network address."""
    try:
        # strict=False allows host bits to be set (e.g. 192.168.1.5/24 → 192.168.1.0/24)
        net = ipaddress.ip_network(cidr, strict=False)
        return str(net)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid CIDR '{cidr}': {exc}")


@router.post("/ip-allowlist", status_code=201)
async def add_ip_allowlist(request: Request, body: IPAllowlistRequest):
    """Add a CIDR to a tenant's IP allowlist.

    Once a tenant has at least one CIDR entry, all requests from IPs outside
    those ranges will be rejected with HTTP 403.

    Protected by ``X-Bootstrap-Secret`` header.
    """
    _check_bootstrap_secret(request)
    normalized_cidr = _validate_cidr(body.cidr)
    db = get_db()
    db.add_ip_to_allowlist(body.tenant_id, normalized_cidr)
    logger.info("ip_allowlist_add: tenant=%s cidr=%s", body.tenant_id, normalized_cidr)
    return {
        "tenant_id": body.tenant_id,
        "cidr": normalized_cidr,
        "status": "added",
        "message": f"CIDR {normalized_cidr} added to allowlist for tenant {body.tenant_id}.",
    }


@router.delete("/ip-allowlist", status_code=200)
async def remove_ip_allowlist(request: Request, body: IPAllowlistRequest):
    """Remove a CIDR from a tenant's IP allowlist.

    If the allowlist becomes empty, the tenant reverts to no IP restriction.

    Protected by ``X-Bootstrap-Secret`` header.
    """
    _check_bootstrap_secret(request)
    normalized_cidr = _validate_cidr(body.cidr)
    db = get_db()
    removed = db.remove_ip_from_allowlist(body.tenant_id, normalized_cidr)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail=f"CIDR {normalized_cidr} not found in allowlist for tenant {body.tenant_id}.",
        )
    logger.info("ip_allowlist_remove: tenant=%s cidr=%s", body.tenant_id, normalized_cidr)
    return {
        "tenant_id": body.tenant_id,
        "cidr": normalized_cidr,
        "status": "removed",
        "message": f"CIDR {normalized_cidr} removed from allowlist for tenant {body.tenant_id}.",
    }


@router.get("/ip-allowlist/{tenant_id}", status_code=200)
async def get_ip_allowlist(tenant_id: str, request: Request):
    """Return all CIDRs in the IP allowlist for a tenant.

    An empty list means no IP restriction is enforced for that tenant.

    Protected by ``X-Bootstrap-Secret`` header.
    """
    _check_bootstrap_secret(request)
    db = get_db()
    cidrs = db.get_ip_allowlist(tenant_id)
    return {
        "tenant_id": tenant_id,
        "cidrs": cidrs,
        "count": len(cidrs),
        "restricted": len(cidrs) > 0,
    }


@router.post("/unlock-ip")
async def unlock_ip(request: Request):
    """Clear brute force lockout for an IP address.

    Protected by X-Bootstrap-Secret. Deletes all brute force counters for
    the given IP so that it can attempt authentication again immediately.
    """
    _check_bootstrap_secret(request)
    body = await request.json()
    ip = body.get("ip", "").strip()
    if not ip:
        raise HTTPException(status_code=400, detail="ip field required")
    db = get_db()
    try:
        with db._get_connection() as conn:
            conn.execute("DELETE FROM counters WHERE key LIKE ?", (f"brute_force:{ip}:%",))
            conn.commit()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")
    logger.info("[admin/unlock-ip] unlocked ip=%s", ip)
    return {"ip": ip, "status": "unlocked"}
