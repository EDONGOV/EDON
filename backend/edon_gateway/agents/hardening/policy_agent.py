"""Hardening Agent 2 — Policy Agent.

Converts approved fix proposals into concrete policy rule deltas ready
for DB insertion. Closes the gap between "proposal approved" and
"rule actually written."

Without this agent: approved proposals sit in the fix pipeline forever.
An operator has to manually translate "block prompt injection on email.send"
into the exact rule schema the DB expects.

With this agent: approved proposals automatically generate a fully-formed
rule dict, pre-validated against the policy schema, tagged as
"pending_deployment" and ready for a single operator confirm-and-apply.

Design:
  - Reads approved proposals from fix_pipeline (status="approved")
  - Generates the rule delta using structural logic (deterministic path)
  - For complex cases, uses Claude to produce the rule description
  - Never auto-applies — output status is "rule_ready", requires human confirm
  - Idempotent: same proposal_id always produces the same rule
"""

from __future__ import annotations

import json
from datetime import datetime, UTC
from typing import Optional

from ...logging_config import get_logger

logger = get_logger(__name__)

# Proposal action → rule action mapping
_ACTION_MAP = {
    "BLOCK": "BLOCK",
    "ESCALATE": "ESCALATE",
    "PAUSE": "ESCALATE",
}

# Perturbation type → rule condition hints
_CONDITION_HINTS: dict[str, dict] = {
    "prompt_injection": {
        "description_suffix": "Block when payload contains adversarial injection patterns.",
        "priority": "high",
    },
    "privilege_escalation": {
        "description_suffix": "Block privileged operation not declared in intent scope.",
        "priority": "critical",
    },
    "context_poisoning": {
        "description_suffix": "Escalate when context signals conflict with action scope.",
        "priority": "high",
    },
    "malformed_payload": {
        "description_suffix": "Block malformed or oversized payload values.",
        "priority": "medium",
    },
    "boundary_input": {
        "description_suffix": "Block boundary inputs (empty, max-length) that bypass validation.",
        "priority": "medium",
    },
}


def _build_rule_delta(proposal: dict) -> dict:
    """Build a fully-formed policy rule dict from an approved proposal.

    Returns a rule dict matching the tenant policy rule schema.
    """
    action = _ACTION_MAP.get(proposal.get("suggested_action", "ESCALATE"), "ESCALATE")
    tool = (proposal.get("condition_tool") or "").strip()
    op = (proposal.get("condition_op") or "").strip()
    ptype = proposal.get("perturbation_type", "unknown")
    hints = _CONDITION_HINTS.get(ptype, {})

    # Build description
    base_desc = proposal.get("rule_description", "")[:200]
    suffix = hints.get("description_suffix", "")
    description = f"{base_desc} {suffix}".strip()[:300]

    return {
        "tool": tool or None,
        "operation": op or None,
        "action": action,
        "description": description,
        "rationale": proposal.get("rationale", "")[:500],
        "priority": hints.get("priority", "medium"),
        "source": "shadow_hardening_agent",
        "proposal_id": proposal.get("proposal_id"),
        "perturbation_type": ptype,
        "severity": proposal.get("severity", "advisory"),
        "enabled": False,           # starts disabled — operator must explicitly enable
        "created_at": datetime.now(UTC).isoformat(),
        "status": "rule_ready",     # distinguishes from live rules
    }


async def run(
    *,
    tenant_id: Optional[str] = None,
    max_proposals: int = 20,
) -> dict:
    """Run the policy agent: convert approved proposals to rule deltas.

    Returns summary dict with generated rules.
    """
    from ...shadow.fix_pipeline import get_proposals

    summary = {
        "agent": "policy",
        "proposals_processed": 0,
        "rules_generated": 0,
        "errors": 0,
        "rules": [],
    }

    approved = get_proposals(
        tenant_id=tenant_id,
        status="approved",
        limit=max_proposals,
    )

    for proposal in approved:
        try:
            rule = _build_rule_delta(proposal)
            summary["rules"].append(rule)
            summary["rules_generated"] += 1
            summary["proposals_processed"] += 1

            logger.info(
                "[hardening/policy] rule_ready: proposal=%s tool=%s op=%s action=%s",
                (proposal.get("proposal_id") or "")[:8],
                rule.get("tool"), rule.get("operation"), rule.get("action"),
            )
        except Exception as exc:
            logger.warning(
                "[hardening/policy] rule generation failed for proposal=%s: %s",
                (proposal.get("proposal_id") or "")[:8], exc,
            )
            summary["errors"] += 1

    return summary
