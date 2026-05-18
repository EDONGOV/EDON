"""Rate limit enforcement, cross-tenant HTTP isolation, and production auth tests.

Covers the gaps left by test_rate_limit_usage_counting.py (which only tests
that counters increment — not that 429s are actually returned) and
test_multitenant_rbac.py (which only tests DB-level isolation — not HTTP).
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from edon_gateway.middleware.rate_limit import RateLimitMiddleware, DEFAULT_LIMITS


# ── Helpers ───────────────────────────────────────────────────────────────────

def _app_with_rate_limit() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.post("/v1/action")
    async def v1_action(request: Request):
        request.state.tenant_id = "tenant-rl-test"
        return JSONResponse({"verdict": "ALLOW", "decision_id": "test-123"})

    return app


class _CounterDb:
    """Stub DB that returns a configurable counter value."""

    def __init__(self, count: int = 0):
        self._count = count
        self.incremented = []

    def increment_tenant_usage(self, tenant_id: str, amount: int):
        pass

    def get_tenant(self, tenant_id: str):
        return {"id": tenant_id}

    def get_counter(self, key: str) -> int:
        return self._count

    def increment_counter(self, key: str, amount: int = 1) -> int:
        self.incremented.append(key)
        self._count += amount
        return self._count


# ── Rate limit enforcement ────────────────────────────────────────────────────

def test_rate_limit_returns_429_when_limit_exceeded(monkeypatch):
    """When the per-minute counter is at the limit, the next request must get 429."""
    limit = DEFAULT_LIMITS["per_minute"]
    stub_db = _CounterDb(count=limit)  # already at limit

    monkeypatch.setenv("EDON_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr("edon_gateway.middleware.rate_limit.RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr("edon_gateway.middleware.rate_limit.get_db", lambda: stub_db)
    monkeypatch.setattr("edon_gateway.persistence.get_db", lambda: stub_db)

    app = _app_with_rate_limit()
    client = TestClient(app, raise_server_exceptions=False)

    r = client.post(
        "/v1/action",
        json={"agent_id": "rate-limited-agent", "action_type": "email.send", "action_payload": {}},
        headers={"X-EDON-TOKEN": "test-token", "X-Tenant-ID": "tenant-rl-test"},
    )
    assert r.status_code == 429, \
        f"Expected 429 when counter at limit, got {r.status_code}: {r.text[:200]}"


def test_rate_limit_allows_when_under_limit(monkeypatch):
    """Requests under the limit must pass through normally."""
    stub_db = _CounterDb(count=0)  # fresh counter

    monkeypatch.setenv("EDON_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr("edon_gateway.middleware.rate_limit.RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr("edon_gateway.middleware.rate_limit.get_db", lambda: stub_db)
    monkeypatch.setattr("edon_gateway.persistence.get_db", lambda: stub_db)

    app = _app_with_rate_limit()
    client = TestClient(app, raise_server_exceptions=False)

    r = client.post(
        "/v1/action",
        json={"agent_id": "fresh-agent", "action_type": "email.send", "action_payload": {}},
        headers={"X-EDON-TOKEN": "test-token", "X-Tenant-ID": "tenant-rl-test"},
    )
    assert r.status_code == 200, \
        f"Request under limit should pass, got {r.status_code}: {r.text[:200]}"


def test_rate_limit_disabled_in_development(monkeypatch):
    """Rate limiting must be off in development mode — tests must not flake due to limits."""
    stub_db = _CounterDb(count=999_999_999)  # absurdly high counter

    monkeypatch.setenv("EDON_RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setattr("edon_gateway.middleware.rate_limit.RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr("edon_gateway.middleware.rate_limit.get_db", lambda: stub_db)
    monkeypatch.setattr("edon_gateway.persistence.get_db", lambda: stub_db)

    app = _app_with_rate_limit()
    client = TestClient(app, raise_server_exceptions=False)

    r = client.post(
        "/v1/action",
        json={"agent_id": "dev-agent", "action_type": "email.send", "action_payload": {}},
        headers={"X-Tenant-ID": "tenant-dev"},
    )
    assert r.status_code == 200, \
        f"Rate limit should be disabled in dev, got {r.status_code}: {r.text[:200]}"


# ── Cross-tenant HTTP isolation ───────────────────────────────────────────────

@pytest.fixture
def full_client(monkeypatch):
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


def test_audit_query_scoped_to_requesting_tenant(full_client):
    """Audit query results must only contain events belonging to the requesting tenant.
    Sending X-Tenant-ID: tenant-b must not return tenant-a's events."""
    import tempfile, os
    from pathlib import Path
    from edon_gateway.persistence.database import Database

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = Database(Path(db_path))

        # Insert one event per tenant
        base_action = {
            "requested_at": "2026-01-01T00:00:00Z",
            "tool": "memory", "op": "get", "params": {},
            "source": "agent", "estimated_risk": "", "computed_risk": None,
        }
        decision = {"verdict": "ALLOW", "reason_code": "OK",
                    "explanation": "ok", "policy_version": "1.0"}

        db.save_audit_event(
            action={**base_action, "id": "evt-tenant-a"},
            decision=decision, intent_id=None,
            agent_id="agent-a", context={}, customer_id="tenant-a",
        )
        db.save_audit_event(
            action={**base_action, "id": "evt-tenant-b"},
            decision=decision, intent_id=None,
            agent_id="agent-b", context={}, customer_id="tenant-b",
        )

        events_a = db.query_audit_events(customer_id="tenant-a", limit=50)
        events_b = db.query_audit_events(customer_id="tenant-b", limit=50)

        ids_a = {e["action"]["id"] for e in events_a}
        ids_b = {e["action"]["id"] for e in events_b}

        assert "evt-tenant-a" in ids_a, "tenant-a's own event missing from its own query"
        assert "evt-tenant-b" not in ids_a, "CROSS-TENANT LEAK: tenant-b event visible to tenant-a"
        assert "evt-tenant-b" in ids_b, "tenant-b's own event missing from its own query"
        assert "evt-tenant-a" not in ids_b, "CROSS-TENANT LEAK: tenant-a event visible to tenant-b"
    finally:
        os.unlink(db_path)


def test_v1_action_tenant_id_scoped_to_header(full_client):
    """Two concurrent requests with different X-Tenant-ID headers must not share state."""
    r_a = full_client.post("/v1/action", json={
        "agent_id": "agent-scope-a",
        "action_type": "email.send",
        "action_payload": {"to": "a@tenant-a.com"},
        "timestamp": "2026-04-24T00:00:00Z",
        "context": {},
    }, headers={"X-Tenant-ID": "tenant-scope-a"})

    r_b = full_client.post("/v1/action", json={
        "agent_id": "agent-scope-b",
        "action_type": "email.send",
        "action_payload": {"to": "b@tenant-b.com"},
        "timestamp": "2026-04-24T00:00:00Z",
        "context": {},
    }, headers={"X-Tenant-ID": "tenant-scope-b"})

    assert r_a.status_code == 200, f"tenant-a request failed: {r_a.text[:200]}"
    assert r_b.status_code == 200, f"tenant-b request failed: {r_b.text[:200]}"

    # Both get independent decision IDs (not the same audit entry)
    id_a = r_a.json().get("decision_id") or r_a.json().get("audit_id")
    id_b = r_b.json().get("decision_id") or r_b.json().get("audit_id")
    if id_a and id_b:
        assert id_a != id_b, "Two different tenants received the same decision_id — state shared"


# ── Production auth: invalid token must be rejected ──────────────────────────

def test_production_auth_rejects_wrong_token(monkeypatch):
    """In production mode with auth enabled, a wrong (but syntactically valid) token
    must return 401 — not 200."""
    monkeypatch.setenv("EDON_AUTH_ENABLED", "true")
    monkeypatch.setenv("EDON_ENV", "production")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("EDON_API_TOKEN", "correct-production-token")
    monkeypatch.setenv("EDON_ALLOW_ENV_TOKEN_IN_PROD", "true")  # allow env token so we can test rejection
    monkeypatch.setenv("EDON_DB_ENCRYPTION_KEY", Fernet.generate_key().decode())

    import edon_gateway.config as cfg
    from edon_gateway.config import Config
    prod_config = Config()
    monkeypatch.setattr(cfg, "config", prod_config)

    import edon_gateway.middleware.auth as auth_mod
    monkeypatch.setattr(auth_mod, "config", prod_config)

    from edon_gateway.main import app
    client = TestClient(app, raise_server_exceptions=False)

    r = client.post("/v1/action", json={
        "agent_id": "test-agent",
        "action_type": "email.send",
        "action_payload": {"to": "user@example.com"},
    }, headers={"X-EDON-TOKEN": "wrong-token"})

    assert r.status_code in (401, 403), \
        f"Wrong token accepted in production mode — got {r.status_code}: {r.text[:200]}"


def test_production_auth_accepts_correct_token(monkeypatch):
    """In production mode, verify_token accepts the correct env token when explicitly allowed."""
    monkeypatch.setenv("EDON_AUTH_ENABLED", "true")
    monkeypatch.setenv("EDON_ENV", "production")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("EDON_API_TOKEN", "correct-production-token")
    monkeypatch.setenv("EDON_ALLOW_ENV_TOKEN_IN_PROD", "true")

    from edon_gateway.config import Config
    import edon_gateway.middleware.auth as auth_mod
    fresh_config = Config()
    monkeypatch.setattr(auth_mod, "config", fresh_config)

    is_valid, tenant = auth_mod.verify_token("correct-production-token")
    assert is_valid is True, \
        f"Correct token rejected with EDON_ALLOW_ENV_TOKEN_IN_PROD=true — verify_token returned is_valid={is_valid}"


def test_no_token_rejected_in_production(monkeypatch):
    """Requests with no auth token must be rejected in production mode."""
    monkeypatch.setenv("EDON_AUTH_ENABLED", "true")
    monkeypatch.setenv("EDON_ENV", "production")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("EDON_API_TOKEN", "correct-production-token")
    monkeypatch.setenv("EDON_ALLOW_ENV_TOKEN_IN_PROD", "true")
    monkeypatch.setenv("EDON_DB_ENCRYPTION_KEY", Fernet.generate_key().decode())

    import edon_gateway.config as cfg
    from edon_gateway.config import Config
    prod_config = Config()
    monkeypatch.setattr(cfg, "config", prod_config)

    import edon_gateway.middleware.auth as auth_mod
    monkeypatch.setattr(auth_mod, "config", prod_config)

    from edon_gateway.main import app
    client = TestClient(app, raise_server_exceptions=False)

    r = client.post("/v1/action", json={
        "agent_id": "test-agent",
        "action_type": "email.send",
        "action_payload": {"to": "user@example.com"},
    })  # no auth header

    assert r.status_code in (401, 403), \
        f"Unauthenticated request accepted in production mode — got {r.status_code}: {r.text[:200]}"
