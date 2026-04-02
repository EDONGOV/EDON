import os
import pytest
from fastapi.testclient import TestClient

from edon_gateway.main import app

@pytest.mark.parametrize("endpoint", ["/clawdbot/invoke", "/edon/invoke"])
def test_clawdbot_proxy_never_throws_request_nameerror(monkeypatch, endpoint):
    # Force a known intent path to avoid "No intent configured" errors.
    # We don't need a real DB/intent for this test; we only want to ensure the proxy path
    # never references an undefined "request" variable.
    client = TestClient(app)

    # Minimal payload that hits the handler logic
    headers = {
        "X-EDON-TOKEN": "dev_token_ok",     # your AuthMiddleware may accept dev fallback depending on config
        "X-Intent-ID": "intent_test",
        "X-Agent-ID": "agent_demo_001",
    }

    r = client.post(endpoint, json={"tool": "sessions_list", "action": "json", "args": {}}, headers=headers)

    # If the old bug exists, you'd see "name 'request' is not defined" in error string.
    assert "name 'request' is not defined" not in (r.text or "")
