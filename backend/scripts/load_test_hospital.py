"""
Hospital-scale load test: POST /v1/action — 500 concurrent requests.

Asserts:
  - p99 latency < 100ms  (hospital SLA)
  - 0 requests returned 5xx errors
  - throughput >= 100 req/sec

Runs as a pytest test so it is automatically collected by the CI test suite
and enforces the hospital SLA on every merge.

Usage (standalone):
    # Against a running gateway (default: http://127.0.0.1:8000)
    pytest edon_gateway/scripts/load_test_hospital.py -v

    # Against a custom URL
    EDON_GATEWAY_URL=https://edon-gateway.fly.dev pytest edon_gateway/scripts/load_test_hospital.py -v

    # Adjust concurrency / request count via env vars
    EDON_HOSPITAL_REQUESTS=200 EDON_HOSPITAL_CONCURRENT=50 pytest ...

Design notes:
    - Uses httpx.AsyncClient for truly concurrent async I/O (not thread-per-request).
    - Payload simulates a hospital AI agent reading patient vitals — the canonical
      hospital governance use-case.
    - Auth is disabled inside the in-process TestClient path; the live-gateway path
      uses EDON_API_TOKEN from the environment (same as CI).
"""

import asyncio
import os
import statistics
import time
from datetime import datetime, UTC
from typing import List, Tuple

import pytest

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_BASE_URL = os.getenv("EDON_GATEWAY_URL", "").rstrip("/")
_AUTH_TOKEN = os.getenv("EDON_API_TOKEN", "test-token")
_TOTAL_REQUESTS = int(os.getenv("EDON_HOSPITAL_REQUESTS", "500"))
_CONCURRENT = int(os.getenv("EDON_HOSPITAL_CONCURRENT", "50"))

# SLA thresholds
_P99_MAX_MS = float(os.getenv("EDON_HOSPITAL_P99_MAX_MS", "100"))
_MIN_RPS = float(os.getenv("EDON_HOSPITAL_MIN_RPS", "100"))

# Hospital AI agent test payload
_HOSPITAL_PAYLOAD = {
    "agent_id": "hospital_ai_agent_load_test",
    "action": {
        "tool": "read_file",
        "operation": "read",
        "parameters": {"path": "/patient/records/test123"},
        "risk_level": "medium",
    },
    "stated_intent": "retrieve patient vitals for clinical review",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _percentile(sorted_values: List[float], p: float) -> float:
    """Return the p-th percentile (0–100) using linear interpolation."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    k = (n - 1) * (p / 100)
    lo = min(int(k), n - 1)
    hi = min(lo + 1, n - 1)
    return sorted_values[lo] + (k - lo) * (sorted_values[hi] - sorted_values[lo])


def _action_body() -> dict:
    """Return a fresh timestamped copy of the hospital payload."""
    payload = dict(_HOSPITAL_PAYLOAD)
    payload["timestamp"] = datetime.now(UTC).isoformat()
    return payload


# ---------------------------------------------------------------------------
# Async worker (used when hitting a live gateway via httpx)
# ---------------------------------------------------------------------------

async def _async_fire(
    client,  # httpx.AsyncClient
    semaphore: asyncio.Semaphore,
    req_id: int,
) -> Tuple[int, float]:
    """Send one POST /v1/action; return (status_code, latency_ms)."""
    async with semaphore:
        start = time.perf_counter()
        try:
            resp = await client.post("/v1/action", json=_action_body())
            elapsed_ms = (time.perf_counter() - start) * 1000
            return resp.status_code, elapsed_ms
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return 0, elapsed_ms


async def _run_async_load(base_url: str) -> Tuple[List[float], int, float]:
    """
    Fire _TOTAL_REQUESTS requests to base_url with up to _CONCURRENT in flight.

    Returns:
        (latencies_ms, error_count, total_elapsed_sec)
    """
    try:
        import httpx
    except ImportError:
        raise ImportError("httpx is required for the async load test: pip install httpx")

    headers = {
        "X-EDON-TOKEN": _AUTH_TOKEN,
        "X-Agent-ID": "hospital_ai_agent_load_test",
        "Content-Type": "application/json",
    }

    semaphore = asyncio.Semaphore(_CONCURRENT)
    latencies: List[float] = []
    error_count = 0

    async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=30) as client:
        wall_start = time.perf_counter()
        tasks = [
            _async_fire(client, semaphore, i)
            for i in range(_TOTAL_REQUESTS)
        ]
        results = await asyncio.gather(*tasks)
        total_elapsed = time.perf_counter() - wall_start

    for status, lat in results:
        latencies.append(lat)
        if status == 0 or status >= 500:
            error_count += 1

    return latencies, error_count, total_elapsed


# ---------------------------------------------------------------------------
# Sync in-process path (used when EDON_GATEWAY_URL is not set)
# ---------------------------------------------------------------------------

def _run_sync_load_via_testclient() -> Tuple[List[float], int, float]:
    """
    Fire _TOTAL_REQUESTS requests through FastAPI's synchronous TestClient.

    This avoids needing a running server and is safe for pytest collection.
    Concurrency is emulated sequentially here — for true concurrent testing
    set EDON_GATEWAY_URL to a running instance.
    """
    from starlette.testclient import TestClient
    from edon_gateway.main import app

    latencies: List[float] = []
    error_count = 0

    with TestClient(app, headers={"X-Agent-ID": "hospital_ai_agent_load_test"}) as client:
        wall_start = time.perf_counter()
        for _ in range(_TOTAL_REQUESTS):
            start = time.perf_counter()
            resp = client.post("/v1/action", json=_action_body())
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)
            if resp.status_code >= 500:
                error_count += 1
        total_elapsed = time.perf_counter() - wall_start

    return latencies, error_count, total_elapsed


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def disable_auth(monkeypatch):
    """Disable auth so tests run without a real token — applies for in-process path only."""
    monkeypatch.setenv("EDON_AUTH_ENABLED", "false")
    try:
        from cryptography.fernet import Fernet
        monkeypatch.setenv("EDON_DB_ENCRYPTION_KEY", Fernet.generate_key().decode())
    except ImportError:
        pass
    try:
        import edon_gateway.config as cfg
        monkeypatch.setattr(cfg.config, "_AUTH_ENABLED", False)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

def test_hospital_scale_p99_latency_and_throughput():
    """
    Hospital SLA gate: 500 requests, p99 < 100ms, 0 5xx, >= 100 req/s.

    When EDON_GATEWAY_URL is set, fires against a live running gateway using
    httpx async (true concurrent I/O).  Otherwise uses FastAPI TestClient for
    in-process testing.
    """
    if _BASE_URL:
        # Hit a real running gateway — use async httpx for concurrency
        latencies, error_count, total_elapsed = asyncio.run(
            _run_async_load(_BASE_URL)
        )
        mode = f"live gateway at {_BASE_URL} ({_CONCURRENT} concurrent async workers)"
    else:
        # In-process via TestClient — sequential (no real concurrent I/O)
        latencies, error_count, total_elapsed = _run_sync_load_via_testclient()
        mode = "in-process TestClient (sequential; set EDON_GATEWAY_URL for true concurrency)"

    assert latencies, "No requests completed — is the gateway running?"

    latencies_sorted = sorted(latencies)
    n = len(latencies_sorted)
    p50 = statistics.median(latencies_sorted)
    p95 = _percentile(latencies_sorted, 95)
    p99 = _percentile(latencies_sorted, 99)
    rps = n / total_elapsed if total_elapsed > 0 else 0

    print(
        f"\n{'=' * 60}\n"
        f"Hospital Load Test Results\n"
        f"Mode:       {mode}\n"
        f"Requests:   {n}/{_TOTAL_REQUESTS}\n"
        f"Duration:   {total_elapsed:.2f}s\n"
        f"Throughput: {rps:.1f} req/s  (SLA: >= {_MIN_RPS})\n"
        f"Latency:    p50={p50:.2f}ms  p95={p95:.2f}ms  p99={p99:.2f}ms  "
        f"(SLA: p99 < {_P99_MAX_MS}ms)\n"
        f"5xx errors: {error_count}  (SLA: 0)\n"
        f"{'=' * 60}"
    )

    # ---- Assert 0 5xx errors ----
    assert error_count == 0, (
        f"{error_count} requests returned 5xx (or connection error). "
        f"Hospital agents must never receive server errors."
    )

    # ---- Assert p99 < hospital SLA ----
    assert p99 < _P99_MAX_MS, (
        f"p99 latency {p99:.2f}ms exceeds hospital SLA of {_P99_MAX_MS}ms "
        f"(p50={p50:.2f}ms, p95={p95:.2f}ms). "
        f"Tune policy engine or add caching. Override with EDON_HOSPITAL_P99_MAX_MS."
    )

    # ---- Assert throughput >= 100 req/s ----
    # In-process TestClient is single-threaded so throughput reflects
    # average per-request latency, not true concurrent throughput.
    # Skip the throughput assertion in in-process mode to avoid false failures.
    if _BASE_URL:
        assert rps >= _MIN_RPS, (
            f"Throughput {rps:.1f} req/s is below the minimum of {_MIN_RPS} req/s. "
            f"The gateway may be CPU-bound or the DB is a bottleneck. "
            f"Override with EDON_HOSPITAL_MIN_RPS."
        )
