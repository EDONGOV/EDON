import sqlite3
from pathlib import Path

from edon_gateway.persistence.database import Database


def _sample_action():
    return {
        "id": "act-1",
        "tool": "email",
        "op": "send",
        "params": {"to": ["a@b.com"]},
        "source": "agent",
        "estimated_risk": "low",
        "computed_risk": "low",
    }


def _sample_decision():
    return {
        "verdict": "ALLOW",
        "reason_code": "APPROVED",
        "explanation": "ok",
        "policy_version": "1.0.0",
    }


def test_signed_chain_verification_detects_tamper(tmp_path, monkeypatch):
    monkeypatch.setenv("EDON_AUDIT_CHAIN_SIGNING_KEY", "test-signing-key")
    db_path = Path(tmp_path) / "audit_chain.db"
    db = Database(db_path=db_path)

    db.save_audit_event(_sample_action(), _sample_decision(), "intent_a", "agent_a", {"tenant_id": "t1"}, customer_id="t1")
    db.save_audit_event({**_sample_action(), "id": "act-2"}, _sample_decision(), "intent_a", "agent_a", {"tenant_id": "t1"}, customer_id="t1")
    assert db.verify_audit_chain().get("valid") is True

    # Simulate DB compromise by dropping append-only trigger then mutating a row.
    with sqlite3.connect(str(db_path)) as conn:
        cur = conn.cursor()
        cur.execute("DROP TRIGGER IF EXISTS audit_events_append_only_update")
        cur.execute("UPDATE audit_events SET action_op = 'draft' WHERE id = 1")
        conn.commit()

    result = db.verify_audit_chain()
    assert result.get("valid") is False


def test_unsigned_legacy_rows_handled_by_policy(tmp_path, monkeypatch):
    # Create legacy unsigned row
    monkeypatch.delenv("EDON_AUDIT_CHAIN_SIGNING_KEY", raising=False)
    db = Database(db_path=Path(tmp_path) / "legacy_chain.db")
    db.save_audit_event(_sample_action(), _sample_decision(), "intent_a", "agent_a", {"tenant_id": "t1"}, customer_id="t1")

    # Enable signing key post-hoc; unsigned legacy rows are allowed by default.
    monkeypatch.setenv("EDON_AUDIT_CHAIN_SIGNING_KEY", "test-signing-key")
    monkeypatch.setenv("EDON_AUDIT_ALLOW_UNSIGNED_LEGACY", "true")
    assert db.verify_audit_chain().get("valid") is True

    # In strict mode, unsigned legacy rows fail verification.
    monkeypatch.setenv("EDON_AUDIT_ALLOW_UNSIGNED_LEGACY", "false")
    assert db.verify_audit_chain().get("valid") is False
