"""Initial schema — captures all tables existing at Alembic adoption.

Revision ID: 001
Revises: (none — initial baseline)
Create Date: 2026-04-02

This migration is a BASELINE. It represents the schema that already exists
in production. Running upgrade() on a fresh database creates the full schema.
Running it against an existing database is safe — all CREATE TABLE statements
use IF NOT EXISTS.
"""
from __future__ import annotations

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS intents (
            intent_id TEXT PRIMARY KEY,
            objective TEXT NOT NULL,
            scope TEXT NOT NULL,
            constraints TEXT NOT NULL,
            risk_level TEXT NOT NULL,
            approved_by_user INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action_id TEXT NOT NULL,
            action_tool TEXT NOT NULL,
            action_op TEXT NOT NULL,
            action_params TEXT NOT NULL,
            action_source TEXT NOT NULL,
            action_estimated_risk TEXT NOT NULL,
            action_computed_risk TEXT,
            decision_verdict TEXT NOT NULL,
            decision_reason_code TEXT NOT NULL,
            decision_explanation TEXT NOT NULL,
            decision_policy_version TEXT NOT NULL,
            policy_rule_id TEXT,
            action_summary TEXT,
            stated_intent TEXT,
            user_message TEXT,
            intent_id TEXT,
            agent_id TEXT,
            context TEXT,
            created_at TEXT NOT NULL,
            chain_hash TEXT,
            chain_sig TEXT,
            customer_id TEXT,
            anomaly_score REAL,
            human_override INTEGER NOT NULL DEFAULT 0,
            human_override_actor_id TEXT,
            human_override_reason TEXT,
            processing_latency_ms REAL,
            edge_node_id TEXT,
            is_payload_encrypted INTEGER NOT NULL DEFAULT 0
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_agent_id ON audit_events(agent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_intent_id ON audit_events(intent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_verdict ON audit_events(decision_verdict)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_agent_timestamp ON audit_events(agent_id, timestamp)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_customer_timestamp ON audit_events(customer_id, timestamp)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_chain ON audit_events(chain_hash)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS decisions (
            decision_id TEXT PRIMARY KEY,
            action_id TEXT NOT NULL,
            verdict TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            explanation TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            intent_id TEXT,
            agent_id TEXT,
            created_at TEXT NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS policy_versions (
            version TEXT PRIMARY KEY,
            description TEXT,
            created_at TEXT NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS active_policy_preset (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            preset_name TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            applied_by TEXT,
            UNIQUE(id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            auth_provider TEXT NOT NULL DEFAULT 'clerk',
            auth_subject TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(auth_provider, auth_subject)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_auth_provider ON users(auth_provider, auth_subject)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'trial',
            plan TEXT NOT NULL DEFAULT 'free',
            mag_enabled INTEGER NOT NULL DEFAULT 0,
            stripe_customer_id TEXT UNIQUE,
            stripe_subscription_id TEXT UNIQUE,
            current_period_start TEXT,
            current_period_end TEXT,
            cancel_at_period_end INTEGER DEFAULT 0,
            default_intent_id TEXT,
            retention_days INTEGER NOT NULL DEFAULT 365,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_tenants_user_id ON tenants(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tenants_stripe_customer ON tenants(stripe_customer_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tenants_stripe_subscription ON tenants(stripe_subscription_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants(status)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            key_hash TEXT NOT NULL UNIQUE,
            name TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL,
            last_used_at TEXT,
            expires_at TEXT,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_tenant ON api_keys(tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_status ON api_keys(status)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS channel_tokens (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            external_user_id TEXT,
            token_hash TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            last_used_at TEXT,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS connect_codes (
            code TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            channel TEXT NOT NULL DEFAULT 'telegram',
            expires_at TEXT NOT NULL,
            used_at TEXT,
            used_by TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS connect_service_codes (
            code TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            service TEXT NOT NULL,
            chat_id TEXT,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            created_at TEXT NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS channel_bindings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            external_user_id TEXT NOT NULL,
            external_chat_id TEXT,
            username TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(channel, external_user_id),
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS tenant_alert_preferences (
            tenant_id TEXT NOT NULL PRIMARY KEY,
            preferences TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS tenant_usage (
            tenant_id TEXT NOT NULL,
            period_start TEXT NOT NULL,
            requests_count INTEGER DEFAULT 0,
            PRIMARY KEY (tenant_id, period_start),
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS counters (
            key TEXT PRIMARY KEY,
            value INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS credentials (
            credential_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            tenant_id TEXT,
            credential_type TEXT NOT NULL,
            credential_data TEXT NOT NULL,
            encrypted INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_used_at TEXT,
            last_error TEXT,
            PRIMARY KEY (credential_id, tenant_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_credentials_tool ON credentials(tool_name)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS token_agent_bindings (
            token_hash TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_used_at TEXT NOT NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_token_bindings_agent ON token_agent_bindings(agent_id)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS tenant_agents (
            tenant_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            first_seen TEXT NOT NULL,
            display_name TEXT,
            PRIMARY KEY (tenant_id, agent_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_tenant_agents_tenant ON tenant_agents(tenant_id)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            customer_id TEXT PRIMARY KEY,
            customer_name TEXT,
            email TEXT
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS preference_memory (
            tenant_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, key),
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_preference_memory_tenant ON preference_memory(tenant_id)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS episodic_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            episode_id TEXT NOT NULL,
            task_summary TEXT NOT NULL,
            outcome TEXT,
            tool TEXT,
            op TEXT,
            context TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_episodic_memory_tenant_created ON episodic_memory(tenant_id, created_at)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS policy_rules (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            condition_tool TEXT,
            condition_op TEXT,
            condition_risk_level TEXT,
            condition_tags TEXT,
            action TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1,
            rule_code TEXT,
            protected INTEGER NOT NULL DEFAULT 0,
            regulation TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_policy_rules_tenant ON policy_rules(tenant_id, enabled, priority DESC)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            agent_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            name TEXT NOT NULL,
            agent_type TEXT NOT NULL DEFAULT 'software',
            description TEXT,
            capabilities TEXT NOT NULL DEFAULT '[]',
            policy_pack TEXT,
            mag_enabled INTEGER NOT NULL DEFAULT 0,
            cav_enabled INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'active',
            registered_at TEXT NOT NULL,
            last_seen_at TEXT,
            total_actions INTEGER NOT NULL DEFAULT 0,
            total_allowed INTEGER NOT NULL DEFAULT 0,
            total_blocked INTEGER NOT NULL DEFAULT 0,
            total_escalated INTEGER NOT NULL DEFAULT 0,
            metadata TEXT DEFAULT '{}',
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_agents_tenant ON agents(tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_behavioral_windows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            actions_per_min REAL,
            error_rate REAL,
            tool_switch_rate REAL,
            risk_trend TEXT,
            retry_count INTEGER,
            session_duration_mins REAL,
            cav_score REAL,
            cav_state TEXT,
            raw_window TEXT,
            created_at TEXT NOT NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_behavioral_agent ON agent_behavioral_windows(agent_id)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS sandbox_audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action_id TEXT NOT NULL,
            action_tool TEXT NOT NULL,
            action_op TEXT NOT NULL,
            action_params TEXT NOT NULL,
            action_source TEXT NOT NULL,
            action_estimated_risk TEXT NOT NULL,
            action_computed_risk TEXT,
            decision_verdict TEXT NOT NULL,
            decision_reason_code TEXT NOT NULL,
            decision_explanation TEXT NOT NULL,
            decision_policy_version TEXT NOT NULL DEFAULT '1.0.0',
            policy_rule_id TEXT,
            action_summary TEXT,
            stated_intent TEXT,
            agent_id TEXT,
            customer_id TEXT,
            context TEXT,
            anomaly_score REAL,
            processing_latency_ms REAL,
            created_at TEXT NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS alert_rules (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            name TEXT NOT NULL,
            metric TEXT NOT NULL,
            operator TEXT NOT NULL,
            threshold REAL NOT NULL,
            window_minutes INTEGER NOT NULL DEFAULT 60,
            webhook_url TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'warning',
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_alert_rules_tenant ON alert_rules(tenant_id, enabled)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS alert_incidents (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            rule_name TEXT NOT NULL,
            severity TEXT NOT NULL,
            metric TEXT NOT NULL,
            threshold REAL NOT NULL,
            observed_value REAL NOT NULL,
            window_minutes INTEGER NOT NULL,
            webhook_url TEXT NOT NULL,
            webhook_status TEXT NOT NULL DEFAULT 'pending',
            webhook_attempts INTEGER NOT NULL DEFAULT 0,
            payload TEXT,
            triggered_at TEXT NOT NULL,
            resolved_at TEXT,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS policy_changes (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            changed_by TEXT,
            change_type TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT,
            entity_name TEXT,
            diff_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_policy_changes_tenant ON policy_changes(tenant_id, created_at)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS dsar_requests (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            request_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            requested_at TEXT NOT NULL,
            completed_at TEXT,
            notes TEXT,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS purge_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            purged_count INTEGER NOT NULL,
            retention_days INTEGER NOT NULL,
            purged_before TEXT NOT NULL,
            purged_at TEXT NOT NULL,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            device_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            vendor_id TEXT,
            device_type TEXT NOT NULL,
            name TEXT NOT NULL,
            serial_number TEXT,
            make TEXT,
            model TEXT,
            department TEXT,
            location TEXT,
            status TEXT NOT NULL DEFAULT 'available',
            current_agent_id TEXT,
            current_session_id TEXT,
            session_started_at TEXT,
            requires_supervision INTEGER NOT NULL DEFAULT 0,
            metadata TEXT NOT NULL DEFAULT '{}',
            registered_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_device_bindings (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            bound_at TEXT NOT NULL,
            unbound_at TEXT,
            status TEXT NOT NULL DEFAULT 'active'
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS device_sessions (
            session_id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            metadata TEXT DEFAULT '{}'
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """)
    # Swarm tables
    op.execute("""
        CREATE TABLE IF NOT EXISTS swarms (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            name TEXT NOT NULL,
            policy_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS swarm_members (
            swarm_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            joined_at TEXT NOT NULL,
            PRIMARY KEY (swarm_id, agent_id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS swarm_action_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            swarm_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            verdict TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            amount REAL
        )
    """)


def downgrade() -> None:
    # Drop in reverse dependency order
    for table in [
        "swarm_action_log", "swarm_members", "swarms",
        "schema_version", "device_sessions", "agent_device_bindings", "devices",
        "purge_log", "dsar_requests", "policy_changes",
        "alert_incidents", "alert_rules", "sandbox_audit_events",
        "agent_behavioral_windows", "agents", "policy_rules",
        "episodic_memory", "preference_memory", "customers",
        "tenant_agents", "token_agent_bindings", "credentials",
        "counters", "tenant_usage", "tenant_alert_preferences",
        "channel_bindings", "connect_service_codes", "connect_codes",
        "channel_tokens", "api_keys", "tenants", "users",
        "active_policy_preset", "policy_versions", "decisions",
        "audit_events", "intents",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table}")
