"""Tests for default system-level policy rules and preset seeding.

Verifies that:
1. System default rules are defined and cover critical operations
2. Dangerous operations are blocked/escalated when system rules are active
3. Tenant rules with higher priority can override system defaults
4. ops_commander is set as the active preset when none is configured
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from datetime import datetime, UTC
from starlette.testclient import TestClient


# ── Fixture ────────────────────────────────────────────────────────────────────


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("EDON_ENV", "development")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("EDON_AUTH_ENABLED", "false")
    monkeypatch.setenv("EDON_CREDENTIALS_STRICT", "false")
    monkeypatch.setenv("EDON_STRICT_FAIL_CLOSED", "false")
    monkeypatch.setenv("EDON_AI_ENABLED", "false")
    monkeypatch.setenv("EDON_PROBE_ENABLED", "false")
    monkeypatch.setenv("EDON_DB_ENCRYPTION_KEY", Fernet.generate_key().decode())

    import edon_gateway.config as cfg
    monkeypatch.setattr(cfg.config, "_AUTH_ENABLED", False)
    monkeypatch.setattr(cfg.config, "_ENVIRONMENT", "development")
    monkeypatch.setattr(cfg.config, "_CREDENTIALS_STRICT", False)

    from edon_gateway.main import app
    with TestClient(app) as c:
        yield c


def _action(action_type: str, payload: dict | None = None) -> dict:
    return {
        "agent_id": "test-agent-defaults",
        "action_type": action_type,
        "action_payload": payload or {},
        "timestamp": datetime.now(UTC).isoformat(),
        "context": {},
    }


# ── Rule definitions ───────────────────────────────────────────────────────────


def test_system_default_rules_cover_critical_ops():
    """SYSTEM_DEFAULT_RULES must include blocks/escalations for the most dangerous ops."""
    from edon_gateway.policy.defaults import SYSTEM_DEFAULT_RULES

    # Build a lookup: (tool, op) -> action
    rule_map = {
        (r["condition_tool"], r["condition_op"]): r["action"]
        for r in SYSTEM_DEFAULT_RULES
    }

    assert rule_map.get(("database", "drop")) == "BLOCK", "database.drop must be BLOCK"
    assert rule_map.get(("database", "truncate")) == "BLOCK", "database.truncate must be BLOCK"
    assert rule_map.get(("shell", "execute")) == "ESCALATE", "shell.execute must be ESCALATE"
    assert rule_map.get(("shell", "run")) == "ESCALATE", "shell.run must be ESCALATE"
    assert rule_map.get(("database", "delete")) == "ESCALATE", "database.delete must be ESCALATE"
    assert rule_map.get(("file", "delete")) == "ESCALATE", "file.delete must be ESCALATE"
    assert rule_map.get(("agent", "deploy")) == "ESCALATE", "agent.deploy must be ESCALATE"
    assert rule_map.get(("credential", "read")) == "ESCALATE", "credential.read must be ESCALATE"


def test_system_default_rules_have_required_fields():
    """Every rule dict must have the fields _apply_tenant_rules expects."""
    from edon_gateway.policy.defaults import SYSTEM_DEFAULT_RULES

    for rule in SYSTEM_DEFAULT_RULES:
        assert "name" in rule, f"Rule missing 'name': {rule}"
        assert "action" in rule, f"Rule missing 'action': {rule}"
        assert rule["action"] in ("BLOCK", "ALLOW", "ESCALATE"), (
            f"Invalid action '{rule['action']}' in rule '{rule['name']}'"
        )
        assert rule.get("enabled") is True, f"Rule '{rule['name']}' must be enabled=True"


# ── Preset seeding ─────────────────────────────────────────────────────────────


def test_seed_default_preset_sets_ops_commander(client: TestClient):
    """seed_default_preset sets ops_commander when no preset is configured."""
    from edon_gateway.policy.defaults import seed_default_preset
    from edon_gateway.persistence import get_db

    db = get_db()
    try:
        with db._get_connection() as conn:
            conn.execute("DELETE FROM active_policy_preset WHERE id = 1")
            conn.commit()
    except Exception:
        pytest.skip("Cannot clear preset — skipping")

    result = seed_default_preset(db)
    assert result is True
    preset = db.get_active_policy_preset()
    assert preset is not None
    assert preset["preset_name"] == "ops_commander"


def test_seed_default_preset_noop_when_preset_exists(client: TestClient):
    """seed_default_preset is a no-op if a preset is already configured."""
    from edon_gateway.policy.defaults import seed_default_preset
    from edon_gateway.persistence import get_db

    db = get_db()
    db.set_active_policy_preset("casual_user", applied_by="test")
    result = seed_default_preset(db)
    assert result is False
    preset = db.get_active_policy_preset()
    assert preset is not None
    assert preset["preset_name"] == "casual_user"


# ── Enforcement via HTTP ───────────────────────────────────────────────────────


def test_database_drop_blocked_by_default(client: TestClient):
    """database.drop must return BLOCK via the system default rules."""
    resp = client.post("/v1/action", json=_action("database.drop"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "BLOCK", (
        f"database.drop should be BLOCK but got {data['decision']}: "
        f"{data.get('decision_reason')}"
    )


def test_database_truncate_blocked_by_default(client: TestClient):
    """database.truncate must return BLOCK via the system default rules."""
    resp = client.post("/v1/action", json=_action("database.truncate"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "BLOCK", (
        f"database.truncate should be BLOCK but got {data['decision']}: "
        f"{data.get('decision_reason')}"
    )


def test_shell_execute_escalated_by_default(client: TestClient):
    """shell.execute must return HUMAN_REQUIRED via the system default rules."""
    resp = client.post("/v1/action", json=_action("shell.execute", {"command": "ls -la"}))
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "HUMAN_REQUIRED", (
        f"shell.execute should be HUMAN_REQUIRED but got {data['decision']}: "
        f"{data.get('decision_reason')}"
    )


def test_credential_read_not_allowed_by_default(client: TestClient):
    """credential.read must never be silently ALLOW'd — BLOCK or HUMAN_REQUIRED both satisfy this."""
    resp = client.post("/v1/action", json=_action("credential.read", {"name": "api_key"}))
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] in ("BLOCK", "HUMAN_REQUIRED"), (
        f"credential.read must not be ALLOW by default; got {data['decision']}: "
        f"{data.get('decision_reason')}"
    )


def test_file_delete_escalated_by_default(client: TestClient):
    """file.delete must return HUMAN_REQUIRED via the system default rules."""
    resp = client.post("/v1/action", json=_action("file.delete", {"path": "/tmp/report.csv"}))
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "HUMAN_REQUIRED", (
        f"file.delete should be HUMAN_REQUIRED but got {data['decision']}: "
        f"{data.get('decision_reason')}"
    )


# ── Tenant override ────────────────────────────────────────────────────────────


def test_tenant_allow_overrides_system_block():
    """A higher-priority tenant ALLOW rule must shadow the system BLOCK for database.drop."""
    from edon_gateway.policy.defaults import SYSTEM_DEFAULT_RULES
    from edon_gateway.governor import EDONGovernor
    from edon_gateway.schemas import Action, Tool, IntentContract, RiskLevel, ActionSource

    governor = EDONGovernor()
    action = Action(
        tool=Tool.DATABASE,
        op="drop",
        params={"table": "users"},
        requested_at=datetime.now(UTC),
        source=ActionSource.AGENT,
        tags=[],
    )
    intent = IntentContract(
        objective="Database maintenance",
        scope={"database": ["drop", "truncate"]},
        constraints={},
        risk_level=RiskLevel.HIGH,
        approved_by_user=True,
    )
    tenant_allow_rule = {
        "id": "tenant-override-allow-drop",
        "name": "allow database.drop for migration",
        "condition_tool": "database",
        "condition_op": "drop",
        "action": "ALLOW",
        "enabled": True,
        "priority": 9999,
    }
    # Tenant rule is first (higher priority); system rules follow
    merged = [tenant_allow_rule] + SYSTEM_DEFAULT_RULES
    decision = governor.evaluate(action, intent, context={}, tenant_rules=merged)
    assert decision.verdict.value == "ALLOW", (
        f"Tenant ALLOW rule should override system BLOCK; got {decision.verdict}: "
        f"{decision.explanation}"
    )
