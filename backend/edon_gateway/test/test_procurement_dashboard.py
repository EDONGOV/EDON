from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_procurement_dashboard_reports_core_controls(monkeypatch):
    import backend.edon_gateway.routes.ops as ops

    monkeypatch.setattr(ops, "_get_database_dependency_status", lambda _app: {"scheme": "postgresql"})
    monkeypatch.setattr(ops.config, "is_production", lambda: True)
    monkeypatch.setattr(ops.config, "_AUTH_ENABLED", True)
    monkeypatch.setattr(ops.config, "_ENTERPRISE_SSO_ONLY", True)
    monkeypatch.setattr(ops.config, "_ENTERPRISE_MODE", True)
    monkeypatch.setattr(ops.config, "_ENTERPRISE_DEFAULT_USER_ROLE", "viewer")
    monkeypatch.setattr(ops.config, "_REQUIRE_ADMIN_MFA", True)
    monkeypatch.setattr(ops.config, "_REQUIRE_PHISHING_RESISTANT_MFA", True)
    monkeypatch.setattr(ops.config, "_TOKEN_BINDING_ENABLED", True)
    monkeypatch.setattr(ops.config, "_ENCRYPT_AUDIT_PAYLOAD", True)
    monkeypatch.setattr(ops.config, "_EDGE_REQUIRE_NODE_CERTIFICATE", True)
    monkeypatch.setattr(ops.config, "_EDGE_REQUIRE_ATTESTATION", True)
    monkeypatch.setattr(ops.config, "_EDGE_BUNDLE_SIGNING_KEY", "edge-signing-key")

    app = FastAPI()
    app.state.db = object()
    app.include_router(ops.router)

    client = TestClient(app)
    resp = client.get("/governance/procurement-dashboard")

    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["controls"]["sso_only"] is True
    assert payload["controls"]["mfa"]["admin"] is True
    assert payload["controls"]["postgres"] is True
    assert payload["controls"]["edge_identity"]["bundle_signing_key"] is True
    assert payload["drift"]["status"] == "healthy"
