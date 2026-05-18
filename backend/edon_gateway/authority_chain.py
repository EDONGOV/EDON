"""Authority chain — explicit conflict resolution ordering for the EDON governor.

When multiple subsystems produce conflicting signals under partial failure,
this module defines which subsystem wins. Priority 0 is highest.

Any change to AUTHORITY_PRECEDENCE is a safety-significant change that must be
reviewed and reflected in docs/safety/authority-chain.md.
"""
from typing import Optional

AUTHORITY_PRECEDENCE: list[tuple[int, str, str]] = [
    (0, "AUDIT_WRITE",        "Audit write failure for fail-closed actions → BLOCK"),
    (1, "ESTOP",              "Emergency stop active → BLOCK, no exceptions"),
    (2, "BLAST_RADIUS_FLOOR", "Governor minimum risk floor overrides policy engine verdict"),
    (3, "SESSION_BLOCK",      "Session risk accumulation block"),
    (4, "TENANT_POLICY",      "Tenant-defined rules (highest tenant priority)"),
    (5, "INTENT_CONTRACT",    "Scope and constraint checks"),
    (6, "DEFAULT",            "Default: allow if all checks pass"),
]

# Actions for which audit write failure must produce BLOCK.
# These mirror _FAILURE_MODE_REGISTRY in governor.py (fail_closed entries).
_AUDIT_REQUIRED_PATTERNS: frozenset[tuple[str, str]] = frozenset({
    ("payment", "wire_transfer"),
    ("payment", "transfer"),
    ("finance", "transfer"),
    ("database", "truncate"),
    ("database", "drop"),
})

def audit_write_required(tool_str: str, op: str) -> bool:
    """Return True if an audit write failure for this action must produce BLOCK.

    Level 0 of the authority chain: the audit record is a prerequisite for
    allowing a fail-closed action. Without a durable record, the action cannot
    be verified to have occurred, which violates the governance contract.
    """
    return (tool_str.lower(), op.lower()) in _AUDIT_REQUIRED_PATTERNS


def describe_authority_chain() -> list[dict]:
    """Return the authority chain as a list of dicts (for API/docs consumption)."""
    return [
        {"priority": p, "name": name, "description": desc}
        for p, name, desc in AUTHORITY_PRECEDENCE
    ]
