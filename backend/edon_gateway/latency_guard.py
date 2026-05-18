"""Per-layer latency budgets for EDON's pre-governance pipeline.

Every enrichment layer that runs before the governor adds latency. At scale
this becomes p95 explosion. This module enforces hard budgets per layer with
graceful degradation: if a layer times out, it returns a conservative fallback
rather than failing the request.

Conservative = the safe assumption when we don't have data:
  - causal_risk:    CausalRisk with score=0.5 (unknown history, treat as suspicious)
  - fleet:          CampaignSignal with threat_level="watch" (can't verify, flag it)
  - coordination:   CoordinationRisk with composite_score=0.3 (possible multi-agent)
  - trust:          TrustScore with combined=0.3 (unknown agent, treat cautiously)

SLA enforcement:
  Each layer tracks a rolling window of actual p50/p95/p99 latencies.
  When p95 > budget * _SLA_WARN_FACTOR (1.5×), a warning fires.
  When p95 > budget * _SLA_BREACH_FACTOR (2.0×), an alert fires.
  Stats exposed via sla_stats() → /v1/internal/latency-sla.

The budgets here are defaults. Override via env vars:
  EDON_BUDGET_CAUSAL_MS, EDON_BUDGET_FLEET_MS, EDON_BUDGET_COORD_MS,
  EDON_BUDGET_TRUST_MS, EDON_BUDGET_ENTROPY_MS, EDON_BUDGET_EXPLOIT_MS
"""
from __future__ import annotations

import collections
import concurrent.futures
import os
import threading
import time
from typing import Callable, Optional, TypeVar

from .logging_config import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

# Default layer budgets (milliseconds)
_BUDGETS: dict[str, int] = {
    "causal":       int(os.getenv("EDON_BUDGET_CAUSAL_MS",   "80")),
    "fleet":        int(os.getenv("EDON_BUDGET_FLEET_MS",    "40")),
    "coordination": int(os.getenv("EDON_BUDGET_COORD_MS",    "60")),
    "trust":        int(os.getenv("EDON_BUDGET_TRUST_MS",    "100")),
    "entropy":      int(os.getenv("EDON_BUDGET_ENTROPY_MS",  "30")),
    "exploit":      int(os.getenv("EDON_BUDGET_EXPLOIT_MS",  "50")),
}

_SLA_WARN_FACTOR   = float(os.getenv("EDON_SLA_WARN_FACTOR",   "1.5"))  # p95 > budget*1.5 → warning
_SLA_BREACH_FACTOR = float(os.getenv("EDON_SLA_BREACH_FACTOR", "2.0"))  # p95 > budget*2.0 → alert
_SLA_WINDOW        = int(os.getenv("EDON_SLA_WINDOW", "500"))           # rolling sample count per layer
_SLA_MIN_SAMPLES   = int(os.getenv("EDON_SLA_MIN_SAMPLES", "20"))       # minimum before alerting

_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=int(os.getenv("EDON_GUARD_WORKERS", "8")),
    thread_name_prefix="latency_guard",
)

# Rolling latency samples and alert state per layer
_samples:      dict[str, collections.deque] = {}
_alert_state:  dict[str, str] = {}   # "ok" | "warn" | "breach"
_samples_lock  = threading.Lock()


def _get_deque(layer: str) -> collections.deque:
    with _samples_lock:
        if layer not in _samples:
            _samples[layer] = collections.deque(maxlen=_SLA_WINDOW)
        return _samples[layer]


def _record_sample(layer: str, elapsed_ms: int, timed_out: bool) -> None:
    """Record one latency sample and check SLA thresholds."""
    budget = _BUDGETS.get(layer, 100)
    # For timeouts, record the full budget as the sample value (worst case)
    value = budget if timed_out else elapsed_ms

    dq = _get_deque(layer)
    with _samples_lock:
        dq.append(value)
        n = len(dq)

    if n < _SLA_MIN_SAMPLES:
        return

    samples_snapshot = list(dq)
    p95 = _percentile(samples_snapshot, 95)
    warn_threshold   = budget * _SLA_WARN_FACTOR
    breach_threshold = budget * _SLA_BREACH_FACTOR

    prev_state = _alert_state.get(layer, "ok")

    if p95 > breach_threshold:
        new_state = "breach"
        if prev_state != "breach":
            logger.error(
                "[latency_guard] SLA BREACH layer=%s p95=%dms budget=%dms (%.1fx) "
                "samples=%d — governance quality degraded",
                layer, p95, budget, p95 / budget, n,
            )
    elif p95 > warn_threshold:
        new_state = "warn"
        if prev_state not in ("warn", "breach"):
            logger.warning(
                "[latency_guard] SLA WARNING layer=%s p95=%dms budget=%dms (%.1fx) samples=%d",
                layer, p95, budget, p95 / budget, n,
            )
    else:
        new_state = "ok"
        if prev_state in ("warn", "breach"):
            logger.info("[latency_guard] SLA RECOVERED layer=%s p95=%dms", layer, p95)

    _alert_state[layer] = new_state


def _percentile(data: list[int], pct: int) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * pct / 100
    lo, hi = int(k), min(int(k) + 1, len(sorted_data) - 1)
    return sorted_data[lo] + (sorted_data[hi] - sorted_data[lo]) * (k - lo)


def run_with_budget(
    layer: str,
    fn: Callable[[], T],
    fallback: T,
    budget_ms: Optional[int] = None,
) -> tuple[T, bool]:
    """Run fn() within the layer's latency budget.

    Returns (result, timed_out).
    If fn raises OR exceeds budget_ms, returns (fallback, True).
    Always records a latency sample for SLA tracking.
    """
    budget = budget_ms if budget_ms is not None else _BUDGETS.get(layer, 100)
    timeout_sec = budget / 1000.0
    start = time.monotonic()
    future = _executor.submit(fn)
    try:
        result = future.result(timeout=timeout_sec)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        _record_sample(layer, elapsed_ms, timed_out=False)
        return result, False
    except concurrent.futures.TimeoutError:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.warning(
            "[latency_guard] TIMEOUT layer=%s elapsed=%dms budget=%dms — conservative fallback",
            layer, elapsed_ms, budget,
        )
        future.cancel()
        _record_sample(layer, elapsed_ms, timed_out=True)
        return fallback, True
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.warning(
            "[latency_guard] ERROR layer=%s elapsed=%dms err=%s — conservative fallback",
            layer, elapsed_ms, exc,
        )
        _record_sample(layer, elapsed_ms, timed_out=False)
        return fallback, True


def get_budget(layer: str) -> int:
    return _BUDGETS.get(layer, 100)


def budget_summary() -> dict[str, int]:
    return dict(_BUDGETS)


def sla_stats() -> dict:
    """Return p50/p95/p99 latency stats and SLA status for every layer."""
    result = {}
    for layer, budget in _BUDGETS.items():
        dq = _get_deque(layer)
        with _samples_lock:
            data = list(dq)
        n = len(data)
        if n == 0:
            result[layer] = {"budget_ms": budget, "samples": 0, "status": "no_data"}
            continue
        p50 = _percentile(data, 50)
        p95 = _percentile(data, 95)
        p99 = _percentile(data, 99)
        timeouts = sum(1 for v in data if v >= budget)
        result[layer] = {
            "budget_ms":     budget,
            "samples":       n,
            "p50_ms":        round(p50, 1),
            "p95_ms":        round(p95, 1),
            "p99_ms":        round(p99, 1),
            "timeout_count": timeouts,
            "timeout_rate":  round(timeouts / n, 4),
            "p95_vs_budget": round(p95 / budget, 2),
            "status":        _alert_state.get(layer, "ok"),
        }
    return result
