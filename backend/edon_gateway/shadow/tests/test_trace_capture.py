"""Tests for trace capture and store.

Verifies that traces, baselines, action results, confirmed bypasses,
and session queries are persisted and retrieved correctly.
"""

import json
import pytest
from pathlib import Path

from ..trace_capture import AgentTrace, ActionResult, TraceStore


# ── Fixtures ────────────────────────────────────────────────────────────────────


@pytest.fixture
def store(tmp_path: Path) -> TraceStore:
    return TraceStore(db_path=str(tmp_path / "test_shadow.db"))


def _make_trace(
    trace_id: str = "trace-001",
    agent_id: str = "agent-test",
    tenant_id: str = "tenant-abc",
    action_type: str = "email.send",
    verdict: str = "BLOCK",
    session_id: str = "sess-001",
) -> AgentTrace:
    return AgentTrace(
        trace_id=trace_id,
        captured_at="2026-04-11T10:00:00+00:00",
        agent_id=agent_id,
        tenant_id=tenant_id,
        action_type=action_type,
        action_payload={"to": "user@example.com", "body": "hello"},
        context={"session_id": session_id, "stated_intent": "send report"},
        timestamp="2026-04-11T10:00:00Z",
        intent_id=None,
        original_verdict=verdict,
        original_reason="Policy rule matched",
        original_latency_ms=42,
        original_meta={},
    )


# ── AgentTrace.from_action_request ────────────────────────────────────────────


def test_from_action_request_strips_secrets():
    trace = AgentTrace.from_action_request(
        agent_id="agent-1",
        tenant_id="t1",
        action_type="http.post",
        action_payload={"url": "https://api.example.com"},
        context={"api_key": "super-secret", "session_id": "s1"},
        timestamp="2026-04-11T10:00:00Z",
        intent_id=None,
        verdict="ALLOW",
        reason="ok",
        latency_ms=10,
    )
    assert "api_key" not in trace.context
    assert "session_id" in trace.context


def test_from_action_request_assigns_trace_id():
    t1 = AgentTrace.from_action_request(
        agent_id="a", tenant_id=None, action_type="file.read",
        action_payload={}, context={}, timestamp="2026-01-01T00:00:00Z",
        intent_id=None, verdict="ALLOW", reason="", latency_ms=1,
    )
    t2 = AgentTrace.from_action_request(
        agent_id="a", tenant_id=None, action_type="file.read",
        action_payload={}, context={}, timestamp="2026-01-01T00:00:00Z",
        intent_id=None, verdict="ALLOW", reason="", latency_ms=1,
    )
    assert t1.trace_id != t2.trace_id


# ── TraceStore: traces ─────────────────────────────────────────────────────────


def test_save_and_retrieve_trace(store: TraceStore):
    trace = _make_trace()
    store.save_trace(trace)
    traces = store.get_recent_traces(limit=10)
    assert len(traces) == 1
    assert traces[0].trace_id == "trace-001"
    assert traces[0].original_verdict == "BLOCK"
    assert traces[0].action_payload == {"to": "user@example.com", "body": "hello"}


def test_get_recent_traces_tenant_filter(store: TraceStore):
    store.save_trace(_make_trace("t1", tenant_id="tenant-A"))
    store.save_trace(_make_trace("t2", tenant_id="tenant-B"))
    traces_a = store.get_recent_traces(tenant_id="tenant-A")
    assert len(traces_a) == 1
    assert traces_a[0].trace_id == "t1"


def test_get_recent_traces_limit(store: TraceStore):
    for i in range(5):
        store.save_trace(_make_trace(trace_id=f"trace-{i:03d}"))
    traces = store.get_recent_traces(limit=3)
    assert len(traces) == 3


# ── TraceStore: session traces ─────────────────────────────────────────────────


def test_get_session_traces_ordered_by_time(store: TraceStore):
    t1 = _make_trace("t1", session_id="sess-xyz")
    t1_late = AgentTrace(
        trace_id="t2",
        captured_at="2026-04-11T10:01:00+00:00",
        agent_id="agent-test",
        tenant_id="tenant-abc",
        action_type="file.read",
        action_payload={},
        context={"session_id": "sess-xyz"},
        timestamp="2026-04-11T10:01:00Z",
        intent_id=None,
        original_verdict="ALLOW",
        original_reason="ok",
        original_latency_ms=5,
    )
    store.save_trace(t1)
    store.save_trace(t1_late)

    session_traces = store.get_session_traces("sess-xyz")
    assert len(session_traces) == 2
    assert session_traces[0].trace_id == "t1"
    assert session_traces[1].trace_id == "t2"


def test_get_session_traces_unknown_session_returns_empty(store: TraceStore):
    store.save_trace(_make_trace("t1", session_id="sess-real"))
    result = store.get_session_traces("sess-nonexistent")
    assert result == []


# ── TraceStore: action results ─────────────────────────────────────────────────


def test_save_and_retrieve_action_result(store: TraceStore):
    result = ActionResult.build(
        action_id="dec-001",
        agent_id="agent-test",
        tenant_id="tenant-abc",
        action_type="email.send",
        outcome="success",
        latency_ms=340,
        executed_at="2026-04-11T10:05:00Z",
    )
    store.save_action_result(result)
    row = store.get_action_result("dec-001")
    assert row is not None
    assert row["outcome"] == "success"
    assert row["agent_id"] == "agent-test"


def test_action_result_caps_summary_length(store: TraceStore):
    result = ActionResult.build(
        action_id="dec-002",
        agent_id="a",
        tenant_id=None,
        action_type="file.write",
        outcome="success",
        latency_ms=10,
        executed_at="2026-04-11T10:00:00Z",
        result_summary="x" * 1000,
    )
    assert result.result_summary is not None and len(result.result_summary) == 500


def test_get_action_result_missing_returns_none(store: TraceStore):
    assert store.get_action_result("nonexistent-id") is None


def test_outcome_stats_counts_correctly(store: TraceStore):
    for outcome in ("success", "success", "failure", "timeout"):
        r = ActionResult.build(
            action_id=f"dec-{outcome}-{id(outcome)}",
            agent_id="a", tenant_id=None,
            action_type="email.send", outcome=outcome,
            latency_ms=1, executed_at="2026-04-11T10:00:00Z",
        )
        store.save_action_result(r)
    stats = store.outcome_stats()
    assert stats["success"] == 2
    assert stats["failure"] == 1
    assert stats["timeout"] == 1


# ── TraceStore: confirmed bypasses ─────────────────────────────────────────────


def test_save_and_retrieve_confirmed_bypass(store: TraceStore):
    store.save_confirmed_bypass(
        action_id="dec-001",
        trace_id="trace-001",
        agent_id="agent-test",
        tenant_id="tenant-abc",
        action_type="email.send",
        perturbation_name="prompt_injection_payload_0",
        perturbation_type="prompt_injection",
        original_verdict="BLOCK",
        shadow_verdict="ALLOW",
        real_outcome="success",
    )
    bypasses = store.get_confirmed_bypasses()
    assert len(bypasses) == 1
    assert bypasses[0]["original_verdict"] == "BLOCK"
    assert bypasses[0]["shadow_verdict"] == "ALLOW"


def test_confirmed_bypasses_tenant_filter(store: TraceStore):
    store.save_confirmed_bypass(
        action_id="a1", trace_id="t1", agent_id="ag", tenant_id="tenant-A",
        action_type="shell.run", perturbation_name="p", perturbation_type="boundary_input",
        original_verdict="BLOCK", shadow_verdict="ALLOW", real_outcome="success",
    )
    store.save_confirmed_bypass(
        action_id="a2", trace_id="t2", agent_id="ag", tenant_id="tenant-B",
        action_type="shell.run", perturbation_name="p", perturbation_type="boundary_input",
        original_verdict="BLOCK", shadow_verdict="ALLOW", real_outcome="success",
    )
    result = store.get_confirmed_bypasses(tenant_id="tenant-A")
    assert len(result) == 1
    assert result[0]["tenant_id"] == "tenant-A"


# ── TraceStore: non-determinism count ─────────────────────────────────────────


def test_non_determinism_count(store: TraceStore):
    from ..replay import BaselineResult
    b1 = BaselineResult(
        trace_id="t1", baseline_verdict="BLOCK", baseline_reason="",
        baseline_latency_ms=5, matches_original=False, non_determinism_flag=True,
    )
    b2 = BaselineResult(
        trace_id="t2", baseline_verdict="ALLOW", baseline_reason="",
        baseline_latency_ms=5, matches_original=True, non_determinism_flag=False,
    )
    store.save_trace(_make_trace("t1"))
    store.save_trace(_make_trace("t2"))
    store.save_baseline(b1)
    store.save_baseline(b2)
    assert store.non_determinism_count() == 1
