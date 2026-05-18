"""Execution-time telemetry monitor for physical robot actions.

After the governor issues ALLOW, the robot controller streams telemetry here.
The monitor watches for in-execution anomalies and triggers e-stop + alerts when
thresholds are breached.

Monitored signals:
  joint_torques (dict[str, float])     — per-joint Nm; compared to max_joint_torque_nm
  contact_forces (dict[str, float])    — per-body-region N; compared to ISO 15066 limits
  position_deviation_m (float)         — deviation from planned path in metres
  velocity_ms (float)                  — current end-effector speed
  fault_code (str | None)              — hardware fault string from robot controller

Execution states: RUNNING → COMPLETED | FAULTED | ESTOP

Thread-safe in-memory store; no DB persistence (telemetry is high-frequency,
only anomalies are persisted via the alert dispatcher).
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from typing import Any, Optional

from ..logging_config import get_logger

logger = get_logger(__name__)


class ExecutionStatus(str, Enum):
    RUNNING   = "running"
    COMPLETED = "completed"
    FAULTED   = "faulted"
    ESTOP     = "estop"


@dataclass
class TelemetryReading:
    timestamp: float  # monotonic time
    joint_torques: dict[str, float] = field(default_factory=dict)
    contact_forces: dict[str, float] = field(default_factory=dict)
    position_deviation_m: Optional[float] = None
    velocity_ms: Optional[float] = None
    fault_code: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionState:
    robot_id: str
    action_id: str
    tenant_id: str
    status: ExecutionStatus = ExecutionStatus.RUNNING
    started_at: float = field(default_factory=time.monotonic)
    ended_at: Optional[float] = None
    anomaly_reason: Optional[str] = None
    telemetry_buffer: deque = field(default_factory=lambda: deque(maxlen=100))
    constraints: dict = field(default_factory=dict)

    @property
    def duration_s(self) -> float:
        end = self.ended_at or time.monotonic()
        return end - self.started_at


# ── Store ──────────────────────────────────────────────────────────────────────

_lock = threading.Lock()
# robot_id → {action_id → ExecutionState}
_store: dict[str, dict[str, ExecutionState]] = {}

# Retain completed/faulted states for this long before eviction (seconds)
_RETENTION_S = 300


def register_execution(
    robot_id: str,
    action_id: str,
    tenant_id: str,
    constraints: dict,
) -> ExecutionState:
    """Register a new in-progress execution. Called when governor returns ALLOW."""
    state = ExecutionState(
        robot_id=robot_id,
        action_id=action_id,
        tenant_id=tenant_id,
        constraints=constraints,
    )
    with _lock:
        _store.setdefault(robot_id, {})[action_id] = state
    logger.debug("[exec_monitor] registered robot=%s action=%s", robot_id, action_id)
    return state


def get_execution(robot_id: str, action_id: str) -> Optional[ExecutionState]:
    with _lock:
        return (_store.get(robot_id) or {}).get(action_id)


def get_active_executions(robot_id: str) -> list[ExecutionState]:
    with _lock:
        robot_states = dict(_store.get(robot_id) or {})
    return [s for s in robot_states.values() if s.status == ExecutionStatus.RUNNING]


def ingest_telemetry(
    robot_id: str,
    action_id: str,
    reading: TelemetryReading,
) -> Optional[str]:
    """Ingest one telemetry reading and check for anomalies.

    Returns an anomaly description string if a threshold is breached (caller
    should trigger e-stop + alert), or None if everything is within limits.
    """
    state = get_execution(robot_id, action_id)
    if state is None or state.status != ExecutionStatus.RUNNING:
        return None

    with _lock:
        state.telemetry_buffer.append(reading)

    c = state.constraints

    # Hardware fault
    if reading.fault_code:
        return _mark_faulted(state, f"Hardware fault: {reading.fault_code}")

    # Joint torque limits
    max_torque = c.get("max_joint_torque_nm")
    if max_torque is not None and reading.joint_torques:
        for joint, torque in reading.joint_torques.items():
            if isinstance(torque, (int, float)) and torque > max_torque:
                return _mark_faulted(
                    state,
                    f"Joint '{joint}' torque {torque:.1f}Nm exceeded limit {max_torque:.1f}Nm during execution",
                )

    # ISO 15066 contact forces
    if c.get("iso15066_enabled") and reading.contact_forces:
        from .iso15066 import check_contact_forces
        violations = check_contact_forces(
            contact_force_n=None,
            target_body_region=None,
            contact_forces=reading.contact_forces,
            contact_type=c.get("contact_type", "transient"),
        )
        if violations:
            return _mark_faulted(state, f"ISO 15066 contact force violation: {violations[0]}")

    # Position deviation
    max_dev = c.get("max_position_deviation_m")
    if max_dev is not None and reading.position_deviation_m is not None:
        if reading.position_deviation_m > max_dev:
            return _mark_faulted(
                state,
                f"Position deviation {reading.position_deviation_m:.3f}m exceeded limit {max_dev:.3f}m",
            )

    # Velocity during execution
    max_vel = c.get("max_velocity_ms")
    if max_vel is not None and reading.velocity_ms is not None:
        if reading.velocity_ms > max_vel:
            return _mark_faulted(
                state,
                f"Execution velocity {reading.velocity_ms:.2f}m/s exceeded limit {max_vel:.2f}m/s",
            )

    return None


def mark_completed(robot_id: str, action_id: str) -> None:
    state = get_execution(robot_id, action_id)
    if state and state.status == ExecutionStatus.RUNNING:
        with _lock:
            state.status = ExecutionStatus.COMPLETED
            state.ended_at = time.monotonic()
        logger.debug("[exec_monitor] completed robot=%s action=%s", robot_id, action_id)


def mark_estop(robot_id: str, action_id: str, reason: str) -> None:
    state = get_execution(robot_id, action_id)
    if state:
        with _lock:
            state.status = ExecutionStatus.ESTOP
            state.ended_at = time.monotonic()
            state.anomaly_reason = reason


def evict_old_states() -> int:
    """Remove completed/faulted/estop states older than _RETENTION_S. Returns count."""
    now = time.monotonic()
    evicted = 0
    with _lock:
        for robot_id in list(_store.keys()):
            robot_map = _store[robot_id]
            to_delete = [
                aid for aid, s in robot_map.items()
                if s.status != ExecutionStatus.RUNNING
                and s.ended_at is not None
                and now - s.ended_at > _RETENTION_S
            ]
            for aid in to_delete:
                del robot_map[aid]
                evicted += 1
            if not robot_map:
                del _store[robot_id]
    return evicted


def _mark_faulted(state: ExecutionState, reason: str) -> str:
    with _lock:
        state.status = ExecutionStatus.FAULTED
        state.ended_at = time.monotonic()
        state.anomaly_reason = reason
    logger.warning(
        "[exec_monitor] FAULT robot=%s action=%s reason=%s",
        state.robot_id, state.action_id, reason,
    )
    return reason
