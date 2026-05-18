"""General-purpose action degradation registry.

Maps (tool_val, op) → a safe-alternative spec. When the governor would
otherwise BLOCK, it first checks this registry. If a safe alternative exists,
it returns DEGRADE instead — better UX, same safety guarantee.

To add a new degradation:
    register_degradation("mytool", "dangerous_op", "safe_op", ["degraded", "mytag"])
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Callable

logger = logging.getLogger(__name__)


@dataclass
class DegradationSpec:
    safe_op: str
    extra_tags: list[str] = field(default_factory=list)
    # Optional param transform: receives params dict, returns modified params dict
    params_transform: Optional[Callable[[dict], dict]] = None
    explanation_template: str = "Action degraded to safe alternative: {tool}.{op} → {tool}.{safe_op}"


_REGISTRY: dict[tuple[str, str], DegradationSpec] = {}


def register_degradation(
    tool_val: str,
    op: str,
    safe_op: str,
    extra_tags: Optional[list[str]] = None,
    params_transform: Optional[Callable[[dict], dict]] = None,
    explanation_template: Optional[str] = None,
) -> None:
    spec = DegradationSpec(
        safe_op=safe_op,
        extra_tags=extra_tags or ["degraded"],
        params_transform=params_transform,
        explanation_template=explanation_template or DegradationSpec.explanation_template,
    )
    _REGISTRY[(tool_val, op)] = spec


def get_degraded_action(action, reason_tags: Optional[list[str]] = None):
    """Return a degraded Action or None if no degradation is registered.

    Args:
        action: The Action dataclass instance to degrade.
        reason_tags: Additional tags to attach (e.g. ["scope_violation"]).

    Returns:
        A new Action with safe_op, or None if no degradation spec exists.
    """
    from .schemas import Action

    tool_val = action.tool.value if hasattr(action.tool, "value") else str(action.tool)
    spec = _REGISTRY.get((tool_val, action.op))
    if spec is None:
        return None

    params = action.params.copy()
    if spec.params_transform:
        try:
            params = spec.params_transform(params)
        except Exception as exc:
            logger.debug("Degradation params_transform failed: %s", exc)

    all_tags = list(action.tags or []) + spec.extra_tags + (reason_tags or [])

    return Action(
        tool=action.tool,
        op=spec.safe_op,
        params=params,
        requested_at=action.requested_at,
        source=action.source,
        tags=all_tags,
        computed_risk=action.computed_risk,
    )


def get_degradation_explanation(tool_val: str, op: str) -> Optional[str]:
    spec = _REGISTRY.get((tool_val, op))
    if spec is None:
        return None
    return spec.explanation_template.format(tool=tool_val, op=op, safe_op=spec.safe_op)


# ── Built-in registrations ────────────────────────────────────────────────────

# Email: send → draft
register_degradation(
    "email", "send", "draft",
    extra_tags=["degraded", "send_to_draft"],
    explanation_template="Email send degraded to draft: review before sending",
)
register_degradation(
    "gmail", "send", "draft",
    extra_tags=["degraded", "send_to_draft"],
    explanation_template="Gmail send degraded to draft: review before sending",
)

# File: delete → archive (soft delete)
register_degradation(
    "file", "delete", "archive",
    extra_tags=["degraded", "delete_to_archive"],
    explanation_template="File delete degraded to archive: reversible soft-delete applied",
)

# Database: delete → soft_delete (mark deleted_at, don't drop rows)
register_degradation(
    "database", "delete", "soft_delete",
    extra_tags=["degraded", "hard_delete_to_soft"],
    explanation_template="Database delete degraded to soft-delete: rows marked, not removed",
)

# Shell: execute → dry_run
register_degradation(
    "shell", "execute", "dry_run",
    extra_tags=["degraded", "execute_to_dryrun"],
    explanation_template="Shell execute degraded to dry-run: command previewed, not executed",
)
register_degradation(
    "shell", "run", "dry_run",
    extra_tags=["degraded", "run_to_dryrun"],
    explanation_template="Shell run degraded to dry-run: command previewed, not executed",
)

# GitHub: merge → draft_pr
register_degradation(
    "github", "merge", "draft_pr",
    extra_tags=["degraded", "merge_to_draft"],
    explanation_template="GitHub merge degraded to draft PR: requires human review",
)

# Physical: gate open → gate alert (notify without opening)
register_degradation(
    "gate", "open", "alert",
    extra_tags=["degraded", "open_to_alert"],
    explanation_template="Gate open degraded to alert: human must confirm physical access",
)
register_degradation(
    "gate", "unlock", "alert",
    extra_tags=["degraded", "unlock_to_alert"],
    explanation_template="Gate unlock degraded to alert: human must confirm physical access",
)

# Robot: actuate → simulate
register_degradation(
    "robot", "actuate", "simulate",
    extra_tags=["degraded", "actuate_to_simulate"],
    explanation_template="Robot actuate degraded to simulation: physical execution held",
)
register_degradation(
    "robot", "execute", "simulate",
    extra_tags=["degraded", "execute_to_simulate"],
    explanation_template="Robot execute degraded to simulation: physical execution held",
)

# Humanoid: execute/actuate → simulate (same pattern as robot)
register_degradation(
    "humanoid", "execute", "simulate",
    extra_tags=["degraded", "execute_to_simulate"],
    explanation_template="Humanoid execute degraded to simulation: physical execution held pending confirmation",
)
register_degradation(
    "humanoid", "actuate", "simulate",
    extra_tags=["degraded", "actuate_to_simulate"],
    explanation_template="Humanoid actuate degraded to simulation: physical execution held pending confirmation",
)
register_degradation(
    "humanoid", "grasp", "simulate",
    extra_tags=["degraded", "grasp_to_simulate"],
    explanation_template="Humanoid grasp degraded to simulation: confirm object and force limits",
)

# Drone: fly → hold_position (stay in place vs. full land, keeps it safe without full abort)
register_degradation(
    "drone", "fly", "hold_position",
    extra_tags=["degraded", "fly_to_hold"],
    explanation_template="Drone fly degraded to hold position: trajectory requires confirmation",
)

# Vehicle: drive → halt
register_degradation(
    "vehicle", "drive", "halt",
    extra_tags=["degraded", "drive_to_halt"],
    explanation_template="Vehicle drive degraded to halt: movement requires confirmation",
)

# Forklift: lift → lower_and_hold
register_degradation(
    "forklift", "lift", "lower_and_hold",
    extra_tags=["degraded", "lift_to_hold"],
    explanation_template="Forklift lift degraded to lower_and_hold: payload requires confirmation",
)

# Calendar: create_event → draft_event (attendees not notified)
register_degradation(
    "google_calendar", "create", "draft",
    extra_tags=["degraded", "event_to_draft"],
    explanation_template="Calendar event degraded to draft: attendees not yet notified",
)
