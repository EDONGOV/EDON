"""EDON Emergency Stop (E-Stop) — per-robot physical halt.

When an e-stop is active for a robot_id, the governor hard-blocks ALL physical
actions (HUMANOID, ROBOT, VEHICLE, DRONE, FORKLIFT, CONVEYOR) for that robot,
regardless of intent or policy.

E-stops are independent of the tenant kill switch:
  - Kill switch: halts all AI agent actions for a tenant (software layer).
  - E-stop: halts all physical commands for a specific robot (physical safety layer).

Both can be active simultaneously. Clearing one does not clear the other.

Endpoints (registered in routes/estop.py):
    POST   /v1/estop/{robot_id}    — trigger e-stop
    DELETE /v1/estop/{robot_id}    — clear e-stop
    GET    /v1/estop/{robot_id}    — get e-stop state
    GET    /v1/estop               — list all active e-stops for tenant

State is persisted to disk and survives gateway restarts.
All activations and clearances are recorded in a per-robot history ring (last 20).
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

from .logging_config import get_logger

logger = get_logger(__name__)

# ── Physical tool types that the e-stop governs ───────────────────────────────

PHYSICAL_TOOLS = frozenset({
    "humanoid", "robot", "vehicle", "drone",
    "forklift", "conveyor", "gate", "dock",
})

# ── In-memory state ────────────────────────────────────────────────────────────
# Dict: robot_id → state dict
_lock = threading.Lock()
_state: dict[str, dict] = {}


# ── Persistence ────────────────────────────────────────────────────────────────

def _state_path() -> Path:
    db_path = os.getenv("EDON_DATABASE_PATH", "").strip()
    if db_path:
        p = Path(db_path).parent / "estop_state.json"
    else:
        url = os.getenv("EDON_DB_URL", "").strip()
        if url.startswith("sqlite:///"):
            p = Path(url.replace("sqlite:///", "", 1)).parent / "estop_state.json"
        else:
            p = Path("/tmp/edon_data/estop_state.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _persist() -> None:
    try:
        _state_path().write_text(json.dumps(_state, indent=2))
    except Exception as exc:
        logger.warning("[estop] persist failed: %s", exc)


def _load() -> None:
    path = _state_path()
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text())
        with _lock:
            _state.update(data)
        active = [rid for rid, s in _state.items() if s.get("active")]
        if active:
            logger.warning("[estop] LOADED WITH ACTIVE E-STOPS for robots: %s", active)
    except Exception as exc:
        logger.warning("[estop] load failed: %s", exc)


_load()


# ── Core functions ─────────────────────────────────────────────────────────────

def is_estop_active(robot_id: Optional[str]) -> bool:
    """Return True if an e-stop is active for this robot_id.

    Called in the governor on every physical tool action — must be O(1).
    """
    if not robot_id:
        return False
    with _lock:
        return bool(_state.get(robot_id, {}).get("active", False))


def get_estop_state(robot_id: str) -> dict:
    with _lock:
        return dict(_state.get(robot_id, {"active": False, "robot_id": robot_id}))


def trigger_estop(
    robot_id: str,
    reason: str,
    triggered_by: str,
    tenant_id: Optional[str] = None,
) -> dict:
    """Trigger an e-stop for a robot. Returns the new state."""
    now = datetime.now(UTC).isoformat()
    entry = {
        "active": True,
        "robot_id": robot_id,
        "tenant_id": tenant_id or "unknown",
        "reason": reason[:500],
        "triggered_by": triggered_by,
        "triggered_at": now,
        "cleared_at": None,
        "cleared_by": None,
        "history": [],
    }
    with _lock:
        existing = _state.get(robot_id, {})
        entry["history"] = (existing.get("history", []) + [{
            "event": "triggered",
            "at": now,
            "by": triggered_by,
            "reason": reason[:200],
        }])[-20:]
        _state[robot_id] = entry
        _persist()

    logger.warning(
        "[estop] TRIGGERED robot=%s tenant=%s by=%s reason=%s",
        robot_id, tenant_id, triggered_by, reason[:100],
    )
    return dict(entry)


def clear_estop(
    robot_id: str,
    cleared_by: str,
    note: Optional[str] = None,
) -> dict:
    """Clear an e-stop for a robot. Returns the new state."""
    now = datetime.now(UTC).isoformat()
    with _lock:
        entry = dict(_state.get(robot_id, {"active": False, "robot_id": robot_id}))
        if not entry.get("active"):
            return {**entry, "message": "E-stop was not active"}
        entry["active"] = False
        entry["cleared_at"] = now
        entry["cleared_by"] = cleared_by
        history = (entry.get("history", []) + [{
            "event": "cleared",
            "at": now,
            "by": cleared_by,
            "note": note or "",
        }])[-20:]
        entry["history"] = history
        _state[robot_id] = entry
        _persist()

    logger.warning("[estop] CLEARED robot=%s by=%s", robot_id, cleared_by)
    return dict(entry)


def list_active_estops(tenant_id: Optional[str] = None) -> list[dict]:
    """Return all active e-stops, optionally filtered by tenant."""
    with _lock:
        entries = [dict(v) for v in _state.values() if v.get("active")]
    if tenant_id:
        entries = [e for e in entries if e.get("tenant_id") == tenant_id]
    return entries


def trigger_tenant_estop(tenant_id: str, reason: str) -> list[str]:
    """Trigger e-stops for all known robots belonging to a tenant.

    Called automatically when the tenant kill switch fires.
    Returns the list of robot_ids that were stopped.
    """
    with _lock:
        tenant_robots = [
            rid for rid, s in _state.items()
            if s.get("tenant_id") == tenant_id
        ]
    stopped = []
    for robot_id in tenant_robots:
        if not is_estop_active(robot_id):
            trigger_estop(robot_id, reason=reason, triggered_by="kill_switch", tenant_id=tenant_id)
            stopped.append(robot_id)
    return stopped
