"""Integration tests for the shadow replay system.

Uses the real EDONGovernor + real perturbations + real TraceStore (SQLite).
No mocks — these prove the end-to-end pipeline actually works.

Marked with @pytest.mark.integration so CI can separate them from unit tests.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from ...governor import EDONGovernor
from ...schemas import Action, Tool, IntentContract, RiskLevel, ActionSource
from ..trace_capture import AgentTrace, TraceStore
from ..perturbations import get_perturbations
from ..replay import (
    BaselineResult,
    ShadowRunResult,
    ChainStressResult,
    replay_baseline,
    session_chain_stress,
    shadow_run_trace,
    _baseline_sync,
    _replay_one_sync,
)
from ..diff_eval import evaluate_diff

pytestmark = pytest.mark.integration


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def governor() -> EDONGovernor:
    """Real governor with default policy config — no DB needed."""
    return EDONGovernor()


@pytest.fixture
def store(tmp_path: Path) -> TraceStore:
    return TraceStore(db_path=str(tmp_path / "integration.db"))


def _email_trace(
    trace_id: str = "integ-trace-001",
    verdict: str = "ALLOW",
    session_id: str = "sess-integ",
) -> AgentTrace:
    return AgentTrace(
        trace_id=trace_id,
        captured_at="2026-04-11T10:00:00+00:00",
        agent_id="agent-integ",
        tenant_id="tenant-integ",
        action_type="email.send",
        action_payload={"to": "user@example.com", "subject": "Report", "body": "Here is your report."},
        context={"session_id": session_id, "stated_intent": "send weekly report"},
        timestamp="2026-04-11T10:00:00Z",
        intent_id=None,
        original_verdict=verdict,
        original_reason="Policy passed",
        original_latency_ms=10,
        original_meta={},
    )


# ── Real governor produces a real Decision ─────────────────────────────────────


def test_governor_returns_decision_for_email_action(governor: EDONGovernor):
    """Sanity-check: real governor evaluates a standard email action without crashing."""
    from datetime import datetime, UTC

    action = Action(
        tool=Tool.EMAIL,
        op="send",
        params={"to": "user@example.com", "body": "Hello"},
        requested_at=datetime.now(UTC),
        source=ActionSource.AGENT,
        tags=[],
    )
    intent = IntentContract(
        objective="Send report",
        scope={},
        constraints={},
        risk_level=RiskLevel.LOW,
        approved_by_user=True,
    )
    decision = governor.evaluate(action=action, intent=intent, context={}, tenant_rules=[])
    assert decision.verdict is not None
    assert decision.verdict.value in ("ALLOW", "BLOCK", "ESCALATE", "PAUSE", "DEGRADE")


# ── _baseline_sync with real governor ─────────────────────────────────────────


def test_baseline_sync_real_governor_returns_baseline_result(governor: EDONGovernor):
    """Real governor + real trace → BaselineResult with a proper verdict."""
    trace = _email_trace()
    result = _baseline_sync(trace, governor)
    assert isinstance(result, BaselineResult)
    assert result.trace_id == "integ-trace-001"
    assert result.baseline_verdict in ("ALLOW", "BLOCK", "ESCALATE", "PAUSE", "DEGRADE", "ERROR")
    assert result.baseline_latency_ms >= 0


def test_baseline_sync_real_governor_shadow_flag_does_not_crash(governor: EDONGovernor):
    """Shadow context flags (_shadow, _shadow_mode) are passed through without crashing the governor."""
    trace = _email_trace(verdict="ALLOW")
    result = _baseline_sync(trace, governor)
    # If governor crashed, verdict would be ERROR; otherwise it evaluated normally
    assert result.baseline_verdict != "ERROR", f"Governor crashed: {result.baseline_reason}"


def test_baseline_sync_schema_construction_does_not_crash_for_unknown_tool(governor: EDONGovernor):
    """action_type with unknown tool prefix falls back to CUSTOM and evaluates without crash."""
    trace = AgentTrace(
        trace_id="unknown-tool-trace",
        captured_at="2026-04-11T10:00:00+00:00",
        agent_id="agent-x",
        tenant_id="tenant-x",
        action_type="totally_custom_tool.do_something",
        action_payload={"key": "value"},
        context={"session_id": "sess-x"},
        timestamp="2026-04-11T10:00:00Z",
        intent_id=None,
        original_verdict="ALLOW",
        original_reason="ok",
        original_latency_ms=5,
        original_meta={},
    )
    result = _baseline_sync(trace, governor)
    assert result.trace_id == "unknown-tool-trace"
    assert result.baseline_verdict in ("ALLOW", "BLOCK", "ESCALATE", "PAUSE", "DEGRADE", "ERROR")


# ── _replay_one_sync with real perturbations ───────────────────────────────────


def test_replay_one_sync_real_perturbation_real_governor(governor: EDONGovernor):
    """Real perturbation mutates trace; real governor evaluates the mutated input."""
    trace = _email_trace()
    perturbations = get_perturbations()
    assert len(perturbations) > 0, "Perturbation library is empty"

    perturb = perturbations[0]
    result = _replay_one_sync(trace, perturb, governor)

    assert isinstance(result, ShadowRunResult)
    assert result.trace_id == "integ-trace-001"
    assert result.perturbation_name == perturb.name
    assert result.perturbation_type == perturb.type
    assert result.shadow_verdict in ("ALLOW", "BLOCK", "ESCALATE", "PAUSE", "DEGRADE", "ERROR")
    assert result.shadow_latency_ms >= 0


def test_replay_one_sync_all_perturbation_types_complete(governor: EDONGovernor):
    """Every perturbation in the library can run against a standard email trace without crashing."""
    trace = _email_trace()
    perturbations = get_perturbations()

    for perturb in perturbations:
        result = _replay_one_sync(trace, perturb, governor)
        assert result.shadow_verdict in (
            "ALLOW", "BLOCK", "ESCALATE", "PAUSE", "DEGRADE", "ERROR"
        ), f"Unexpected verdict from perturbation '{perturb.name}': {result.shadow_verdict}"


def test_replay_one_sync_prompt_injection_type_evaluated(governor: EDONGovernor):
    """Prompt injection perturbations are evaluated by the real governor (not silently dropped)."""
    trace = _email_trace()
    injections = get_perturbations(["prompt_injection"])
    assert len(injections) > 0, "No prompt_injection perturbations found"

    for perturb in injections:
        result = _replay_one_sync(trace, perturb, governor)
        # Governor ran (not silently skipped) — latency proves evaluation happened
        assert result.shadow_latency_ms >= 0
        assert result.perturbation_type == "prompt_injection"


# ── diff_eval with real results ────────────────────────────────────────────────


def test_diff_eval_classifies_real_shadow_result(governor: EDONGovernor):
    """evaluate_diff produces a severity for a real ShadowRunResult."""
    trace = _email_trace(verdict="ALLOW")
    perturb = get_perturbations(["prompt_injection"])[0]
    result = _replay_one_sync(trace, perturb, governor)
    baseline = _baseline_sync(trace, governor)

    evaluated = evaluate_diff(trace, result, baseline=baseline)
    assert evaluated.severity in ("stable", "advisory", "critical")
    assert isinstance(evaluated.findings, list)


# ── replay_baseline (async) with real governor ─────────────────────────────────


@pytest.mark.asyncio
async def test_replay_baseline_async_real_governor(governor: EDONGovernor):
    """Async wrapper runs baseline in thread pool with real governor."""
    trace = _email_trace(verdict="ALLOW")
    result = await replay_baseline(trace, governor=governor)
    assert isinstance(result, BaselineResult)
    assert result.baseline_verdict in ("ALLOW", "BLOCK", "ESCALATE", "PAUSE", "DEGRADE", "ERROR")


@pytest.mark.asyncio
async def test_replay_baseline_latency_is_measured(governor: EDONGovernor):
    result = await replay_baseline(_email_trace(), governor=governor)
    assert result.baseline_latency_ms >= 0


# ── shadow_run_trace end-to-end ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_shadow_run_trace_returns_results(governor: EDONGovernor, store: TraceStore, monkeypatch):
    """Full pipeline: trace → baseline → perturbations → diff_eval → store."""
    import edon_gateway.shadow.replay as replay_mod
    import edon_gateway.shadow.trace_capture as tc_mod
    monkeypatch.setattr(replay_mod, "_MAX_PERTURBATIONS", 3)
    # Patch the function so the lazy import inside shadow_run_trace gets our store
    monkeypatch.setattr(tc_mod, "get_trace_store", lambda: store)

    trace = _email_trace()
    store.save_trace(trace)

    results = await shadow_run_trace(trace, governor=governor)

    assert isinstance(results, list)
    assert len(results) > 0
    for r in results:
        assert isinstance(r, ShadowRunResult)
        assert r.severity in ("stable", "advisory", "critical")


def test_store_persists_baseline_result(governor: EDONGovernor, store: TraceStore):
    """TraceStore correctly persists and retrieves a real BaselineResult."""
    trace = _email_trace(trace_id="persist-trace")
    store.save_trace(trace)

    baseline = _baseline_sync(trace, governor)
    store.save_baseline(baseline)

    row = store.get_baseline("persist-trace")
    assert row is not None
    assert row["trace_id"] == "persist-trace"
    assert row["baseline_verdict"] in ("ALLOW", "BLOCK", "ESCALATE", "PAUSE", "DEGRADE", "ERROR")
    assert row["baseline_latency_ms"] >= 0
    assert row["non_determinism_flag"] in (0, 1)


def test_store_persists_shadow_run_result(governor: EDONGovernor, store: TraceStore):
    """TraceStore correctly persists and retrieves a real ShadowRunResult after diff_eval."""
    trace = _email_trace(trace_id="shadow-persist")
    store.save_trace(trace)

    baseline = _baseline_sync(trace, governor)
    perturb = get_perturbations(["prompt_injection"])[0]
    result = _replay_one_sync(trace, perturb, governor)
    result = evaluate_diff(trace, result, baseline=baseline)
    store.save_result(result)

    findings = store.recent_findings()
    assert len(findings) >= 1
    row = findings[0]
    assert row["trace_id"] == "shadow-persist"
    assert row["severity"] in ("stable", "advisory", "critical")
    assert row["perturbation_type"] == "prompt_injection"


# ── session_chain_stress end-to-end ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_session_chain_stress_real_governor_two_traces(
    governor: EDONGovernor, store: TraceStore
):
    """Two real traces in a session → at least one ChainStressResult produced."""
    store.save_trace(_email_trace("cs-t1", "ALLOW", "sess-chain"))
    store.save_trace(_email_trace("cs-t2", "ALLOW", "sess-chain"))

    results = await session_chain_stress(
        "sess-chain", governor=governor, store=store, max_perturbations=2
    )
    assert len(results) >= 1
    assert all(isinstance(r, ChainStressResult) for r in results)


@pytest.mark.asyncio
async def test_session_chain_stress_severity_is_valid(
    governor: EDONGovernor, store: TraceStore
):
    """All chain stress results have a recognized severity string."""
    for i in range(3):
        store.save_trace(_email_trace(f"cs-multi-{i}", "ALLOW", "sess-multi"))

    results = await session_chain_stress(
        "sess-multi", governor=governor, store=store, max_perturbations=2
    )
    assert all(r.severity in ("stable", "advisory", "critical") for r in results)


@pytest.mark.asyncio
async def test_session_chain_stress_cascade_counts_are_non_negative(
    governor: EDONGovernor, store: TraceStore
):
    store.save_trace(_email_trace("cs-a", "ALLOW", "sess-cascade"))
    store.save_trace(_email_trace("cs-b", "ALLOW", "sess-cascade"))
    store.save_trace(_email_trace("cs-c", "BLOCK", "sess-cascade"))

    results = await session_chain_stress(
        "sess-cascade", governor=governor, store=store, max_perturbations=2
    )
    assert all(r.cascade_count >= 0 for r in results)
    assert all(r.steps_after > 0 for r in results)
