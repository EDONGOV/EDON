import sqlite3
from pathlib import Path


def test_rbac_requires_auth_for_assistant_and_autonomy_routes():
    from edon_gateway.middleware.rbac import required_permission_for

    assert required_permission_for("POST", "/v1/jarvis/ask") == "admin"
    assert required_permission_for("POST", "/v1/voice/ask") == "admin"
    assert required_permission_for("POST", "/v1/autonomous/run") == "admin"
    assert required_permission_for("POST", "/v1/codex/task") == "admin"
    assert required_permission_for("GET", "/v1/autonomous/status") == "read"


def test_rbac_keeps_high_risk_console_mutations_admin_only():
    from edon_gateway.middleware.rbac import required_permission_for

    assert required_permission_for("POST", "/v1/assistant/apply") == "admin"
    assert required_permission_for("POST", "/v1/assistant/memories/mem-1/review") == "admin"
    assert required_permission_for("POST", "/v1/onboarding/runtimes/run-1/promote") == "admin"
    assert required_permission_for("POST", "/v1/onboarding/signoffs/sig-1/approve") == "admin"
    assert required_permission_for("POST", "/v1/operations/reconciliation/batch-1/promote") == "admin"
    assert required_permission_for("POST", "/access/user-invites") == "admin"
    assert required_permission_for("POST", "/access/user-invites/accept") is None


def test_encrypted_audit_mode_encrypts_context_and_params(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("EDON_ENV", "test")
    monkeypatch.setenv("EDON_DB_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("EDON_AUDIT_CHAIN_SIGNING_KEY", "test-signing-key")

    import edon_gateway.config as cfg
    import edon_gateway.security.encryption as enc

    monkeypatch.setattr(cfg.config, "_ENVIRONMENT", "test")
    monkeypatch.setattr(cfg.config, "_ENCRYPT_AUDIT_PAYLOAD", True)
    enc._fernet_instance = None

    from edon_gateway.persistence.database import Database

    db_path = Path(tmp_path) / "encrypted_audit.db"
    db = Database(db_path=db_path)
    db.save_audit_event(
        action={
            "id": "act-phi",
            "requested_at": "2026-01-01T00:00:00Z",
            "tool": "ehr",
            "op": "read",
            "params": {"patient_id": "P-12345", "note": "sensitive"},
            "source": "agent",
            "estimated_risk": "medium",
            "computed_risk": "medium",
        },
        decision={
            "verdict": "ALLOW",
            "reason_code": "OK",
            "explanation": "allowed",
            "policy_version": "1.0.0",
        },
        intent_id=None,
        agent_id="agent-1",
        context={"tenant_id": "tenant-1", "patient_id": "P-12345", "data_class": "PHI"},
        customer_id="tenant-1",
    )

    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute("SELECT action_params, context, is_payload_encrypted FROM audit_events").fetchone()

    assert row[2] == 1
    assert "P-12345" not in row[0]
    assert "P-12345" not in row[1]

    events = db.query_audit_events(customer_id="tenant-1")
    assert events[0]["action"]["params"]["patient_id"] == "P-12345"
    assert events[0]["context"]["patient_id"] == "P-12345"
    assert db.verify_audit_chain()["valid"] is True


def test_unsigned_audit_legacy_default_is_strict_in_production(tmp_path, monkeypatch):
    from edon_gateway.persistence.database import Database

    monkeypatch.setenv("EDON_ENV", "test")
    monkeypatch.delenv("EDON_AUDIT_CHAIN_SIGNING_KEY", raising=False)
    monkeypatch.delenv("EDON_AUDIT_ALLOW_UNSIGNED_LEGACY", raising=False)
    import edon_gateway.config as cfg

    monkeypatch.setattr(cfg.config, "_ENVIRONMENT", "test")
    monkeypatch.setattr(cfg.config, "_ENCRYPT_AUDIT_PAYLOAD", False)

    db = Database(db_path=Path(tmp_path) / "unsigned_legacy.db")
    db.save_audit_event(
        action={
            "id": "act-legacy",
            "requested_at": "2026-01-01T00:00:00Z",
            "tool": "email",
            "op": "send",
            "params": {},
            "source": "agent",
            "estimated_risk": "low",
            "computed_risk": "low",
        },
        decision={
            "verdict": "ALLOW",
            "reason_code": "OK",
            "explanation": "allowed",
            "policy_version": "1.0.0",
        },
        intent_id=None,
        agent_id="agent-1",
        context={"tenant_id": "tenant-1"},
        customer_id="tenant-1",
    )

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("EDON_ENV", "production")
    monkeypatch.setenv("EDON_AUDIT_CHAIN_SIGNING_KEY", "test-signing-key")
    monkeypatch.setattr(cfg.config, "_ENVIRONMENT", "production")
    result = db.verify_audit_chain()
    assert result["valid"] is False
    assert "Unsigned chain row" in result["message"]
