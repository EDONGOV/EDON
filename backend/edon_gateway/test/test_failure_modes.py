"""Failure-mode tests: DB down, Claude API down, policy engine crash.

Verifies that EDON degrades gracefully rather than returning 500s or
silently allowing dangerous actions when internal components fail.
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from starlette.testclient import TestClient


# ── Shared fixture ────────────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("EDON_ENV", "development")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("EDON_AUTH_ENABLED", "false")
    monkeypatch.setenv("EDON_CREDENTIALS_STRICT", "false")
    monkeypatch.setenv("EDON_STRICT_FAIL_CLOSED", "false")
    monkeypatch.setenv("EDON_AI_ENABLED", "false")
    monkeypatch.setenv("EDON_DB_ENCRYPTION_KEY", Fernet.generate_key().decode())

    import edon_gateway.config as cfg
    monkeypatch.setattr(cfg.config, "_AUTH_ENABLED", False)
    monkeypatch.setattr(cfg.config, "_ENVIRONMENT", "development")
    monkeypatch.setattr(cfg.config, "_CREDENTIALS_STRICT", False)

    from edon_gateway.main import app
    with TestClient(app) as c:
        yield c


def _action(action_type="email.send", payload=None):
    from datetime import datetime, UTC
    return {
        "agent_id": "failure-test-agent",
        "action_type": action_type,
        "action_payload": payload or {"to": "user@example.com"},
        "timestamp": datetime.now(UTC).isoformat(),
        "context": {},
    }


# ── 1. AI advisory layer: fail-open when API key absent ──────────────────────

def test_ai_advisory_fail_open_no_api_key(monkeypatch):
    """Advisory layer returns None (not an exception) when ANTHROPIC_API_KEY is unset."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("EDON_AI_ENABLED", "true")

    from edon_gateway.ai.client import call_advisory, is_ai_available

    assert is_ai_available() is False
    result = call_advisory("You are a risk scorer.", "action_type=email.send risk=low")
    assert result is None, "call_advisory must return None when API key is absent, not raise"


def test_ai_advisory_fail_open_on_api_exception(monkeypatch):
    """Advisory layer returns None when the Anthropic API raises any exception."""
    monkeypatch.setenv("EDON_AI_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-key-for-test")

    import edon_gateway.ai.client as ai_mod

    class _BrokenClient:
        class messages:
            @staticmethod
            def stream(*_args, **_kwargs):
                raise ConnectionError("Simulated API outage")

    monkeypatch.setattr(ai_mod, "_get_client", lambda: _BrokenClient())

    result = ai_mod.call_advisory("system", "user message")
    assert result is None, "call_advisory must return None on API exception, not raise"


# ── 2. Governance continues when AI advisory layer is broken ─────────────────

def test_governance_unaffected_when_advisory_returns_none(client, monkeypatch):
    """Governance pipeline still returns a valid verdict when all advisory calls return None."""
    monkeypatch.setenv("EDON_AI_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")

    import edon_gateway.ai.client as ai_mod
    monkeypatch.setattr(ai_mod, "_call_advisory_direct", lambda *_, **__: None)

    r = client.post("/v1/action", json=_action())
    assert r.status_code == 200, f"Governance crashed when advisory returned None: {r.text}"
    assert r.json().get("verdict") or r.json().get("decision"), \
        "Response missing verdict/decision field"


# ── 3. Audit write failure does not crash the governance response ─────────────

def test_governance_continues_when_audit_write_fails(client, monkeypatch):
    """A failure in save_audit_event must not cause a 500 — governance is fire-and-forget on audit."""
    import edon_gateway.persistence.database as db_mod

    def _exploding_save(*_a, **_kw):
        raise RuntimeError("Simulated DB write failure")

    monkeypatch.setattr(db_mod.Database, "save_audit_event", _exploding_save)

    r = client.post("/v1/action", json=_action())
    assert r.status_code != 500, \
        f"Governance returned 500 when audit write failed — DB write must not block response"
    assert r.status_code in (200, 503), f"Unexpected status: {r.status_code} {r.text[:200]}"


# ── 4. Policy engine exception → fail-safe, never 500 ───────────────────────

def test_policy_engine_crash_returns_failsafe_not_500(client, monkeypatch):
    """If the policy engine raises an unhandled exception, the response must be a structured
    BLOCK (fail-closed) or 503 — never an unhandled 500 with a traceback."""
    monkeypatch.setenv("EDON_POLICY_FAIL_SAFE", "block")

    import edon_gateway.policy.engine as engine_mod

    def _exploding_evaluate(*_a, **_kw):
        raise RuntimeError("Simulated policy engine crash")

    monkeypatch.setattr(engine_mod.PolicyEngine, "evaluate", _exploding_evaluate)

    r = client.post("/v1/action", json=_action("database.delete", {"table": "users"}))
    assert r.status_code != 500, \
        f"Policy engine crash leaked as 500 — must be caught and fail-safe applied"

    if r.status_code == 200:
        verdict = (r.json().get("verdict") or r.json().get("decision") or "").upper()
        assert verdict != "ALLOW", \
            f"Policy engine crash should not silently ALLOW — got: {verdict}"


# ── 5. DB read failure returns clean error, not traceback ────────────────────

def test_audit_query_db_failure_returns_clean_error(client, monkeypatch):
    """GET /audit/query returns a structured error (not a raw traceback) when the DB is unavailable."""
    import edon_gateway.persistence.database as db_mod

    def _exploding_query(*_a, **_kw):
        raise RuntimeError("Simulated DB read failure")

    monkeypatch.setattr(db_mod.Database, "query_audit_events", _exploding_query)

    r = client.get("/audit/query", params={"limit": 10},
                   headers={"X-Tenant-ID": "test-tenant"})

    assert r.status_code != 500 or "traceback" not in r.text.lower(), \
        "DB read failure leaked raw traceback — must return structured error"

    body = r.text.lower()
    assert "runtimeerror" not in body, \
        f"Raw exception class leaked in response: {r.text[:200]}"


# ── 6. Hard-blocked actions remain blocked even under full layer timeout ──────

def test_hard_blocked_action_stays_blocked_under_timeout(client, monkeypatch):
    """credential.read must remain BLOCK even when all latency-guard layers time out.
    This is the core governance-fails-closed guarantee."""
    import edon_gateway.latency_guard as lg

    def _always_timeout(layer, fn, fallback, budget_ms=None):
        budget = budget_ms if budget_ms is not None else lg._BUDGETS.get(layer, 100)
        lg._record_sample(layer, budget, timed_out=True)
        return fallback, True

    monkeypatch.setattr(lg, "run_with_budget", _always_timeout)

    r = client.post("/v1/action", json=_action(
        "credential.read", {"vault": "production-secrets", "key": "db_password"}
    ))
    assert r.status_code == 200, f"Hard-blocked action crashed under timeout: {r.text}"

    verdict = (r.json().get("verdict") or r.json().get("decision") or "").upper()
    assert verdict in ("BLOCK", "ESCALATE", "HUMAN_REQUIRED"), \
        f"credential.read allowed through under full timeout saturation: verdict={verdict}"
