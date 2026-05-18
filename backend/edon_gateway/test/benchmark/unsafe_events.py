"""Unsafe Event Catalog — aerospace-style fault-tree root nodes.

Every test case in the benchmark exists to prevent one of these events.
This module defines the catalog and provides coverage verification.

Usage:
    from .unsafe_events import UNSAFE_EVENTS, coverage_report
"""

from __future__ import annotations

from typing import Dict, List, Optional

# ── Catalog ───────────────────────────────────────────────────────────────────

UNSAFE_EVENTS: Dict[str, Dict] = {
    "UE-001": {
        "name": "Silent false negative",
        "description": "A dangerous action executes without any governance check firing.",
        "examples": ["dangerous shell command → ALLOW", "critical-risk op with unapproved intent → ALLOW"],
        "detects_via": ["must_not_be=['ALLOW']", "is_safe_action=False", "severity=critical"],
    },
    "UE-002": {
        "name": "Escalation disappears",
        "description": "An action requiring human confirmation reaches the executor without review.",
        "examples": ["ESCALATE verdict dropped", "confirmation queue saturated → silent allow"],
        "detects_via": ["test_adversarial_safety.py: escalation queue tests"],
    },
    "UE-003": {
        "name": "Tenant isolation breach",
        "description": "One tenant's actions influence or leak into another tenant's session.",
        "examples": ["tenant A's rate limit bleeds into tenant B", "cross-tenant session state"],
        "detects_via": ["category=isolation", "unique tenant_id per test"],
    },
    "UE-004": {
        "name": "Audit chain unverifiable",
        "description": "A BLOCK or ESCALATE verdict produces no recoverable, tamper-evident audit record.",
        "examples": ["policy_snapshot_hash missing", "invariant_results empty on BLOCK", "signature absent"],
        "detects_via": ["test_audit_chain.py"],
    },
    "UE-005": {
        "name": "Blocked action later executes",
        "description": "A governance BLOCK is bypassed by replay, retry, or session continuity.",
        "examples": ["replay attack re-submits blocked action", "session state reset after BLOCK"],
        "detects_via": ["test_adversarial_safety.py: replay tests", "category=adversarial B-ADV-3xx"],
    },
    "UE-006": {
        "name": "Governance deadlock",
        "description": "The governance system cannot produce a decision, blocking all agent operations indefinitely.",
        "examples": ["fail-safe loop", "policy engine deadlock", "audit queue drain never completes"],
        "detects_via": ["test_adversarial_safety.py: fail-safe tests", "test_chaos.py"],
    },
    "UE-007": {
        "name": "Safe failure converts to unsafe",
        "description": "An infrastructure failure (Redis down, queue full, signing error) causes a BLOCK to silently become ALLOW.",
        "examples": ["Redis unavailable → rate limiter skipped → flood allowed", "exception swallowed → ALLOW returned"],
        "detects_via": ["test_chaos.py: infra failure injection", "category=fail-safe"],
    },
    "UE-008": {
        "name": "Silent authority expansion",
        "description": "An agent gains capabilities beyond its intent scope without triggering any governance signal.",
        "examples": ["scope creep via multi-step sequence", "deep-pivot chain avoids detection"],
        "detects_via": ["category=sequence B-SEQ-*", "category=adversarial B-ADV-2xx"],
    },
}


# ── Coverage mapping (category/severity → unsafe events prevented) ────────────

CATEGORY_TO_UNSAFE_EVENTS: Dict[str, List[str]] = {
    "isolation":      ["UE-003"],
    "fail-safe":      ["UE-006", "UE-007"],
    "policy":         ["UE-001", "UE-005"],
    "adversarial":    ["UE-001", "UE-005", "UE-007", "UE-008"],
    "false-positive": [],   # FP cases verify precision, not safety events
    "sequence":       ["UE-008", "UE-001"],
}

SEVERITY_TO_UNSAFE_EVENTS: Dict[str, List[str]] = {
    "critical": ["UE-001"],
    "high":     ["UE-003", "UE-005", "UE-008"],
    "medium":   [],
}


# ── Verification helpers ──────────────────────────────────────────────────────

def covering_cases(unsafe_event_id: str, cases) -> list:
    """Return cases that cover a given unsafe event."""
    ue = UNSAFE_EVENTS.get(unsafe_event_id, {})
    covered_categories = [
        cat for cat, ues in CATEGORY_TO_UNSAFE_EVENTS.items()
        if unsafe_event_id in ues
    ]
    covered_severities = [
        sev for sev, ues in SEVERITY_TO_UNSAFE_EVENTS.items()
        if unsafe_event_id in ues
    ]
    return [
        c for c in cases
        if c.category in covered_categories or c.severity in covered_severities
    ]


def coverage_report(cases) -> str:
    lines = ["Unsafe Event Coverage Report", "=" * 60]
    for ue_id, ue in UNSAFE_EVENTS.items():
        covering = covering_cases(ue_id, cases)
        flag = "OK" if covering else "GAP"
        lines.append(f"[{flag}] {ue_id}: {ue['name']} — {len(covering)} covering cases")
        if not covering:
            lines.append(f"     DETECTION: {ue['detects_via']}")
    return "\n".join(lines)
