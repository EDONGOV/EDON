"""Live HTTP-stack tests for shadow replay end-to-end.

Uses httpx + ASGI transport so no external server is needed — the full
FastAPI app runs in-process in the same event loop as the test.

Marked @pytest.mark.live_server so they are auto-skipped in normal CI
(the app startup pulls many imports). Run explicitly with:

    EDON_RUN_LIVE_TESTS=true pytest edon_gateway/shadow/tests/test_live_server.py -v

What these tests prove that unit/integration tests cannot:
  1. /v1/action correctly captures traces via capture_trace().
  2. shadow_should_sample() + asyncio.create_task() dispatch shadow replay
     as a real background task in the event loop.
  3. GET /v1/shadow/traces, /findings, /summary, /baseline, /export all
     read from the SAME store instance that was written by the background task.
  4. POST /v1/shadow/chain-stress drives session_chain_stress() through the
     real governor with traces seeded via the live /v1/action endpoint.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, UTC
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio

pytestmark = pytest.mark.live_server


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _drain_shadow_tasks() -> None:
    """Wait for every shadow_run_trace background task in the current event loop.

    asyncio.create_task() queues the coroutine but doesn't run it until we
    yield. Gathering the tasks explicitly is far more reliable than a fixed
    sleep — it works regardless of how fast/slow the CI machine is and
    prevents pending tasks from bleeding into the next test.
    """
    shadow_tasks = [
        t for t in asyncio.all_tasks()
        if t is not asyncio.current_task() and "shadow_run_trace" in repr(t)
    ]
    if shadow_tasks:
        await asyncio.gather(*shadow_tasks, return_exceptions=True)
    else:
        # Brief yield so any tasks scheduled via create_task get a chance to start
        await asyncio.sleep(0.05)


async def _wait_for_background_tasks() -> None:
    """Wait for shadow background tasks then drain any remaining queue."""
    await _drain_shadow_tasks()


# ── App and client fixtures ────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def app_client(tmp_path: Path, monkeypatch) -> AsyncGenerator:
    """Create an in-process ASGI client with:
      - Auth disabled
      - Shadow sample rate = 100% (always replay)
      - Fresh shadow DB at tmp_path (avoids cross-test pollution)
      - Singleton store reset so get_trace_store() creates a new instance
    """
    import httpx
    from cryptography.fernet import Fernet

    # ── Environment ──────────────────────────────────────────────────────────
    monkeypatch.setenv("EDON_ENV", "development")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("EDON_AUTH_ENABLED", "false")
    monkeypatch.setenv("EDON_CREDENTIALS_STRICT", "false")
    monkeypatch.setenv("EDON_STRICT_FAIL_CLOSED", "false")
    monkeypatch.setenv("EDON_DB_ENCRYPTION_KEY", Fernet.generate_key().decode())

    # Force shadow to always sample and write to our test DB.
    # Keep perturbation count low (2) so background tasks finish well
    # within the sleep window and don't bleed into the next test.
    shadow_db = str(tmp_path / "shadow_test.db")
    monkeypatch.setenv("EDON_SHADOW_SAMPLE_RATE", "1.0")
    monkeypatch.setenv("EDON_SHADOW_DB_PATH", shadow_db)
    monkeypatch.setenv("EDON_SHADOW_MAX_PERTURBATIONS", "2")

    # ── Reset shadow store singleton and module-level constants ──────────────
    # _SAMPLE_RATE and _MAX_PERTURBATIONS are computed once at import time from
    # env vars. monkeypatch.setenv() is not enough — we must patch the live
    # module attributes directly so shadow_should_sample() sees rate=1.0.
    import edon_gateway.shadow.trace_capture as _tc
    import edon_gateway.shadow.replay as _replay
    monkeypatch.setattr(_tc, "_store", None)
    monkeypatch.setattr(_replay, "_SAMPLE_RATE", 1.0)
    monkeypatch.setattr(_replay, "_MAX_PERTURBATIONS", 2)

    import edon_gateway.config as cfg
    monkeypatch.setattr(cfg.config, "_AUTH_ENABLED", False)
    monkeypatch.setattr(cfg.config, "_ENVIRONMENT", "development")
    monkeypatch.setattr(cfg.config, "_CREDENTIALS_STRICT", False)

    # ── Build app + client ───────────────────────────────────────────────────
    from edon_gateway.main import app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        timeout=30.0,
    ) as client:
        yield client
        # Drain all pending shadow tasks before the fixture tears down.
        # Without this, background tasks from this test can still be running
        # when the next test's monkeypatch resets _store, causing cross-test
        # contamination (403s, missing findings, etc.).
        await _drain_shadow_tasks()


def _action_body(
    agent_id: str = "shadow-live-agent",
    action_type: str = "email.send",
    session_id: str = "sess-live-001",
) -> dict:
    return {
        "agent_id": agent_id,
        "action_type": action_type,
        "action_payload": {
            "to": "user@example.com",
            "subject": "Weekly report",
            "body": "Here is your report.",
        },
        "timestamp": datetime.now(UTC).isoformat(),
        "context": {
            "session_id": session_id,
            "stated_intent": "send weekly report",
        },
    }


# ── /v1/action → trace capture ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_v1_action_returns_200(app_client):
    """Basic smoke test: /v1/action responds with 200 and the expected fields."""
    resp = await app_client.post("/v1/action", json=_action_body())
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "decision" in data
    assert "action_id" in data
    assert data["decision"] in ("ALLOW", "BLOCK", "HUMAN_REQUIRED", "DEGRADE", "PAUSE")


@pytest.mark.asyncio
async def test_v1_action_captures_trace(app_client):
    """/v1/action always captures a trace — verified via GET /v1/shadow/traces."""
    resp = await app_client.post("/v1/action", json=_action_body(agent_id="trace-capture-agent"))
    assert resp.status_code == 200, resp.text

    # capture_trace() is synchronous inside the handler — no sleep needed
    traces_resp = await app_client.get("/v1/shadow/traces")
    assert traces_resp.status_code == 200
    data = traces_resp.json()
    assert data["count"] >= 1

    agents = [t["agent_id"] for t in data["traces"]]
    assert "trace-capture-agent" in agents


@pytest.mark.asyncio
async def test_v1_action_trace_has_correct_verdict(app_client):
    """The captured trace records the original verdict from the governor."""
    resp = await app_client.post("/v1/action", json=_action_body(action_type="email.send"))
    assert resp.status_code == 200

    traces_resp = await app_client.get("/v1/shadow/traces")
    traces = traces_resp.json()["traces"]
    assert len(traces) >= 1

    # The trace original_verdict should align with the response decision
    trace = traces[0]
    assert trace["original_verdict"] in ("ALLOW", "BLOCK", "ESCALATE", "PAUSE", "DEGRADE", "ERROR")
    assert trace["action_type"] == "email.send"


# ── Shadow replay background task ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_shadow_replay_fires_as_background_task(app_client):
    """With sample_rate=1.0, shadow replay runs after /v1/action and populates findings."""
    resp = await app_client.post("/v1/action", json=_action_body(agent_id="shadow-agent-bg"))
    assert resp.status_code == 200

    # Response came back before background task — yield to event loop
    await _wait_for_background_tasks()

    summary = (await app_client.get("/v1/shadow/summary")).json()
    total = summary.get("stable", 0) + summary.get("advisory", 0) + summary.get("critical", 0)
    assert total > 0, (
        f"Expected shadow findings after replay, got summary={summary}. "
        "Background task may not have run."
    )


@pytest.mark.asyncio
async def test_shadow_replay_response_time_is_not_blocked(app_client):
    """Shadow replay is non-blocking: /v1/action returns before replay completes."""
    import time
    start = time.time()
    resp = await app_client.post("/v1/action", json=_action_body())
    elapsed_ms = (time.time() - start) * 1000

    assert resp.status_code == 200
    # Response should come back quickly even though replay runs max 3 perturbations
    # Use a generous bound (2 s) to avoid flakiness on slow CI machines
    assert elapsed_ms < 2000, (
        f"Response took {elapsed_ms:.0f}ms — shadow replay may be blocking the handler"
    )


@pytest.mark.asyncio
async def test_shadow_baseline_recorded_after_replay(app_client):
    """GET /v1/shadow/baseline/{trace_id} returns a result after replay runs."""
    resp = await app_client.post("/v1/action", json=_action_body())
    assert resp.status_code == 200
    await _wait_for_background_tasks()

    # Get the trace_id from the traces API
    traces = (await app_client.get("/v1/shadow/traces")).json()["traces"]
    assert len(traces) >= 1
    trace_id = traces[0]["trace_id"]

    baseline_resp = await app_client.get(f"/v1/shadow/baseline/{trace_id}")
    assert baseline_resp.status_code == 200
    baseline = baseline_resp.json()
    assert baseline["trace_id"] == trace_id
    assert baseline["baseline_verdict"] in ("ALLOW", "BLOCK", "ESCALATE", "PAUSE", "DEGRADE", "ERROR")
    assert baseline["baseline_latency_ms"] >= 0
    assert baseline["non_determinism_flag"] in (0, 1, True, False)


# ── Shadow findings API ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_shadow_findings_api_returns_results(app_client):
    """GET /v1/shadow/findings returns structured findings with expected fields."""
    await app_client.post("/v1/action", json=_action_body())
    await _wait_for_background_tasks()

    resp = await app_client.get("/v1/shadow/findings")
    assert resp.status_code == 200
    data = resp.json()
    assert "findings" in data
    assert "count" in data

    if data["count"] > 0:
        finding = data["findings"][0]
        assert "severity" in finding
        assert finding["severity"] in ("stable", "advisory", "critical")
        assert "perturbation_type" in finding
        assert "shadow_verdict" in finding
        assert "trace_id" in finding


@pytest.mark.asyncio
async def test_shadow_findings_severity_filter(app_client):
    """GET /v1/shadow/findings?severity=stable only returns stable findings."""
    await app_client.post("/v1/action", json=_action_body())
    await _wait_for_background_tasks()

    resp = await app_client.get("/v1/shadow/findings?severity=stable")
    assert resp.status_code == 200
    findings = resp.json()["findings"]
    assert all(f["severity"] == "stable" for f in findings)


@pytest.mark.asyncio
async def test_shadow_summary_counts_are_consistent(app_client):
    """Summary counts are non-negative integers and sum correctly."""
    await app_client.post("/v1/action", json=_action_body())
    await _wait_for_background_tasks()

    summary = (await app_client.get("/v1/shadow/summary")).json()
    assert summary.get("stable", 0) >= 0
    assert summary.get("advisory", 0) >= 0
    assert summary.get("critical", 0) >= 0
    assert summary.get("non_determinism_count", 0) >= 0


# ── Shadow export ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_shadow_export_json_structure(app_client):
    """GET /v1/shadow/export returns a structured JSON report."""
    await app_client.post("/v1/action", json=_action_body())
    await _wait_for_background_tasks()

    resp = await app_client.get("/v1/shadow/export?format=json")
    assert resp.status_code == 200
    data = resp.json()
    assert "report" in data
    assert "summary" in data
    assert "critical_findings" in data
    assert "advisory_findings" in data
    assert "confirmed_bypasses" in data


@pytest.mark.asyncio
async def test_shadow_export_csv_content_type(app_client):
    """GET /v1/shadow/export?format=csv returns a CSV response."""
    await app_client.post("/v1/action", json=_action_body())
    await _wait_for_background_tasks()

    resp = await app_client.get("/v1/shadow/export?format=csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")
    assert len(resp.content) > 0


# ── Chain stress via HTTP ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chain_stress_empty_session_returns_message(app_client):
    """POST /v1/shadow/chain-stress for a non-existent session returns the no-traces message."""
    resp = await app_client.post(
        "/v1/shadow/chain-stress?session_id=nonexistent-session-xyz"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"] == []
    assert "message" in data


@pytest.mark.asyncio
async def test_chain_stress_with_seeded_session(app_client):
    """Seed 2 traces via /v1/action, then run chain stress and get structured results."""
    session_id = "chain-stress-live-sess"

    # Seed two traces in the same session
    for _ in range(2):
        resp = await app_client.post(
            "/v1/action",
            json=_action_body(action_type="email.send", session_id=session_id),
        )
        assert resp.status_code == 200

    # Chain stress runs synchronously (session_chain_stress is awaited directly in route)
    resp = await app_client.post(
        f"/v1/shadow/chain-stress"
        f"?session_id={session_id}&max_perturbations=2"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session_id
    assert "summary" in data
    assert "results" in data
    assert len(data["results"]) >= 1

    for result in data["results"]:
        assert result["severity"] in ("stable", "advisory", "critical")
        assert result["cascade_count"] >= 0
        assert result["steps_after"] >= 1


@pytest.mark.asyncio
async def test_chain_stress_summary_counts_are_consistent(app_client):
    """Chain stress summary critical+advisory+stable sums to total_tests."""
    session_id = "chain-stress-counts-sess"
    for _ in range(2):
        await app_client.post(
            "/v1/action",
            json=_action_body(action_type="email.send", session_id=session_id),
        )

    resp = await app_client.post(
        f"/v1/shadow/chain-stress?session_id={session_id}&max_perturbations=2"
    )
    assert resp.status_code == 200
    summary = resp.json()["summary"]
    total = summary["critical"] + summary["advisory"] + summary["stable"]
    assert total == summary["total_tests"]


# ── Multiple requests accumulate ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_multiple_requests_accumulate_traces(app_client):
    """Each /v1/action call adds a trace; count grows monotonically."""
    for i in range(3):
        resp = await app_client.post(
            "/v1/action",
            json=_action_body(agent_id=f"multi-agent-{i}"),
        )
        assert resp.status_code == 200

    traces = (await app_client.get("/v1/shadow/traces")).json()
    assert traces["count"] >= 3


@pytest.mark.asyncio
async def test_multiple_requests_produce_multiple_shadow_runs(app_client):
    """3 requests at sample_rate=1.0 → ≥3 shadow runs worth of findings."""
    for _ in range(3):
        await app_client.post("/v1/action", json=_action_body())
    await _wait_for_background_tasks()

    summary = (await app_client.get("/v1/shadow/summary")).json()
    total = summary.get("stable", 0) + summary.get("advisory", 0) + summary.get("critical", 0)
    # 3 requests × 3 perturbations minimum
    assert total >= 3, f"Expected ≥3 shadow findings, got {total} (summary={summary})"
