from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _set_enterprise_config(monkeypatch, cfg):
    monkeypatch.setattr(cfg.config, "_AUTH_ENABLED", True)
    monkeypatch.setattr(cfg.config, "_ENTERPRISE_MODE", True)
    monkeypatch.setattr(cfg.config, "_ENTERPRISE_SSO_ONLY", True)
    monkeypatch.setattr(cfg.config, "_REQUIRE_ADMIN_MFA", True)
    monkeypatch.setattr(cfg.config, "_REQUIRE_PHISHING_RESISTANT_MFA", True)
    monkeypatch.setattr(cfg.config, "_EDGE_REQUIRE_NODE_CERTIFICATE", True)
    monkeypatch.setattr(cfg.config, "_EDGE_REQUIRE_ATTESTATION", True)
    monkeypatch.setattr(cfg.config, "_EDGE_BUNDLE_SIGNING_KEY", "edge")
    monkeypatch.setattr(cfg.config, "_TOKEN_BINDING_ENABLED", True)
    monkeypatch.setattr(cfg.config, "_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(cfg.config, "_ENCRYPT_AUDIT_PAYLOAD", True)
    monkeypatch.setattr(cfg.config, "_CORS_ORIGINS", ["https://console.hospital.example"])
    monkeypatch.setattr(cfg.config, "_ALLOW_ENV_TOKEN_IN_PROD", False)
    monkeypatch.setattr(cfg.config, "_CLERK_SECRET_KEY", "clerk")


def _set_hipaa_env(monkeypatch):
    values = {
        "DATABASE_URL": "postgresql://edon:secret@db.example:5432/edon",
        "EDON_API_TOKEN": "prod-token",
        "EDON_DB_ENCRYPTION_KEY": "fernet-key",
        "EDON_CLOUD_PROVIDER": "azure",
        "EDON_BAA_SIGNED": "true",
        "EDON_HIPAA_DEPLOYMENT_PROFILE": "true",
        "EDON_PRIVATE_NETWORK_ENABLED": "true",
        "EDON_WAF_ENABLED": "true",
        "EDON_MANAGED_POSTGRES": "true",
        "AZURE_KEY_VAULT_URL": "https://edon.vault.azure.net/",
        "AZURE_KEY_VAULT_KEY_ID": "https://edon.vault.azure.net/keys/signing/v1",
        "EDON_SIGNING_KEY_HEX": "a" * 64,
        "EDON_AUDIT_CHAIN_SIGNING_KEY": "audit-key",
        "EDON_BACKUP_BUCKET": "edon-backups",
        "EDON_BACKUP_SCHEDULE": "0 3 * * *",
        "EDON_RESTORE_DRILL_LAST_RUN_AT": "2026-05-21T00:00:00Z",
        "EDON_SENTINEL_WORKSPACE_ID": "workspace",
        "EDON_LOG_RETENTION_DAYS": "2190",
        "EDON_ALERT_WEBHOOK": "https://alerts.example",
        "EDON_SSO_ROLE_CLAIM": "edon_role",
        "EDON_SSO_DEPARTMENT_CLAIM": "edon_department",
        "CLERK_ISSUER": "https://issuer.example",
        "CLERK_AUDIENCE": "edon-console",
        "EDON_SMTP_HOST": "smtp.example",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_enterprise_violations_require_hipaa_cloud_controls(monkeypatch):
    import backend.edon_gateway.config as cfg

    monkeypatch.setattr(cfg.config, "is_production", lambda: True)
    _set_enterprise_config(monkeypatch, cfg)
    monkeypatch.setenv("DATABASE_URL", "postgresql://edon:secret@db.example:5432/edon")
    monkeypatch.setenv("EDON_API_TOKEN", "prod-token")
    monkeypatch.setenv("EDON_DB_ENCRYPTION_KEY", "fernet-key")
    monkeypatch.setenv("CLERK_ISSUER", "https://issuer.example")
    monkeypatch.setenv("CLERK_AUDIENCE", "edon-console")

    violations = cfg.config.enterprise_violations()

    assert "EDON_BAA_SIGNED must be true before HIPAA production deployment" in violations
    assert "A production vault provider must be configured" in violations
    assert "Cloud-native log retention or SIEM export must be configured" in violations


def test_production_readiness_passes_when_hipaa_controls_are_configured(monkeypatch):
    import backend.edon_gateway.config as cfg
    import backend.edon_gateway.routes.ops as ops

    monkeypatch.setattr(cfg.config, "is_production", lambda: True)
    monkeypatch.setattr(ops.config, "is_production", lambda: True)
    _set_enterprise_config(monkeypatch, cfg)
    _set_enterprise_config(monkeypatch, ops)
    _set_hipaa_env(monkeypatch)
    monkeypatch.setattr(ops, "_get_database_dependency_status", lambda _app: {"scheme": "postgresql", "status": "healthy"})
    monkeypatch.setattr(ops.config, "enterprise_violations", lambda: [])

    app = FastAPI()
    app.state.db = object()
    app.include_router(ops.router)

    resp = TestClient(app).get("/ops/production-readiness")

    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["cloud_profile"]["provider"] == "azure"
    assert payload["vault"]["provider"] == "azure_key_vault"
    assert payload["observability"]["log_retention_days"] == 2190
    assert payload["ready"] is False  # client_e2e remains manual_required
