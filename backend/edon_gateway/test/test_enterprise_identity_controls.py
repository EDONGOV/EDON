"""Enterprise identity control regressions."""

from __future__ import annotations

import os
import hashlib
import hmac
import json

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import backend.edon_gateway.config as cfg
import backend.edon_gateway.middleware.auth as auth_module
import backend.edon_gateway.routes.auth as auth_routes
import backend.edon_gateway.routes.edge as edge_routes


@pytest.fixture(autouse=True)
def _enterprise_env(monkeypatch):
    enterprise_clerk_secret_key = os.environ.get("EDON_TEST_CLERK_SECRET_KEY", "enterprise-clerk-key")
    enterprise_stripe_secret_key = os.environ.get("EDON_TEST_STRIPE_SECRET_KEY", "enterprise-stripe-key")
    edge_bundle_signing_key = os.environ.get("EDON_TEST_EDGE_BUNDLE_SIGNING_KEY", "enterprise-edge-bundle-key")

    monkeypatch.setenv("EDON_ENV", "development")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("EDON_AUTH_ENABLED", "false")
    monkeypatch.setenv("EDON_CREDENTIALS_STRICT", "false")
    monkeypatch.setenv("EDON_API_TOKEN", "enterprise-token")
    monkeypatch.setenv("EDON_ALLOW_ENV_TOKEN_IN_PROD", "false")
    monkeypatch.setenv("EDON_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("EDON_CORS_ORIGINS", "https://console.example.com")
    monkeypatch.setenv("EDON_DB_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("STRIPE_SECRET_KEY", enterprise_stripe_secret_key)
    monkeypatch.setenv("EDON_AUDIT_CHAIN_SIGNING_KEY", "enterprise-audit-key")
    monkeypatch.setenv("CLERK_SECRET_KEY", enterprise_clerk_secret_key)
    monkeypatch.setenv("CLERK_ISSUER", "https://clerk.example")
    monkeypatch.setenv("CLERK_AUDIENCE", "edon-enterprise")
    monkeypatch.setenv("EDON_ENTERPRISE_MODE", "true")
    monkeypatch.setenv("EDON_ENTERPRISE_SSO_ONLY", "true")
    monkeypatch.setenv("EDON_REQUIRE_ADMIN_MFA", "true")
    monkeypatch.setenv("EDON_REQUIRE_PHISHING_RESISTANT_MFA", "true")
    monkeypatch.setenv("EDON_EDGE_REQUIRE_NODE_CERTIFICATE", "true")
    monkeypatch.setenv("EDON_EDGE_REQUIRE_ATTESTATION", "true")
    monkeypatch.setenv("EDON_EDGE_BUNDLE_SIGNING_KEY", edge_bundle_signing_key)

    monkeypatch.setattr(cfg.config, "_ENVIRONMENT", "development")
    monkeypatch.setattr(cfg.config, "_AUTH_ENABLED", False)
    monkeypatch.setattr(cfg.config, "_CREDENTIALS_STRICT", False)
    monkeypatch.setattr(cfg.config, "_API_TOKEN", "enterprise-token")
    monkeypatch.setattr(cfg.config, "_ALLOW_ENV_TOKEN_IN_PROD", False)
    monkeypatch.setattr(cfg.config, "_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(cfg.config, "_CORS_ORIGINS", ["https://console.example.com"])
    monkeypatch.setattr(cfg.config, "_CLERK_SECRET_KEY", enterprise_clerk_secret_key)
    monkeypatch.setattr(cfg.config, "_STRIPE_SECRET_KEY", enterprise_stripe_secret_key)
    monkeypatch.setattr(cfg.config, "_ENTERPRISE_MODE", True)
    monkeypatch.setattr(cfg.config, "_ENTERPRISE_SSO_ONLY", True)
    monkeypatch.setattr(cfg.config, "_REQUIRE_ADMIN_MFA", True)
    monkeypatch.setattr(cfg.config, "_REQUIRE_PHISHING_RESISTANT_MFA", True)
    monkeypatch.setattr(cfg.config, "_EDGE_REQUIRE_NODE_CERTIFICATE", True)
    monkeypatch.setattr(cfg.config, "_EDGE_REQUIRE_ATTESTATION", True)
    monkeypatch.setattr(cfg.config, "_EDGE_BUNDLE_SIGNING_KEY", edge_bundle_signing_key)
    monkeypatch.setattr(auth_module, "_is_brute_force_locked", lambda _ip: False)
    monkeypatch.setattr(auth_module, "_record_failed_auth", lambda _ip: None)
    monkeypatch.setattr(auth_routes, "check_rate_limit", lambda *args, **kwargs: (True, ""))
    monkeypatch.setattr(auth_routes, "increment_rate_limit", lambda *args, **kwargs: None)


def _edge_registration_signature(tenant_id: str, payload: dict, cert_fingerprint: str, attestation: dict, identity_provider: str) -> str:
    signing_key = os.environ.get("EDON_TEST_EDGE_BUNDLE_SIGNING_KEY", "enterprise-edge-bundle-key")
    canonical = json.dumps(
        {
            "tenant_id": tenant_id,
            "node_id": payload["node_id"],
            "name": payload["name"],
            "capabilities": sorted(payload.get("capabilities") or []),
            "metadata": payload.get("metadata") or {},
            "cert_fingerprint": cert_fingerprint or "",
            "attestation": json.dumps(attestation, sort_keys=True, separators=(",", ":")),
            "identity_provider": identity_provider.strip().lower(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hmac.new(signing_key.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


@pytest.fixture
def client():
    cfg.config.assert_enterprise_ready = lambda: None
    from backend.edon_gateway.main import app

    with TestClient(app) as c:
        yield c


def test_enterprise_config_requires_identity_controls(monkeypatch):
    monkeypatch.setenv("EDON_ENV", "production")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://edon:edon@db/edon")
    monkeypatch.setenv("EDON_ENCRYPT_AUDIT_PAYLOAD", "false")
    monkeypatch.setenv("EDON_TOKEN_BINDING_ENABLED", "false")
    monkeypatch.setattr(cfg.config, "_ENTERPRISE_SSO_ONLY", False)
    monkeypatch.setattr(cfg.config, "_REQUIRE_ADMIN_MFA", False)
    monkeypatch.setattr(cfg.config, "_REQUIRE_PHISHING_RESISTANT_MFA", False)
    monkeypatch.setattr(cfg.config, "_EDGE_REQUIRE_NODE_CERTIFICATE", False)
    monkeypatch.setattr(cfg.config, "_EDGE_REQUIRE_ATTESTATION", False)
    monkeypatch.setattr(cfg.config, "_ENCRYPT_AUDIT_PAYLOAD", False)
    monkeypatch.setattr(cfg.config, "_TOKEN_BINDING_ENABLED", False)

    violations = cfg.config.enterprise_violations()

    assert "EDON_ENTERPRISE_SSO_ONLY must be true in enterprise mode" in violations
    assert "EDON_REQUIRE_ADMIN_MFA must be true in enterprise mode" in violations
    assert "EDON_REQUIRE_PHISHING_RESISTANT_MFA must be true in enterprise mode" in violations
    assert "EDON_EDGE_REQUIRE_NODE_CERTIFICATE must be true in enterprise mode" in violations
    assert "EDON_EDGE_REQUIRE_ATTESTATION must be true in enterprise mode" in violations
    assert "EDON_TOKEN_BINDING_ENABLED must be true in production" in violations
    assert "EDON_ENCRYPT_AUDIT_PAYLOAD must be true in production" in violations


def test_password_registration_blocked_in_enterprise_mode(client):
    resp = client.post("/auth/register", json={"email": "ops@example.com", "password": "TestPass123!"})
    assert resp.status_code == 403
    assert "enterprise SSO-only mode" in resp.json()["detail"]


def test_password_login_blocked_in_enterprise_mode(client):
    resp = client.post("/auth/login", json={"email": "ops@example.com", "password": "TestPass123!"})
    assert resp.status_code == 403
    assert "enterprise SSO-only mode" in resp.json()["detail"]


def test_edge_registration_requires_node_identity(monkeypatch, client):
    monkeypatch.setattr(edge_routes, "get_request_tenant_id", lambda request: "tenant-enterprise")

    resp = client.post(
        "/edge/register",
        json={"node_id": "edge-001", "name": "Edge One"},
    )

    assert resp.status_code == 403
    assert "certificate fingerprint" in resp.json()["detail"]


def test_edge_registration_accepts_cert_and_attestation(monkeypatch, client):
    monkeypatch.setattr(edge_routes, "get_request_tenant_id", lambda request: "tenant-enterprise")
    payload = {
        "node_id": "edge-002",
        "name": "Edge Two",
        "cert_fingerprint": "fp-123",
        "signed_config_bundle": "",
        "attestation": {"healthy": True},
        "identity_provider": "mtls-proxy",
    }
    payload["signed_config_bundle"] = _edge_registration_signature(
        "tenant-enterprise",
        payload,
        "fp-123",
        payload["attestation"],
        payload["identity_provider"],
    )

    resp = client.post(
        "/edge/register",
        headers={
            "X-Client-Cert-Fingerprint": "fp-123",
            "X-Edge-Attestation": "{\"healthy\": true}",
        },
        json=payload,
    )

    assert resp.status_code == 200
    assert resp.json()["node_id"] == "edge-002"


def test_edge_revocation_blocks_bundle_access(monkeypatch, client):
    monkeypatch.setattr(edge_routes, "get_request_tenant_id", lambda request: "tenant-enterprise")
    payload = {
        "node_id": "edge-003",
        "name": "Edge Three",
        "cert_fingerprint": "fp-333",
        "signed_config_bundle": "",
        "attestation": {"healthy": True},
        "identity_provider": "mtls-proxy",
    }
    payload["signed_config_bundle"] = _edge_registration_signature(
        "tenant-enterprise",
        payload,
        "fp-333",
        payload["attestation"],
        payload["identity_provider"],
    )

    reg = client.post(
        "/edge/register",
        headers={
            "X-Client-Cert-Fingerprint": "fp-333",
            "X-Edge-Attestation": "{\"healthy\":true}",
        },
        json=payload,
    )
    assert reg.status_code == 200

    revoke = client.post("/edge/edge-003/revoke", json={"reason": "retired"})
    assert revoke.status_code == 200
    assert revoke.json()["status"] == "revoked"

    bundle = client.get("/edge/edge-003/policy-bundle")
    assert bundle.status_code == 403
    assert "revoked" in bundle.json()["detail"].lower()
