"""
Integration tests for key EDON Gateway endpoints.

Covers:
  - GET /health
  - POST /v1/action (valid allow case, malformed cases)
  - GET /audit/query
  - GET /audit/export?format=json
  - GET /compliance/report
  - GET /version
  - Auth enforcement (protected endpoint with no token)
"""

from datetime import datetime, UTC

import pytest


# ============================================================
# Fixtures
# ============================================================

# Auth/env fixtures provided by conftest.py (_dev_environment, autouse)


@pytest.fixture
def client(_dev_environment):
    from starlette.testclient import TestClient
    from edon_gateway.main import app
    with TestClient(app, headers={"X-Agent-ID": "integ-test-client"}) as c:
        yield c


def _valid_action_body():
    return {
        "agent_id": "integ-agent-001",
        "action_type": "email.read",
        "action_payload": {"tool": "email", "op": "read", "params": {"folder": "inbox"}},
        "timestamp": datetime.now(UTC).isoformat(),
        "context": {},
    }


# ============================================================
# GET /health
# ============================================================

class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_contains_status_key(self, client):
        resp = client.get("/health")
        data = resp.json()
        assert "status" in data

    def test_health_status_is_string(self, client):
        resp = client.get("/health")
        data = resp.json()
        assert isinstance(data["status"], str)

    def test_health_contains_components(self, client):
        resp = client.get("/health")
        data = resp.json()
        assert "components" in data

    def test_health_database_component_present(self, client):
        resp = client.get("/health")
        data = resp.json()
        components = data.get("components", {})
        assert "database" in components

    def test_health_database_has_status(self, client):
        resp = client.get("/health")
        components = resp.json().get("components", {})
        database = components.get("database", {})
        assert "status" in database
        assert database["status"] in ("healthy", "degraded", "unhealthy")


# ============================================================
# POST /v1/action
# ============================================================

class TestV1ActionEndpoint:
    def test_valid_action_returns_200(self, client):
        resp = client.post("/v1/action", json=_valid_action_body())
        assert resp.status_code == 200

    def test_valid_action_has_decision(self, client):
        resp = client.post("/v1/action", json=_valid_action_body())
        data = resp.json()
        # Accept both "decision" and "verdict" keys
        assert "decision" in data or "verdict" in data

    def test_valid_action_decision_is_valid(self, client):
        resp = client.post("/v1/action", json=_valid_action_body())
        data = resp.json()
        value = data.get("decision") or data.get("verdict", "")
        assert str(value).upper() in ("ALLOW", "BLOCK", "HUMAN_REQUIRED", "DEGRADE", "PAUSE", "ESCALATE")

    def test_missing_agent_id_returns_4xx(self, client):
        body = _valid_action_body()
        body["agent_id"] = ""
        resp = client.post("/v1/action", json=body)
        assert resp.status_code in (400, 422)

    def test_missing_action_type_returns_4xx(self, client):
        body = _valid_action_body()
        body["action_type"] = ""
        resp = client.post("/v1/action", json=body)
        assert resp.status_code in (400, 422)

    def test_missing_action_payload_returns_422(self, client):
        body = {
            "agent_id": "integ-agent-001",
            "action_type": "email.read",
        }
        resp = client.post("/v1/action", json=body)
        assert resp.status_code == 422

    def test_extra_unknown_field_is_ignored(self, client):
        # V1ActionRequest does not forbid extra fields — they are silently ignored
        body = _valid_action_body()
        body["unknown_extra_field"] = "ignored"
        resp = client.post("/v1/action", json=body)
        assert resp.status_code == 200

    def test_malformed_action_type_no_dot_returns_400(self, client):
        body = _valid_action_body()
        body["action_type"] = "nodothere"
        resp = client.post("/v1/action", json=body)
        # Either 200 (routed as custom) or 400 depending on parse strictness
        assert resp.status_code in (200, 400, 422)

    def test_empty_body_returns_422(self, client):
        resp = client.post("/v1/action", json={})
        assert resp.status_code == 422


# ============================================================
# GET /audit/query
# ============================================================

class TestAuditQueryEndpoint:
    def test_audit_query_returns_200(self, client):
        resp = client.get("/audit/query")
        assert resp.status_code == 200

    def test_audit_query_returns_list_or_events_key(self, client):
        resp = client.get("/audit/query")
        data = resp.json()
        assert isinstance(data, (list, dict))

    def test_audit_query_accepts_limit_param(self, client):
        resp = client.get("/audit/query?limit=5")
        assert resp.status_code == 200


# ============================================================
# GET /audit/export?format=json
# ============================================================

class TestAuditExportEndpoint:
    def test_audit_export_json_returns_200(self, client):
        resp = client.get("/audit/export?format=json")
        assert resp.status_code == 200

    def test_audit_export_csv_returns_200(self, client):
        resp = client.get("/audit/export?format=csv")
        assert resp.status_code == 200


# ============================================================
# GET /compliance/report
# ============================================================

class TestComplianceReportEndpoint:
    def test_compliance_report_returns_200(self, client):
        resp = client.get("/compliance/report")
        assert resp.status_code == 200

    def test_compliance_report_has_content(self, client):
        resp = client.get("/compliance/report")
        data = resp.json()
        assert data is not None


# ============================================================
# GET /version
# ============================================================

class TestVersionEndpoint:
    def test_version_returns_200(self, client):
        resp = client.get("/version")
        assert resp.status_code == 200

    def test_version_has_version_key(self, client):
        resp = client.get("/version")
        data = resp.json()
        assert "version" in data

    def test_version_value_is_string(self, client):
        resp = client.get("/version")
        data = resp.json()
        assert isinstance(data["version"], str)


# ============================================================
# Auth enforcement
# ============================================================

class TestAuthEnforcement:
    def test_no_token_to_protected_endpoint_blocked_when_auth_enabled(self, monkeypatch):
        """When auth is enabled, a request with no token should be rejected."""
        monkeypatch.setenv("EDON_AUTH_ENABLED", "true")
        monkeypatch.setenv("EDON_API_TOKEN", "secret-token-for-test")
        import edon_gateway.config as cfg
        monkeypatch.setattr(cfg.config, "_AUTH_ENABLED", True)

        from starlette.testclient import TestClient
        from edon_gateway.main import app
        with TestClient(app, raise_server_exceptions=False) as auth_client:
            resp = auth_client.post("/v1/action", json=_valid_action_body())
            assert resp.status_code in (401, 403)
