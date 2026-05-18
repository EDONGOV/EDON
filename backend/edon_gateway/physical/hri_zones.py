"""HRI Safety Zones — three-zone Human-Robot Interaction model.

Based on ISO/TS 15066 and ISO 10218-2 collaborative operation modes.
Zones are defined by distance from the nearest human in the workspace.

  STOP zone         (d < stop_m):         halt all movement immediately
  COLLABORATIVE zone (stop_m <= d < collab_m): reduce speed + apply force limits
  FREE zone         (d >= collab_m):      normal operation

Default distances (configurable via intent constraints):
  stop_m:   0.30 m  — robot must stop before entering this radius
  collab_m: 1.00 m  — robot reduces speed when human is within this radius

Speed and force modifiers in COLLABORATIVE zone:
  speed_factor:     0.50  (50% of max commanded velocity)
  force_factor:     0.50  (50% of ISO 15066 contact force limits)

Typical deployment: a 3D sensing system (lidar, vision) measures human proximity
and passes `human_proximity_m` in the action context or params.  The governor
reads this and applies the appropriate zone logic.

Intent constraint keys:
    hri_stop_zone_m: float        — override stop zone distance (default 0.30)
    hri_collab_zone_m: float      — override collaborative zone distance (default 1.00)
    hri_collab_speed_factor: float — speed multiplier in collaborative zone (default 0.50)
    hri_collab_force_factor: float — ISO force multiplier in collaborative zone (default 0.50)

Action param keys (or context keys):
    human_proximity_m: float      — distance to nearest human in metres
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class HRIZone(str, Enum):
    FREE          = "free"          # Normal operation
    COLLABORATIVE = "collaborative"  # Reduced speed + force
    STOP          = "stop"          # Halt immediately


@dataclass
class ZoneResult:
    zone: HRIZone
    human_proximity_m: float
    speed_factor: float    # Multiply requested velocity by this
    force_factor: float    # Multiply ISO force limits by this
    explanation: str


def determine_zone(
    human_proximity_m: float,
    stop_m: float = 0.30,
    collab_m: float = 1.00,
    collab_speed_factor: float = 0.50,
    collab_force_factor: float = 0.50,
) -> ZoneResult:
    """Determine the HRI zone given the distance to the nearest human.

    Args:
        human_proximity_m: Distance to nearest human (metres). Must be >= 0.
        stop_m: Stop zone boundary in metres.
        collab_m: Collaborative zone outer boundary in metres.
        collab_speed_factor: Speed multiplier when in collaborative zone.
        collab_force_factor: Force limit multiplier when in collaborative zone.

    Returns:
        ZoneResult with zone, applicable speed/force factors, and explanation.
    """
    d = max(0.0, human_proximity_m)

    if d < stop_m:
        return ZoneResult(
            zone=HRIZone.STOP,
            human_proximity_m=d,
            speed_factor=0.0,
            force_factor=0.0,
            explanation=(
                f"Human is {d:.2f}m away (stop zone threshold: {stop_m}m). "
                "All robot movement must halt immediately."
            ),
        )

    if d < collab_m:
        return ZoneResult(
            zone=HRIZone.COLLABORATIVE,
            human_proximity_m=d,
            speed_factor=collab_speed_factor,
            force_factor=collab_force_factor,
            explanation=(
                f"Human is {d:.2f}m away (collaborative zone: {stop_m}–{collab_m}m). "
                f"Speed limited to {int(collab_speed_factor*100)}%, "
                f"contact force limits reduced to {int(collab_force_factor*100)}%."
            ),
        )

    return ZoneResult(
        zone=HRIZone.FREE,
        human_proximity_m=d,
        speed_factor=1.0,
        force_factor=1.0,
        explanation=f"Human is {d:.2f}m away. Free zone — normal operation.",
    )


def zone_from_intent(constraints: dict, human_proximity_m: Optional[float]) -> Optional[ZoneResult]:
    """Evaluate HRI zone using intent constraints.

    Returns None if human_proximity_m is not provided (fail-open).
    """
    if human_proximity_m is None:
        return None
    return determine_zone(
        human_proximity_m=human_proximity_m,
        stop_m=float(constraints.get("hri_stop_zone_m", 0.30)),
        collab_m=float(constraints.get("hri_collab_zone_m", 1.00)),
        collab_speed_factor=float(constraints.get("hri_collab_speed_factor", 0.50)),
        collab_force_factor=float(constraints.get("hri_collab_force_factor", 0.50)),
    )


def apply_zone_to_velocity(requested_velocity_ms: Optional[float], zone: ZoneResult) -> Optional[float]:
    """Return the capped velocity given the zone's speed factor."""
    if requested_velocity_ms is None:
        return None
    return requested_velocity_ms * zone.speed_factor


def apply_zone_to_force_limit(iso_limit_n: float, zone: ZoneResult) -> float:
    """Return the effective ISO force limit after applying the zone's force factor."""
    return iso_limit_n * zone.force_factor
