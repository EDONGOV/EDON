"""Prometheus metric objects for the EDON Gateway.

Defined here so main.py can re-export them (for backward-compat with
governor.py and route files that do `from .main import prometheus_*`)
while keeping main.py free of metric definitions.
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

from ..config import config

if config.METRICS_ENABLED:
    prometheus_decisions_total = Counter(
        "edon_decisions_total",
        "Total number of governance decisions",
        ["verdict", "reason_code"],
    )
    prometheus_decision_latency_ms = Histogram(
        "edon_decision_latency_ms",
        "Decision evaluation latency in milliseconds",
        ["endpoint"],
        buckets=[10, 50, 100, 200, 500, 1000, 2000, 5000],
    )
    prometheus_rate_limit_hits_total = Counter(
        "edon_rate_limit_hits_total",
        "Total number of rate limit hits",
    )
    prometheus_active_intents = Gauge(
        "edon_active_intents",
        "Number of active intent contracts currently registered",
    )
    prometheus_uptime_seconds = Gauge(
        "edon_uptime_seconds",
        "Gateway uptime in seconds",
    )
    prometheus_policy_eval_time_ms = Histogram(
        "edon_policy_eval_time_ms",
        "Policy evaluation latency in milliseconds",
        ["verdict"],
        buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000],
    )
    prometheus_anomalies_detected_total = Counter(
        "edon_anomalies_detected_total",
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
