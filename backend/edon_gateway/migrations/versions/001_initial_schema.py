"""Initial schema — core EDON Gateway tables.

Revision ID: 001
Revises: (none)
Create Date: 2026-05-06

Creates:
    audit_events, policy_rules, escalations, agents, tenants, api_keys, intents

Column type strategy:
    - TEXT for all long strings (PostgreSQL-native; compatible with SQLite)
    - JSONB for structured JSON columns on PostgreSQL; falls back to TEXT on SQLite
    - TIMESTAMP WITH TIME ZONE for all datetimes on PostgreSQL; DATETIME on SQLite
    - customer_id TEXT NOT NULL on every table for tenant isolation
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# ---------------------------------------------------------------------------
# Alembic metadata
# ---------------------------------------------------------------------------
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_type() -> sa.types.TypeEngine:
    """JSONB on PostgreSQL, TEXT on SQLite/other dialects."""
    return postgresql.JSONB().with_variant(sa.Text, "sqlite").with_variant(sa.Text, "default")


def _timestamp_type() -> sa.types.TypeEngine:
    """TIMESTAMP WITH TIME ZONE on PostgreSQL, DATETIME on SQLite/other dialects."""
    return sa.TIMESTAMP(timezone=True).with_variant(sa.DateTime, "sqlite")


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    # ------------------------------------------------------------------
    # tenants
    # ------------------------------------------------------------------
    op.create_table(
        "tenants",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("customer_id", sa.Text, nullable=False),
        sa.Column("user_id", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="trial"),
        sa.Column("plan", sa.Text, nullable=False, server_default="free"),
        sa.Column("mag_enabled", sa.Integer, nullable=False, server_default="0"),
        sa.Column("stripe_customer_id", sa.Text, nullable=True),
        sa.Column("stripe_subscription_id", sa.Text, nullable=True),
        sa.Column("current_period_start", _timestamp_type(), nullable=True),
        sa.Column("current_period_end", _timestamp_type(), nullable=True),
        sa.Column("cancel_at_period_end", sa.Integer, nullable=True, server_default="0"),
        sa.Column("created_at", _timestamp_type(), nullable=False),
        sa.Column("updated_at", _timestamp_type(), nullable=False),
    )
    op.create_index("ix_tenants_customer_id", "tenants", ["customer_id"])
    op.create_index("ix_tenants_status", "tenants", ["status"])

    # ------------------------------------------------------------------
    # api_keys
    # ------------------------------------------------------------------
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("customer_id", sa.Text, nullable=False),
        sa.Column("key_hash", sa.Text, nullable=False, unique=True),
        sa.Column("name", sa.Text, nullable=True),
        sa.Column("created_at", _timestamp_type(), nullable=False),
        sa.Column("last_used_at", _timestamp_type(), nullable=True),
        sa.Column("enabled", sa.Integer, nullable=False, server_default="1"),
    )
    op.create_index("ix_api_keys_customer_id", "api_keys", ["customer_id"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])

    # ------------------------------------------------------------------
    # agents
    # ------------------------------------------------------------------
    op.create_table(
        "agents",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("customer_id", sa.Text, nullable=False),
        sa.Column("agent_id", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=True),
        sa.Column("department", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.Column("total_actions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_allowed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_blocked", sa.Integer, nullable=False, server_default="0"),
        sa.Column("registered_at", _timestamp_type(), nullable=False),
    )
    op.create_index("ix_agents_customer_id", "agents", ["customer_id"])
    op.create_index("ix_agents_agent_id", "agents", ["agent_id"])

    # ------------------------------------------------------------------
    # intents
    # ------------------------------------------------------------------
    op.create_table(
        "intents",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("customer_id", sa.Text, nullable=False),
        sa.Column("agent_id", sa.Text, nullable=True),
        sa.Column("objective", sa.Text, nullable=False),
        sa.Column("scope", _json_type(), nullable=True),
        sa.Column("constraints", _json_type(), nullable=True),
        sa.Column("risk_level", sa.Text, nullable=True),
        sa.Column("approved_by_user", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", _timestamp_type(), nullable=False),
        sa.Column("updated_at", _timestamp_type(), nullable=True),
    )
    op.create_index("ix_intents_customer_id", "intents", ["customer_id"])

    # ------------------------------------------------------------------
    # policy_rules
    # ------------------------------------------------------------------
    op.create_table(
        "policy_rules",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("customer_id", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("condition_tool", sa.Text, nullable=True),
        sa.Column("condition_op", sa.Text, nullable=True),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("enabled", sa.Integer, nullable=False, server_default="1"),
        sa.Column("failure_mode", sa.Text, nullable=True),
        sa.Column("protected", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", _timestamp_type(), nullable=False),
    )
    op.create_index("ix_policy_rules_customer_id", "policy_rules", ["customer_id"])
    op.create_index("ix_policy_rules_enabled", "policy_rules", ["enabled"])

    # ------------------------------------------------------------------
    # audit_events
    # ------------------------------------------------------------------
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("customer_id", sa.Text, nullable=False),
        sa.Column("agent_id", sa.Text, nullable=True),
        sa.Column("action_tool", sa.Text, nullable=True),
        sa.Column("action_op", sa.Text, nullable=True),
        sa.Column("action_payload", _json_type(), nullable=True),
        sa.Column("decision_verdict", sa.Text, nullable=False),
        sa.Column("decision_reason_code", sa.Text, nullable=True),
        sa.Column("decision_explanation", sa.Text, nullable=True),
        sa.Column("chain_hash", sa.Text, nullable=True),
        sa.Column("timestamp", _timestamp_type(), nullable=False),
        sa.Column("anomaly_score", sa.Float, nullable=True),
    )
    op.create_index("ix_audit_events_customer_id", "audit_events", ["customer_id"])
    op.create_index("ix_audit_events_timestamp", "audit_events", ["timestamp"])
    op.create_index("ix_audit_events_agent_id", "audit_events", ["agent_id"])
    op.create_index("ix_audit_events_verdict", "audit_events", ["decision_verdict"])

    # ------------------------------------------------------------------
    # escalations
    # ------------------------------------------------------------------
    op.create_table(
        "escalations",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("customer_id", sa.Text, nullable=False),
        sa.Column("decision_id", sa.Text, nullable=True),
        sa.Column("agent_id", sa.Text, nullable=True),
        sa.Column("action_type", sa.Text, nullable=True),
        sa.Column("action_payload", _json_type(), nullable=True),
        sa.Column("escalation_question", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("created_at", _timestamp_type(), nullable=False),
        sa.Column("resolved_at", _timestamp_type(), nullable=True),
        sa.Column("resolved_by", sa.Text, nullable=True),
        sa.Column("resolution", sa.Text, nullable=True),
        sa.Column("resolution_note", sa.Text, nullable=True),
    )
    op.create_index("ix_escalations_customer_id", "escalations", ["customer_id"])
    op.create_index("ix_escalations_status", "escalations", ["status"])
    op.create_index("ix_escalations_agent_id", "escalations", ["agent_id"])


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    op.drop_table("escalations")
    op.drop_table("audit_events")
    op.drop_table("policy_rules")
    op.drop_table("intents")
    op.drop_table("agents")
    op.drop_table("api_keys")
    op.drop_table("tenants")
