"""SLO validation — 50 users, 2 minutes. Validates p95 < 200ms for /v1/action.

Usage:
    locust -f load_tests/scenarios/slo_validation.py \
        --headless --host http://localhost:8000 \
        --users 50 --spawn-rate 10 --run-time 2m \
        --csv load_tests/results/slo_$(date +%Y%m%d_%H%M%S)

Pass/fail:
    - p95 response time for /v1/action must be < 200ms
    - Failure rate must be < 1%
    - Check the CSV output or Locust HTML report for details
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from locust import events
from locustfile import EdonGatewayUser  # noqa: F401

SLO_P95_MS = 200   # milliseconds
SLO_FAILURE_RATE_PCT = 1.0  # percent


@events.quitting.add_listener
def assert_slo(environment, **kwargs):
    """Fail the test run if SLO targets are not met."""
    stats = environment.runner.stats
    total = stats.total

    # Check failure rate
    failure_rate = (total.num_failures / max(total.num_requests, 1)) * 100
    if failure_rate > SLO_FAILURE_RATE_PCT:
        print(f"SLO BREACH: failure rate {failure_rate:.1f}% > {SLO_FAILURE_RATE_PCT}%")
        environment.process_exit_code = 1
        return

    # Check p95 for /v1/action
    action_stats = stats.get("/v1/action [low-risk]", "POST")
    if action_stats and action_stats.num_requests > 0:
        p95 = action_stats.get_response_time_percentile(0.95)
        if p95 > SLO_P95_MS:
            print(f"SLO BREACH: /v1/action p95={p95}ms > {SLO_P95_MS}ms target")
            environment.process_exit_code = 1
            return
        print(f"SLO PASS: /v1/action p95={p95}ms (target <{SLO_P95_MS}ms)")
    else:
        print("WARNING: No /v1/action requests recorded — check test configuration")
