"""Prometheus metric objects for the EDON Gateway.

Defined here so main.py can re-export them (for backward-compat with
governor.py and route files that do `from .main import prometheus_*`)
while keeping main.py free of metric definitions.
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, REGISTRY

from ..config import config

if config.METRICS_ENABLED:
    def _metric(name: str, factory, *args, **kwargs):
        existing = getattr(REGISTRY, "_names_to_collectors", {}).get(name)
        if existing is not None:
            return existing
        return factory(name, *args, **kwargs)

    prometheus_decisions_total = _metric(
        "edon_decisions_total",
        Counter,
        "Total number of governance decisions",
        ["verdict", "reason_code"],
    )
    prometheus_decision_latency_ms = _metric(
        "edon_decision_latency_ms",
        Histogram,
        "Decision evaluation latency in milliseconds",
        ["endpoint"],
        buckets=[10, 50, 100, 200, 500, 1000, 2000, 5000],
    )
    prometheus_rate_limit_hits_total = _metric(
        "edon_rate_limit_hits_total",
        Counter,
        "Total number of rate limit hits",
    )
    prometheus_active_intents = _metric(
        "edon_active_intents",
        Gauge,
        "Number of active intent contracts currently registered",
    )
    prometheus_uptime_seconds = _metric(
        "edon_uptime_seconds",
        Gauge,
        "Gateway uptime in seconds",
    )
    prometheus_policy_eval_time_ms = _metric(
        "edon_policy_eval_time_ms",
        Histogram,
        "Policy evaluation latency in milliseconds",
        ["verdict"],
        buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000],
    )
    prometheus_anomalies_detected_total = _metric(
        "edon_anomalies_detected_total",
        Counter,
        "Total number of anomalous actions detected and escalated",
        ["severity"],
    )
else:
    prometheus_decisions_total = None
    prometheus_decision_latency_ms = None
    prometheus_rate_limit_hits_total = None
    prometheus_active_intents = None
    prometheus_uptime_seconds = None
    prometheus_policy_eval_time_ms = None
    prometheus_anomalies_detected_total = None
