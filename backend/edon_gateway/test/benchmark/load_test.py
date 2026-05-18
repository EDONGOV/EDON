"""Concurrent load benchmark.

Measures governance latency under sustained parallel load.
Run directly (not via pytest):

    python -m edon_gateway.test.benchmark.load_test

Or from pytest:

    pytest edon_gateway/test/benchmark/test_benchmark_suite.py::test_load_latency_p99 -s
"""

from __future__ import annotations

import statistics
import threading
import time
from dataclasses import dataclass
from typing import List

from .adapters.edon import EDONAdapter
from .cases import ALL_CASES
from .protocol import GovernanceInput


@dataclass
class LoadResult:
    total_requests: int
    concurrency: int
    duration_sec: float
    throughput_rps: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    latency_p999_ms: float
    error_count: int

    def summary(self) -> str:
        return (
            f"Load test: {self.total_requests} req @ {self.concurrency} concurrency "
            f"in {self.duration_sec:.1f}s\n"
            f"  Throughput : {self.throughput_rps:.1f} req/s\n"
            f"  Latency p50: {self.latency_p50_ms:.1f}ms\n"
            f"  Latency p95: {self.latency_p95_ms:.1f}ms\n"
            f"  Latency p99: {self.latency_p99_ms:.1f}ms\n"
            f"  Latency p999:{self.latency_p999_ms:.1f}ms\n"
            f"  Errors     : {self.error_count}"
        )


def _percentile(data: List[float], p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    idx = (p / 100) * (len(s) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def run_load_test(
    concurrency: int = 10,
    requests_per_worker: int = 20,
) -> LoadResult:
    """Run governance evaluation under concurrent load.

    Each worker thread cycles through ALL_CASES repeatedly.
    """
    inputs = [c.input for c in ALL_CASES]
    latencies: List[float] = []
    errors: List[int] = [0]
    lock = threading.Lock()

    def worker():
        adapter = EDONAdapter()
        for i in range(requests_per_worker):
            inp = inputs[i % len(inputs)]
            try:
                t0 = time.perf_counter()
                adapter.evaluate(inp)
                elapsed = (time.perf_counter() - t0) * 1000
                with lock:
                    latencies.append(elapsed)
            except Exception:
                with lock:
                    errors[0] += 1

    threads = [threading.Thread(target=worker) for _ in range(concurrency)]
    t_start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    duration = time.perf_counter() - t_start

    total = concurrency * requests_per_worker
    return LoadResult(
        total_requests=total,
        concurrency=concurrency,
        duration_sec=duration,
        throughput_rps=total / duration if duration else 0,
        latency_p50_ms=_percentile(latencies, 50),
        latency_p95_ms=_percentile(latencies, 95),
        latency_p99_ms=_percentile(latencies, 99),
        latency_p999_ms=_percentile(latencies, 99.9),
        error_count=errors[0],
    )


if __name__ == "__main__":
    print("Running load test (10 workers × 20 requests)...")
    result = run_load_test(concurrency=10, requests_per_worker=20)
    print(result.summary())
