"""EDON Gateway load tests — main Locust file.

Usage:
    # With web UI:
    locust -f load_tests/locustfile.py --host http://localhost:8000

    # Headless smoke:
    locust -f load_tests/scenarios/smoke.py --headless --host http://localhost:8000

    # SLO validation (50 users, 2 min, p95 < 200ms):
    locust -f load_tests/scenarios/slo_validation.py --headless --host http://localhost:8000
"""
import os
import random
import uuid
from locust import HttpUser, task, between

# Auth token — use env var or a dev token
EDON_TOKEN = os.getenv("EDON_LOAD_TEST_TOKEN", "dev-load-test-token")
AGENT_IDS = [f"load-test-agent-{i}" for i in range(1, 6)]


class EdonGatewayUser(HttpUser):
    """Simulates a realistic mix of governance decision requests."""

    wait_time = between(0.1, 0.5)

    def on_start(self):
        self.agent_id = random.choice(AGENT_IDS)
        self.headers = {
            "X-EDON-TOKEN": EDON_TOKEN,
            "X-Agent-ID": self.agent_id,
            "Content-Type": "application/json",
        }

    @task(5)
    def test_simple_allow_action(self):
        """Most common path: low-risk action that gets ALLOW."""
        payload = {
            "action_type": "email.send",
            "action_payload": {
                "recipients": ["user@example.com"],
                "subject": "Weekly report",
                "body": "Here is your report.",
            },
            "agent_id": self.agent_id,
            "timestamp": _now_iso(),
            "context": {"session_id": f"sess-{uuid.uuid4().hex[:8]}"},
        }
        with self.client.post(
            "/execute",
            json=payload,
            headers=self.headers,
            catch_response=True,
            name="/execute [low-risk]",
        ) as resp:
            if resp.status_code not in (200, 201):
                resp.failure(f"HTTP {resp.status_code}")

    @task(3)
    def test_v1_action_allow(self):
        """Governance evaluation only via /v1/action (no execution)."""
        payload = {
            "agent_id": self.agent_id,
            "action_type": "http.request",
            "action_payload": {
                "url": "https://api.example.com/data",
                "method": "GET",
            },
            "timestamp": _now_iso(),
            "estimated_risk": "low",
            "context": {},
        }
        with self.client.post(
            "/v1/action",
            json=payload,
            headers=self.headers,
            catch_response=True,
            name="/v1/action [low-risk]",
        ) as resp:
            if resp.status_code not in (200, 201):
                resp.failure(f"HTTP {resp.status_code}")

    @task(2)
    def test_risky_action(self):
        """High-risk action — exercises risk scoring pipeline."""
        payload = {
            "agent_id": self.agent_id,
            "action_type": "filesystem.write",
            "action_payload": {
                "path": "/tmp/output.txt",
                "content": "Generated content",
            },
            "timestamp": _now_iso(),
            "estimated_risk": "high",
            "context": {"session_id": f"sess-{uuid.uuid4().hex[:8]}"},
        }
        with self.client.post(
            "/v1/action",
            json=payload,
            headers=self.headers,
            catch_response=True,
            name="/v1/action [high-risk]",
        ) as resp:
            if resp.status_code not in (200, 201):
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    def test_health_check(self):
        """Health endpoint — should always be fast."""
        with self.client.get(
            "/health",
            headers=self.headers,
            catch_response=True,
            name="/health",
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"Health check failed: HTTP {resp.status_code}")

    @task(1)
    def test_audit_query(self):
        """Audit query — exercises DB read path."""
        with self.client.get(
            f"/audit/query?agent_id={self.agent_id}&limit=10",
            headers=self.headers,
            catch_response=True,
            name="/audit/query",
        ) as resp:
            if resp.status_code not in (200, 404):
                resp.failure(f"HTTP {resp.status_code}")


def _now_iso() -> str:
    from datetime import datetime, UTC
    return datetime.now(UTC).isoformat()
