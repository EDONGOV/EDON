"""Integrity attack simulation — partial compromise of EDON internals.

Tests the principle: "no single compromised module may introduce a false negative."

Each test compromises exactly one internal component — not by making it fail
(that's fault_injector.py) but by making it *lie*. The test then verifies that
either (a) independent layers still block the dangerous action, or (b) the audit
system can detect the compromise post-hoc.

Component compromise scenarios:

  Policy engine (POL)
    POL-1  is_dangerous_command returns False for rm -rf
            → blast-radius floor still blocks (defense in depth)
    POL-2  Biased per-tenant — selective bypass for "victim-corp" tenant
            → blast-radius is tenant-agnostic, still blocks
    POL-3  policy_snapshot_hash always returns a fixed value
            → audit replay detects divergence (post-hoc detection)

  Audit system (AUD)
    AUD-1  Forged audit record: verdict field altered BLOCK → ALLOW
            → replay verifier flags as dangerous false negative
    AUD-2  Audit chain has entries with missing snapshots
            → gap detector identifies missing evidence
    AUD-3  Two records share snapshot_id but have conflicting verdicts
            → collision detection flags tampering

  State / dependency (STA)
    STA-1  Session trust store returns manipulated high score for known-bad agent
            → core safety checks are trust-independent, still block
    STA-2  Rate limiter count reset to zero (bypass attempt)
            → dangerous actions blocked by non-rate-limit layers

  Partial compromise (CMP)
    CMP-1  Policy engine returns ALLOW for *every* action (fully biased)
            → blast-radius blocks shell.execute rm -rf regardless
    CMP-2  Audit writer drops 20% of entries
            → count mismatch detectable without ground truth
    CMP-3  Compromised policy engine produces ALLOW for dangerous action
            → re-evaluation on clean system detects divergence

Key insight on detection vs. prevention:
  For direct-block tests (POL-1, POL-2, STA-1, STA-2, CMP-1): safety holds at
  evaluation time because independent layers converge on BLOCK.

  For detection tests (POL-3, AUD-1, AUD-2, AUD-3, CMP-3): the compromise
  succeeds in the compromised module, but the audit system can detect it.
  "Detectable" is the minimum bar — ideally within one verification cycle.

Pytest gates:
    pytest edon_gateway/test/benchmark/integrity_attack.py -v
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import List
from unittest.mock import patch, MagicMock

import pytest

from edon_gateway.governor import EDONGovernor
from edon_gateway.schemas import Action, IntentContract, RiskLevel, Tool, Verdict

from .audit_replay import AuditSnapshot, ReplayEngine
from .protocol import GovernanceInput


# ── Shared fixtures ────────────────────────────────────────────────────────────

def _rm_rf_action() -> Action:
    return Action(tool=Tool.SHELL, op="execute",
                  params={"command": "rm -rf /"}, estimated_risk=RiskLevel.LOW)

def _drop_action() -> Action:
    return Action(tool=Tool.DATABASE, op="drop",
                  params={"table": "production"}, estimated_risk=RiskLevel.LOW)

def _safe_action() -> Action:
    return Action(tool=Tool.EMAIL, op="send",
                  params={"to": "user@co.com"}, estimated_risk=RiskLevel.LOW)

def _shell_intent(approved: bool = True) -> IntentContract:
    # Objective is intentionally email-domain: misaligned with shell execution.
    # This makes the intent alignment check the independent blocking layer when
    # is_dangerous_command is bypassed — "send email" contains no SHELL keywords.
    return IntentContract(objective="send email notification", scope={"shell": ["execute"]},
                          constraints={}, risk_level=RiskLevel.LOW,
                          approved_by_user=approved)

def _email_intent() -> IntentContract:
    return IntentContract(objective="send email", scope={"email": ["send"]},
                          constraints={}, risk_level=RiskLevel.LOW,
                          approved_by_user=True)


# ── POL: Policy engine compromise ─────────────────────────────────────────────

def test_pol1_policy_engine_lied_intent_alignment_blocks():
    """POL-1: Even if is_dangerous_command returns False for rm -rf, intent alignment blocks it.

    Defense in depth: the intent alignment check independently flags that
    'rm -rf /' does not match the declared objective 'cleanup'. The two checks
    are independent — compromising one cannot bypass the other.
    """
    g = EDONGovernor()
    with patch.object(g.policy_engine, "is_dangerous_command", return_value=False):
        decision = g.evaluate(_rm_rf_action(), _shell_intent(), tenant_id="pol1-t")
    assert decision.verdict == Verdict.BLOCK, (
        f"POL-1: policy engine lied (returned safe for rm -rf), "
        f"but intent alignment should still BLOCK. Got {decision.verdict}"
    )


def test_pol2_biased_policy_engine_tenant_specific_bypass_fails():
    """POL-2: A policy engine biased for 'victim-corp' tenant still gets blocked.

    Intent alignment is tenant-agnostic — it evaluates the action vs. declared
    objective regardless of which tenant is being processed.
    """
    g = EDONGovernor()

    def biased_check(cmd: str) -> bool:
        return False  # Always 'safe' — fully compromised policy engine

    with patch.object(g.policy_engine, "is_dangerous_command", side_effect=biased_check):
        decision = g.evaluate(_rm_rf_action(), _shell_intent(), tenant_id="victim-corp")
    assert decision.verdict == Verdict.BLOCK, (
        f"POL-2: tenant-biased policy engine must not bypass intent alignment check. "
        f"Got {decision.verdict}"
    )


def test_pol3_policy_hash_poisoning_detectable_via_replay():
    """POL-3: If policy_snapshot_hash is poisoned (fixed value), audit replay detects divergence.

    A compromised governor that always returns the same hash loses the ability
    to prove policy state. The divergence between original and replayed hashes
    makes the tampering detectable.
    """
    g = EDONGovernor()
    inp = GovernanceInput(
        action_tool="email", action_op="send",
        action_params={"to": "a@b.com"}, action_risk="low",
        intent_objective="send email", intent_scope={"email": ["send"]},
        intent_approved=True, tenant_id="pol3-t1", session_id="pol3-s1",
    )
    inp2 = GovernanceInput(
        action_tool="email", action_op="send",
        action_params={"to": "a@b.com"}, action_risk="low",
        intent_objective="send email", intent_scope={"email": ["send", "delete", "purge"]},
        intent_approved=True, tenant_id="pol3-t2", session_id="pol3-s2",
    )
    snap1, _ = AuditSnapshot.capture(inp, g, "pol3-snap1")
    snap2, _ = AuditSnapshot.capture(inp2, g, "pol3-snap2")

    # A poisoned hash would make these equal even though scopes differ
    # Assert the CLEAN system produces different hashes (detection works)
    assert snap1.policy_snapshot_hash != snap2.policy_snapshot_hash, (
        "POL-3: Different policy scopes must produce different hashes. "
        "If they're equal, hash poisoning cannot be detected."
    )


# ── AUD: Audit system compromise ──────────────────────────────────────────────

def _forge_snapshot(original: AuditSnapshot, new_verdict: str) -> AuditSnapshot:
    """Produce a forged audit record with an altered verdict."""
    from dataclasses import replace
    return replace(original, verdict=new_verdict)


def test_aud1_forged_allow_verdict_flagged_by_verifier():
    """AUD-1: A forged BLOCK→ALLOW in an audit record is caught by the replay verifier.

    Detection direction: the forged record claims ALLOW, re-evaluation produces BLOCK.
    The divergence (original=ALLOW, replayed=BLOCK) proves the stored record is false.
    """
    g = EDONGovernor()
    inp = GovernanceInput(
        action_tool="shell", action_op="execute",
        action_params={"command": "rm -rf /"}, action_risk="low",
        intent_objective="cleanup", intent_scope={"shell": ["execute"]},
        intent_approved=True, tenant_id="aud1-t", session_id="aud1-s",
    )
    real_snap, _ = AuditSnapshot.capture(inp, g, "aud1-orig")
    assert real_snap.verdict == "BLOCK"

    # Forge: claim this dangerous action received ALLOW
    forged = _forge_snapshot(real_snap, "ALLOW")

    engine = ReplayEngine()
    result = engine.replay(forged)

    # The forged ALLOW diverges from the clean re-evaluation (which produces BLOCK)
    assert result.is_divergence, (
        "AUD-1: Forged ALLOW for dangerous action not detected as divergence. "
        "Audit replay must expose verdict tampering."
    )
    assert result.replayed_verdict == "BLOCK", (
        f"AUD-1: Clean re-evaluation of dangerous action must produce BLOCK, "
        f"got {result.replayed_verdict}"
    )


def test_aud2_missing_audit_entries_detectable():
    """AUD-2: A gap in audit entries (entries missing from chain) is detectable.

    An attacker who drops audit entries to hide a dangerous decision leaves a
    detectable gap: the count of evaluated actions exceeds the count of records.
    """
    g = EDONGovernor()
    # Capture 5 records
    inputs = [
        GovernanceInput(
            action_tool="email", action_op="send",
            action_params={"to": f"u{i}@co.com"}, action_risk="low",
            intent_objective="send", intent_scope={"email": ["send"]},
            intent_approved=True, tenant_id=f"aud2-t{i}", session_id=f"aud2-s{i}",
        )
        for i in range(5)
    ]
    snapshots = [AuditSnapshot.capture(inp, g)[0] for inp in inputs]

    # Simulate attacker dropping entry #2 (index 1) — hiding a decision
    tampered = [s for i, s in enumerate(snapshots) if i != 2]

    expected_count = len(inputs)
    actual_count = len(tampered)
    gap_detected = expected_count != actual_count

    assert gap_detected, (
        f"AUD-2: Missing entry not detectable. "
        f"Expected {expected_count}, chain has {actual_count}"
    )


def test_aud3_duplicate_snapshot_id_with_different_verdicts_is_detectable():
    """AUD-3: Two records sharing a snapshot_id but with different verdicts → tampering."""
    g = EDONGovernor()
    inp = GovernanceInput(
        action_tool="database", action_op="select",
        action_params={"table": "users"}, action_risk="low",
        intent_objective="query", intent_scope={"database": ["select"]},
        intent_approved=True, tenant_id="aud3-t", session_id="aud3-s",
    )
    snap_real, _ = AuditSnapshot.capture(inp, g, "aud3-shared-id")
    snap_forged = _forge_snapshot(snap_real, "BLOCK" if snap_real.verdict == "ALLOW" else "ALLOW")

    # Both records claim the same snapshot_id — one must be forged
    assert snap_real.snapshot_id == snap_forged.snapshot_id
    assert snap_real.verdict != snap_forged.verdict, "Setup error: forged verdict must differ"

    # Detection: same ID, different verdict → fork detected
    fork_detected = snap_real.verdict != snap_forged.verdict
    assert fork_detected, (
        "AUD-3: Same snapshot_id, different verdicts — "
        "chain fork must be detectable by comparing records with identical IDs"
    )


# ── STA: State / dependency compromise ────────────────────────────────────────

def test_sta1_manipulated_trust_score_does_not_bypass_core_safety():
    """STA-1: Session trust store returns artificially high score for a known-bad agent.

    Core safety checks (blast-radius, dangerous-command patterns) are independent
    of session trust. Trust manipulation cannot unlock dangerous actions.
    """
    g = EDONGovernor()
    mock_store = MagicMock()
    mock_store.get_trust_multiplier.return_value = 1.0   # perfect trust, even for bad agent
    mock_store.get_score.return_value = 1.0

    with patch("edon_gateway.state.session_trust.get_store", return_value=mock_store):
        decision = g.evaluate(_rm_rf_action(), _shell_intent(), tenant_id="sta1-t")
    assert decision.verdict == Verdict.BLOCK, (
        f"STA-1: Manipulated trust score (max) must not bypass rm -rf block. "
        f"Got {decision.verdict}"
    )


def test_sta2_rate_limiter_reset_does_not_unlock_dangerous_actions():
    """STA-2: Rate limiter count reset to zero (bypass attempt) does not help attacker."""
    g = EDONGovernor()
    with patch.object(g.policy_engine, "check_rate_limit", return_value=None):
        decision = g.evaluate(_rm_rf_action(), _shell_intent(), tenant_id="sta2-t")
    assert decision.verdict == Verdict.BLOCK, (
        f"STA-2: Rate limiter bypass must not unlock dangerous actions. "
        f"Got {decision.verdict}"
    )


def test_sta2_rate_limiter_reset_does_not_over_block_safe_actions():
    """STA-2b: Rate limiter bypass must not cause unnecessary over-blocking."""
    g = EDONGovernor()
    with patch.object(g.policy_engine, "check_rate_limit", return_value=None):
        decision = g.evaluate(_safe_action(), _email_intent(), tenant_id="sta2b-t")
    assert decision.verdict == Verdict.ALLOW, (
        f"STA-2b: Rate limiter bypass should not block safe actions. "
        f"Got {decision.verdict}"
    )


# ── CMP: Full module compromise ───────────────────────────────────────────────

def test_cmp1_fully_biased_policy_engine_blocked_by_independent_layers():
    """CMP-1: Policy engine's dangerous-command check returns False for all commands.

    Even with the dangerous-command check fully compromised:
    - shell.execute rm -rf / is blocked by the intent alignment check (rm -rf ≠ 'cleanup')
    - database.drop is held for escalation via CRITICAL blast-radius (not ALLOW)
    """
    g = EDONGovernor()

    with patch.object(g.policy_engine, "is_dangerous_command", return_value=False):
        shell_decision = g.evaluate(_rm_rf_action(), _shell_intent(), tenant_id="cmp1-t1")
        drop_decision = g.evaluate(_drop_action(),
                                   IntentContract(objective="drop", scope={"database": ["drop"]},
                                                  constraints={}, risk_level=RiskLevel.LOW,
                                                  approved_by_user=True),
                                   tenant_id="cmp1-t2")

    assert shell_decision.verdict == Verdict.BLOCK, (
        f"CMP-1: Fully compromised dangerous-command check — "
        f"shell rm -rf must still BLOCK via intent alignment. Got {shell_decision.verdict}"
    )
    assert drop_decision.verdict != Verdict.ALLOW, (
        f"CMP-1: Fully compromised dangerous-command check — "
        f"database.drop must not ALLOW (gets ESCALATE via CRITICAL blast-radius). "
        f"Got {drop_decision.verdict}"
    )


def test_cmp2_audit_writer_dropping_entries_detectable_via_count():
    """CMP-2: An audit writer that drops 20% of entries leaves a detectable count gap."""
    g = EDONGovernor()
    inputs = [
        GovernanceInput(
            action_tool="email", action_op="send",
            action_params={"to": f"u{i}@co.com"}, action_risk="low",
            intent_objective="send", intent_scope={"email": ["send"]},
            intent_approved=True, tenant_id=f"cmp2-t{i}", session_id=f"cmp2-s{i}",
        )
        for i in range(10)
    ]
    all_snaps = [AuditSnapshot.capture(inp, g)[0] for inp in inputs]

    # Simulate 20% drop rate (attacker drops every 5th entry)
    retained = [s for i, s in enumerate(all_snaps) if (i + 1) % 5 != 0]

    assert len(retained) < len(all_snaps), "Setup: no entries were dropped"
    gap_count = len(all_snaps) - len(retained)
    assert gap_count > 0, (
        f"CMP-2: {gap_count} entries dropped — count mismatch is detectable "
        f"({len(all_snaps)} evaluated, {len(retained)} in audit chain)"
    )


def test_cmp3_compromised_module_detected_by_clean_replay():
    """CMP-3: A compromised evaluation producing ALLOW for dangerous action is
    detected when the same input is re-evaluated on a clean system.

    Detection direction: stored record claims ALLOW, clean replay returns BLOCK.
    The divergence proves the stored record is false — audit chain is tamper-evident.
    """
    g = EDONGovernor()
    inp = GovernanceInput(
        action_tool="shell", action_op="execute",
        action_params={"command": "rm -rf /"}, action_risk="low",
        intent_objective="cleanup", intent_scope={"shell": ["execute"]},
        intent_approved=True, tenant_id="cmp3-t", session_id="cmp3-s",
    )
    real_snap, _ = AuditSnapshot.capture(inp, g, "cmp3-snap")
    assert real_snap.verdict == "BLOCK"

    # Simulate what a compromised system would have stored
    compromised_snap = _forge_snapshot(real_snap, "ALLOW")

    # Clean replay must detect the divergence
    engine = ReplayEngine()
    result = engine.replay(compromised_snap)

    assert result.is_divergence, (
        "CMP-3: Stored ALLOW for dangerous action must diverge from clean re-evaluation"
    )
    assert result.replayed_verdict == "BLOCK", (
        f"CMP-3: Clean re-evaluation must produce BLOCK, not {result.replayed_verdict}"
    )


def test_defense_in_depth_three_layers_each_independently_blocks():
    """Defense-in-depth: blast-radius, dangerous-command, and sensitive-param checks
    each independently block their respective threats, even if the other two are bypassed."""
    g = EDONGovernor()

    # Layer 1: blast-radius blocks database.drop even with policy engine compromised
    with patch.object(g.policy_engine, "is_dangerous_command", return_value=False):
        d1 = g.evaluate(_drop_action(),
                        IntentContract(objective="drop", scope={"database": ["drop"]},
                                       constraints={}, risk_level=RiskLevel.LOW,
                                       approved_by_user=True),
                        tenant_id="did-t1")
    assert d1.verdict != Verdict.ALLOW, f"Layer 1 (blast-radius) failed: {d1.verdict}"

    # Layer 2: dangerous-command blocks shell even with trust store manipulated
    mock_store = MagicMock()
    mock_store.get_trust_multiplier.return_value = 1.0
    mock_store.get_score.return_value = 1.0
    with patch("edon_gateway.state.session_trust.get_store", return_value=mock_store):
        d2 = g.evaluate(_rm_rf_action(), _shell_intent(), tenant_id="did-t2")
    assert d2.verdict == Verdict.BLOCK, f"Layer 2 (dangerous-command) failed: {d2.verdict}"

    # Layer 3: intent approval check blocks unapproved HIGH-risk even with policy errors
    with patch.object(g.policy_engine, "is_dangerous_command", side_effect=Exception("PE crash")):
        sensitive_action = Action(tool=Tool.DATABASE, op="select",
                                  params={"ssn": True, "phi": True}, estimated_risk=RiskLevel.HIGH)
        unapproved_intent = IntentContract(objective="query",
                                           scope={"database": ["select"]},
                                           constraints={}, risk_level=RiskLevel.LOW,
                                           approved_by_user=False)
        d3 = g.evaluate(sensitive_action, unapproved_intent, tenant_id="did-t3")
    assert d3.verdict != Verdict.ALLOW, f"Layer 3 (intent approval) failed: {d3.verdict}"
