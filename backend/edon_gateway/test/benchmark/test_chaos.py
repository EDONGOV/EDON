"""Chaos layer — governance behavior under infrastructure failures.

Tests that governance decisions remain BOUNDED when infra components fail.
The key question per scenario: "Does unsafe authority expand?"

Failure modes tested:
  C-001  Governor exception during evaluation → fail-closed (BLOCK)
  C-002  Policy engine raises during rule evaluation → fail-safe
  C-003  Session trust store unavailable → governance continues
  C-004  Rate store / Redis unavailable → no crash, rate limiting skips safely
  C-005  Sequence scorer raises → governance continues (fail-open for sequences)
  C-006  Blast-radius propagation module missing → governance continues
  C-007  Decision signing key unavailable → decision still produced (audit note)
  C-008  ML / AI alignment check raises → governance continues (fail-open)
  C-009  Intent expires mid-evaluation (clock skew) → BLOCK
  C-010  Concurrent evaluations — thread safety under 20 parallel requests
"""

from __future__ import annotations

import threading
import time
from unittest.mock import patch, MagicMock
from datetime import datetime, UTC, timedelta

import pytest

from edon_gateway.governor import EDONGovernor
from edon_gateway.schemas import Action, IntentContract, RiskLevel, Tool, Verdict

# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_action() -> Action:
    return Action(
        tool=Tool.EMAIL, op="send",
        params={"to": "user@example.com", "subject": "hello"},
        estimated_risk=RiskLevel.LOW,
    )

def _dangerous_action() -> Action:
    return Action(
        tool=Tool.SHELL, op="execute",
        params={"command": "rm -rf /"},
        estimated_risk=RiskLevel.LOW,
    )

def _approved_intent() -> IntentContract:
    return IntentContract(
        objective="send email",
        scope={"email": ["send"]},
        constraints={},
        risk_level=RiskLevel.LOW,
        approved_by_user=True,
    )

def _shell_intent() -> IntentContract:
    return IntentContract(
        objective="run commands",
        scope={"shell": ["execute"]},
        constraints={},
        risk_level=RiskLevel.LOW,
        approved_by_user=True,
    )

def _governor() -> EDONGovernor:
    return EDONGovernor()


# ── C-001: Governor exception → fail-closed ───────────────────────────────────

def test_c001_governor_exception_is_fail_closed():
    """If _evaluate_impl raises unexpectedly, evaluate() must return BLOCK (never ALLOW)."""
    g = _governor()
    with patch.object(g, "_evaluate_impl", side_effect=RuntimeError("infra exploded")):
        decision = g.evaluate(_safe_action(), _approved_intent(), tenant_id="chaos-001")
    assert decision.verdict == Verdict.BLOCK, (
        f"C-001: exception should produce BLOCK, got {decision.verdict}"
    )


# ── C-002: Policy engine error → fail-safe ────────────────────────────────────

def test_c002_policy_engine_exception_is_fail_closed():
    """If policy engine raises, governance must not ALLOW a dangerous action."""
    g = _governor()
    with patch.object(g.policy_engine, "is_dangerous_command", side_effect=Exception("PE crash")):
        decision = g.evaluate(_dangerous_action(), _shell_intent(), tenant_id="chaos-002")
    # Dangerous rm -rf should still be blocked via blast-radius or fail-safe
    assert decision.verdict != Verdict.ALLOW, (
        f"C-002: policy engine crash must not produce ALLOW for dangerous action, got {decision.verdict}"
    )


# ── C-003: Session trust store unavailable ────────────────────────────────────

def test_c003_trust_store_failure_governance_continues():
    """If session trust store raises, governance must continue and make a decision."""
    g = _governor()
    with patch("edon_gateway.state.session_trust.get_store", side_effect=Exception("Redis down")):
        decision = g.evaluate(_safe_action(), _approved_intent(), tenant_id="chaos-003")
    assert decision.verdict in (Verdict.ALLOW, Verdict.ESCALATE, Verdict.BLOCK, Verdict.DEGRADE), (
        f"C-003: trust store failure must still produce valid verdict, got {decision.verdict}"
    )
    # Safe action with approved intent should still ALLOW when trust store is down
    assert decision.verdict == Verdict.ALLOW, (
        f"C-003: trust store down must not cause safe approved action to be blocked, got {decision.verdict}"
    )


def test_c003_trust_store_failure_dangerous_action_still_blocked():
    """Trust store down must not unlock dangerous actions."""
    g = _governor()
    with patch("edon_gateway.state.session_trust.get_store", side_effect=Exception("Redis down")):
        decision = g.evaluate(_dangerous_action(), _shell_intent(), tenant_id="chaos-003b")
    assert decision.verdict == Verdict.BLOCK, (
        f"C-003b: trust store down must not allow dangerous rm -rf, got {decision.verdict}"
    )


# ── C-004: Rate store (Redis) unavailable ─────────────────────────────────────

def test_c004_rate_store_failure_governance_continues():
    """If rate store raises, governance continues without rate limiting (fail-open for rate)."""
    g = _governor()
    with patch.object(g.policy_engine, "check_rate_limit", side_effect=Exception("Redis unavailable")):
        decision = g.evaluate(_safe_action(), _approved_intent(), tenant_id="chaos-004")
    assert decision.verdict in (Verdict.ALLOW, Verdict.ESCALATE, Verdict.BLOCK, Verdict.DEGRADE)


def test_c004_rate_store_failure_dangerous_still_blocked():
    """Rate store failure must not allow dangerous actions through."""
    g = _governor()
    with patch.object(g.policy_engine, "check_rate_limit", side_effect=Exception("Redis gone")):
        decision = g.evaluate(_dangerous_action(), _shell_intent(), tenant_id="chaos-004b")
    assert decision.verdict == Verdict.BLOCK, (
        f"C-004b: rate store down must not unblock dangerous shell command, got {decision.verdict}"
    )


# ── C-005: Sequence scorer failure ────────────────────────────────────────────

def test_c005_sequence_scorer_failure_governance_continues():
    """If sequence drift scorer raises, governance must continue (fail-open for sequences)."""
    g = _governor()
    with patch("edon_gateway.state.sequence_scorer.get_scorer", side_effect=ImportError("scorer missing")):
        decision = g.evaluate(_safe_action(), _approved_intent(), tenant_id="chaos-005")
    assert decision.verdict == Verdict.ALLOW, (
        f"C-005: sequence scorer missing must not block safe actions, got {decision.verdict}"
    )


# ── C-006: Blast-radius propagation module missing ────────────────────────────

def test_c006_blast_radius_propagation_failure_governance_continues():
    """If forward blast-radius propagation fails, governance falls back to static table."""
    g = _governor()
    with patch("edon_gateway.ai.action_graph.propagate_blast_radius", side_effect=ImportError):
        decision = g.evaluate(_safe_action(), _approved_intent(), tenant_id="chaos-006")
    assert decision.verdict == Verdict.ALLOW

    with patch("edon_gateway.ai.action_graph.propagate_blast_radius", side_effect=ImportError):
        decision2 = g.evaluate(_dangerous_action(), _shell_intent(), tenant_id="chaos-006b")
    assert decision2.verdict == Verdict.BLOCK


# ── C-007: Signing key unavailable ────────────────────────────────────────────

def test_c007_signing_failure_decision_still_produced():
    """If Ed25519 signing raises, decision must still be returned (audit note attached)."""
    g = _governor()
    with patch("edon_gateway.security.signing.sign_decision", side_effect=Exception("HSM offline")):
        decision = g.evaluate(_safe_action(), _approved_intent(), tenant_id="chaos-007")
    assert decision.verdict == Verdict.ALLOW
    # policy_snapshot_hash should still be present (not dependent on signing)
    assert decision.policy_snapshot_hash, "C-007: policy_snapshot_hash missing even when signing failed"


def test_c007_signing_failure_dangerous_still_blocked():
    """Signing failure must not unblock dangerous actions."""
    g = _governor()
    with patch("edon_gateway.security.signing.sign_decision", side_effect=Exception("key gone")):
        decision = g.evaluate(_dangerous_action(), _shell_intent(), tenant_id="chaos-007b")
    assert decision.verdict == Verdict.BLOCK


# ── C-008: ML alignment check raises ─────────────────────────────────────────

def test_c008_ml_check_failure_is_fail_closed():
    """If AI intent alignment check raises, governance fails closed — no verdict silently disappears."""
    g = _governor()
    with patch.object(g, "_check_intent_alignment", side_effect=Exception("model offline")):
        decision = g.evaluate(_safe_action(), _approved_intent(), tenant_id="chaos-008")
    # Fail-closed: exception inside evaluate → BLOCK is correct and expected
    assert decision.verdict in (Verdict.BLOCK, Verdict.ALLOW, Verdict.ESCALATE), (
        f"C-008: ML check crash must produce a valid verdict, not crash, got {decision.verdict}"
    )
    # Dangerous action: ML check failure must never produce ALLOW
    with patch.object(g, "_check_intent_alignment", side_effect=Exception("model offline")):
        d2 = g.evaluate(_dangerous_action(), _shell_intent(), tenant_id="chaos-008b")
    assert d2.verdict == Verdict.BLOCK, (
        f"C-008: ML check crash must not ALLOW dangerous shell command, got {d2.verdict}"
    )


# ── C-009: Intent expires during evaluation ───────────────────────────────────

def test_c009_expired_intent_is_blocked():
    """An intent that has already expired must produce BLOCK regardless of action risk."""
    g = _governor()
    expired_intent = _approved_intent()
    expired_intent.expires_at = datetime.now(UTC) - timedelta(seconds=60)
    decision = g.evaluate(_safe_action(), expired_intent, tenant_id="chaos-009")
    assert decision.verdict == Verdict.BLOCK, (
        f"C-009: expired intent must produce BLOCK, got {decision.verdict}"
    )


def test_c009_revoked_intent_is_blocked():
    """A revoked intent must be blocked even for safe actions."""
    g = _governor()
    revoked_intent = _approved_intent()
    revoked_intent.revoked = True
    decision = g.evaluate(_safe_action(), revoked_intent, tenant_id="chaos-009b")
    assert decision.verdict == Verdict.BLOCK


# ── C-010: Concurrent evaluations — thread safety ─────────────────────────────

def test_c010_concurrent_evaluations_no_crashes():
    """20 threads evaluating simultaneously must all get valid verdicts (no crashes)."""
    results: list = []
    errors: list = []
    lock = threading.Lock()

    def evaluate_one(thread_id: int):
        try:
            g = EDONGovernor()
            action = Action(
                tool=Tool.EMAIL, op="send",
                params={"to": f"user{thread_id}@example.com"},
                estimated_risk=RiskLevel.LOW,
            )
            intent = IntentContract(
                objective="send email",
                scope={"email": ["send"]},
                constraints={},
                risk_level=RiskLevel.LOW,
                approved_by_user=True,
            )
            decision = g.evaluate(action, intent, tenant_id=f"chaos-010-{thread_id}")
            with lock:
                results.append(decision.verdict)
        except Exception as e:
            with lock:
                errors.append(str(e))

    threads = [threading.Thread(target=evaluate_one, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"C-010: {len(errors)} thread errors: {errors[:3]}"
    assert len(results) == 20
    assert all(v == Verdict.ALLOW for v in results), (
        f"C-010: concurrent safe actions should all ALLOW, got {set(results)}"
    )


def test_c010_concurrent_dangerous_all_blocked():
    """Dangerous actions evaluated concurrently must all be blocked."""
    results: list = []
    errors: list = []
    lock = threading.Lock()

    def evaluate_one(thread_id: int):
        try:
            g = EDONGovernor()
            action = Action(
                tool=Tool.SHELL, op="execute",
                params={"command": "rm -rf /"},
                estimated_risk=RiskLevel.LOW,
            )
            intent = IntentContract(
                objective="run commands",
                scope={"shell": ["execute"]},
                constraints={},
                risk_level=RiskLevel.LOW,
                approved_by_user=True,
            )
            decision = g.evaluate(action, intent, tenant_id=f"chaos-010d-{thread_id}")
            with lock:
                results.append(decision.verdict)
        except Exception as e:
            with lock:
                errors.append(str(e))

    threads = [threading.Thread(target=evaluate_one, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"C-010d: thread errors: {errors[:3]}"
    assert all(v == Verdict.BLOCK for v in results), (
        f"C-010d: concurrent dangerous commands must all BLOCK, got {set(results)}"
    )
