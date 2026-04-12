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
from datetime import datetime, UTC, timedelta

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

    # --- Create API key (always sandbox for new tenants) ---
    key_name = body.name or f"{tenant_id}-sandbox-key"
    key_id = db.create_api_key(
        tenant_id=tenant_id,
        key_hash=key_hash,
        name=key_name,
        role=body.role,
        is_sandbox=True,
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
        "sandbox": True,
        "message": "API key provisioned. Tenant starts in sandbox (shadow) mode — no actions will be blocked until you go live.",
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


# ---------------------------------------------------------------------------
# Tenant management
# ---------------------------------------------------------------------------

@router.get("/tenants")
async def list_tenants(request: Request):
    """List all tenants. Protected by X-Bootstrap-Secret."""
    _check_bootstrap_secret(request)
    db = get_db()
    try:
        tenants_raw = db.list_tenants() if hasattr(db, "list_tenants") else []
    except Exception:
        tenants_raw = []
    tenants = []
    for t in tenants_raw:
        tid = t.get("id") or t.get("tenant_id", "")
        keys = []
        try:
            keys = db.list_api_keys(tid) if hasattr(db, "list_api_keys") else []
        except Exception:
            pass
        active_keys = [k for k in keys if k.get("status") == "active"]
        tenants.append({
            "tenant_id": tid,
            "plan": t.get("plan", "free"),
            "status": t.get("status", "active"),
            "created_at": t.get("created_at"),
            "updated_at": t.get("updated_at"),
            "active_key_count": len(active_keys),
            "total_key_count": len(keys),
        })
    return {"tenants": tenants, "count": len(tenants)}


@router.patch("/tenants/{tenant_id}")
async def update_tenant(tenant_id: str, request: Request):
    """Update tenant plan or status. Protected by X-Bootstrap-Secret."""
    _check_bootstrap_secret(request)
    body = await request.json()
    db = get_db()
    now = datetime.now(UTC).isoformat()
    updates = []
    params = []
    if "plan" in body:
        updates.append("plan = ?")
        params.append(body["plan"])
    if "status" in body:
        updates.append("status = ?")
        params.append(body["status"])
    if not updates:
        raise HTTPException(status_code=400, detail="No updatable fields provided")
    updates.append("updated_at = ?")
    params.append(now)
    params.append(tenant_id)
    try:
        with db._get_connection() as conn:
            conn.execute(f"UPDATE tenants SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    tenant = db.get_tenant(tenant_id) or {}
    return {"tenant_id": tenant_id, "plan": tenant.get("plan"), "status": tenant.get("status")}


@router.post("/tenants/{tenant_id}/support-key")
async def create_support_key(tenant_id: str, request: Request):
    """Create a temporary support key for a tenant. Protected by X-Bootstrap-Secret."""
    _check_bootstrap_secret(request)
    body = await request.json()
    label = body.get("label") or f"support-{uuid.uuid4().hex[:8]}"
    raw_key = secrets.token_hex(32)
    key_hash = hash_api_key_fast(raw_key)
    db = get_db()
    key_id = db.create_api_key(tenant_id=tenant_id, key_hash=key_hash, name=label, role="operator")
    logger.info("support_key_created: tenant=%s key_id=%s label=%s", tenant_id, key_id, label)
    try:
        now = datetime.now(UTC).isoformat()
        with db._get_connection() as conn:
            conn.execute(
                "INSERT INTO admin_audit_log (id, action_type, tenant_affected, performed_by_ip, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), "support_key_created", tenant_id,
                 request.client.host if request.client else "unknown",
                 '{"label":"' + label + '"}', now),
            )
            conn.commit()
    except Exception:
        pass
    return {"key": raw_key, "key_id": key_id, "tenant_id": tenant_id, "label": label}


# ---------------------------------------------------------------------------
# Per-tenant shadow mode (sandbox) control
# ---------------------------------------------------------------------------

@router.get("/tenants/{tenant_id}/shadow-mode")
async def get_tenant_shadow_mode(tenant_id: str, request: Request):
    """Get sandbox/shadow mode status for a tenant. Protected by X-Bootstrap-Secret."""
    _check_bootstrap_secret(request)
    db = get_db()
    enabled = db.get_shadow_mode(tenant_id) if hasattr(db, "get_shadow_mode") else False
    return {"tenant_id": tenant_id, "sandbox": enabled, "enabled": enabled}


@router.post("/tenants/{tenant_id}/go-live")
async def tenant_go_live(tenant_id: str, request: Request):
    """Provision a live (non-sandbox) key for a tenant and mark them as live.

    Returns the new live key once — store it securely.
    Protected by X-Bootstrap-Secret.
    """
    _check_bootstrap_secret(request)
    body = await request.json()
    label = body.get("label") or f"{tenant_id}-live-key"
    db = get_db()

    raw_key = secrets.token_hex(32)
    key_hash = hash_api_key_fast(raw_key)
    key_id = db.create_api_key(
        tenant_id=tenant_id,
        key_hash=key_hash,
        name=label,
        role="admin",
        is_sandbox=False,
    )
    logger.info("admin.go_live: tenant=%s key_id=%s", tenant_id, key_id)

    # Store raw key for in-console claim (expires in 48h)
    now = datetime.now(UTC)
    expires_at = (now + timedelta(hours=48)).isoformat()
    try:
        with db._get_connection() as conn:
            # Clear any previous unclaimed record for this tenant
            conn.execute("DELETE FROM pending_live_keys WHERE tenant_id = ?", (tenant_id,))
            conn.execute(
                "INSERT INTO pending_live_keys (id, tenant_id, raw_key, key_id, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), tenant_id, raw_key, key_id, now.isoformat(), expires_at),
            )
            conn.execute(
                "INSERT INTO admin_audit_log (id, action_type, tenant_affected, performed_by_ip, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), "gone_live", tenant_id,
                 request.client.host if request.client else "unknown",
                 '{"key_id":"' + key_id + '"}', now.isoformat()),
            )
            conn.commit()
    except Exception as e:
        logger.warning("go_live: could not store pending key: %s", e)

    return {
        "tenant_id": tenant_id,
        "key_id": key_id,
        "label": label,
        "sandbox": False,
        "pending_claim": True,
        "message": "Live key created and waiting for client to claim in their console (48h window).",
    }


@router.post("/tenants/{tenant_id}/shadow-mode")
async def set_tenant_shadow_mode(tenant_id: str, request: Request):
    """Enable or disable tenant-level shadow mode. Protected by X-Bootstrap-Secret."""
    _check_bootstrap_secret(request)
    body = await request.json()
    enabled = bool(body.get("enabled", False))
    db = get_db()
    if hasattr(db, "set_shadow_mode"):
        db.set_shadow_mode(tenant_id, enabled)
    action = "sandbox_enabled" if enabled else "shadow_mode_disabled"
    logger.info("admin.%s: tenant=%s", action, tenant_id)
    return {"tenant_id": tenant_id, "sandbox": enabled, "enabled": enabled, "ok": True}


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

@router.get("/audit-log")
async def get_audit_log(request: Request, limit: int = 50, offset: int = 0):
    """Return admin audit log entries. Protected by X-Bootstrap-Secret."""
    _check_bootstrap_secret(request)
    db = get_db()
    try:
        with db._get_connection() as conn:
            # Ensure table exists
            conn.execute("""
                CREATE TABLE IF NOT EXISTS admin_audit_log (
                    id TEXT PRIMARY KEY,
                    action_type TEXT NOT NULL,
                    tenant_affected TEXT,
                    performed_by_ip TEXT,
                    details TEXT DEFAULT '{}',
                    bootstrap_key_hint TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()
            rows = conn.execute(
                "SELECT * FROM admin_audit_log ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset)
            ).fetchall()
            total = conn.execute("SELECT COUNT(*) FROM admin_audit_log").fetchone()[0]
    except Exception as e:
        return {"entries": [], "total": 0}

    entries = []
    import json
    for row in rows:
        d = dict(row)
        try:
            d["details"] = json.loads(d.get("details") or "{}")
        except Exception:
            d["details"] = {}
        entries.append(d)
    return {"entries": entries, "total": total}


# ---------------------------------------------------------------------------
# Contracts (ARR tracking)
# ---------------------------------------------------------------------------

@router.get("/contracts")
async def list_contracts(request: Request):
    """List all contracts. Protected by X-Bootstrap-Secret."""
    _check_bootstrap_secret(request)
    db = get_db()
    import json
    try:
        with db._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS contracts (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT,
                    client_name TEXT NOT NULL,
                    arr REAL DEFAULT 0,
                    status TEXT DEFAULT 'active',
                    start_date TEXT,
                    end_date TEXT,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()
            rows = conn.execute("SELECT * FROM contracts ORDER BY created_at DESC").fetchall()
    except Exception:
        return {"contracts": [], "total_arr": 0}
    contracts = [dict(r) for r in rows]
    total_arr = sum(c.get("arr", 0) or 0 for c in contracts if c.get("status") == "active")
    return {"contracts": contracts, "total_arr": total_arr}


@router.post("/contracts", status_code=201)
async def create_contract(request: Request):
    """Create a contract. Protected by X-Bootstrap-Secret."""
    _check_bootstrap_secret(request)
    body = await request.json()
    db = get_db()
    now = datetime.now(UTC).isoformat()
    cid = str(uuid.uuid4())
    try:
        with db._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS contracts (
                    id TEXT PRIMARY KEY, tenant_id TEXT, client_name TEXT NOT NULL,
                    arr REAL DEFAULT 0, status TEXT DEFAULT 'active',
                    start_date TEXT, end_date TEXT, notes TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                )
            """)
            conn.execute(
                "INSERT INTO contracts (id, tenant_id, client_name, arr, status, start_date, end_date, notes, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (cid, body.get("tenant_id"), body.get("client_name", ""), body.get("arr", 0),
                 body.get("status", "active"), body.get("start_date"), body.get("end_date"),
                 body.get("notes"), now, now)
            )
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"id": cid, "status": "created"}


@router.patch("/contracts/{contract_id}")
async def update_contract(contract_id: str, request: Request):
    """Update a contract. Protected by X-Bootstrap-Secret."""
    _check_bootstrap_secret(request)
    body = await request.json()
    db = get_db()
    now = datetime.now(UTC).isoformat()
    allowed = {"tenant_id", "client_name", "arr", "status", "start_date", "end_date", "notes"}
    updates = [f"{k} = ?" for k in body if k in allowed]
    params = [body[k] for k in body if k in allowed]
    if not updates:
        raise HTTPException(status_code=400, detail="No updatable fields")
    updates.append("updated_at = ?")
    params.append(now)
    params.append(contract_id)
    try:
        with db._get_connection() as conn:
            conn.execute(f"UPDATE contracts SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"id": contract_id, "status": "updated"}


@router.delete("/contracts/{contract_id}")
async def delete_contract(contract_id: str, request: Request):
    """Delete a contract. Protected by X-Bootstrap-Secret."""
    _check_bootstrap_secret(request)
    db = get_db()
    try:
        with db._get_connection() as conn:
            conn.execute("DELETE FROM contracts WHERE id = ?", (contract_id,))
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"id": contract_id, "status": "deleted"}


# ---------------------------------------------------------------------------
# Usage analytics
# ---------------------------------------------------------------------------

@router.get("/usage")
async def get_usage(request: Request, period: int = 30):
    """Return usage stats per tenant. Protected by X-Bootstrap-Secret."""
    _check_bootstrap_secret(request)
    db = get_db()
    try:
        with db._get_connection() as conn:
            from_ts = datetime.now(UTC).replace(microsecond=0)
            import datetime as dt_mod
            from_ts = (datetime.now(UTC) - dt_mod.timedelta(days=period)).isoformat()
            rows = conn.execute("""
                SELECT agent_id, decision_verdict, COUNT(*) as cnt
                FROM decisions
                WHERE timestamp >= ?
                GROUP BY agent_id, decision_verdict
            """, (from_ts,)).fetchall()
    except Exception:
        return {"period_days": period, "totals": {"total_decisions": 0, "unique_agents": 0}, "by_tenant": []}

    # Group by tenant (derive from agent registrations)
    agent_tenant: dict = {}
    try:
        with db._get_connection() as conn:
            agent_rows = conn.execute("SELECT agent_id, tenant_id FROM agents").fetchall()
            for r in agent_rows:
                agent_tenant[r[0]] = r[1]
    except Exception:
        pass

    tenant_stats: dict = {}
    for row in rows:
        agent_id = row[0]
        tid = agent_tenant.get(agent_id, "unknown")
        if tid not in tenant_stats:
            tenant_stats[tid] = {"tenant_id": tid, "total_decisions": 0, "unique_agents": set()}
        tenant_stats[tid]["total_decisions"] += row[2]
        tenant_stats[tid]["unique_agents"].add(agent_id)

    by_tenant = [
        {"tenant_id": v["tenant_id"], "total_decisions": v["total_decisions"], "unique_agents": len(v["unique_agents"])}
        for v in tenant_stats.values()
    ]
    total = sum(t["total_decisions"] for t in by_tenant)
    return {
        "period_days": period,
        "totals": {"total_decisions": total, "unique_agents": sum(t["unique_agents"] for t in by_tenant)},
        "by_tenant": by_tenant,
    }


# ---------------------------------------------------------------------------
# Feature flags per tenant
# ---------------------------------------------------------------------------

@router.get("/feature-flags/{tenant_id}")
async def get_feature_flags(tenant_id: str, request: Request):
    """Get feature flags for a tenant. Protected by X-Bootstrap-Secret."""
    _check_bootstrap_secret(request)
    db = get_db()
    import json
    try:
        with db._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS feature_flags (
                    tenant_id TEXT NOT NULL, flag TEXT NOT NULL, enabled INTEGER DEFAULT 0,
                    updated_at TEXT, PRIMARY KEY (tenant_id, flag)
                )
            """)
            conn.commit()
            rows = conn.execute("SELECT flag, enabled FROM feature_flags WHERE tenant_id = ?", (tenant_id,)).fetchall()
    except Exception:
        return {"tenant_id": tenant_id, "flags": {}}
    return {"tenant_id": tenant_id, "flags": {r[0]: bool(r[1]) for r in rows}}


@router.post("/feature-flags")
async def set_feature_flag(request: Request):
    """Set a feature flag for a tenant. Protected by X-Bootstrap-Secret."""
    _check_bootstrap_secret(request)
    body = await request.json()
    tenant_id = body.get("tenant_id")
    flag = body.get("flag")
    enabled = bool(body.get("enabled", False))
    if not tenant_id or not flag:
        raise HTTPException(status_code=400, detail="tenant_id and flag required")
    db = get_db()
    now = datetime.now(UTC).isoformat()
    try:
        with db._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS feature_flags (
                    tenant_id TEXT NOT NULL, flag TEXT NOT NULL, enabled INTEGER DEFAULT 0,
                    updated_at TEXT, PRIMARY KEY (tenant_id, flag)
                )
            """)
            conn.execute(
                "INSERT INTO feature_flags (tenant_id, flag, enabled, updated_at) VALUES (?,?,?,?) ON CONFLICT(tenant_id, flag) DO UPDATE SET enabled=excluded.enabled, updated_at=excluded.updated_at",
                (tenant_id, flag, int(enabled), now)
            )
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"tenant_id": tenant_id, "flag": flag, "enabled": enabled}


# ---------------------------------------------------------------------------
# Unlock IP (existing)
# ---------------------------------------------------------------------------

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
