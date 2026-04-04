"""Rate limiting, TTL caching, and observability for the AI advisory layer.

Prevents runaway Claude API costs by:
  - Caching responses for identical (action_type, risk_level) tuples
  - Enforcing per-tenant RPM limits
  - Structured error logging with Prometheus-compatible counters

All functions are fail-open: errors never propagate to the governance pipeline.
"""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable, Optional, TypeVar

try:
    from cachetools import TTLCache
    _CACHETOOLS = True
except ImportError:
    _CACHETOOLS = False

logger = logging.getLogger(__name__)

# ── Configuration (env-overridable) ──────────────────────────────────────────

_CACHE_TTL = int(os.getenv("EDON_ADVISORY_CACHE_TTL_SECONDS", "300"))
_CACHE_MAX = int(os.getenv("EDON_ADVISORY_CACHE_MAX_SIZE", "1000"))
_RATE_LIMIT_RPM = int(os.getenv("EDON_ADVISORY_RATE_LIMIT_RPM", "60"))

# ── Metrics counters (lightweight, no Prometheus dep required) ────────────────

@dataclass
class _AdvisoryMetrics:
    calls_total: dict = field(default_factory=lambda: defaultdict(int))
    latency_sum_ms: dict = field(default_factory=lambda: defaultdict(float))
    latency_count: dict = field(default_factory=lambda: defaultdict(int))

    def record(self, function: str, status: str, latency_ms: float = 0.0) -> None:
        key = (function, status)
        self.calls_total[key] += 1
        if latency_ms:
            self.latency_sum_ms[function] += latency_ms
            self.latency_count[function] += 1

    def snapshot(self) -> dict:
        """Return a JSON-serialisable metrics snapshot."""
        result: dict = {"calls": {}, "avg_latency_ms": {}}
        for (fn, status), count in self.calls_total.items():
            result["calls"].setdefault(fn, {})[status] = count
        for fn, total in self.latency_sum_ms.items():
            count = self.latency_count.get(fn, 1)
            result["avg_latency_ms"][fn] = round(total / count, 1)
        return result


_metrics = _AdvisoryMetrics()
_metrics_lock = Lock()


def get_advisory_metrics() -> dict:
    """Return current advisory metrics snapshot (thread-safe)."""
    with _metrics_lock:
        return _metrics.snapshot()


# ── TTL Cache ─────────────────────────────────────────────────────────────────

if _CACHETOOLS:
    _cache: TTLCache = TTLCache(maxsize=_CACHE_MAX, ttl=_CACHE_TTL)
else:
    # Fallback: simple dict (no TTL eviction, bounded by insertion order)
    _cache: dict = {}  # type: ignore[no-redef]

_cache_lock = Lock()


def _cache_key(function: str, action_type: str, risk_level: str, agent_id: str = "") -> str:
    """Stable cache key. Intentionally coarse — maximise hit rate."""
    return f"{function}:{action_type}:{risk_level}"


def cache_get(function: str, action_type: str, risk_level: str) -> Optional[Any]:
    with _cache_lock:
        key = _cache_key(function, action_type, risk_level)
        return _cache.get(key)


def cache_set(function: str, action_type: str, risk_level: str, value: Any) -> None:
    with _cache_lock:
        key = _cache_key(function, action_type, risk_level)
        try:
            _cache[key] = value
        except ValueError:
            pass  # TTLCache full (shouldn't happen with maxsize set)


# ── Per-tenant rate limiter (sliding 60-second window) ───────────────────────

_rate_windows: dict = defaultdict(list)  # tenant_id → [timestamp_float, ...]
_rate_lock = Lock()


def check_rate_limit(tenant_id: str) -> bool:
    """Return True if tenant is within the advisory RPM limit, False if exceeded."""
    now = time.monotonic()
    cutoff = now - 60.0
    with _rate_lock:
        window = _rate_windows[tenant_id]
        # Evict old timestamps
        _rate_windows[tenant_id] = [t for t in window if t > cutoff]
        if len(_rate_windows[tenant_id]) >= _RATE_LIMIT_RPM:
            return False
        _rate_windows[tenant_id].append(now)
        return True


# ── Decorator / wrapper ────────────────────────────────────────────────────────

T = TypeVar("T")


def advisory_call(
    function_name: str,
    action_type: str,
    risk_level: str,
    tenant_id: str,
    fn: Callable[[], T],
    *,
    cacheable: bool = True,
) -> Optional[T]:
    """Wrap an advisory Claude call with cache, rate limit, and observability.

    Args:
        function_name: Human-readable name for metrics (e.g. "risk_classifier")
        action_type:   Governance action type (e.g. "email.send")
        risk_level:    Estimated risk level string
        tenant_id:     Customer/tenant ID for per-tenant rate limiting
        fn:            Zero-arg callable that makes the actual Claude API call
        cacheable:     Whether to use the TTL cache for this call type

    Returns:
        The advisory result, or None on cache miss + rate limit + any error.
    """
    t0 = time.monotonic()

    # 1. Cache hit
    if cacheable:
        cached = cache_get(function_name, action_type, risk_level)
        if cached is not None:
            with _metrics_lock:
                _metrics.record(function_name, "cache_hit")
            logger.debug("Advisory cache hit: fn=%s action=%s", function_name, action_type)
            return cached

    # 2. Rate limit check
    if not check_rate_limit(tenant_id):
        with _metrics_lock:
            _metrics.record(function_name, "rate_limited")
        logger.warning(
            "Advisory rate limit exceeded: tenant=%s fn=%s (limit=%d rpm)",
            tenant_id, function_name, _RATE_LIMIT_RPM,
        )
        return None

    # 3. Execute the advisory call
    try:
        result = fn()
        latency_ms = (time.monotonic() - t0) * 1000
        status = "success" if result is not None else "empty"
        with _metrics_lock:
            _metrics.record(function_name, status, latency_ms)
        if result is not None and cacheable:
            cache_set(function_name, action_type, risk_level, result)
        return result

    except Exception as exc:
        latency_ms = (time.monotonic() - t0) * 1000
        with _metrics_lock:
            _metrics.record(function_name, "error", latency_ms)
        logger.error(
            "Advisory call error: fn=%s action=%s tenant=%s latency_ms=%.1f error=%r",
            function_name, action_type, tenant_id, latency_ms, str(exc),
        )
        return None
