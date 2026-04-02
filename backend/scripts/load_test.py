#!/usr/bin/env python3
"""Load test for EDON Gateway — validates 10K requests/min throughput target.

Fires concurrent POST /v1/action requests and reports p50/p95/p99 latency.
Exits non-zero if p99 > P99_TARGET_MS or error rate > MAX_ERROR_RATE_PCT.

Usage:
    python scripts/load_test.py [--url URL] [--token TOKEN] [--rps RPS]
                                [--duration SECS] [--workers WORKERS]

Environment (override via flags):
    EDON_GATEWAY_URL    Base URL (default: http://localhost:8000)
    EDON_API_TOKEN      Bearer token (default: test-token)
    EDON_AUTH_ENABLED   Set to "true" to include auth header

Defaults target: 100 robots × ~2 req/sec = ~200 req/sec sustained (12,000/min),
 running for 30 seconds with 20 worker threads.
"""

import argparse
import os
import sys
import time
import statistics
import threading
import queue
from datetime import datetime, UTC
from typing import List, Optional

try:
    import requests
except ImportError:
    print("requests library not found. Install: pip install requests")
    sys.exit(1)

# ---- Defaults ----
DEFAULT_URL = os.getenv("EDON_GATEWAY_URL", "http://localhost:8000")
DEFAULT_TOKEN = os.getenv("EDON_API_TOKEN", "test-token")
DEFAULT_AUTH = os.getenv("EDON_AUTH_ENABLED", "false").lower() == "true"
DEFAULT_RPS = 200          # requests per second (12K/min)
DEFAULT_DURATION = 30      # seconds
DEFAULT_WORKERS = 20       # concurrent threads
P99_TARGET_MS = float(os.getenv("EDON_SLO_P99_MS", "100"))
MAX_ERROR_RATE_PCT = 1.0   # fail if >1% errors


# ---- Result tracking ----
results_lock = threading.Lock()
latencies: List[float] = []
errors: List[str] = []
status_codes: dict = {}


def _make_headers(token: str, use_auth: bool) -> dict:
    h = {"Content-Type": "application/json"}
    if use_auth and token:
        h["Authorization"] = f"Bearer {token}"
        h["X-EDON-TOKEN"] = token
    return h


def _make_body(agent_num: int) -> dict:
    return {
        "agent_id": f"load-test-agent-{agent_num % 100:03d}",
        "action_type": "tool_call",
        "action_payload": {
            "tool": "memory",
            "op": "get",
            "params": {"key": f"test_{agent_num}"},
        },
        "timestamp": datetime.now(UTC).isoformat(),
        "context": {"cav_score": 0.2, "environment": "load_test"},
    }


def worker(
    base_url: str,
    headers: dict,
    request_queue: queue.Queue,
    done_event: threading.Event,
):
    """Worker thread: drain request_queue until done_event set."""
    session = requests.Session()
    session.headers.update(headers)

    while not done_event.is_set() or not request_queue.empty():
        try:
            req_num = request_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        body = _make_body(req_num)
        t0 = time.perf_counter()
        status = 0
        try:
            resp = session.post(f"{base_url}/v1/action", json=body, timeout=5)
            status = resp.status_code
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            with results_lock:
                latencies.append(elapsed_ms)
                status_codes[status] = status_codes.get(status, 0) + 1

                if status >= 400:
                    errors.append(f"HTTP {status}: {resp.text[:100]}")

        except requests.exceptions.ConnectionError:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            with results_lock:
                errors.append("ConnectionError")
                latencies.append(elapsed_ms)
        except requests.exceptions.Timeout:
            with results_lock:
                errors.append("Timeout")
                latencies.append(5000.0)

        request_queue.task_done()


def run_load_test(
    base_url: str,
    token: str,
    use_auth: bool,
    target_rps: int,
    duration_secs: int,
    num_workers: int,
) -> bool:
    """Run the load test. Returns True if all SLOs met."""
    print(f"\nEDON Gateway Load Test")
    print(f"  Target:   {base_url}/v1/action")
    print(f"  RPS:      {target_rps} req/sec ({target_rps * 60:,}/min)")
    print(f"  Duration: {duration_secs}s")
    print(f"  Workers:  {num_workers}")
    print(f"  P99 SLO:  {P99_TARGET_MS}ms")
    print("-" * 50)

    headers = _make_headers(token, use_auth)
    request_queue = queue.Queue(maxsize=target_rps * duration_secs * 2)
    done_event = threading.Event()

    # Start workers
    threads = []
    for _ in range(num_workers):
        t = threading.Thread(target=worker, args=(base_url, headers, request_queue, done_event))
        t.daemon = True
        t.start()
        threads.append(t)

    # Feed requests at target rate
    total_requests = target_rps * duration_secs
    interval = 1.0 / target_rps
    t_start = time.perf_counter()
    sent = 0

    print(f"Sending {total_requests:,} requests...")
    try:
        for i in range(total_requests):
            request_queue.put(i)
            sent += 1

            # Pace the queue to stay at target RPS
            elapsed = time.perf_counter() - t_start
            expected = (i + 1) * interval
            sleep_time = expected - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

            # Progress update every 10%
            if sent % max(1, total_requests // 10) == 0:
                pct = 100 * sent // total_requests
                current_rps = sent / max(0.001, time.perf_counter() - t_start)
                print(f"  {pct}% sent ({sent:,}/{total_requests:,}), actual RPS: {current_rps:.0f}")

    except KeyboardInterrupt:
        print("\nInterrupted by user.")

    # Wait for all requests to complete
    print("Waiting for in-flight requests to complete...")
    done_event.set()
    for t in threads:
        t.join(timeout=10)

    elapsed_total = time.perf_counter() - t_start

    # ---- Report ----
    with results_lock:
        total = len(latencies)
        num_errors = len(errors)

    if total == 0:
        print("ERROR: No requests completed. Is the gateway running?")
        return False

    sorted_lat = sorted(latencies)
    p50 = statistics.median(sorted_lat)
    p95 = sorted_lat[int(len(sorted_lat) * 0.95)]
    p99 = sorted_lat[int(len(sorted_lat) * 0.99)]
    avg = statistics.mean(sorted_lat)
    actual_rps = total / elapsed_total
    error_rate = 100.0 * num_errors / total

    print("\n" + "=" * 50)
    print("LOAD TEST RESULTS")
    print("=" * 50)
    print(f"  Total requests:    {total:,}")
    print(f"  Duration:          {elapsed_total:.1f}s")
    print(f"  Actual RPS:        {actual_rps:.1f} req/sec ({actual_rps * 60:,.0f}/min)")
    print(f"  Error rate:        {error_rate:.2f}% ({num_errors} errors)")
    print(f"\n  Latency:")
    print(f"    p50:  {p50:.1f}ms")
    print(f"    p95:  {p95:.1f}ms")
    print(f"    p99:  {p99:.1f}ms  (SLO target: {P99_TARGET_MS}ms)")
    print(f"    avg:  {avg:.1f}ms")
    print(f"\n  Status codes: {dict(sorted(status_codes.items()))}")

    if errors[:5]:
        print(f"\n  Sample errors (first 5):")
        for e in errors[:5]:
            print(f"    - {e}")

    print("=" * 50)

    # ---- SLO evaluation ----
    passed = True

    if p99 > P99_TARGET_MS:
        print(f"FAIL: p99 {p99:.1f}ms exceeds SLO target {P99_TARGET_MS}ms")
        passed = False
    else:
        print(f"PASS: p99 {p99:.1f}ms <= SLO target {P99_TARGET_MS}ms")

    if error_rate > MAX_ERROR_RATE_PCT:
        print(f"FAIL: error rate {error_rate:.2f}% exceeds max {MAX_ERROR_RATE_PCT}%")
        passed = False
    else:
        print(f"PASS: error rate {error_rate:.2f}% <= max {MAX_ERROR_RATE_PCT}%")

    target_rps_actual = target_rps * 0.9  # allow 10% slack
    if actual_rps < target_rps_actual:
        print(f"WARN: actual RPS {actual_rps:.0f} below target {target_rps} (>10% shortfall)")
    else:
        print(f"PASS: actual RPS {actual_rps:.0f} >= {target_rps_actual:.0f} (90% of target)")

    return passed


def main():
    parser = argparse.ArgumentParser(description="EDON Gateway load test")
    parser.add_argument("--url", default=DEFAULT_URL, help="Gateway base URL")
    parser.add_argument("--token", default=DEFAULT_TOKEN, help="API token")
    parser.add_argument("--auth", action="store_true", default=DEFAULT_AUTH, help="Include auth header")
    parser.add_argument("--rps", type=int, default=DEFAULT_RPS, help="Target requests/second")
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION, help="Test duration in seconds")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Concurrent workers")
    args = parser.parse_args()

    # Sanity check: gateway reachable?
    try:
        resp = requests.get(f"{args.url}/health", timeout=5)
        print(f"Gateway health: HTTP {resp.status_code}")
    except Exception as exc:
        print(f"Gateway not reachable at {args.url}: {exc}")
        print("Start the gateway first: uvicorn edon_gateway.main:app --port 8000")
        sys.exit(1)

    passed = run_load_test(
        base_url=args.url,
        token=args.token,
        use_auth=args.auth,
        target_rps=args.rps,
        duration_secs=args.duration,
        num_workers=args.workers,
    )

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
