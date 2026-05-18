"""Default system-level policy rules shipped with EDON.

These rules are kept in memory and appended (at lower priority than tenant
rules) to every governance request in ``v1_action.py``.  No database writes
are needed — the policy_rules table has a tenant FK constraint, so a pure
in-memory approach avoids that complexity while still enforcing baseline safety.

Rule action values must be "BLOCK", "ALLOW", or "ESCALATE" — the same
strings accepted by ``_apply_tenant_rules`` in ``governor.py``.
"""

from __future__ import annotations

import logging
from typing import Any, List, Dict

logger = logging.getLogger(__name__)

# Sentinel used to identify system-level rules in logs and metrics.
SYSTEM_TENANT_ID = "__system__"

# Priorities below 1000 so a tenant's own explicit rules always take precedence.
SYSTEM_DEFAULT_RULES: List[Dict[str, Any]] = [
    # ── Hard blocks: destruction-class operations ──────────────────────────
    {
        "id": "default:block database.drop",
        "name": "default:block database.drop",
        "condition_tool": "database",
        "condition_op": "drop",
        "action": "BLOCK",
        "priority": 995,
        "enabled": True,
        "description": "Schema destruction blocked by default system policy",
    },
    {
        "id": "default:block database.truncate",
        "name": "default:block database.truncate",
        "condition_tool": "database",
        "condition_op": "truncate",
        "action": "BLOCK",
        "priority": 995,
        "enabled": True,
        "description": "Bulk data wipe blocked by default system policy",
    },
    # ── Escalation required: high-impact reversible operations ─────────────
    {
        "id": "default:escalate shell.execute",
        "name": "default:escalate shell.execute",
        "condition_tool": "shell",
        "condition_op": "execute",
        "action": "ESCALATE",
        "priority": 990,
        "enabled": True,
        "description": "Shell command execution requires human confirmation",
    },
    {
        "id": "default:escalate shell.run",
        "name": "default:escalate shell.run",
        "condition_tool": "shell",
        "condition_op": "run",
        "action": "ESCALATE",
        "priority": 990,
        "enabled": True,
        "description": "Shell command execution requires human confirmation",
    },
    {
        "id": "default:escalate database.delete",
        "name": "default:escalate database.delete",
        "condition_tool": "database",
        "condition_op": "delete",
        "action": "ESCALATE",
        "priority": 985,
        "enabled": True,
        "description": "Database record deletion requires human confirmation",
    },
    {
        "id": "default:escalate file.delete",
        "name": "default:escalate file.delete",
        "condition_tool": "file",
        "condition_op": "delete",
        "action": "ESCALATE",
        "priority": 985,
        "enabled": True,
        "description": "File deletion requires human confirmation",
    },
    {
        "id": "default:escalate agent.deploy",
        "name": "default:escalate agent.deploy",
        "condition_tool": "agent",
        "condition_op": "deploy",
        "action": "ESCALATE",
        "priority": 980,
        "enabled": True,
        "description": "Deploying agents requires human sign-off",
    },
    {
        "id": "default:escalate credential.read",
        "name": "default:escalate credential.read",
        "condition_tool": "credential",
        "condition_op": "read",
        "action": "ESCALATE",
        "priority": 980,
        "enabled": True,
        "description": "Reading credentials requires human confirmation",
    },
]


def seed_default_preset(db) -> bool:
    """Set ops_commander as the active policy preset if none is configured.

    Returns True if the preset was set, False if one was already configured.
    ops_commander is the safest practical default: allows email drafting and
    calendar reads but blocks direct sends, shell access, and external sharing.
    """
    try:
        if db.get_active_policy_preset():
            return False
        db.set_active_policy_preset("ops_commander", applied_by="system_defaults")
        logger.info("Active policy preset set to 'ops_commander' (system default)")
        return True
    except Exception as exc:
        logger.warning("seed_default_preset failed (non-fatal): %s", exc)
        return False
