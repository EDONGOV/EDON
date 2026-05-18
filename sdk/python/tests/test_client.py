"""Unit tests for EdonClient and AsyncEdonClient.

Uses respx to mock httpx calls — no real network traffic.
Run with: pytest tests/test_client.py -v
"""
from __future__ import annotations

import os
import sys

import httpx
import pytest
import respx

# Allow importing edon_sdk from the local tree without installing it.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from edon_sdk import AsyncEdonClient, EdonClient  # noqa: E402
from edon_sdk.exceptions import AuthenticationError, RateLimitError  # noqa: E402

_BASE = "https://edon-gateway-prod.fly.dev"


# ── Test 1: ValueError on empty token ────────────────────────────────────────

def test_empty_token_raises_value_error():
    """EdonClient must refuse to construct without a token."""
    with pytest.raises(ValueError, match="EDON API key is required"):
        EdonClient(token="")


# ── Test 2: reads EDON_API_KEY from environment ───────────────────────────────

def test_reads_token_from_environment(monkeypatch):
    """EdonClient falls back to EDON_API_KEY env var when no token is passed."""
    monkeypatch.setenv("EDON_API_KEY", "edon-from-env")
    client = EdonClient()
    assert client.token == "edon-from-env"
    client.close()


# ── Test 3: evaluate() returns correct verdict dict on 200 ────────────────────

@respx.mock
def test_evaluate_returns_verdict_on_200():
    """evaluate() correctly unpacks a 200 gateway response."""
    gateway_resp = {
        "decision": "ALLOW",
        "reason_code": "POLICY_PASS",
        "explanation": "Action is within policy",
        "action_id": "act_abc123",
        "safe_alternative": None,
        "escalation_question": None,
        "escalation_options": [],
    }
    respx.post(f"{_BASE}/v1/action").mock(
        return_value=httpx.Response(200, json=gateway_resp)
    )

    client = EdonClient(token="edon-test")
    result = client.evaluate("database.query", {"query": "SELECT 1"})
    client.close()

    assert result["verdict"] == "ALLOW"
    assert result["reason_code"] == "POLICY_PASS"
    assert result["action_id"] == "act_abc123"
    assert result["fallback"] is False


# ── Test 4: evaluate() returns fail-open dict on connection error ─────────────

@respx.mock
def test_evaluate_fail_open_on_connection_error():
    """evaluate() returns fail-open ALLOW when the gateway is unreachable."""
    respx.post(f"{_BASE}/v1/action").mock(side_effect=httpx.ConnectError("refused"))

    client = EdonClient(token="edon-test", max_retries=0)
    result = client.evaluate("database.query", {"query": "SELECT 1"})
    client.close()

    assert result["verdict"] == "ALLOW"
    assert result["fallback"] is True
    assert result["reason_code"] == "GATEWAY_UNREACHABLE"


# ── Test 5: evaluate() raises AuthenticationError on 401 ─────────────────────

@respx.mock
def test_evaluate_raises_authentication_error_on_401():
    """evaluate() propagates AuthenticationError on a 401 response."""
    respx.post(f"{_BASE}/v1/action").mock(
        return_value=httpx.Response(401, json={"detail": "Invalid API key"})
    )

    client = EdonClient(token="edon-bad-key", max_retries=0)
    with pytest.raises(AuthenticationError) as exc_info:
        client.evaluate("database.query", {"query": "SELECT 1"})
    client.close()

    assert exc_info.value.status_code == 401


# ── Test 6: evaluate() raises RateLimitError on 429 with retry_after ─────────

@respx.mock
def test_evaluate_raises_rate_limit_error_on_429():
    """evaluate() raises RateLimitError with retry_after populated on 429."""
    respx.post(f"{_BASE}/v1/action").mock(
        return_value=httpx.Response(
            429,
            json={"detail": "Too Many Requests", "retry_after": 30.0},
        )
    )

    client = EdonClient(token="edon-test", max_retries=0)
    with pytest.raises(RateLimitError) as exc_info:
        client.evaluate("database.query", {"query": "SELECT 1"})
    client.close()

    assert exc_info.value.status_code == 429
    assert exc_info.value.retry_after == 30.0


# ── Test 7: evaluate() retries on 500 and succeeds on second attempt ─────────

@respx.mock
def test_evaluate_retries_on_500_and_succeeds():
    """evaluate() retries a 500 response and returns the verdict on success."""
    success_resp = {
        "decision": "ALLOW",
        "reason_code": "POLICY_PASS",
        "explanation": "",
        "action_id": "act_retry",
        "safe_alternative": None,
        "escalation_question": None,
        "escalation_options": [],
    }
    route = respx.post(f"{_BASE}/v1/action")
    route.side_effect = [
        httpx.Response(500, json={"error": "internal error"}),
        httpx.Response(200, json=success_resp),
    ]

    # max_retries=1 means one retry after the first failure
    client = EdonClient(token="edon-test", max_retries=1)
    result = client.evaluate("database.query", {"query": "SELECT 1"})
    client.close()

    assert result["verdict"] == "ALLOW"
    assert result["action_id"] == "act_retry"
    assert route.call_count == 2


# ── Test 8: scan_output() returns PASS verdict on clean response ──────────────

@respx.mock
def test_scan_output_returns_pass_on_clean_response():
    """scan_output() returns the gateway PASS verdict and passes payload through."""
    gateway_resp = {
        "verdict": "PASS",
        "payload": {"data": "clean"},
        "findings": [],
        "redacted": False,
    }
    respx.post(f"{_BASE}/v1/output").mock(
        return_value=httpx.Response(200, json=gateway_resp)
    )

    client = EdonClient(token="edon-test")
    result = client.scan_output({"data": "clean"}, action_type="database.query")
    client.close()

    assert result["verdict"] == "PASS"
    assert result["findings"] == []
    assert result["fallback"] is False


# ── Test 9: scan_output() returns fail-open on connection error ───────────────

@respx.mock
def test_scan_output_fail_open_on_connection_error():
    """scan_output() returns a fail-open PASS and the original payload on error."""
    original = {"data": "original"}
    respx.post(f"{_BASE}/v1/output").mock(side_effect=httpx.ConnectError("refused"))

    client = EdonClient(token="edon-test", max_retries=0)
    result = client.scan_output(original, action_type="database.query")
    client.close()

    assert result["verdict"] == "PASS"
    assert result["payload"] == original
    assert result["fallback"] is True


# ── Test 10: begin_intent() returns an intent_id string ──────────────────────

@respx.mock
def test_begin_intent_returns_intent_id_string():
    """begin_intent() returns an intent_id string and stores it on the client."""
    respx.post(f"{_BASE}/intent/set").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    client = EdonClient(token="edon-test")
    intent_id = client.begin_intent(
        objective="Summarise patient records",
        allowed_tools=["database.query"],
    )
    client.close()

    assert isinstance(intent_id, str)
    assert intent_id.startswith("intent_")
    assert client._active_intent_id == intent_id


# ── Test 11: AsyncEdonClient raises ValueError on empty token ─────────────────

def test_async_client_empty_token_raises_value_error():
    """AsyncEdonClient must refuse to construct without a token."""
    with pytest.raises(ValueError, match="EDON API key is required"):
        AsyncEdonClient(token="")
