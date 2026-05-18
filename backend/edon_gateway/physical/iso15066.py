"""ISO/TS 15066:2016 — Contact force limits for collaborative robot operation.

Table A.2 defines maximum permissible contact forces by body region for two
contact types:
  - TRANSIENT: brief impact, robot continues moving after contact
  - QUASI_STATIC: sustained contact, robot presses against the body part

The governor uses these limits to block or escalate actions where the requested
contact_force_n and target_body_region would violate the standard.

Usage in intent constraints:
    constraints:
        iso15066_enabled: true   # opt-in; false = skip this check
        contact_type: "transient" | "quasi_static"  # default: transient

Usage in action params:
    contact_force_n: 85.0
    target_body_region: "chest"
    contact_forces: {"chest": 85.0, "upper_arm_outside": 60.0}  # multi-point
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RegionLimit:
    transient_n: float    # Max transient contact force (Newton)
    quasi_static_n: float  # Max quasi-static contact force (Newton)
    description: str


# ISO/TS 15066:2016 Annex A, Table A.2
# All values in Newtons.
BODY_REGION_LIMITS: dict[str, RegionLimit] = {
    "skull_forehead":      RegionLimit(130, 65,  "Skull and forehead"),
    "face":                RegionLimit(65,  33,  "Face (cheek, jaw, nose)"),
    "neck_front":          RegionLimit(145, 73,  "Neck, front"),
    "neck_back":           RegionLimit(145, 73,  "Neck, back/sides"),
    "back_of_head":        RegionLimit(150, 75,  "Back of head"),
    "shoulder_joint":      RegionLimit(210, 105, "Shoulder joint"),
    "upper_arm_outside":   RegionLimit(160, 80,  "Upper arm, outside"),
    "upper_arm_inside":    RegionLimit(160, 80,  "Upper arm, inside"),
    "lower_arm_outside":   RegionLimit(160, 80,  "Lower arm (forearm), outside"),
    "lower_arm_inside":    RegionLimit(160, 80,  "Lower arm (forearm), inside"),
    "hand_dorsal":         RegionLimit(140, 70,  "Hand, dorsal side"),
    "hand_palm":           RegionLimit(140, 70,  "Hand, palm"),
    "finger":              RegionLimit(140, 70,  "Fingers"),
    "chest":               RegionLimit(210, 105, "Chest"),
    "abdomen":             RegionLimit(110, 55,  "Abdomen"),
    "pelvis":              RegionLimit(180, 90,  "Pelvis"),
    "upper_leg":           RegionLimit(220, 110, "Upper leg / thigh"),
    "knee":                RegionLimit(220, 110, "Knee joint"),
    "lower_leg":           RegionLimit(130, 65,  "Lower leg"),
    "ankle_foot":          RegionLimit(130, 65,  "Ankle and foot"),
    # Aliases for common param names
    "head":                RegionLimit(130, 65,  "Head (conservative — use skull_forehead)"),
    "neck":                RegionLimit(145, 73,  "Neck (use neck_front for stricter)"),
    "arm":                 RegionLimit(160, 80,  "Arm (conservative)"),
    "hand":                RegionLimit(140, 70,  "Hand"),
    "torso":               RegionLimit(110, 55,  "Torso (conservative — abdomen limit)"),
    "leg":                 RegionLimit(130, 65,  "Leg (conservative — lower leg limit)"),
}


@dataclass
class ForceViolation:
    body_region: str
    requested_n: float
    limit_n: float
    contact_type: str

    @property
    def margin_n(self) -> float:
        return self.requested_n - self.limit_n

    def __str__(self) -> str:
        region_info = BODY_REGION_LIMITS.get(self.body_region)
        desc = region_info.description if region_info else self.body_region
        return (
            f"{desc}: {self.requested_n:.1f}N requested, "
            f"ISO limit {self.limit_n:.1f}N ({self.contact_type} contact). "
            f"Exceeds by {self.margin_n:.1f}N."
        )


def check_contact_forces(
    contact_force_n: Optional[float],
    target_body_region: Optional[str],
    contact_forces: Optional[dict[str, float]],
    contact_type: str = "transient",
) -> list[ForceViolation]:
    """Check contact forces against ISO/TS 15066 limits.

    Args:
        contact_force_n: Single force value (N) for target_body_region.
        target_body_region: Body region for contact_force_n.
        contact_forces: Dict of {region: force_n} for multi-point contact.
        contact_type: "transient" or "quasi_static".

    Returns:
        List of ForceViolation objects. Empty list = all within limits.
    """
    violations: list[ForceViolation] = []
    ct = contact_type.lower().replace("-", "_").replace(" ", "_")
    use_quasi = ct in ("quasi_static", "quasi-static", "static", "sustained")

    def _check_one(region: str, force_n: float) -> None:
        region_key = region.lower().replace(" ", "_").replace("-", "_")
        limits = BODY_REGION_LIMITS.get(region_key)
        if limits is None:
            return  # Unknown region — fail-open (don't block on unknown anatomy)
        limit = limits.quasi_static_n if use_quasi else limits.transient_n
        if force_n > limit:
            violations.append(ForceViolation(
                body_region=region_key,
                requested_n=force_n,
                limit_n=limit,
                contact_type="quasi-static" if use_quasi else "transient",
            ))

    if contact_force_n is not None and target_body_region:
        _check_one(target_body_region, contact_force_n)

    if contact_forces and isinstance(contact_forces, dict):
        for region, force in contact_forces.items():
            if isinstance(force, (int, float)):
                _check_one(region, force)

    return violations


def most_sensitive_region(regions: list[str], contact_type: str = "transient") -> Optional[str]:
    """Return the region with the lowest force limit from a list of regions."""
    use_quasi = contact_type.lower() in ("quasi_static", "quasi-static", "static")
    best_region = None
    best_limit = float("inf")
    for r in regions:
        key = r.lower().replace(" ", "_").replace("-", "_")
        limits = BODY_REGION_LIMITS.get(key)
        if limits:
            limit = limits.quasi_static_n if use_quasi else limits.transient_n
            if limit < best_limit:
                best_limit = limit
                best_region = r
    return best_region
