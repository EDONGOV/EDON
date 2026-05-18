"""Multi-robot workspace zone registry — conflict detection for shared spaces.

When the governor issues ALLOW for a physical action that declares a
workspace_zone, the registry records a time-limited claim for that robot.
Subsequent requests from *other* robots for the same zone are escalated or
blocked until the first robot's claim expires or is released.

Zone claims:
  robot_id:     who holds the claim
  action_id:    which action triggered the claim
  tenant_id:    tenant scoping (robots in different tenants never conflict)
  expires_at:   monotonic timestamp when the claim auto-expires
  priority:     int (lower = higher priority); used to resolve conflicts

Claim TTL:
  Taken from action param `estimated_duration_s` (default 60s), capped at
  `max_workspace_claim_ttl_s` intent constraint (default 300s).

Action param keys:
    workspace_zone: str            — zone name to claim (e.g. "assembly_cell_A")
    estimated_duration_s: float    — expected action duration (sets claim TTL)
    workspace_priority: int        — priority level (default 0; lower wins)

Intent constraint keys:
    max_workspace_claim_ttl_s: float  — hard cap on claim TTL (default 300s)
    workspace_conflict_action: str    — "block" | "escalate" (default "escalate")
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

from ..logging_config import get_logger

logger = get_logger(__name__)

_DEFAULT_TTL_S = 60.0
_MAX_TTL_CAP_S = 300.0

_lock = threading.Lock()
# (tenant_id, zone_name) → ZoneClaim
_claims: dict[tuple[str, str], "ZoneClaim"] = {}


@dataclass
class ZoneClaim:
    robot_id: str
    action_id: str
    tenant_id: str
    zone_name: str
    expires_at: float   # monotonic time
    priority: int = 0

    @property
    def active(self) -> bool:
        return time.monotonic() < self.expires_at

    def to_dict(self) -> dict:
        remaining = max(0.0, self.expires_at - time.monotonic())
        return {
            "robot_id": self.robot_id,
            "action_id": self.action_id,
            "zone_name": self.zone_name,
            "priority": self.priority,
            "expires_in_s": round(remaining, 1),
        }


@dataclass
class ConflictResult:
    conflict: bool
    holder: Optional[ZoneClaim] = None
    should_block: bool = False


def try_claim(
    robot_id: str,
    action_id: str,
    tenant_id: str,
    zone_name: str,
    estimated_duration_s: float = _DEFAULT_TTL_S,
    max_ttl_s: float = _MAX_TTL_CAP_S,
    priority: int = 0,
) -> ConflictResult:
    """Attempt to claim a workspace zone.

    If the zone is free or held by the same robot: claim it and return no conflict.
    If held by a different robot with higher or equal priority: return conflict.
    If held by a different robot with lower priority: preempt and claim.

    Args:
        robot_id: Robot requesting the zone.
        action_id: Action ID for this request.
        tenant_id: Tenant isolation key.
        zone_name: Zone name to claim.
        estimated_duration_s: How long to hold the claim.
        max_ttl_s: Hard cap on TTL.
        priority: Claim priority (lower int = higher priority).

    Returns:
        ConflictResult — if conflict=False, the claim was successfully registered.
    """
    key = (tenant_id, zone_name)
    ttl = min(float(estimated_duration_s), max_ttl_s)

    with _lock:
        existing = _claims.get(key)

        # No claim or expired
        if existing is None or not existing.active:
            _claims[key] = ZoneClaim(
                robot_id=robot_id,
                action_id=action_id,
                tenant_id=tenant_id,
                zone_name=zone_name,
                expires_at=time.monotonic() + ttl,
                priority=priority,
            )
            logger.debug(
                "[workspace] zone '%s' claimed by robot=%s action=%s ttl=%.0fs",
                zone_name, robot_id, action_id, ttl,
            )
            return ConflictResult(conflict=False)

        # Same robot renewing its own claim
        if existing.robot_id == robot_id:
            existing.expires_at = time.monotonic() + ttl
            existing.action_id = action_id
            return ConflictResult(conflict=False)

        # Different robot — check priority (lower = higher priority)
        if priority < existing.priority:
            # Requesting robot has higher priority — preempt
            logger.warning(
                "[workspace] zone '%s' preempted: robot=%s (priority %d) > robot=%s (priority %d)",
                zone_name, robot_id, priority, existing.robot_id, existing.priority,
            )
            _claims[key] = ZoneClaim(
                robot_id=robot_id,
                action_id=action_id,
                tenant_id=tenant_id,
                zone_name=zone_name,
                expires_at=time.monotonic() + ttl,
                priority=priority,
            )
            return ConflictResult(conflict=False)

        # Conflict — zone is held by a higher or equal priority robot
        return ConflictResult(conflict=True, holder=existing)


def release_claim(tenant_id: str, zone_name: str, robot_id: str) -> bool:
    """Release a zone claim. Only the holding robot can release its own claim.

    Returns True if the claim was found and released.
    """
    key = (tenant_id, zone_name)
    with _lock:
        existing = _claims.get(key)
        if existing and existing.robot_id == robot_id:
            del _claims[key]
            logger.debug("[workspace] zone '%s' released by robot=%s", zone_name, robot_id)
            return True
    return False


def release_all_claims(tenant_id: str, robot_id: str) -> int:
    """Release all zone claims held by a robot. Called on e-stop or completion."""
    released = 0
    with _lock:
        to_delete = [
            k for k, c in _claims.items()
            if k[0] == tenant_id and c.robot_id == robot_id
        ]
        for k in to_delete:
            del _claims[k]
            released += 1
    if released:
        logger.debug("[workspace] released %d zone(s) for robot=%s", released, robot_id)
    return released


def list_claims(tenant_id: Optional[str] = None) -> list[dict]:
    """Return all active zone claims, optionally filtered by tenant."""
    now = time.monotonic()
    with _lock:
        claims = [c for c in _claims.values() if c.expires_at > now]
    if tenant_id:
        claims = [c for c in claims if c.tenant_id == tenant_id]
    return [c.to_dict() for c in claims]


def evict_expired() -> int:
    """Remove expired claims. Called periodically by the heartbeat watchdog."""
    now = time.monotonic()
    evicted = 0
    with _lock:
        expired = [k for k, c in _claims.items() if c.expires_at <= now]
        for k in expired:
            del _claims[k]
            evicted += 1
    return evicted
