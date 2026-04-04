"""Smoke test — 5 users, 30 seconds. Verifies basic connectivity."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from locust import events
from locustfile import EdonGatewayUser  # noqa: F401 — re-export for locust discovery

# Smoke test: minimal load to verify the stack is up
# locust -f load_tests/scenarios/smoke.py --headless --host http://localhost:8000
#         --users 5 --spawn-rate 5 --run-time 30s
