#!/usr/bin/env python3
"""
Load test for POST /v1/action (and optionally /execute).
Target: verify p99 < 100ms at sustained load for 100 systems / 20M decisions/day readiness.

Usage:
  # With gateway running at default URL, 200 requests, 20 concurrent, assert p99 < 100ms
  python scripts/load_test_v1_action.py

  # Custom URL and duration
  EDON_GATEWAY_URL=http://127.0.0.1:8000 python scripts/load_test_v1_action.py --requests 500 --concurrent 25

  # Exit 0 only if p99 < 100ms (for CI)
  python scripts/load_test_v1_action.py --p99-max-ms 100
"""

import os
import sys
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)

BASE_URL = os.getenv("EDON_GATEWAY_URL", "http://127.0.0.1:8000").rstrip("/")
AUTH_TOKEN = os.getenv("EDON_API_TOKEN", "test-token")
# NOTE: X-Agent-ID is set per-request so the rate limiter treats each agent separately.
# Without it every request looks "anonymous" and hits the 10/min anonymous cap.
HEADERS = {"Content-Type": "application/json", "X-EDON-TOKEN": AUTH_TOKEN}

# Default: ~50 req/s for 4 seconds = 200 requests (light load for CI)
# For 20M/day peak (~500 req/s) run manually with --requests 2000 --concurrent 50
DEFAULT_REQUESTS = int(os.getenv("EDON_LOAD_TEST_REQUESTS", "200"))
DEFAULT_CONCURRENT = int(os.getenv("EDON_LOAD_TEST_CONCURRENT", "20"))


_first_error_printed = False

def one_request(session: requests.Session, endpoint: str, req_id: int) -> tuple[int, float]:
    """Send one POST /v1/action; return (status_code, latency_sec)."""
    global _first_error_printed
    payload = {
        "agent_id": "load-test-agent-ci",
        "action_type": "memory.get",
        "action_payload": {
            "key": f"test-key-{req_id % 10}",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    # Send agent_id in header so rate limiter uses per-agent limits, not anonymous limits
    req_headers = {**HEADERS, "X-Agent-ID": "load-test-agent-ci"}
    start = time.perf_counter()
    try:
        r = session.post(f"{BASE_URL}{endpoint}", json=payload, headers=req_headers, timeout=30)
        elapsed = time.perf_counter() - start
        if r.status_code != 200 and not _first_error_printed:
            _first_error_printed = True
            print(f"\n[FIRST ERROR] HTTP {r.status_code}: {r.text[:300]}\n", file=sys.stderr)
        return r.status_code, elapsed
    except Exception as exc:
        elapsed = time.perf_counter() - start
        if not _first_error_printed:
            _first_error_printed = True
            print(f"\n[FIRST ERROR] Exception: {exc}\n", file=sys.stderr)
        return 0, elapsed  # 0 = connection/error


def percentile(sorted_values: list[float], p: float) -> float:
    """p in 0..100. Returns value at percentile (linear interpolation)."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    k = (n - 1) * (p / 100)
    f = min(int(k), n - 1)
    c = min(f + 1, n - 1)
    return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])


def main():
    ap = argparse.ArgumentParser(description="Load test /v1/action for 100 systems / 20M day readiness")
    ap.add_argument("--requests", type=int, default=DEFAULT_REQUESTS, help="Total requests")
    ap.add_argument("--concurrent", type=int, default=DEFAULT_CONCURRENT, help="Concurrent workers")
    ap.add_argument("--endpoint", default="/v1/action", help="Endpoint (e.g. /v1/action or /execute)")
    ap.add_argument("--p99-max-ms", type=float, default=0, help="Exit 1 if p99 latency >= this (0 = don't fail)")
    args = ap.parse_args()

    latencies: list[float] = []
    errors = 0
    lock = Lock()

    t0 = time.perf_counter()
    with requests.Session() as session:
        with ThreadPoolExecutor(max_workers=args.concurrent) as ex:
            futures = [ex.submit(one_request, session, args.endpoint, i) for i in range(args.requests)]
            for fut in as_completed(futures):
                code, sec = fut.result()
                with lock:
                    latencies.append(sec * 1000.0)  # store as ms
                    if code != 200:
                        errors += 1
    total_sec = time.perf_counter() - t0

    if not latencies:
        print("No requests completed. Is the gateway running?", file=sys.stderr)
        sys.exit(2)

    latencies.sort()
    n = len(latencies)
    p50 = percentile(latencies, 50)
    p95 = percentile(latencies, 95)
    p99 = percentile(latencies, 99)
    rps = n / total_sec if total_sec > 0 else 0

    print(f"Target:    {BASE_URL}")
    print(f"Completed {n}/{args.requests} requests in {total_sec:.1f}s (~{rps:.0f} req/s), {errors} non-200")
    print(f"Latency ms — p50: {p50:.1f}  p95: {p95:.1f}  p99: {p99:.1f}")
    if args.p99_max_ms > 0:
        if p99 >= args.p99_max_ms:
            print(f"FAIL: p99 {p99:.1f} ms >= {args.p99_max_ms} ms", file=sys.stderr)
            sys.exit(1)
        print(f"PASS: p99 {p99:.1f} ms < {args.p99_max_ms} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
