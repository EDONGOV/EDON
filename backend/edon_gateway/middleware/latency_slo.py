"""Latency SLO tracking middleware.

Tracks p50/p95/p99 request latency in a sliding window and:
- Adds X-Response-Time-Ms header to every response
- Logs SLO warnings when p99 > EDON_SLO_P99_MS (default 100 ms)
- Exposes current stats via module-level get_slo_stats() for /health endpoint
"""

import logging
import os
import time
from collections import deque
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

logger = logging.getLogger(__name__)

# SLO thresholds (configurable via env)
SLO_P99_MS = float(os.getenv("EDON_SLO_P99_MS", "100"))
SLO_P95_MS = float(os.getenv("EDON_SLO_P95_MS", "75"))

# Sliding window size (last N completed requests)
_WINDOW_SIZE = int(os.getenv("EDON_SLO_WINDOW", "1000"))

# Paths excluded from SLO tracking (health probes, metrics scrapes)
_EXCLUDED_PATHS = {"/health", "/healthz", "/metrics", "/docs", "/openapi.json", "/redoc"}

# ---------------------------------------------------------------------------
# Module-level tracker – shared across requests (thread-safe via GIL for deque)
# ---------------------------------------------------------------------------

_latency_window: deque = deque(maxlen=_WINDOW_SIZE)  # latencies in ms (float)
_slo_breach_count: int = 0  # cumulative p99 SLO breaches


def _percentile(sorted_samples: list, pct: float) -> Optional[float]:
    """Return the pct-th percentile from a sorted list, or None if empty."""
    if not sorted_samples:
        return None
    idx = int(len(sorted_samples) * pct / 100)
    idx = min(idx, len(sorted_samples) - 1)
    return round(sorted_samples[idx], 2)


def get_slo_stats() -> dict:
    """Return current SLO statistics for health/metrics endpoints."""
    samples = sorted(_latency_window)
    return {
        "window_size": len(samples),
        "p50_ms": _percentile(samples, 50),
        "p95_ms": _percentile(samples, 95),
        "p99_ms": _percentile(samples, 99),
        "slo_p99_target_ms": SLO_P99_MS,
        "slo_p95_target_ms": SLO_P95_MS,
        "cumulative_slo_breaches": _slo_breach_count,
    }


class LatencySLOMiddleware(BaseHTTPMiddleware):
    """Measures end-to-end request latency, enforces SLO alerting, adds timing header."""

    async def dispatch(self, request: Request, call_next):
        global _slo_breach_count

        t_start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - t_start) * 1000.0

        # Add timing header (always)
        response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.1f}"

        # Skip SLO accounting for excluded paths
        if request.url.path in _EXCLUDED_PATHS:
            return response

        # Record in sliding window
        _latency_window.append(elapsed_ms)

        # Check p99 SLO with at least 10 samples
        if len(_latency_window) >= 10:
            samples = sorted(_latency_window)
            p99 = _percentile(samples, 99)
            if p99 is not None and p99 > SLO_P99_MS:
                _slo_breach_count += 1
                logger.warning(
                    "SLO BREACH: p99 latency %.1f ms exceeds target %.1f ms "
                    "(window=%d, this_request=%.1f ms, path=%s)",
                    p99,
                    SLO_P99_MS,
                    len(samples),
                    elapsed_ms,
                    request.url.path,
                )

        return response
