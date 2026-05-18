"""Communication loss watchdog for physical robots.

Each robot registers with a declared TTL and fail-safe posture. A background
thread checks every 5 seconds. If a robot misses its heartbeat deadline:
  1. E-stop is triggered
  2. Alert fires (physical.comm_loss)
  3. All workspace zone claims are released

The fail-safe posture is embedded in every ALLOW response so the robot knows
what to do if it loses contact with the gateway mid-action:
  "freeze"            — stop all joints immediately, hold position
  "complete_and_halt" — finish current primitive, then stop and wait
  "controlled_descent"— lower payload/limbs to ground safely, then freeze
  "safe_home"         — return to declared home position if reachable

Registration happens via POST /v1/robots/{robot_id}/heartbeat with body:
    {"ttl_s": 10, "comm_loss_posture": "freeze", "tenant_id": "..."}

Subsequent heartbeats are POST /v1/robots/{robot_id}/heartbeat with empty body
(or any body — just the POST counts).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from ..logging_config import get_logger

logger = get_logger(__name__)

_CHECK_INTERVAL_S = 5.0

VALID_POSTURES = frozenset({"freeze", "complete_and_halt", "controlled_descent", "safe_home"})
DEFAULT_POSTURE = "freeze"
DEFAULT_TTL_S = 10


@dataclass
class RobotHeartbeat:
    robot_id: str
    tenant_id: str
    ttl_s: float
    comm_loss_posture: str
    last_heartbeat: float = field(default_factory=time.monotonic)
    registered_at: float = field(default_factory=time.monotonic)
    missed_count: int = 0

    @property
    def deadline(self) -> float:
        return self.last_heartbeat + self.ttl_s

    @property
    def is_overdue(self) -> bool:
        return time.monotonic() > self.deadline


_lock = threading.Lock()
_registry: dict[str, RobotHeartbeat] = {}  # robot_id → heartbeat
_watchdog_thread: Optional[threading.Thread] = None
_running = False


# ── Public API ─────────────────────────────────────────────────────────────────

def register(
    robot_id: str,
    tenant_id: str,
    ttl_s: float = DEFAULT_TTL_S,
    comm_loss_posture: str = DEFAULT_POSTURE,
) -> RobotHeartbeat:
    """Register or re-register a robot for heartbeat monitoring."""
    posture = comm_loss_posture if comm_loss_posture in VALID_POSTURES else DEFAULT_POSTURE
    hb = RobotHeartbeat(
        robot_id=robot_id,
        tenant_id=tenant_id,
        ttl_s=max(1.0, float(ttl_s)),
        comm_loss_posture=posture,
    )
    with _lock:
        _registry[robot_id] = hb
    logger.debug(
        "[heartbeat] registered robot=%s ttl=%.0fs posture=%s",
        robot_id, ttl_s, posture,
    )
    _ensure_watchdog_running()
    return hb


def record_heartbeat(robot_id: str) -> Optional[RobotHeartbeat]:
    """Record a heartbeat ping from a robot. Returns the registration or None."""
    with _lock:
        hb = _registry.get(robot_id)
        if hb is None:
            return None
        hb.last_heartbeat = time.monotonic()
        hb.missed_count = 0
    return hb


def deregister(robot_id: str) -> bool:
    with _lock:
        if robot_id in _registry:
            del _registry[robot_id]
            return True
    return False


def get_posture(robot_id: str) -> str:
    """Return the declared comm_loss_posture for a robot, or the default."""
    with _lock:
        hb = _registry.get(robot_id)
    return hb.comm_loss_posture if hb else DEFAULT_POSTURE


def list_registrations(tenant_id: Optional[str] = None) -> list[dict]:
    with _lock:
        entries = list(_registry.values())
    if tenant_id:
        entries = [e for e in entries if e.tenant_id == tenant_id]
    now = time.monotonic()
    return [
        {
            "robot_id": e.robot_id,
            "tenant_id": e.tenant_id,
            "ttl_s": e.ttl_s,
            "comm_loss_posture": e.comm_loss_posture,
            "overdue": e.is_overdue,
            "seconds_until_deadline": round(e.deadline - now, 1),
            "missed_count": e.missed_count,
        }
        for e in entries
    ]


# ── Watchdog ───────────────────────────────────────────────────────────────────

def _ensure_watchdog_running() -> None:
    global _watchdog_thread, _running
    if _running and _watchdog_thread and _watchdog_thread.is_alive():
        return
    _running = True
    _watchdog_thread = threading.Thread(
        target=_watchdog_loop, daemon=True, name="edon-heartbeat-watchdog"
    )
    _watchdog_thread.start()
    logger.info("[heartbeat] watchdog started")


def _watchdog_loop() -> None:
    global _running
    while _running:
        try:
            _check_heartbeats()
            from .workspace_registry import evict_expired
            evict_expired()
            from ..physical.execution_monitor import evict_old_states
            evict_old_states()
        except Exception as exc:
            logger.debug("[heartbeat] watchdog iteration error: %s", exc)
        time.sleep(_CHECK_INTERVAL_S)


def _check_heartbeats() -> None:
    with _lock:
        overdue = [hb for hb in _registry.values() if hb.is_overdue]

    for hb in overdue:
        with _lock:
            hb.missed_count += 1
        missed = hb.missed_count

        # Only fire e-stop on first missed beat — avoid repeated triggers
        if missed != 1:
            continue

        logger.warning(
            "[heartbeat] COMM LOSS robot=%s tenant=%s ttl=%.0fs posture=%s",
            hb.robot_id, hb.tenant_id, hb.ttl_s, hb.comm_loss_posture,
        )

        # Trigger e-stop
        try:
            from ..estop import trigger_estop
            trigger_estop(
                robot_id=hb.robot_id,
                reason=f"Communication loss — no heartbeat for {hb.ttl_s:.0f}s",
                triggered_by="heartbeat_watchdog",
                tenant_id=hb.tenant_id,
            )
        except Exception as exc:
            logger.debug("[heartbeat] e-stop trigger failed: %s", exc)

        # Release workspace zone claims
        try:
            from .workspace_registry import release_all_claims
            release_all_claims(hb.tenant_id, hb.robot_id)
        except Exception as exc:
            logger.debug("[heartbeat] workspace release failed: %s", exc)

        # Fire alert
        try:
            from ..alerts.dispatcher import _dispatch
            _dispatch("physical.comm_loss", {
                "robot_id": hb.robot_id,
                "tenant_id": hb.tenant_id,
                "ttl_s": hb.ttl_s,
                "comm_loss_posture": hb.comm_loss_posture,
                "message": (
                    f"Robot '{hb.robot_id}' stopped sending heartbeats. "
                    f"E-stop triggered. Declared fail-safe posture: {hb.comm_loss_posture}."
                ),
            })
        except Exception as exc:
            logger.debug("[heartbeat] alert dispatch failed: %s", exc)
