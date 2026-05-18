"""
Multitenant isolation tests.

Verifies that no state bleeds across tenant boundaries for:
  - Audit records
  - Kill switch state
  - Agent stats
  - Policy rules

These tests use an in-memory SQLite DB — no gateway process needed.
"""

import pytest
from datetime import datetime, UTC


@pytest.fixture
def db(tmp_path):
    from edon_gateway.persistence.database import Database
    return Database(tmp_path / "isolation_test.db")


# ── Fixtures ──────────────────────────────────────────────────────────────────

_ACTION_A = {
    "id": "act-a-1",
    "requested_at": "2026-01-01T00:00:00Z",
    "tool": "email",
    "op": "send",
    "params": {"to": "a@example.com"},
    "source": "agent",
    "estimated_risk": "low",
    "computed_risk": None,
}
_ACTION_B = {**_ACTION_A, "id": "act-b-1", "tool": "file", "op": "read"}
_DECISION = {"verdict": "ALLOW", "reason_code": "OK", "explanation": "", "policy_version": "1.0"}


# ── Audit isolation ───────────────────────────────────────────────────────────

class TestAuditIsolation:
    def test_events_scoped_to_tenant(self, db):
        db.save_audit_event(
            action=_ACTION_A, decision=_DECISION,
            intent_id=None, agent_id="agent-alpha",
            context={}, customer_id="tenant-alpha",
        )
        db.save_audit_event(
            action=_ACTION_B, decision=_DECISION,
            intent_id=None, agent_id="agent-beta",
            context={}, customer_id="tenant-beta",
        )

        events_alpha = db.query_audit_events(customer_id="tenant-alpha", limit=100)
        events_beta = db.query_audit_events(customer_id="tenant-beta", limit=100)

        # query_audit_events filters at DB level; verify count and agent_id
        assert len(events_alpha) == 1, f"Expected 1 event for tenant-alpha, got {len(events_alpha)}"
        assert len(events_beta) == 1, f"Expected 1 event for tenant-beta, got {len(events_beta)}"
        assert events_alpha[0]["agent_id"] == "agent-alpha", "tenant-alpha returned wrong agent"
        assert events_beta[0]["agent_id"] == "agent-beta", "tenant-beta returned wrong agent"

    def test_no_cross_tenant_bleed_on_agent_filter(self, db):
        db.save_audit_event(
            action=_ACTION_A, decision=_DECISION,
            intent_id=None, agent_id="shared-agent-id",
            context={}, customer_id="tenant-alpha",
        )
        db.save_audit_event(
            action={**_ACTION_B, "id": "act-b-2"}, decision=_DECISION,
            intent_id=None, agent_id="shared-agent-id",
            context={}, customer_id="tenant-beta",
        )

        # Same agent_id in two tenants — customer_id filter must scope correctly
        events = db.query_audit_events(customer_id="tenant-alpha", limit=100)
        assert len(events) == 1, \
            f"Expected 1 event for tenant-alpha (not both tenants), got {len(events)}"


# ── Kill switch isolation ─────────────────────────────────────────────────────

class TestKillSwitchIsolation:
    def test_activate_does_not_affect_other_tenant(self, db):
        db.set_kill_switch("tenant-alpha", {
            "active": True,
            "tenant_id": "tenant-alpha",
            "reason": "test",
            "activated_by": "test",
            "activated_at": datetime.now(UTC).isoformat(),
        })

        state_beta = db.get_kill_switch("tenant-beta")
        assert state_beta.get("active") is False, \
            "Activating kill switch for tenant-alpha affected tenant-beta"

    def test_deactivate_scoped_to_tenant(self, db):
        for tid in ("tenant-alpha", "tenant-beta"):
            db.set_kill_switch(tid, {
                "active": True, "tenant_id": tid,
                "reason": "test", "activated_by": "test",
                "activated_at": datetime.now(UTC).isoformat(),
            })

        db.set_kill_switch("tenant-alpha", {
            "active": False, "tenant_id": "tenant-alpha",
            "reason": "test", "activated_by": "test",
            "activated_at": datetime.now(UTC).isoformat(),
        })

        state_beta = db.get_kill_switch("tenant-beta")
        assert state_beta.get("active") is True, \
            "Deactivating tenant-alpha kill switch changed tenant-beta state"

    def test_kill_switch_round_trips_correctly(self, db):
        state_in = {
            "active": True,
            "tenant_id": "tenant-gamma",
            "reason": "security incident",
            "activated_by": "ops-team",
            "activated_at": "2026-01-01T12:00:00Z",
            "history": [{"event": "activated", "at": "2026-01-01T12:00:00Z", "by": "ops-team", "reason": "test"}],
        }
        db.set_kill_switch("tenant-gamma", state_in)
        state_out = db.get_kill_switch("tenant-gamma")

        assert state_out["active"] is True
        assert state_out["reason"] == "security incident"
        assert state_out["activated_by"] == "ops-team"
        assert len(state_out.get("history", [])) == 1


# ── Agent stats isolation ─────────────────────────────────────────────────────

class TestAgentStatsIsolation:
    def test_agent_count_scoped_to_tenant(self, db):
        db.register_agent("tenant-alpha", "agent-shared-id")
        db.register_agent("tenant-beta", "agent-shared-id")

        count_alpha = db.get_agent_count("tenant-alpha")
        count_beta = db.get_agent_count("tenant-beta")

        # Each tenant sees only their own agent — same agent_id in two tenants = 2 rows
        assert count_alpha == 1, f"Expected 1 agent for tenant-alpha, got {count_alpha}"
        assert count_beta == 1, f"Expected 1 agent for tenant-beta, got {count_beta}"

    def test_tenant_agents_list_scoped(self, db):
        db.register_agent("tenant-alpha", "alpha-agent-1")
        db.register_agent("tenant-alpha", "alpha-agent-2")
        db.register_agent("tenant-beta", "beta-agent-1")

        agents_alpha = db.get_tenant_agents("tenant-alpha")
        agents_beta = db.get_tenant_agents("tenant-beta")

        alpha_ids = {a["agent_id"] for a in agents_alpha}
        beta_ids = {a["agent_id"] for a in agents_beta}

        assert "alpha-agent-1" in alpha_ids
        assert "alpha-agent-2" in alpha_ids
        assert "beta-agent-1" not in alpha_ids
        assert "beta-agent-1" in beta_ids
        assert "alpha-agent-1" not in beta_ids


# ── Policy rule isolation ─────────────────────────────────────────────────────

class TestPolicyRuleIsolation:
    def test_rules_scoped_to_tenant(self, db):
        # policy_rules has FK to tenants — create users + tenants first
        db.create_user("user-alpha", "alpha@test.com", "test", "alpha-sub")
        db.create_tenant("tenant-alpha", "user-alpha")
        db.create_user("user-beta", "beta@test.com", "test", "beta-sub")
        db.create_tenant("tenant-beta", "user-beta")

        db.create_policy_rule(
            tenant_id="tenant-alpha",
            action="BLOCK",
            condition_tool="email",
            condition_op="send",
            name="Block email for alpha",
            description="",
        )
        db.create_policy_rule(
            tenant_id="tenant-beta",
            action="ALLOW",
            condition_tool="email",
            condition_op="send",
            name="Allow email for beta",
            description="",
        )

        rules_alpha = db.get_policy_rules("tenant-alpha", enabled_only=False)
        rules_beta = db.get_policy_rules("tenant-beta", enabled_only=False)

        alpha_names = {r["name"] for r in rules_alpha}
        beta_names = {r["name"] for r in rules_beta}

        assert "Block email for alpha" in alpha_names
        assert "Allow email for beta" not in alpha_names
        assert "Allow email for beta" in beta_names
        assert "Block email for alpha" not in beta_names
