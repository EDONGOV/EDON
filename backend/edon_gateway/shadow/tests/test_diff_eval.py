"""Tests for the shadow diff evaluator.

Verifies that verdict transition classification is correct:
- critical transitions are always classified as critical
- advisory transitions are always classified as advisory
- stable (no change) is classified as stable
- semantic checks (privilege escalation, context poisoning, prompt injection)
  override the base classification when needed
- governor drift is surfaced when baseline disagrees with original
"""

import pytest
from unittest.mock import MagicMock

from ..diff_eval import evaluate_diff
from ..replay import ShadowRunResult, BaselineResult


# ── Fixtures ────────────────────────────────────────────────────────────────────


def _make_trace(original_verdict: str = "BLOCK", action_type: str = "email.send"):
    t = MagicMock()
    t.original_verdict = original_verdict
    t.action_type = action_type
    t.trace_id = "trace-test-001"
    return t


def _make_result(
    shadow_verdict: str,
    perturbation_name: str = "test_perturb",
    perturbation_type: str = "prompt_injection",
    perturbed_field: str = "payload.body",
) -> ShadowRunResult:
    return ShadowRunResult(
        trace_id="trace-test-001",
        perturbation_name=perturbation_name,
        perturbation_type=perturbation_type,
        perturbed_field=perturbed_field,
        shadow_verdict=shadow_verdict,
        shadow_reason="test reason",
        shadow_latency_ms=10,
    )


def _make_baseline(baseline_verdict: str, original_verdict: str) -> BaselineResult:
    return BaselineResult(
        trace_id="trace-test-001",
        baseline_verdict=baseline_verdict,
        baseline_reason="baseline reason",
        baseline_latency_ms=8,
        matches_original=(baseline_verdict == original_verdict),
        non_determinism_flag=(baseline_verdict != original_verdict),
    )


# ── Critical transitions ────────────────────────────────────────────────────────


@pytest.mark.parametrize("original,shadow", [
    ("BLOCK",          "ALLOW"),
    ("BLOCK",          "DEGRADE"),
    ("ESCALATE",       "ALLOW"),
    ("ESCALATE",       "DEGRADE"),
    ("PAUSE",          "ALLOW"),
    ("HUMAN_REQUIRED", "ALLOW"),
    ("ERROR",          "ALLOW"),
])
def test_critical_transitions(original, shadow):
    trace = _make_trace(original_verdict=original)
    result = _make_result(shadow_verdict=shadow, perturbation_type="malformed_payload")
    out = evaluate_diff(trace, result)
    assert out.severity == "critical"
    assert out.verdict_changed is True
    assert any("POLICY BYPASS" in f for f in out.findings)


# ── Advisory transitions ────────────────────────────────────────────────────────


@pytest.mark.parametrize("original,shadow", [
    ("ALLOW",   "ESCALATE"),
    ("ALLOW",   "BLOCK"),
    ("ALLOW",   "PAUSE"),
    ("DEGRADE", "ALLOW"),
    ("DEGRADE", "BLOCK"),
])
def test_advisory_transitions(original, shadow):
    trace = _make_trace(original_verdict=original)
    result = _make_result(shadow_verdict=shadow, perturbation_type="boundary_input")
    out = evaluate_diff(trace, result)
    assert out.severity == "advisory"
    assert out.verdict_changed is True


# ── Stable (no change) ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("verdict", ["ALLOW", "BLOCK", "ESCALATE", "DEGRADE", "PAUSE"])
def test_stable_when_verdict_unchanged(verdict):
    trace = _make_trace(original_verdict=verdict)
    result = _make_result(shadow_verdict=verdict, perturbation_type="malformed_payload")
    out = evaluate_diff(trace, result)
    assert out.severity == "stable"
    assert out.verdict_changed is False
    assert any("STABLE" in f for f in out.findings)


# ── Semantic checks ────────────────────────────────────────────────────────────


def test_privilege_escalation_allow_is_critical():
    trace = _make_trace(original_verdict="BLOCK")
    result = _make_result(
        shadow_verdict="ALLOW",
        perturbation_type="privilege_escalation",
    )
    out = evaluate_diff(trace, result)
    assert out.severity == "critical"
    assert any("PRIVILEGE ESCALATION" in f for f in out.findings)


def test_privilege_escalation_already_allow_is_not_flagged():
    """If original was ALLOW and escalated version is also ALLOW, no extra flag."""
    trace = _make_trace(original_verdict="ALLOW")
    result = _make_result(
        shadow_verdict="ALLOW",
        perturbation_type="privilege_escalation",
    )
    out = evaluate_diff(trace, result)
    # No privilege escalation flag — original was already ALLOW
    assert not any("PRIVILEGE ESCALATION" in f for f in out.findings)


def test_context_poisoning_bypass_is_critical():
    for original in ("BLOCK", "ESCALATE", "PAUSE"):
        trace = _make_trace(original_verdict=original)
        result = _make_result(
            shadow_verdict="ALLOW",
            perturbation_type="context_poisoning",
        )
        out = evaluate_diff(trace, result)
        assert out.severity == "critical"
        assert any("CONTEXT POISONING" in f for f in out.findings)


def test_prompt_injection_advisory_when_verdict_changes_but_not_critical():
    """ALLOW → ESCALATE under prompt injection: advisory + injection note."""
    trace = _make_trace(original_verdict="ALLOW")
    result = _make_result(
        shadow_verdict="ESCALATE",
        perturbation_type="prompt_injection",
    )
    out = evaluate_diff(trace, result)
    assert out.severity == "advisory"
    assert out.verdict_changed is True


# ── Baseline integration ───────────────────────────────────────────────────────


def test_baseline_used_as_reference_instead_of_original():
    """When baseline is available, diff is computed against baseline, not original."""
    trace = _make_trace(original_verdict="ALLOW")
    # Baseline shows governor now returns BLOCK (policy changed since capture)
    baseline = _make_baseline(baseline_verdict="BLOCK", original_verdict="ALLOW")
    # Shadow (under perturbation) returns ALLOW — but reference is BLOCK
    result = _make_result(shadow_verdict="ALLOW", perturbation_type="boundary_input")
    out = evaluate_diff(trace, result, baseline=baseline)
    # BLOCK → ALLOW = critical
    assert out.severity == "critical"
    assert out.verdict_changed is True


def test_non_determinism_flag_surfaces_in_findings():
    trace = _make_trace(original_verdict="ALLOW")
    baseline = _make_baseline(baseline_verdict="BLOCK", original_verdict="ALLOW")
    result = _make_result(shadow_verdict="BLOCK", perturbation_type="malformed_payload")
    out = evaluate_diff(trace, result, baseline=baseline)
    assert any("GOVERNOR DRIFT" in f for f in out.findings)


def test_no_baseline_falls_back_to_original():
    trace = _make_trace(original_verdict="BLOCK")
    result = _make_result(shadow_verdict="ALLOW", perturbation_type="boundary_input")
    out = evaluate_diff(trace, result, baseline=None)
    assert out.severity == "critical"


def test_stable_baseline_no_drift_finding():
    trace = _make_trace(original_verdict="BLOCK")
    baseline = _make_baseline(baseline_verdict="BLOCK", original_verdict="BLOCK")
    result = _make_result(shadow_verdict="BLOCK", perturbation_type="malformed_payload")
    out = evaluate_diff(trace, result, baseline=baseline)
    assert not any("GOVERNOR DRIFT" in f for f in out.findings)
    assert out.severity == "stable"
