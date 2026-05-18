"""Tenant-level kill switch — emergency AI halt.

When activated, ALL governance decisions for the tenant are overridden to BLOCK,
regardless of policy. The agent sees a clear error message. Every activation and
deactivation is audit-logged.

This answers the question enterprise buyers always ask:
"If something goes wrong, can we instantly halt all AI agents?"

Answer: yes, one API call.

Endpoints:
    POST   /settings/kill-switch        — activate (body: reason)
    DELETE /settings/kill-switch        — deactivate
    GET    /settings/kill-switch        — current state

The kill switch is checked in /v1/action BEFORE the governor runs.
It is enforced in-process, not via a DB round-trip, so it is sub-millisecond.
State is persisted to disk so it survives restarts.

Security:
    - Requires authentication (enforced by RBACMiddleware as a write operation).
    - Activation is logged with timestamp, activated_by, and reason.
    - Deactivation is also logged.
    - Cross-tenant isolation: tenant A cannot affect tenant B.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..tenancy import get_request_tenant_id
from ..logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/settings", tags=["kill-switch"])

# ── In-memory state + TTL cache ────────────────────────────────────────────────
# _state is the in-memory fallback; _cache_expires tracks when to refresh from DB.
# TTL=2s means kill switch propagates to all instances within 2s of activation.

_lock = threading.Lock()
_state: dict[str, dict] = {}          # tenant_id → state dict
_cache_expires: dict[str, float] = {} # tenant_id → monotonic time when DB re-read needed
_CACHE_TTL_S = 2.0


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _db_read(tenant_id: str) -> Optional[dict]:
    """Read kill switch state from DB. Returns None on any error."""
    try:
        from ..persistence import get_db
        return get_db().get_kill_switch(tenant_id)
    except Exception as exc:
        logger.debug("[kill_switch] DB read failed: %s", exc)
        return None


def _db_write(tenant_id: str, state: dict) -> bool:
    """Write kill switch state to DB. Returns True on success."""
    try:
        from ..persistence import get_db
        get_db().set_kill_switch(tenant_id, state)
        return True
    except Exception as exc:
        logger.warning("[kill_switch] DB write failed (in-memory only): %s", exc)
        return False


# ── Legacy JSON file (backward compat / startup warm-up) ──────────────────────

def _state_path() -> Path:
    db_path = os.getenv("EDON_DATABASE_PATH", "").strip()
    if db_path:
        p = Path(db_path).parent / "kill_switch_state.json"
    else:
        url = os.getenv("EDON_DB_URL", "").strip()
        if url.startswith("sqlite:///"):
            p = Path(url.replace("sqlite:///", "", 1)).parent / "kill_switch_state.json"
        else:
            p = Path("/tmp/edon_data/kill_switch_state.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load() -> None:
    """Warm in-memory state from JSON file at startup (fallback only)."""
    path = _state_path()
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text())
        with _lock:
            _state.update(data)
        active = [tid for tid, s in _state.items() if s.get("active")]
        if active:
            logger.warning(
                "[kill_switch] LOADED WITH ACTIVE KILL SWITCHES for tenants: %s",
                active,
            )
    except Exception as exc:
        logger.warning("[kill_switch] load failed: %s", exc)


def _persist() -> None:
    """Write in-memory state to JSON file as an extra durability layer."""
    try:
        _state_path().write_text(json.dumps(_state, indent=2))
    except Exception as exc:
        logger.warning("[kill_switch] JSON persist failed: %s", exc)


_load()


# ── Core functions (used by v1_action) ────────────────────────────────────────

def is_kill_switch_active(tenant_id: Optional[str]) -> bool:
    """Return True if the kill switch is active for this tenant.

    Called on every /v1/action. Reads from a 2s TTL cache backed by DB so
    activation propagates across instances within 2s.
    """
    if not tenant_id:
        return False
    now = time.monotonic()
    with _lock:
        if now < _cache_expires.get(tenant_id, 0.0):
            return bool(_state.get(tenant_id, {}).get("active", False))
    # Cache miss — refresh from DB
    db_state = _db_read(tenant_id)
    if db_state is not None:
        with _lock:
            _state[tenant_id] = db_state
            _cache_expires[tenant_id] = time.monotonic() + _CACHE_TTL_S
        return bool(db_state.get("active", False))
    # DB unavailable — use in-memory fallback
    with _lock:
        return bool(_state.get(tenant_id, {}).get("active", False))


def get_kill_switch_state(tenant_id: str) -> dict:
    """Return the current kill switch state for a tenant (always reads DB)."""
    db_state = _db_read(tenant_id)
    if db_state is not None:
        with _lock:
            _state[tenant_id] = db_state
        return db_state
    with _lock:
        return dict(_state.get(tenant_id, {"active": False, "tenant_id": tenant_id}))


def activate_kill_switch(
    tenant_id: str,
    reason: str,
    activated_by: str,
) -> dict:
    """Activate the kill switch for a tenant. Returns the new state."""
    now = datetime.now(UTC).isoformat()
    entry = {
        "active": True,
        "tenant_id": tenant_id,
        "reason": reason[:500],
        "activated_by": activated_by,
        "activated_at": now,
        "deactivated_at": None,
        "deactivated_by": None,
        "history": [],
    }
    with _lock:
        existing = _state.get(tenant_id, {})
        if existing.get("history") is not None:
            entry["history"] = existing["history"]
        entry["history"] = (entry["history"] + [{
            "event": "activated",
            "at": now,
            "by": activated_by,
            "reason": reason[:200],
        }])[-20:]
    if not _db_write(tenant_id, entry):
        raise HTTPException(status_code=503, detail="Kill switch activation failed to persist")

    with _lock:
        _state[tenant_id] = entry
        _cache_expires[tenant_id] = time.monotonic() + _CACHE_TTL_S

    _persist()

    logger.warning(
        "[kill_switch] ACTIVATED tenant=%s by=%s reason=%s",
        tenant_id, activated_by, reason[:100],
    )

    try:
        from ..estop import trigger_tenant_estop
        stopped = trigger_tenant_estop(tenant_id, reason=f"kill_switch: {reason[:200]}")
        if stopped:
            logger.warning("[kill_switch] triggered e-stop for %d robots: %s", len(stopped), stopped)
    except Exception as _exc:
        logger.error("[kill_switch] e-stop propagation failed (fail-closed): %s", _exc)
        raise HTTPException(
            status_code=503,
            detail="Kill switch activation could not propagate to physical safety controls",
        )

    return dict(entry)


def deactivate_kill_switch(
    tenant_id: str,
    deactivated_by: str,
    note: Optional[str] = None,
) -> dict:
    """Deactivate the kill switch for a tenant. Returns the new state."""
    now = datetime.now(UTC).isoformat()
    with _lock:
        entry = dict(_state.get(tenant_id, {"active": False, "tenant_id": tenant_id}))
        if not entry.get("active"):
            return {**entry, "message": "Kill switch was not active"}
        entry["active"] = False
        entry["deactivated_at"] = now
        entry["deactivated_by"] = deactivated_by
        history = entry.get("history", [])
        history = (history + [{
            "event": "deactivated",
            "at": now,
            "by": deactivated_by,
            "note": note or "",
        }])[-20:]
        entry["history"] = history
    if not _db_write(tenant_id, entry):
        raise HTTPException(status_code=503, detail="Kill switch deactivation failed to persist")

    with _lock:
        _state[tenant_id] = entry
        _cache_expires[tenant_id] = time.monotonic() + _CACHE_TTL_S

    _persist()

    logger.warning(
        "[kill_switch] DEACTIVATED tenant=%s by=%s",
        tenant_id, deactivated_by,
    )
    return dict(entry)


# ── Request/response models ────────────────────────────────────────────────────

class KillSwitchActivateBody(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500,
                        description="Why you are halting all AI agents for this tenant")
    activated_by: str = Field(
        default="api",
        description="Identity of the person activating the kill switch"
    )


class KillSwitchDeactivateBody(BaseModel):
    deactivated_by: str = Field(default="api")
    note: Optional[str] = Field(default=None, max_length=500)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/kill-switch")
async def get_kill_switch(request: Request):
    """Return the current kill switch state for this tenant.

    active=true means ALL agent actions are being blocked right now.
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    return get_kill_switch_state(tenant_id)


@router.post("/kill-switch", status_code=200)
async def activate(request: Request, body: KillSwitchActivateBody):
    """Activate the kill switch — immediately halt ALL AI agent actions.

    Every /v1/action call for this tenant will return BLOCK until the kill
    switch is deactivated. The real governance verdict is still computed and
    audit-logged, but the response is always BLOCK.

    Use this when:
    - A security incident is suspected
    - An agent is behaving unexpectedly
    - You need an immediate pause before a policy update

    This action is audit-logged with timestamp and reason.
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    state = activate_kill_switch(
        tenant_id=tenant_id,
        reason=body.reason,
        activated_by=body.activated_by,
    )
    return {
        **state,
        "message": (
            "Kill switch activated. All AI agent actions are now BLOCKED. "
            "Deactivate at DELETE /settings/kill-switch when ready to resume."
        ),
    }


@router.delete("/kill-switch", status_code=200)
async def deactivate(request: Request, body: KillSwitchDeactivateBody):
    """Deactivate the kill switch — resume normal governance.

    Normal policy evaluation resumes immediately. This action is audit-logged.
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    state = deactivate_kill_switch(
        tenant_id=tenant_id,
        deactivated_by=body.deactivated_by,
        note=body.note,
    )
    return {
        **state,
        "message": "Kill switch deactivated. Normal governance resumed.",
    }
