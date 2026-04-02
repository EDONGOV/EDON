"""
Performance test: POST /v1/action latency under load.

Fires 500 requests via TestClient and asserts p99 < 100ms.
"""

import statistics
import time
from datetime import datetime, UTC

import pytest


@pytest.fixture(autouse=True)
def disable_auth(monkeypatch):
    """Disable authentication so tests run without token setup."""
    monkeypatch.setenv("EDON_AUTH_ENABLED", "false")
    from cryptography.fernet import Fernet
    monkeypatch.setenv("EDON_DB_ENCRYPTION_KEY", Fernet.generate_key().decode())
    import edon_gateway.config as cfg
    monkeypatch.setattr(cfg.config, "_AUTH_ENABLED", False)


@pytest.fixture
def client(disable_auth):
    from starlette.testclient import TestClient
    from edon_gateway.main import app
    with TestClient(app, headers={"X-Agent-ID": "perf-agent-001"}) as c:
        yield c


def _action_body():
    return {
        "agent_id": "perf-agent-001",
        "action_type": "tool_call",
        "action_payload": {"tool": "email", "op": "read", "params": {"folder": "inbox"}},
        "timestamp": datetime.now(UTC).isoformat(),
        "context": {},
    }


def test_v1_action_p99_latency(client):
    """500 POST /v1/action requests; p99 must be under threshold.

    Production SLA: p99 < 100ms.
    Dev/CI override: set EDON_PERF_TEST_P99_THRESHOLD_MS env var (default 1000ms
    on non-Linux to account for test environment overhead on Windows/macOS).
    """
    import os
    import platform
    n = 500
    latencies = []

    # Use 100ms on Linux (CI / production), 1000ms on Windows/macOS (dev machines)
    # Windows SQLite has higher scheduling jitter, especially after a full test suite run
    default_threshold = 100 if platform.system() == "Linux" else 1000
    threshold_ms = float(os.getenv("EDON_PERF_TEST_P99_THRESHOLD_MS", str(default_threshold)))

    for _ in range(n):
        start = time.perf_counter()
        resp = client.post("/v1/action", json=_action_body())
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies.append(elapsed_ms)
        # Accept any governance decision — we're measuring latency, not correctness
        assert resp.status_code in (200, 400, 422), f"Unexpected status: {resp.status_code} {resp.text[:200]}"

    latencies.sort()
    p50 = statistics.median(latencies)
    p95 = latencies[int(0.95 * n) - 1]
    p99 = latencies[int(0.99 * n) - 1]

    print(f"\nLatency over {n} requests — p50={p50:.2f}ms  p95={p95:.2f}ms  p99={p99:.2f}ms (threshold={threshold_ms}ms)")

    assert p99 < threshold_ms, (
        f"p99 latency {p99:.2f}ms exceeds {threshold_ms}ms threshold "
        f"(p50={p50:.2f}ms, p95={p95:.2f}ms). "
        f"Production SLA is 100ms (Linux). Override with EDON_PERF_TEST_P99_THRESHOLD_MS."
    )
