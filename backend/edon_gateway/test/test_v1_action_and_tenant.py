"""
Tier 1 integration tests: POST /v1/action (1.1, 1.5) and cross-tenant isolation (16.2, 16.5).

- /v1/action: happy path, validation (reject unknown fields, missing required, invalid payload).
- Cross-tenant: audit query with customer_id returns only that tenant's rows (DB-level).
"""

import os
import tempfile
import pytest

import requests

# Optional: load env for gateway URL/token when running against live gateway
try:
    from pathlib import Path
    _script_dir = Path(__file__).resolve().parent
    for _env in (_script_dir.parent.parent.parent / ".env", _script_dir.parent.parent.parent.parent / "edon_gateway" / ".env"):
        if _env.exists():
            from dotenv import load_dotenv
            load_dotenv(_env, override=True)
            break
except Exception:
    pass

BASE_URL = os.getenv("EDON_GATEWAY_URL", "http://localhost:8000").rstrip("/")
AUTH_TOKEN = os.getenv("EDON_API_TOKEN", "test-token")
AUTH_ENABLED = os.getenv("EDON_AUTH_ENABLED", "").strip().lower() == "true"


def _headers():
    h = {"Content-Type": "application/json"}
    if AUTH_ENABLED and AUTH_TOKEN:
        h["X-EDON-TOKEN"] = AUTH_TOKEN
        h["Authorization"] = f"Bearer {AUTH_TOKEN}"
    return h


def _post_v1_action(json_body, timeout=5):
    """POST /v1/action; on connection error skip."""
    try:
        return requests.post(f"{BASE_URL}/v1/action", json=json_body, headers=_headers(), timeout=timeout)
    except requests.exceptions.ConnectionError:
        pytest.skip("Gateway not running (connection refused)")


# ---- API tests (require gateway running; skip if unreachable) ----


@pytest.mark.skipif(not BASE_URL.startswith("http"), reason="need gateway URL")
def test_v1_action_happy_path():
    """POST /v1/action with valid body returns 200 and verdict/decision_id."""
    resp = _post_v1_action({
        "agent_id": "test-agent-001",
        "action_type": "tool_call",
        "action_payload": {"tool": "memory", "op": "get", "params": {}},
        "timestamp": None,
        "context": None,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "verdict" in data
    assert "decision_id" in data
    assert data["verdict"] in ("allow", "block", "degrade", "ALLOW", "BLOCK", "DEGRADE", "ESCALATE")


@pytest.mark.skipif(not BASE_URL.startswith("http"), reason="need gateway URL")
def test_v1_action_rejects_unknown_fields():
    """POST /v1/action with extra top-level field returns 422 (strict schema)."""
    resp = _post_v1_action({
        "agent_id": "test-agent-001",
        "action_type": "tool_call",
        "action_payload": {"tool": "memory", "op": "get", "params": {}},
        "unknown_field": "forbidden",
    })
    assert resp.status_code == 422, (resp.status_code, resp.text)


@pytest.mark.skipif(not BASE_URL.startswith("http"), reason="need gateway URL")
def test_v1_action_validation_missing_agent_id():
    """POST /v1/action without agent_id returns 400 with error code."""
    resp = _post_v1_action({
        "agent_id": "",
        "action_type": "tool_call",
        "action_payload": {"tool": "memory", "op": "get", "params": {}},
    })
    assert resp.status_code == 400
    detail = resp.json().get("detail", {})
    if isinstance(detail, dict):
        assert detail.get("code") == "MISSING_FIELD" or "agent_id" in str(detail).lower()


@pytest.mark.skipif(not BASE_URL.startswith("http"), reason="need gateway URL")
def test_v1_action_validation_missing_tool_in_payload():
    """POST /v1/action with action_type tool_call but missing tool returns 400."""
    resp = _post_v1_action({
        "agent_id": "test-agent-001",
        "action_type": "tool_call",
        "action_payload": {"op": "get", "params": {}},
    })
    assert resp.status_code == 400


# ---- Validation tests via TestClient (no live server) ----
# Disable auth in tests so we can assert validation (422/400) without token setup.


def test_v1_action_rejects_unknown_fields_testclient(monkeypatch):
    """POST /v1/action with extra field returns 422 (strict schema). Uses TestClient."""
    monkeypatch.setenv("EDON_AUTH_ENABLED", "false")
    from fastapi.testclient import TestClient
    from edon_gateway.main import app
    # Re-read config so AUTH_ENABLED is false (config may be cached)
    import edon_gateway.config as cfg
    monkeypatch.setattr(cfg.config, "_AUTH_ENABLED", False)
    client = TestClient(app)
    resp = client.post(
        "/v1/action",
        json={
            "agent_id": "test-agent-001",
            "action_type": "tool_call",
            "action_payload": {"tool": "memory", "op": "get", "params": {}},
            "unknown_field": "forbidden",
        },
    )
    assert resp.status_code == 422


def test_v1_action_validation_missing_agent_id_testclient(monkeypatch):
    """POST /v1/action with empty agent_id returns 400 or 422."""
    monkeypatch.setenv("EDON_AUTH_ENABLED", "false")
    from fastapi.testclient import TestClient
    from edon_gateway.main import app
    import edon_gateway.config as cfg
    monkeypatch.setattr(cfg.config, "_AUTH_ENABLED", False)
    client = TestClient(app)
    resp = client.post(
        "/v1/action",
        json={
            "agent_id": "",
            "action_type": "memory.get",
            "action_payload": {"key": "test"},
        },
    )
    assert resp.status_code in (400, 422)


def test_v1_action_validation_missing_tool_testclient(monkeypatch):
    """POST /v1/action missing action_payload returns 422 (required field)."""
    monkeypatch.setenv("EDON_AUTH_ENABLED", "false")
    from fastapi.testclient import TestClient
    from edon_gateway.main import app
    import edon_gateway.config as cfg
    monkeypatch.setattr(cfg.config, "_AUTH_ENABLED", False)
    client = TestClient(app)
    resp = client.post(
        "/v1/action",
        json={
            "agent_id": "test-agent-001",
            "action_type": "memory.get",
        },
    )
    assert resp.status_code == 422


# ---- Cross-tenant isolation (DB-level, no gateway required) ----


def test_cross_tenant_audit_isolation():
    """Query with customer_id returns only that tenant's audit rows. No cross-tenant leakage."""
    from edon_gateway.persistence.database import Database

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = Database(__import__("pathlib").Path(db_path))
        # Insert one event for tenant_a
        action = {
            "id": "act-1",
            "requested_at": "2026-02-07T12:00:00Z",
            "tool": "memory",
            "op": "get",
            "params": {},
            "source": "agent",
            "estimated_risk": "",
            "computed_risk": None,
        }
        decision = {
            "verdict": "ALLOW",
            "reason_code": "OK",
            "explanation": "Allowed",
            "policy_version": "1.0.0",
        }
        db.save_audit_event(
            action=action,
            decision=decision,
            intent_id=None,
            agent_id="agent-1",
            context={"v": 1},
            customer_id="tenant_a",
        )
        # Insert one event for tenant_b
        action2 = {
            "id": "act-2",
            "requested_at": "2026-02-07T12:01:00Z",
            "tool": "email",
            "op": "draft",
            "params": {},
            "source": "agent",
            "estimated_risk": "",
            "computed_risk": None,
        }
        db.save_audit_event(
            action=action2,
            decision=decision,
            intent_id=None,
            agent_id="agent-2",
            context={"v": 1},
            customer_id="tenant_b",
        )
        # Query as tenant_a must not see tenant_b's event
        events_a = db.query_audit_events(customer_id="tenant_a", limit=10)
        events_b = db.query_audit_events(customer_id="tenant_b", limit=10)
        action_ids_a = {e["action"]["id"] for e in events_a}
        action_ids_b = {e["action"]["id"] for e in events_b}
        assert "act-1" in action_ids_a
        assert "act-2" not in action_ids_a
        assert "act-2" in action_ids_b
        assert "act-1" not in action_ids_b
    finally:
        try:
            os.unlink(db_path)
        except Exception:
            pass
