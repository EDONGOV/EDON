"""Audit chain verification — UE-004.

Verifies that every BLOCK and ESCALATE decision produced by the governor
has a complete, tamper-evident audit trail:

  1. policy_snapshot_hash is set (non-empty string)
  2. invariant_results list is populated
  3. Ed25519 signature present in decision.meta (or graceful fallback noted)
  4. Same input → same policy_snapshot_hash (deterministic, replayable)
  5. Different intent → different policy_snapshot_hash (scope changes are detectable)
  6. Hard-gate invariant failures never co-exist with ALLOW verdict
"""

from __future__ import annotations

import hashlib
from datetime import datetime, UTC, timedelta

import pytest

from edon_gateway.governor import EDONGovernor
from edon_gateway.schemas import Action, IntentContract, RiskLevel, Tool, Verdict


# ── Helpers ───────────────────────────────────────────────────────────────────

def _gov() -> EDONGovernor:
    return EDONGovernor()

def _email_send(risk: RiskLevel = RiskLevel.LOW) -> Action:
    return Action(
        tool=Tool.EMAIL, op="send",
        params={"to": "user@example.com", "subject": "hello"},
        estimated_risk=risk,
    )

def _db_drop() -> Action:
    return Action(
        tool=Tool.DATABASE, op="drop",
        params={"table": "users"},
        estimated_risk=RiskLevel.LOW,
    )

def _shell_exec(cmd: str = "rm -rf /") -> Action:
    return Action(
        tool=Tool.SHELL, op="execute",
        params={"command": cmd},
        estimated_risk=RiskLevel.LOW,
    )

def _intent(objective="send email", scope=None, approved=True) -> IntentContract:
    return IntentContract(
        objective=objective,
        scope=scope or {"email": ["send"]},
        constraints={},
        risk_level=RiskLevel.LOW,
        approved_by_user=approved,
    )


# ── A-001: BLOCK decisions carry policy_snapshot_hash ────────────────────────

def test_a001_block_has_policy_snapshot_hash():
    """Every BLOCK must have a non-empty policy_snapshot_hash."""
    g = _gov()
    decision = g.evaluate(_shell_exec("rm -rf /"), _intent(scope={"shell": ["execute"]}), tenant_id="audit-001")
    assert decision.verdict == Verdict.BLOCK
    assert decision.policy_snapshot_hash, (
        "UE-004: BLOCK decision missing policy_snapshot_hash — audit is not reproducible"
    )
    assert len(decision.policy_snapshot_hash) == 64, "policy_snapshot_hash should be SHA-256 hex (64 chars)"


def test_a001_escalate_has_policy_snapshot_hash():
    """Every ESCALATE must also carry a policy_snapshot_hash."""
    g = _gov()
    intent = _intent(objective="drop tables", scope={"database": ["drop"]}, approved=False)
    decision = g.evaluate(_db_drop(), intent, tenant_id="audit-001b")
    assert decision.verdict == Verdict.ESCALATE
    assert decision.policy_snapshot_hash, "UE-004: ESCALATE missing policy_snapshot_hash"


def test_a001_allow_has_policy_snapshot_hash():
    """ALLOW decisions should also be auditable."""
    g = _gov()
    decision = g.evaluate(_email_send(), _intent(), tenant_id="audit-001c")
    assert decision.verdict == Verdict.ALLOW
    assert decision.policy_snapshot_hash, "ALLOW missing policy_snapshot_hash"


# ── A-002: BLOCK decisions carry invariant_results ───────────────────────────

def test_a002_block_has_invariant_results():
    """A BLOCK decision must have a non-empty invariant_results list."""
    g = _gov()
    decision = g.evaluate(_shell_exec("rm -rf /"), _intent(scope={"shell": ["execute"]}), tenant_id="audit-002")
    assert decision.verdict == Verdict.BLOCK
    assert isinstance(decision.invariant_results, list), "invariant_results should be a list"
    assert len(decision.invariant_results) > 0, (
        "UE-004: BLOCK decision has empty invariant_results — governance step that fired is untracked"
    )


def test_a002_invariant_results_have_required_fields():
    """Each invariant result must have id, status, details, and timestamp."""
    g = _gov()
    decision = g.evaluate(_shell_exec("rm -rf /"), _intent(scope={"shell": ["execute"]}), tenant_id="audit-002b")
    for inv in decision.invariant_results:
        assert "id" in inv, f"invariant missing 'id': {inv}"
        assert "status" in inv, f"invariant missing 'status': {inv}"
        assert "details" in inv, f"invariant missing 'details': {inv}"
        assert "timestamp" in inv, f"invariant missing 'timestamp': {inv}"
        assert inv["status"] in ("pass", "fail", "skip"), f"invalid status: {inv['status']}"


# ── A-003: Signature present (or graceful fallback) ───────────────────────────

def test_a003_decision_has_signature_or_logged_failure():
    """Decision meta should contain sig+kid or at minimum policy_snapshot_hash."""
    g = _gov()
    decision = g.evaluate(_email_send(), _intent(), tenant_id="audit-003")
    meta = decision.meta or {}
    # Either signed...
    if "sig" in meta and "kid" in meta:
        assert isinstance(meta["sig"], str) and len(meta["sig"]) > 0
        assert isinstance(meta["kid"], str) and len(meta["kid"]) > 0
    else:
        # ...or at minimum has policy_snapshot_hash for offline audit
        assert decision.policy_snapshot_hash, (
            "UE-004: No signature AND no policy_snapshot_hash — decision is not auditable"
        )


def test_a003_block_decision_is_signed_or_has_hash():
    """BLOCK decisions must be auditable even if signing is unavailable."""
    g = _gov()
    decision = g.evaluate(_shell_exec("rm -rf /"), _intent(scope={"shell": ["execute"]}), tenant_id="audit-003b")
    assert decision.verdict == Verdict.BLOCK
    meta = decision.meta or {}
    has_sig = "sig" in meta and "kid" in meta
    has_hash = bool(decision.policy_snapshot_hash)
    assert has_sig or has_hash, "UE-004: BLOCK decision is neither signed nor hashed"


# ── A-004: Determinism — same input → same hash ───────────────────────────────

def test_a004_same_input_same_policy_snapshot_hash():
    """Identical intent + tenant rules must produce identical policy_snapshot_hash."""
    intent = _intent(objective="send email", scope={"email": ["send"]}, approved=True)
    h1 = _gov()._compute_policy_snapshot_hash(intent, [])
    h2 = _gov()._compute_policy_snapshot_hash(intent, [])
    assert h1 == h2, "policy_snapshot_hash is not deterministic — replay audit is impossible"


def test_a004_different_scope_different_hash():
    """Changing intent scope must produce a different hash."""
    intent_narrow = _intent(scope={"email": ["read"]})
    intent_wide = _intent(scope={"email": ["send", "read", "delete"]})
    g = _gov()
    h_narrow = g._compute_policy_snapshot_hash(intent_narrow, [])
    h_wide = g._compute_policy_snapshot_hash(intent_wide, [])
    assert h_narrow != h_wide, (
        "Scope change not reflected in policy_snapshot_hash — scope drift is undetectable in audit"
    )


def test_a004_approval_change_changes_hash():
    """Changing approved_by_user must change the hash."""
    intent_approved = _intent(approved=True)
    intent_unapproved = _intent(approved=False)
    g = _gov()
    assert (
        g._compute_policy_snapshot_hash(intent_approved, []) !=
        g._compute_policy_snapshot_hash(intent_unapproved, [])
    ), "Approval change not reflected in policy_snapshot_hash"


# ── A-005: Hard gate invariant failures never coexist with ALLOW ───────────────

HARD_GATE_IDS = {
    "INV-000-ESTOP", "INV-006-INTENT-FRESH", "INV-005-MAG-AUTH",
    "INV-010-ISO15066", "INV-008-ROBOT-STABILITY",
}

def test_a005_hard_gate_fail_never_allows():
    """No ALLOW verdict may coexist with a hard gate invariant failure."""
    g = _gov()
    # Simulate: revoked intent — INV-006-INTENT-FRESH must fire as fail
    revoked = _intent()
    revoked.revoked = True
    context: dict = {}
    decision = g.evaluate(_email_send(), revoked, context=context, tenant_id="audit-005")
    assert decision.verdict == Verdict.BLOCK

    inv_results = decision.invariant_results or []
    hard_failures = [r for r in inv_results if r.get("id") in HARD_GATE_IDS and r.get("status") == "fail"]
    if hard_failures:
        assert decision.verdict != Verdict.ALLOW, (
            f"UE-004/ML invariant: hard gate failures {[r['id'] for r in hard_failures]} "
            f"must never coexist with ALLOW verdict"
        )


def test_a005_expired_intent_hard_gate_fires():
    """Expired intent must fire INV-006-INTENT-FRESH as fail and produce BLOCK."""
    g = _gov()
    expired = _intent()
    expired.expires_at = datetime.now(UTC) - timedelta(seconds=10)
    decision = g.evaluate(_email_send(), expired, tenant_id="audit-005b")
    assert decision.verdict == Verdict.BLOCK

    inv_results = decision.invariant_results or []
    freshness_inv = [r for r in inv_results if r.get("id") == "INV-006-INTENT-FRESH"]
    assert freshness_inv, "INV-006-INTENT-FRESH must be recorded for expired intent"
    assert freshness_inv[0]["status"] == "fail"


# ── A-006: Every BLOCK has a reason_code (traceability) ───────────────────────

def test_a006_block_has_reason_code():
    """Every BLOCK must have a non-null reason_code for traceability."""
    g = _gov()
    cases = [
        (_shell_exec("rm -rf /"), _intent(scope={"shell": ["execute"]})),
        (_db_drop(), _intent(objective="manage db", scope={"database": ["drop"]}, approved=False)),
    ]
    for action, intent in cases:
        decision = g.evaluate(action, intent, tenant_id="audit-006")
        if decision.verdict == Verdict.BLOCK:
            assert decision.reason_code is not None, (
                f"UE-004: BLOCK for {action.tool.value}.{action.op} has no reason_code"
            )
            assert str(decision.reason_code) != "", "reason_code must be non-empty"
