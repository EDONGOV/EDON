"""Stress test — ramp to 200 users over 60s. Find the breaking point.

Usage:
    locust -f load_tests/scenarios/stress.py \
        --headless --host http://localhost:8000 \
        --users 200 --spawn-rate 3 --run-time 5m \
        --csv load_tests/results/stress_$(date +%Y%m%d_%H%M%S)

Monitor: watch for error rate climbing above 5% or p95 > 500ms.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from locustfile import EdonGatewayUser  # noqa: F401
