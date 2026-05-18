"""Trajectory validation for physical robot actions.

Validates a sequence of waypoints before issuing ALLOW, catching unsafe
intermediate states that are invisible to point-in-time param checks.

Waypoint schema (all fields optional except position):
    {
        "position": {"x": float, "y": float, "z": float},  # metres, world frame
        "velocity_ms": float,          # instantaneous speed at this waypoint
        "joint_angles": {              # degrees or radians (consistent across waypoints)
            "shoulder_pitch": float,
            "elbow": float,
            ...
        },
        "contact_force_n": float,      # predicted contact force if applicable
        "target_body_region": str,     # body region for contact_force_n
        "zone": str,                   # workspace zone name at this waypoint
        "timestamp_ms": int,           # optional timing label
    }

Intent constraint keys that activate validation:
    trajectory_validator_url: str   — external motion planner webhook (optional)
    max_velocity_ms: float          — checked at every waypoint
    no_go_zones: list[str]          — zone names blocked at every waypoint
    iso15066_enabled: bool          — check contact forces at every waypoint
    hri_stop_zone_m: float          — HRI stop zone for trajectory waypoints
    hri_collab_zone_m: float        — HRI collaborative zone

External validator contract (POST trajectory_validator_url):
    Request:  {"trajectory": [...], "action_id": str, "robot_id": str}
    Response: {"valid": bool, "violations": [{"waypoint": int, "reason": str}]}
    Timeout:  3 seconds — fail-open if unreachable
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import requests

from .iso15066 import check_contact_forces
from .hri_zones import determine_zone, HRIZone

logger = logging.getLogger(__name__)

_EXTERNAL_VALIDATOR_TIMEOUT = 3.0


@dataclass
class TrajectoryViolation:
    waypoint_index: int
    reason: str
    severity: str = "block"  # "block" or "escalate"


@dataclass
class TrajectoryReport:
    valid: bool
    violations: list[TrajectoryViolation] = field(default_factory=list)
    waypoint_count: int = 0
    checked_by: str = "builtin"  # "builtin" | "external" | "both"

    def first_violation_summary(self) -> str:
        if not self.violations:
            return "No violations"
        v = self.violations[0]
        extra = f" (+{len(self.violations)-1} more)" if len(self.violations) > 1 else ""
        return f"Waypoint {v.waypoint_index}: {v.reason}{extra}"


def validate_trajectory(
    trajectory: list[dict[str, Any]],
    constraints: dict,
    action_id: str = "",
    robot_id: str = "",
    human_proximity_m: Optional[float] = None,
) -> TrajectoryReport:
    """Run built-in + optional external trajectory validation.

    Args:
        trajectory: List of waypoint dicts.
        constraints: Intent constraint dict.
        action_id: For external validator correlation.
        robot_id: For external validator correlation.
        human_proximity_m: Current distance to nearest human (metres).

    Returns:
        TrajectoryReport with valid flag and violations list.
    """
    if not trajectory:
        return TrajectoryReport(valid=True, waypoint_count=0)

    violations: list[TrajectoryViolation] = []
    max_velocity = constraints.get("max_velocity_ms")
    no_go_zones: list[str] = constraints.get("no_go_zones") or []
    iso_enabled: bool = bool(constraints.get("iso15066_enabled", False))
    contact_type: str = constraints.get("contact_type", "transient")
    stop_m: float = float(constraints.get("hri_stop_zone_m", 0.30))
    collab_m: float = float(constraints.get("hri_collab_zone_m", 1.00))

    for i, wp in enumerate(trajectory):
        if not isinstance(wp, dict):
            continue

        # Velocity check at each waypoint
        if max_velocity is not None:
            vel = wp.get("velocity_ms")
            if isinstance(vel, (int, float)) and vel > max_velocity:
                violations.append(TrajectoryViolation(
                    waypoint_index=i,
                    reason=f"velocity {vel:.2f}m/s exceeds limit {max_velocity:.2f}m/s",
                    severity="block",
                ))

        # No-go zone check at each waypoint
        if no_go_zones:
            wp_zone = wp.get("zone")
            if wp_zone and wp_zone in no_go_zones:
                violations.append(TrajectoryViolation(
                    waypoint_index=i,
                    reason=f"trajectory passes through no-go zone '{wp_zone}'",
                    severity="block",
                ))

        # ISO 15066 force check at each waypoint
        if iso_enabled:
            wp_force = wp.get("contact_force_n")
            wp_region = wp.get("target_body_region")
            wp_forces = wp.get("contact_forces")
            if wp_force is not None or wp_forces:
                iso_violations = check_contact_forces(
                    contact_force_n=wp_force,
                    target_body_region=wp_region,
                    contact_forces=wp_forces,
                    contact_type=contact_type,
                )
                for iv in iso_violations:
                    violations.append(TrajectoryViolation(
                        waypoint_index=i,
                        reason=str(iv),
                        severity="block",
                    ))

        # HRI zone check at each waypoint
        # If a waypoint carries its own human_proximity_m, use it; else use global
        wp_proximity = wp.get("human_proximity_m")
        prox = wp_proximity if isinstance(wp_proximity, (int, float)) else human_proximity_m
        if prox is not None:
            zone_result = determine_zone(prox, stop_m=stop_m, collab_m=collab_m)
            if zone_result.zone == HRIZone.STOP:
                violations.append(TrajectoryViolation(
                    waypoint_index=i,
                    reason=zone_result.explanation,
                    severity="block",
                ))
            elif zone_result.zone == HRIZone.COLLABORATIVE:
                # Check velocity respects collaborative speed factor
                vel = wp.get("velocity_ms")
                if isinstance(vel, (int, float)) and max_velocity is not None:
                    collab_max = max_velocity * zone_result.speed_factor
                    if vel > collab_max:
                        violations.append(TrajectoryViolation(
                            waypoint_index=i,
                            reason=(
                                f"velocity {vel:.2f}m/s exceeds collaborative-zone limit "
                                f"{collab_max:.2f}m/s ({int(zone_result.speed_factor*100)}% of {max_velocity:.2f}m/s)"
                            ),
                            severity="escalate",
                        ))

    builtin_report = TrajectoryReport(
        valid=len(violations) == 0,
        violations=violations,
        waypoint_count=len(trajectory),
        checked_by="builtin",
    )

    # External validator (customer's motion planner)
    external_url = constraints.get("trajectory_validator_url")
    if external_url:
        ext = _call_external_validator(external_url, trajectory, action_id, robot_id)
        if ext is not None:
            # Merge: union of violations, valid only if both pass
            all_violations = builtin_report.violations + ext.violations
            return TrajectoryReport(
                valid=builtin_report.valid and ext.valid,
                violations=all_violations,
                waypoint_count=len(trajectory),
                checked_by="both",
            )

    return builtin_report


def _call_external_validator(
    url: str,
    trajectory: list[dict],
    action_id: str,
    robot_id: str,
) -> Optional[TrajectoryReport]:
    """POST to the customer's motion planner validator. Fail-open."""
    try:
        resp = requests.post(
            url,
            json={"trajectory": trajectory, "action_id": action_id, "robot_id": robot_id},
            timeout=_EXTERNAL_VALIDATOR_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        raw_violations = data.get("violations") or []
        violations = [
            TrajectoryViolation(
                waypoint_index=v.get("waypoint", -1),
                reason=str(v.get("reason", "external validator rejection")),
                severity=v.get("severity", "block"),
            )
            for v in raw_violations
            if isinstance(v, dict)
        ]
        return TrajectoryReport(
            valid=bool(data.get("valid", True)),
            violations=violations,
            waypoint_count=len(trajectory),
            checked_by="external",
        )
    except Exception as exc:
        logger.debug("[trajectory] external validator %s failed (fail-open): %s", url, exc)
        return None
