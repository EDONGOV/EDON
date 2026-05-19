"""SQLite database for EDON Gateway persistence."""

import os
import sqlite3
import json
import hashlib
import hmac
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, UTC
from contextlib import contextmanager


def get_db_url() -> str:
    """Return the DB URL from EDON_DB_URL env var, defaulting to SQLite.

    Used by Alembic migrations and any code that needs the canonical DB URL.
    Does NOT change the existing runtime connection logic in this module.
    """
    url = os.getenv("EDON_DB_URL", "").strip()
    if url:
        return url
    db_path = os.getenv("EDON_DATABASE_PATH", "edon_gateway.db").strip()
    return f"sqlite:///{db_path}"


def is_postgresql() -> bool:
    """Return True when the configured DB URL points to PostgreSQL."""
    return get_db_url().startswith("postgresql")


def _resolve_db_path() -> Path:
    """Resolve DB file path from EDON_DB_URL (sqlite:///path) or EDON_DATABASE_PATH."""
    url = os.getenv("EDON_DB_URL", "").strip()
    if url and url.startswith("sqlite:///"):
        path = url.replace("sqlite:///", "", 1)
        return Path(path)
    path = os.getenv("EDON_DATABASE_PATH", "edon_gateway.db")
    return Path(path)


class Database:
    """SQLite database for storing intents, audit events, and decisions."""
    
    def __init__(self, db_path: Path = Path("edon_gateway.db")):
        """Initialize database.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
    
    def _init_schema(self):
        """Initialize database schema."""
        from .schema_version import check_schema_version, set_schema_version, SCHEMA_VERSION
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Intents table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS intents (
                    intent_id TEXT PRIMARY KEY,
                    objective TEXT NOT NULL,
                    scope TEXT NOT NULL,  -- JSON
                    constraints TEXT NOT NULL,  -- JSON
                    risk_level TEXT NOT NULL,
                    approved_by_user INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            # Audit events table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    action_id TEXT NOT NULL,
                    action_tool TEXT NOT NULL,
                    action_op TEXT NOT NULL,
                    action_params TEXT NOT NULL,  -- JSON
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
                    context TEXT,  -- JSON
                    created_at TEXT NOT NULL
                )
            """)
            
            # Decisions table (for quick lookup)
            cursor.execute("""
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
            
            # Policy versions table (for tracking policy changes)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS policy_versions (
                    version TEXT PRIMARY KEY,
                    description TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            
            # Active policy preset table (stores currently active preset)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS active_policy_preset (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    preset_name TEXT NOT NULL,
                    applied_at TEXT NOT NULL,
                    applied_by TEXT,
                    UNIQUE(id)
                )
            """)
            
            # Users table (internal user IDs - auth provider agnostic)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,  -- Internal UUID (never changes)
                    email TEXT NOT NULL UNIQUE,
                    auth_provider TEXT NOT NULL DEFAULT 'clerk',  -- 'clerk', 'supabase', etc.
                    auth_subject TEXT NOT NULL,  -- Provider's user ID (clerk_user_id, supabase_user_id)
                    role TEXT NOT NULL DEFAULT 'user',  -- 'user', 'admin', etc.
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(auth_provider, auth_subject)  -- One user per auth provider ID
                )
            """)
            
            # Index for auth provider lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_auth_provider 
                ON users(auth_provider, auth_subject)
            """)
            
            # Tenants table (multi-tenant billing) - now references user_id
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tenants (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,  -- References users.id (internal UUID)
                    status TEXT NOT NULL DEFAULT 'trial',  -- trial, active, past_due, canceled, inactive
                    plan TEXT NOT NULL DEFAULT 'free',  -- free, starter, pro, enterprise
                    mag_enabled INTEGER NOT NULL DEFAULT 0,  -- 1 = MAG enforcement enabled
                    stripe_customer_id TEXT UNIQUE,
                    stripe_subscription_id TEXT UNIQUE,
                    current_period_start TEXT,
                    current_period_end TEXT,
                    cancel_at_period_end INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
            
            # Index for Stripe lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_tenants_user_id 
                ON tenants(user_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_tenants_stripe_customer 
                ON tenants(stripe_customer_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_tenants_stripe_subscription 
                ON tenants(stripe_subscription_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_tenants_status 
                ON tenants(status)
            """)
            
            # API Keys table (tenant-scoped authentication)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    key_hash TEXT NOT NULL UNIQUE,  -- SHA256 hash of the actual key
                    name TEXT,  -- User-friendly name for the key
                    status TEXT NOT NULL DEFAULT 'active',  -- active, revoked
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
                )
            """)
            
            # Indexes for API key lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_keys_tenant 
                ON api_keys(tenant_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_keys_hash 
                ON api_keys(key_hash)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_keys_status
                ON api_keys(status)
            """)

            # Migration: add expires_at to api_keys if not present
            try:
                cursor.execute("ALTER TABLE api_keys ADD COLUMN expires_at TEXT")
                conn.commit()
            except Exception:
                pass  # Column already exists

            # Channel tokens (e.g., Telegram/SMS)
            cursor.execute("""
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
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_channel_tokens_tenant 
                ON channel_tokens(tenant_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_channel_tokens_hash 
                ON channel_tokens(token_hash)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_channel_tokens_status 
                ON channel_tokens(status)
            """)

            # Connect codes (short-lived binding codes)
            cursor.execute("""
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
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_connect_codes_tenant 
                ON connect_codes(tenant_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_connect_codes_expires 
                ON connect_codes(expires_at)
            """)

            # Connect service codes (one-time links for Gmail/Calendar/Brave/GitHub/ElevenLabs)
            cursor.execute("""
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
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_connect_service_codes_tenant 
                ON connect_service_codes(tenant_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_connect_service_codes_expires 
                ON connect_service_codes(expires_at)
            """)

            # Channel bindings (telegram user/chat -> tenant)
            cursor.execute("""
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
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_channel_bindings_tenant 
                ON channel_bindings(tenant_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_channel_bindings_user 
                ON channel_bindings(channel, external_user_id)
            """)

            # Tenant alert preferences (what to alert on: blocked, policy violation, drift, escalation)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tenant_alert_preferences (
                    tenant_id TEXT NOT NULL PRIMARY KEY,
                    preferences TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
                )
            """)
            
            # Tenant usage tracking (for plan limits)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tenant_usage (
                    tenant_id TEXT NOT NULL,
                    period_start TEXT NOT NULL,  -- YYYY-MM-DD format
                    requests_count INTEGER DEFAULT 0,
                    PRIMARY KEY (tenant_id, period_start),
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
                )
            """)
            
            # Counters table (for rate limiting and metrics)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS counters (
                    key TEXT PRIMARY KEY,
                    value INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            # Credentials table (for tool credentials)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS credentials (
                    credential_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    tenant_id TEXT,
                    credential_type TEXT NOT NULL,  -- e.g., "smtp", "api_key", "oauth"
                    credential_data TEXT NOT NULL,  -- JSON encrypted/encoded
                    encrypted INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_used_at TEXT,
                    last_error TEXT,
                    PRIMARY KEY (credential_id, tenant_id)
                )
            """)
            
            # Index for tool lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_credentials_tool 
                ON credentials(tool_name)
            """)
            
            # Token to agent_id binding table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS token_agent_bindings (
                    token_hash TEXT PRIMARY KEY,  -- SHA256 hash of token
                    agent_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT NOT NULL
                )
            """)
            
            # Index for agent lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_token_bindings_agent 
                ON token_agent_bindings(agent_id)
            """)
            
            # Indexes for performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp 
                ON audit_events(timestamp)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_agent_id 
                ON audit_events(agent_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_intent_id 
                ON audit_events(intent_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_verdict
                ON audit_events(decision_verdict)
            """)
            conn.commit()
            
            # Migration: Add default_intent_id to tenants table (if not exists)
            try:
                cursor.execute("ALTER TABLE tenants ADD COLUMN default_intent_id TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                pass

            # Migration: Add vertical to tenants table (healthcare, banking, general)
            try:
                cursor.execute("ALTER TABLE tenants ADD COLUMN vertical TEXT DEFAULT NULL")
                conn.commit()
            except sqlite3.OperationalError:
                pass

            # Migration: Add mag_enabled to tenants table (if not exists)
            try:
                cursor.execute("ALTER TABLE tenants ADD COLUMN mag_enabled INTEGER NOT NULL DEFAULT 0")
                conn.commit()
            except sqlite3.OperationalError:
                # Column already exists, ignore
                pass
            
            # Migration: Add tenant_id and last_error to credentials table (if not exists)
            try:
                cursor.execute("ALTER TABLE credentials ADD COLUMN tenant_id TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                # Column already exists, ignore
                pass
            
            try:
                cursor.execute("ALTER TABLE credentials ADD COLUMN last_error TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                # Column already exists, ignore
                pass

            # Audit trail v1.1: chain hash + pilot-ready fields (Tier 1)
            for col, typ in [
                ("chain_hash", "TEXT"),
                ("chain_sig", "TEXT"),
                ("customer_id", "TEXT"),
                ("anomaly_score", "REAL"),
                ("human_override", "INTEGER NOT NULL DEFAULT 0"),
                ("human_override_actor_id", "TEXT"),
                ("human_override_reason", "TEXT"),
                ("processing_latency_ms", "REAL"),
                ("edge_node_id", "TEXT"),
                ("request_hash", "TEXT"),
            ]:
                try:
                    cursor.execute(f"ALTER TABLE audit_events ADD COLUMN {col} {typ}")  # safe: schema-only
                    conn.commit()
                except sqlite3.OperationalError:
                    pass

            # Append-only enforcement: forbid UPDATE/DELETE on audit_events (Tier 1)
            cursor.execute("""
                SELECT name FROM sqlite_master WHERE type='trigger' AND name='audit_events_append_only_update'
            """)
            if cursor.fetchone() is None:
                cursor.execute("""
                    CREATE TRIGGER audit_events_append_only_update
                    BEFORE UPDATE ON audit_events
                    FOR EACH ROW BEGIN
                        SELECT RAISE(ABORT, 'audit_events is append-only: updates not allowed');
                    END
                """)
            cursor.execute("""
                SELECT name FROM sqlite_master WHERE type='trigger' AND name='audit_events_append_only_delete'
            """)
            if cursor.fetchone() is None:
                cursor.execute("""
                    CREATE TRIGGER audit_events_append_only_delete
                    BEFORE DELETE ON audit_events
                    FOR EACH ROW BEGIN
                        SELECT RAISE(ABORT, 'audit_events is append-only: deletes not allowed');
                    END
                """)
            conn.commit()

            # Migration: Add role column to api_keys (RBAC - Tier 1)
            try:
                cursor.execute("ALTER TABLE api_keys ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
                conn.commit()
            except sqlite3.OperationalError:
                pass
            # Normalize historical defaults for API keys that still use legacy 'agent' role
            try:
                cursor.execute("UPDATE api_keys SET role = 'user' WHERE role = 'agent'")
                conn.commit()
            except sqlite3.OperationalError:
                pass
            # Migration: Add is_sandbox column to api_keys
            try:
                cursor.execute("ALTER TABLE api_keys ADD COLUMN is_sandbox INTEGER NOT NULL DEFAULT 0")
                conn.commit()
            except sqlite3.OperationalError:
                pass

            # Pending live keys — temporary store for unclaimed live keys
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pending_live_keys (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    raw_key TEXT NOT NULL,
                    key_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
            """)
            conn.commit()

            # Migration: Add richer audit explainability fields
            for col, typ in [
                ("policy_rule_id", "TEXT"),
                ("action_summary", "TEXT"),
                ("stated_intent", "TEXT"),
                ("user_message", "TEXT"),
                ("chain_sig", "TEXT"),
            ]:
                try:
                    cursor.execute(f"ALTER TABLE audit_events ADD COLUMN {col} {typ}")  # safe: schema-only
                    conn.commit()
                except sqlite3.OperationalError:
                    pass

            # Migration: Add is_payload_encrypted flag to audit_events (encryption - Tier 1)
            try:
                cursor.execute("ALTER TABLE audit_events ADD COLUMN is_payload_encrypted INTEGER NOT NULL DEFAULT 0")
                conn.commit()
            except sqlite3.OperationalError:
                pass

            # Compound indexes for common multi-field queries (scale optimization)
            # Must be after migrations that add customer_id, chain_hash columns
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_agent_timestamp
                ON audit_events(agent_id, timestamp)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_customer_timestamp
                ON audit_events(customer_id, timestamp)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_chain
                ON audit_events(chain_hash)
            """)
            conn.commit()

            # tenant_agents table: tracks registered agent IDs per tenant for plan enforcement
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tenant_agents (
                    tenant_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    first_seen TEXT NOT NULL,
                    display_name TEXT,
                    PRIMARY KEY (tenant_id, agent_id)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_tenant_agents_tenant
                ON tenant_agents(tenant_id)
            """)
            conn.commit()
            # Migration: add display_name if table existed without it
            cursor.execute("PRAGMA table_info(tenant_agents)")
            columns = [row[1] for row in cursor.fetchall()]
            if "display_name" not in columns:
                cursor.execute("ALTER TABLE tenant_agents ADD COLUMN display_name TEXT")
                conn.commit()

            # Migration: customers table for backward-compat with RBAC tests
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    customer_id TEXT PRIMARY KEY,
                    customer_name TEXT,
                    email TEXT
                )
            """)
            # Trigger: INSERT INTO customers also creates minimal user + tenant records
            # so that api_keys FK constraints (tenant_id -> tenants.id) are satisfied.
            cursor.execute("""
                SELECT name FROM sqlite_master WHERE type='trigger'
                AND name='customers_sync_to_tenants'
            """)
            if cursor.fetchone() is None:
                cursor.execute("""
                    CREATE TRIGGER customers_sync_to_tenants
                    AFTER INSERT ON customers
                    FOR EACH ROW BEGIN
                        INSERT OR IGNORE INTO users
                            (id, email, auth_provider, auth_subject, role, created_at, updated_at)
                        VALUES (
                            NEW.customer_id,
                            COALESCE(NEW.email, NEW.customer_id || '@compat.local'),
                            'compat', NEW.customer_id, 'user',
                            datetime('now'), datetime('now')
                        );
                        INSERT OR IGNORE INTO tenants
                            (id, user_id, status, plan, created_at, updated_at)
                        VALUES (
                            NEW.customer_id, NEW.customer_id,
                            'active', 'free',
                            datetime('now'), datetime('now')
                        );
                    END
                """)
            conn.commit()

            # Memory: long-term preferences (KV per tenant)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS preference_memory (
                    tenant_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, key),
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_preference_memory_tenant 
                ON preference_memory(tenant_id)
            """)
            
            # Memory: episodic task memory (past tasks, outcomes, context)
            cursor.execute("""
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
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_episodic_memory_tenant_created
                ON episodic_memory(tenant_id, created_at)
            """)

            # Per-tenant custom policy rules
            cursor.execute("""
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
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_policy_rules_tenant
                ON policy_rules(tenant_id, enabled, priority DESC)
            """)

            conn.commit()

            # Agent registry (full metadata, CAV-enabled, per-tenant)
            cursor.execute("""
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
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_agents_tenant ON agents(tenant_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status)
            """)
            # Lazy migration: add department column if missing
            try:
                cursor.execute("ALTER TABLE agents ADD COLUMN department TEXT")
                conn.commit()
            except Exception:
                pass  # Column already exists

            # Behavioral CAV windows (rolling telemetry snapshots per agent)
            cursor.execute("""
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
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_behavioral_agent ON agent_behavioral_windows(agent_id)
            """)
            conn.commit()

            # Sandbox audit events (isolated from production; mutable — no append-only triggers)
            cursor.execute("""
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
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sandbox_audit_agent
                ON sandbox_audit_events(agent_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sandbox_audit_customer
                ON sandbox_audit_events(customer_id)
            """)
            conn.commit()

            # ── Compliance Feature Tables ───────────────────────────────────────────

            # Alert rules: anomaly threshold → webhook notification
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alert_rules (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    metric TEXT NOT NULL,        -- 'anomaly_score', 'block_rate', 'escalation_count'
                    operator TEXT NOT NULL,      -- 'gt', 'gte', 'lt', 'lte', 'eq'
                    threshold REAL NOT NULL,
                    window_minutes INTEGER NOT NULL DEFAULT 60,
                    webhook_url TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'warning',  -- 'info', 'warning', 'critical'
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_alert_rules_tenant
                ON alert_rules(tenant_id, enabled)
            """)

            # Alert incidents: fired alerts, webhook delivery status
            cursor.execute("""
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
                    webhook_status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'delivered', 'failed'
                    webhook_attempts INTEGER NOT NULL DEFAULT 0,
                    payload TEXT,               -- JSON snapshot sent to webhook
                    triggered_at TEXT NOT NULL,
                    resolved_at TEXT,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_alert_incidents_tenant
                ON alert_incidents(tenant_id, triggered_at)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_alert_incidents_rule
                ON alert_incidents(rule_id)
            """)

            # Policy changes: append-only log for SOC 2 change management
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS policy_changes (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    changed_by TEXT,            -- API key id or user id
                    change_type TEXT NOT NULL,  -- 'create', 'update', 'delete', 'enable', 'disable', 'apply_pack'
                    entity_type TEXT NOT NULL,  -- 'policy_rule', 'policy_pack', 'active_preset'
                    entity_id TEXT,
                    entity_name TEXT,
                    diff_json TEXT,             -- JSON with before/after snapshot
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_policy_changes_tenant
                ON policy_changes(tenant_id, created_at)
            """)

            # DSAR requests: GDPR/CCPA subject data access and deletion
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dsar_requests (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,   -- agent_id or external identifier
                    request_type TEXT NOT NULL, -- 'access', 'deletion'
                    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'completed', 'failed'
                    requested_at TEXT NOT NULL,
                    completed_at TEXT,
                    notes TEXT,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_dsar_requests_tenant
                ON dsar_requests(tenant_id, requested_at)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_dsar_requests_subject
                ON dsar_requests(subject_id)
            """)

            # Purge log: tracks automated data retention purge runs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS purge_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    purged_count INTEGER NOT NULL,
                    retention_days INTEGER NOT NULL,
                    purged_before TEXT NOT NULL,   -- ISO-8601 cutoff timestamp
                    purged_at TEXT NOT NULL,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_purge_log_tenant
                ON purge_log(tenant_id, purged_at)
            """)
            conn.commit()

            # Migration: add rule_code, protected, regulation to policy_rules
            for _col_def in [
                "rule_code TEXT",
                "protected INTEGER NOT NULL DEFAULT 0",
                "regulation TEXT",
            ]:
                try:
                    cursor.execute(f"ALTER TABLE policy_rules ADD COLUMN {_col_def}")  # safe: schema-only
                    conn.commit()
                except sqlite3.OperationalError:
                    pass
            # Unique index on rule_code (per tenant) for fast health-check lookups
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_policy_rules_rule_code
                ON policy_rules(tenant_id, rule_code)
                WHERE rule_code IS NOT NULL
            """)
            conn.commit()

            # Migration: add retention_days to tenants
            try:
                cursor.execute("ALTER TABLE tenants ADD COLUMN retention_days INTEGER NOT NULL DEFAULT 365")
                conn.commit()
            except sqlite3.OperationalError:
                pass

            # ── Device Registry Tables ──────────────────────────────────────────

            # Physical device registry — first-class entities
            cursor.execute("""
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
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_devices_tenant
                ON devices(tenant_id, status)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_devices_type
                ON devices(tenant_id, device_type)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_devices_department
                ON devices(tenant_id, department)
            """)

            # Agent-device bindings — explicit authorization matrix
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agent_device_bindings (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    permission_level TEXT NOT NULL DEFAULT 'full_control',
                    authorized_by TEXT,
                    valid_from TEXT,
                    valid_until TEXT,
                    shift_start TEXT,
                    shift_end TEXT,
                    requires_supervision INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    UNIQUE(agent_id, device_id),
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_bindings_agent
                ON agent_device_bindings(agent_id, enabled)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_bindings_device
                ON agent_device_bindings(device_id, enabled)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_bindings_tenant
                ON agent_device_bindings(tenant_id)
            """)

            # Device sessions — lock/release audit log
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS device_sessions (
                    session_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    action_id TEXT,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    end_reason TEXT,
                    duration_seconds REAL,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_device_sessions_device
                ON device_sessions(device_id, started_at)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_device_sessions_agent
                ON device_sessions(agent_id)
            """)
            conn.commit()

            # Migration: add vendor_id to agents table
            try:
                cursor.execute("ALTER TABLE agents ADD COLUMN vendor_id TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                pass

            # Migration: add device_id + vendor_id to audit_events
            for _col in ("device_id TEXT", "vendor_id TEXT"):
                try:
                    cursor.execute(f"ALTER TABLE audit_events ADD COLUMN {_col}")  # safe: schema-only
                    conn.commit()
                except sqlite3.OperationalError:
                    pass

            # ── Webhook Registrations ───────────────────────────────────────────
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS webhooks (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    events TEXT NOT NULL,  -- JSON list of event strings
                    secret TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_webhooks_tenant
                ON webhooks(tenant_id, enabled)
            """)

            # Webhook delivery log
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS webhook_deliveries (
                    id TEXT PRIMARY KEY,
                    webhook_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,  -- JSON
                    status TEXT NOT NULL DEFAULT 'pending',  -- pending, delivered, failed
                    response_status INTEGER,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    delivered_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_webhook
                ON webhook_deliveries(webhook_id, delivered_at)
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS support_cases (
                    case_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    support_code TEXT,
                    severity TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    assigned_owner TEXT,
                    summary TEXT NOT NULL,
                    issue_type TEXT NOT NULL DEFAULT 'incident',
                    affected_system TEXT,
                    workflow_id TEXT,
                    connector TEXT,
                    decision_id TEXT,
                    action_id TEXT,
                    trace_id TEXT,
                    conversation_id TEXT,
                    request_id TEXT,
                    created_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    timeline_json TEXT NOT NULL,
                    evidence_bundle_json TEXT NOT NULL,
                    issue_payload_json TEXT NOT NULL,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_support_cases_tenant
                ON support_cases(tenant_id, created_at)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_support_cases_status
                ON support_cases(tenant_id, status)
            """)
            conn.commit()

            # Check and set schema version
            from .schema_version import check_schema_version, set_schema_version, SCHEMA_VERSION
            if not check_schema_version(self):
                set_schema_version(self, SCHEMA_VERSION)
    
    @contextmanager
    def _get_connection(self):
        """Get database connection with proper error handling."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        # Enable foreign keys and WAL mode for better concurrency
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
        except sqlite3.Error as e:
            conn.rollback()
            raise RuntimeError(f"Database error: {str(e)}") from e
        finally:
            conn.close()
    
    def save_intent(self, intent_id: str, objective: str, scope: Dict, 
                   constraints: Dict, risk_level: str, approved_by_user: bool):
        """Save or update an intent contract.
        
        Args:
            intent_id: Unique intent identifier
            objective: Intent objective
            scope: Tool scope dictionary
            constraints: Constraints dictionary
            risk_level: Risk level string
            approved_by_user: Whether user approved
            
        Raises:
            ValueError: If validation fails
            RuntimeError: If database operation fails
        """
        # Validation
        if not intent_id or not intent_id.strip():
            raise ValueError("intent_id cannot be empty")
        if not objective or not objective.strip():
            raise ValueError("objective cannot be empty")
        if not isinstance(scope, dict):
            raise ValueError("scope must be a dictionary")
        if not isinstance(constraints, dict):
            raise ValueError("constraints must be a dictionary")
        if risk_level not in ["low", "medium", "high", "critical"]:
            raise ValueError(f"Invalid risk_level: {risk_level}")
        
        now = datetime.now(UTC).isoformat()
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO intents 
                    (intent_id, objective, scope, constraints, risk_level, 
                     approved_by_user, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 
                            COALESCE((SELECT created_at FROM intents WHERE intent_id = ?), ?), ?)
                """, (
                    intent_id, objective, json.dumps(scope), json.dumps(constraints),
                    risk_level, approved_by_user, intent_id, now, now
                ))
                conn.commit()
        except sqlite3.Error as e:
            raise RuntimeError(f"Failed to save intent: {str(e)}") from e
    
    def get_intent(self, intent_id: str) -> Optional[Dict[str, Any]]:
        """Get an intent contract by ID.
        
        Args:
            intent_id: Intent identifier
            
        Returns:
            Intent dictionary or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM intents WHERE intent_id = ?
            """, (intent_id,))
            row = cursor.fetchone()
            
            if row:
                return {
                    "intent_id": row["intent_id"],
                    "objective": row["objective"],
                    "scope": json.loads(row["scope"]),
                    "constraints": json.loads(row["constraints"]),
                    "risk_level": row["risk_level"],
                    "approved_by_user": bool(row["approved_by_user"]),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"]
                }
            return None
    
    def list_intents(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List all intents.
        
        Args:
            limit: Maximum number of intents to return
            
        Returns:
            List of intent dictionaries
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM intents 
                ORDER BY updated_at DESC 
                LIMIT ?
            """, (limit,))
            
            return [
                {
                    "intent_id": row["intent_id"],
                    "objective": row["objective"],
                    "scope": json.loads(row["scope"]),
                    "constraints": json.loads(row["constraints"]),
                    "risk_level": row["risk_level"],
                    "approved_by_user": bool(row["approved_by_user"]),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"]
                }
                for row in cursor.fetchall()
            ]
    
    def get_latest_intent(self) -> Optional[Dict[str, Any]]:
        """Get the most recently updated intent.
        
        Returns:
            Intent dictionary or None if no intents exist
        """
        intents = self.list_intents(limit=1)
        return intents[0] if intents else None

    def _get_previous_chain_hash(self) -> str:
        """Get chain_hash of the most recent audit event for cryptographic chaining."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT chain_hash FROM audit_events ORDER BY id DESC LIMIT 1"
            )
            row = cursor.fetchone()
            if row and row["chain_hash"]:
                return row["chain_hash"]
        return ""

    def _compute_chain_hash(self, prev_hash: str, entry_payload: str) -> str:
        """Compute SHA-256 chain hash: hash(prev_hash || entry_payload)."""
        return hashlib.sha256((prev_hash + entry_payload).encode("utf-8")).hexdigest()

    def _compute_chain_signature(self, chain_hash: str) -> Optional[str]:
        """Compute HMAC signature for chain hash when signing key is configured."""
        key = (os.getenv("EDON_AUDIT_CHAIN_SIGNING_KEY") or "").strip()
        if not key:
            return None
        return hmac.new(key.encode("utf-8"), chain_hash.encode("utf-8"), hashlib.sha256).hexdigest()
    
    def save_audit_event(
        self,
        action: Dict,
        decision: Dict,
        intent_id: Optional[str],
        agent_id: Optional[str],
        context: Dict,
        *,
        customer_id: Optional[str] = None,
        anomaly_score: Optional[float] = None,
        human_override: bool = False,
        human_override_actor_id: Optional[str] = None,
        human_override_reason: Optional[str] = None,
        processing_latency_ms: Optional[float] = None,
        edge_node_id: Optional[str] = None,
        policy_rule_id: Optional[str] = None,
        action_summary: Optional[str] = None,
        stated_intent: Optional[str] = None,
        user_message: Optional[str] = None,
        created_at_override: Optional[str] = None,
        request_hash: Optional[str] = None,
        decision_id_override: Optional[str] = None,
    ) -> str:
        """Save an audit event with optional chain hash and pilot-ready fields.
        
        Args:
            action: Action dictionary
            decision: Decision dictionary
            intent_id: Intent identifier (optional)
            agent_id: Agent identifier (optional)
            context: Additional context dictionary
            customer_id: Tenant/customer ID (optional)
            anomaly_score: Anomaly score 0-100 (optional)
            human_override: Whether decision was overridden by human
            human_override_actor_id: ID of reviewer (optional)
            human_override_reason: Reason for override (optional)
            processing_latency_ms: Latency in ms (optional)
            edge_node_id: Edge node ID for physical systems (optional)
            created_at_override: Use this as created_at/decision_id timestamp (for async audit writer).
            request_hash: SHA-256 of canonical request payload.
            decision_id_override: Preallocated canonical decision ID.
            
        Returns:
            Decision ID that was created
        """
        now = created_at_override if created_at_override else datetime.now(UTC).isoformat()
        ts = action.get("requested_at", now)
        action_id = action.get("id", "")
        tool = action.get("tool", "")
        op = action.get("op", "")
        params_json = json.dumps(action.get("params", {}))
        source = action.get("source", "")
        est_risk = action.get("estimated_risk", "")
        comp_risk = action.get("computed_risk")
        verdict = decision.get("verdict", "")
        reason_code = decision.get("reason_code", "")
        explanation = decision.get("explanation", "")
        policy_version = decision.get("policy_version", "1.0.0")
        policy_rule_id = policy_rule_id or decision.get("policy_rule_id")
        action_summary = action_summary or decision.get("action_summary")
        stated_intent = stated_intent or context.get("stated_intent")
        user_message = user_message or context.get("user_message")
        request_hash = request_hash or context.get("request_hash")
        context_json = json.dumps(context)

        from ..config import config as _config
        if _config.is_production() and not _config.ENCRYPT_AUDIT_PAYLOAD:
            raise RuntimeError("EDON_ENCRYPT_AUDIT_PAYLOAD must be true in production")

        # Optional field-level encryption of action params (Tier 1 security)
        is_payload_encrypted = 0
        if _config.ENCRYPT_AUDIT_PAYLOAD:
            try:
                from ..security.encryption import encrypt_field
                params_json = encrypt_field(params_json)
                is_payload_encrypted = 1
            except Exception as _enc_err:
                raise RuntimeError(f"Audit payload encryption failed: {_enc_err}") from _enc_err

        # Build canonical payload for chain hash (deterministic order)
        entry_payload = "|".join([
            ts, action_id, tool, op, params_json, source, str(est_risk), str(comp_risk),
            verdict, reason_code, explanation, policy_version, policy_rule_id or "", action_summary or "", stated_intent or "", user_message or "",
            intent_id or "", agent_id or "", context_json, now,
            customer_id or "", str(anomaly_score) if anomaly_score is not None else "",
            "1" if human_override else "0", human_override_actor_id or "", human_override_reason or "",
            str(processing_latency_ms) if processing_latency_ms is not None else "", edge_node_id or "", request_hash or "",
        ])
        prev_hash = self._get_previous_chain_hash()
        chain_hash = self._compute_chain_hash(prev_hash, entry_payload)
        chain_sig = self._compute_chain_signature(chain_hash)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO audit_events (
                    timestamp, action_id, action_tool, action_op, action_params,
                    action_source, action_estimated_risk, action_computed_risk,
                    decision_verdict, decision_reason_code, decision_explanation,
                    decision_policy_version, policy_rule_id, action_summary, stated_intent, user_message,
                    intent_id, agent_id, context, created_at,
                    chain_hash, chain_sig, customer_id, anomaly_score, human_override,
                    human_override_actor_id, human_override_reason, processing_latency_ms, edge_node_id,
                    is_payload_encrypted, request_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ts, action_id, tool, op, params_json, source, est_risk, comp_risk,
                verdict, reason_code, explanation, policy_version, policy_rule_id, action_summary, stated_intent, user_message,
                intent_id, agent_id, context_json, now,
                chain_hash, chain_sig, customer_id, anomaly_score, 1 if human_override else 0,
                human_override_actor_id, human_override_reason, processing_latency_ms, edge_node_id,
                is_payload_encrypted, request_hash
            ))
            
            # Also save to decisions table for quick lookup
            # Use action_id + timestamp for unique decision_id
            action_id = action.get("id", "")
            decision_id = decision_id_override or (f"dec-{action_id}-{now}" if action_id else f"dec-{now}")
            cursor.execute("""
                INSERT OR REPLACE INTO decisions 
                (decision_id, action_id, verdict, reason_code, explanation,
                 policy_version, intent_id, agent_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                decision_id,
                action_id,
                decision.get("verdict", ""),
                decision.get("reason_code", ""),
                decision.get("explanation", ""),
                decision.get("policy_version", "1.0.0"),
                intent_id,
                agent_id,
                now
            ))
            
            conn.commit()
            return decision_id

    def verify_audit_chain(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """Verify cryptographic chain of audit_events. Returns first broken position or ok.
        
        Returns:
            {"valid": bool, "checked": int, "broken_at_id": optional int, "message": str}
        """
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            q = "SELECT id, chain_hash, chain_sig, timestamp, action_id, action_tool, action_op, action_params, action_source, action_estimated_risk, action_computed_risk, decision_verdict, decision_reason_code, decision_explanation, decision_policy_version, policy_rule_id, action_summary, stated_intent, user_message, intent_id, agent_id, context, created_at, customer_id, anomaly_score, human_override, human_override_actor_id, human_override_reason, processing_latency_ms, edge_node_id, request_hash FROM audit_events ORDER BY id ASC"
            if limit:
                q += f" LIMIT {int(limit)}"
            cursor.execute(q)
            rows = cursor.fetchall()
        prev_hash = ""
        checked = 0
        allow_unsigned_legacy = (os.getenv("EDON_AUDIT_ALLOW_UNSIGNED_LEGACY", "true").lower() == "true")
        for row in rows:
            if row["chain_hash"] is None or row["chain_hash"] == "":
                # Legacy row without chain hash - cannot verify; chain valid up to here
                continue
            # Build same canonical payload as in save_audit_event
            context_json = row["context"] or "{}"
            params_json = row["action_params"] if isinstance(row["action_params"], str) else json.dumps(row["action_params"] or {})
            entry_payload = "|".join([
                row["timestamp"] or "", row["action_id"] or "", row["action_tool"] or "", row["action_op"] or "", params_json,
                row["action_source"] or "", str(row["action_estimated_risk"] or ""), str(row["action_computed_risk"]),
                row["decision_verdict"] or "", row["decision_reason_code"] or "", row["decision_explanation"] or "",
                row["decision_policy_version"] or "", row["policy_rule_id"] or "", row["action_summary"] or "", row["stated_intent"] or "", row["user_message"] or "", row["intent_id"] or "", row["agent_id"] or "", context_json,
                row["created_at"] or "",
                row["customer_id"] or "", str(row["anomaly_score"]) if row["anomaly_score"] is not None else "",
                "1" if row["human_override"] else "0", row["human_override_actor_id"] or "", row["human_override_reason"] or "",
                str(row["processing_latency_ms"]) if row["processing_latency_ms"] is not None else "", row["edge_node_id"] or "", row["request_hash"] or "",
            ])
            expected = self._compute_chain_hash(prev_hash, entry_payload)
            if row["chain_hash"] != expected:
                return {"valid": False, "checked": checked, "broken_at_id": row["id"], "message": f"Chain broken at id={row['id']}"}
            expected_sig = self._compute_chain_signature(row["chain_hash"])
            stored_sig = row["chain_sig"]
            if expected_sig:
                if not stored_sig:
                    if not allow_unsigned_legacy:
                        return {
                            "valid": False,
                            "checked": checked,
                            "broken_at_id": row["id"],
                            "message": f"Unsigned chain row at id={row['id']}",
                        }
                elif not hmac.compare_digest(str(stored_sig), str(expected_sig)):
                    return {
                        "valid": False,
                        "checked": checked,
                        "broken_at_id": row["id"],
                        "message": f"Chain signature mismatch at id={row['id']}",
                    }
            prev_hash = row["chain_hash"]
            checked += 1
        return {"valid": True, "checked": checked, "broken_at_id": None, "message": "Chain valid"}
    
    def query_audit_events(self, agent_id: Optional[str] = None,
                          verdict: Optional[str] = None,
                          intent_id: Optional[str] = None,
                          customer_id: Optional[str] = None,
                          limit: int = 100) -> List[Dict[str, Any]]:
        """Query audit events. Multi-tenant: when customer_id is set, only that tenant's rows are returned.
        
        Args:
            agent_id: Filter by agent ID
            verdict: Filter by verdict
            intent_id: Filter by intent ID
            customer_id: Filter by tenant/customer (enforces isolation when provided)
            limit: Maximum number of events to return
            
        Returns:
            List of audit event dictionaries
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM audit_events WHERE 1=1"
            params = []
            
            if customer_id is not None:
                query += " AND customer_id = ?"
                params.append(customer_id)
            
            if agent_id:
                query += " AND agent_id = ?"
                params.append(agent_id)
            
            if verdict:
                query += " AND decision_verdict = ?"
                params.append(verdict)
            
            if intent_id:
                query += " AND intent_id = ?"
                params.append(intent_id)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            
            return [
                {
                    "id": f"dec-{row['action_id']}-{row['created_at']}",
                    "timestamp": row["timestamp"],
                    "created_at": row["created_at"],
                    "agent_id": row["agent_id"] or "",
                    "intent_id": row["intent_id"] or "",
                    "verdict": row["decision_verdict"] or "",
                    "reason_code": row["decision_reason_code"] or "",
                    "explanation": row["decision_explanation"] or "",
                    "policy_version": row["decision_policy_version"] or "",
                    "latency_ms": row["processing_latency_ms"],
                    "action": {
                        "id": row["action_id"],
                        "tool": row["action_tool"],
                        "op": row["action_op"],
                        "params": json.loads(row["action_params"]) if row["action_params"] else {},
                        "source": row["action_source"],
                        "estimated_risk": row["action_estimated_risk"],
                        "computed_risk": row["action_computed_risk"]
                    },
                    "decision": {
                        "verdict": row["decision_verdict"],
                        "reason_code": row["decision_reason_code"],
                        "explanation": row["decision_explanation"],
                        "policy_version": row["decision_policy_version"],
                        "policy_rule_id": row["policy_rule_id"],
                    },
                    "action_summary": row["action_summary"],
                    "stated_intent": row["stated_intent"],
                    "user_message": row["user_message"],
                    "context": json.loads(row["context"]) if row["context"] else {},
                }
                for row in cursor.fetchall()
            ]
    
    def increment_counter(self, key: str, amount: int = 1) -> int:
        """Increment a counter (for rate limiting).
        
        Args:
            key: Counter key (e.g., "agent:clawdbot-001:actions:minute")
            amount: Amount to increment
            
        Returns:
            New counter value
        """
        now = datetime.now(UTC).isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO counters (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = value + ?,
                    updated_at = ?
            """, (key, amount, now, amount, now))
            
            cursor.execute("SELECT value FROM counters WHERE key = ?", (key,))
            row = cursor.fetchone()
            conn.commit()
            
            return row["value"] if row else amount
    
    def get_counter(self, key: str) -> int:
        """Get counter value.
        
        Args:
            key: Counter key
            
        Returns:
            Counter value (0 if not found)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM counters WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else 0
    
    def save_credential(self, credential_id: str, tool_name: str, 
                      credential_type: str, credential_data: Dict[str, Any],
                      encrypted: bool = False, tenant_id: Optional[str] = None) -> None:
        """Save or update a credential.
        
        Args:
            credential_id: Unique credential identifier
            tool_name: Tool name (e.g., "email", "filesystem", "clawdbot")
            credential_type: Type of credential (e.g., "smtp", "api_key", "gateway")
            credential_data: Credential data dictionary
            encrypted: Whether credential_data is encrypted
            tenant_id: Optional tenant ID for tenant-scoped credentials
            
        Raises:
            ValueError: If validation fails
            RuntimeError: If database operation fails
        """
        # Validation
        if not credential_id or not credential_id.strip():
            raise ValueError("credential_id cannot be empty")
        if not tool_name or not tool_name.strip():
            raise ValueError("tool_name cannot be empty")
        if not isinstance(credential_data, dict):
            raise ValueError("credential_data must be a dictionary")
        
        now = datetime.now(UTC).isoformat()
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO credentials 
                    (credential_id, tool_name, tenant_id, credential_type, credential_data,
                     encrypted, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 
                            COALESCE((SELECT created_at FROM credentials WHERE credential_id = ? AND (tenant_id = ? OR (tenant_id IS NULL AND ? IS NULL))), ?), ?)
                """, (
                    credential_id, tool_name, tenant_id, credential_type,
                    json.dumps(credential_data), 1 if encrypted else 0,
                    credential_id, tenant_id, tenant_id, now, now
                ))
                conn.commit()
        except sqlite3.Error as e:
            raise RuntimeError(f"Failed to save credential: {str(e)}") from e
    
    def get_credential(self, credential_id: str, tool_name: Optional[str] = None, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get a credential by ID. Deterministic: strict tenant match, most recent row.
        
        When tenant_id is provided: match only that tenant.
        When tenant_id is None: match only tenant_id IS NULL (no fallback to other tenant).
        When multiple rows exist: select most recent (ORDER BY rowid DESC LIMIT 1).
        
        Args:
            credential_id: Credential identifier
            tool_name: Optional tool name filter
            tenant_id: Optional tenant ID for tenant-scoped lookup (None = global only)
            
        Returns:
            Credential dictionary or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM credentials WHERE credential_id = ?"
            params: List[Any] = [credential_id]
            if tool_name:
                query += " AND tool_name = ?"
                params.append(tool_name)
            if tenant_id is not None:
                query += " AND tenant_id = ?"
                params.append(tenant_id)
            else:
                query += " AND tenant_id IS NULL"
            query += " ORDER BY rowid DESC LIMIT 1"
            cursor.execute(query, tuple(params))
            row = cursor.fetchone()
            if row:
                result = {
                    "credential_id": row["credential_id"],
                    "tool_name": row["tool_name"],
                    "credential_type": row["credential_type"],
                    "credential_data": json.loads(row["credential_data"]),
                    "encrypted": bool(row["encrypted"]),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                if "last_used_at" in row.keys():
                    result["last_used_at"] = row["last_used_at"]
                if "tenant_id" in row.keys():
                    result["tenant_id"] = row["tenant_id"]
                if "last_error" in row.keys():
                    result["last_error"] = row["last_error"]
                return result
            return None
    
    def get_credentials_by_tool(self, tool_name: str) -> List[Dict[str, Any]]:
        """Get all credentials for a tool.
        
        Args:
            tool_name: Tool name
            
        Returns:
            List of credential dictionaries
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM credentials 
                WHERE tool_name = ?
                ORDER BY updated_at DESC
            """, (tool_name,))
            
            return [
                {
                    "credential_id": row["credential_id"],
                    "tool_name": row["tool_name"],
                    "credential_type": row["credential_type"],
                    "credential_data": json.loads(row["credential_data"]),
                    "encrypted": bool(row["encrypted"]),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "last_used_at": row["last_used_at"]
                }
                for row in cursor.fetchall()
            ]
    
    def update_credential_last_used(self, credential_id: str, tenant_id: Optional[str] = None):
        """Update last_used_at timestamp for a credential (by credential_id and optional tenant_id)."""
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if tenant_id is not None:
                cursor.execute("""
                    UPDATE credentials SET last_used_at = ?
                    WHERE credential_id = ? AND tenant_id = ?
                """, (now, credential_id, tenant_id))
            else:
                cursor.execute("""
                    UPDATE credentials SET last_used_at = ?
                    WHERE credential_id = ? AND tenant_id IS NULL
                """, (now, credential_id))
            conn.commit()

    def update_credential_status(
        self,
        credential_id: str,
        tenant_id: Optional[str],
        success: bool,
        error_message: Optional[str] = None,
    ) -> None:
        """Record Edonbot invoke result for integration status.
        On success: set last_used_at, clear last_error.
        On failure: set last_error (user-safe message).
        """
        now = datetime.now(UTC).isoformat()
        err_safe = (error_message or "")[:500] if error_message else None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if tenant_id is not None:
                if success:
                    cursor.execute("""
                        UPDATE credentials SET last_used_at = ?, last_error = NULL
                        WHERE credential_id = ? AND tenant_id = ?
                    """, (now, credential_id, tenant_id))
                else:
                    cursor.execute("""
                        UPDATE credentials SET last_error = ?
                        WHERE credential_id = ? AND tenant_id = ?
                    """, (err_safe, credential_id, tenant_id))
            else:
                if success:
                    cursor.execute("""
                        UPDATE credentials SET last_used_at = ?, last_error = NULL
                        WHERE credential_id = ? AND tenant_id IS NULL
                    """, (now, credential_id))
                else:
                    cursor.execute("""
                        UPDATE credentials SET last_error = ?
                        WHERE credential_id = ? AND tenant_id IS NULL
                    """, (err_safe, credential_id))
            conn.commit()

    def delete_credential(self, credential_id: str) -> bool:
        """Delete a credential.
        
        Args:
            credential_id: Credential identifier
            
        Returns:
            True if deleted, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM credentials WHERE credential_id = ?", (credential_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def bind_token_to_agent(self, token: str, agent_id: str):
        """Bind a token to an agent_id.
        
        Args:
            token: Authentication token
            agent_id: Agent identifier
        """
        import hashlib
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        now = datetime.now(UTC).isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO token_agent_bindings 
                (token_hash, agent_id, created_at, last_used_at)
                VALUES (?, ?, 
                        COALESCE((SELECT created_at FROM token_agent_bindings WHERE token_hash = ?), ?), ?)
            """, (token_hash, agent_id, token_hash, now, now))
            conn.commit()
    
    def get_agent_id_for_token(self, token: str) -> Optional[str]:
        """Get agent_id bound to a token.
        
        Args:
            token: Authentication token
            
        Returns:
            Agent ID or None if not found
        """
        import hashlib
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT agent_id FROM token_agent_bindings WHERE token_hash = ?
            """, (token_hash,))
            row = cursor.fetchone()
            return row["agent_id"] if row else None
    
    def update_token_last_used(self, token: str):
        """Update last_used_at for a token.
        
        Args:
            token: Authentication token
        """
        import hashlib
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        now = datetime.now(UTC).isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE token_agent_bindings 
                SET last_used_at = ?
                WHERE token_hash = ?
            """, (now, token_hash))
            conn.commit()
    
    def get_decision(self, decision_id: str) -> Optional[Dict[str, Any]]:
        """Get a decision by ID.
        
        Args:
            decision_id: Decision identifier
            
        Returns:
            Decision dictionary or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM decisions WHERE decision_id = ?
            """, (decision_id,))
            row = cursor.fetchone()
            
            if row:
                return {
                    "decision_id": row["decision_id"],
                    "action_id": row["action_id"],
                    "verdict": row["verdict"],
                    "reason_code": row["reason_code"],
                    "explanation": row["explanation"],
                    "policy_version": row["policy_version"],
                    "intent_id": row["intent_id"],
                    "agent_id": row["agent_id"],
                    "created_at": row["created_at"]
                }
            return None
    
    def query_decisions(self, action_id: Optional[str] = None,
                       verdict: Optional[str] = None,
                       intent_id: Optional[str] = None,
                       agent_id: Optional[str] = None,
                       customer_id: Optional[str] = None,
                       limit: int = 100) -> List[Dict[str, Any]]:
        """Query decisions with action details from audit_events. Multi-tenant: when customer_id is set, only that tenant's data.
        
        Args:
            action_id: Filter by action ID
            verdict: Filter by verdict
            intent_id: Filter by intent ID
            agent_id: Filter by agent ID
            customer_id: Filter by tenant (via audit_events.customer_id)
            limit: Maximum number of decisions to return
            
        Returns:
            List of decision dictionaries with action details
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Join with audit_events to get action details (tool, op); when customer_id set, restrict to that tenant
            if customer_id is not None:
                query = """
                    SELECT 
                        d.decision_id,
                        d.action_id,
                        d.verdict,
                        d.reason_code,
                        d.explanation,
                        d.policy_version,
                        d.intent_id,
                        d.agent_id,
                        d.created_at,
                        a.action_tool,
                        a.action_op,
                        a.action_params,
                        a.timestamp
                    FROM decisions d
                    INNER JOIN audit_events a ON d.action_id = a.action_id AND a.customer_id = ?
                    WHERE 1=1
                """
                params = [customer_id]
            else:
                query = """
                    SELECT 
                        d.decision_id,
                        d.action_id,
                        d.verdict,
                        d.reason_code,
                        d.explanation,
                        d.policy_version,
                        d.intent_id,
                        d.agent_id,
                        d.created_at,
                        a.action_tool,
                        a.action_op,
                        a.action_params,
                        a.timestamp
                    FROM decisions d
                    LEFT JOIN audit_events a ON d.action_id = a.action_id
                    WHERE 1=1
                """
                params: list = []
            
            if action_id:
                query += " AND d.action_id = ?"
                params.append(action_id)
            
            if verdict:
                query += " AND d.verdict = ?"
                params.append(verdict)
            
            if intent_id:
                query += " AND d.intent_id = ?"
                params.append(intent_id)
            
            if agent_id:
                query += " AND d.agent_id = ?"
                params.append(agent_id)
            
            query += " ORDER BY d.created_at DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            
            results = []
            for row in cursor.fetchall():
                # Map verdict to UI format (ALLOW -> allowed, BLOCK -> blocked, etc.)
                verdict_map = {
                    "ALLOW": "allowed",
                    "BLOCK": "blocked",
                    "ESCALATE": "confirm",
                    "DEGRADE": "confirm",
                    "PAUSE": "confirm"
                }
                row_verdict: str = row["verdict"] or "UNKNOWN"
                verdict_lower = verdict_map.get(row_verdict, row_verdict.lower())
                
                decision = {
                    "id": row["decision_id"],  # Use 'id' for UI compatibility
                    "decision_id": row["decision_id"],
                    "action_id": row["action_id"],
                    "verdict": verdict_lower,
                    "reason_code": row["reason_code"],
                    "explanation": row["explanation"],
                    "policy_version": row["policy_version"],
                    "intent_id": row["intent_id"],
                    "agent_id": row["agent_id"] or "unknown",
                    "created_at": row["created_at"],
                    "timestamp": row["timestamp"] or row["created_at"],  # Use timestamp from audit if available
                }
                
                # Add tool information if available
                if row["action_tool"] and row["action_op"]:
                    decision["tool"] = {
                        "name": row["action_tool"],
                        "op": row["action_op"]
                    }
                
                # Add latency_ms if available (could be calculated from timestamps)
                decision["latency_ms"] = 0  # Default, can be calculated if needed
                
                results.append(decision)
            
            return results
    
    def get_decision_by_action_id(self, action_id: str) -> Optional[Dict[str, Any]]:
        """Get decision by action ID (most recent).
        
        Args:
            action_id: Action identifier
            
        Returns:
            Decision dictionary or None if not found
        """
        decisions = self.query_decisions(action_id=action_id, limit=1)
        return decisions[0] if decisions else None
    
    def set_active_policy_preset(self, preset_name: str, applied_by: Optional[str] = None):
        """Set the active policy preset.
        
        Args:
            preset_name: Name of the policy preset
            applied_by: Optional identifier of who applied it
        """
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO active_policy_preset (id, preset_name, applied_at, applied_by)
                VALUES (1, ?, ?, ?)
            """, (preset_name, now, applied_by))
            conn.commit()
    
    def get_active_policy_preset(self) -> Optional[Dict[str, Any]]:
        """Get the currently active policy preset.
        
        Returns:
            Dictionary with preset_name, applied_at, applied_by, or None if not set
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT preset_name, applied_at, applied_by 
                FROM active_policy_preset 
                WHERE id = 1
            """)
            row = cursor.fetchone()
            if row:
                return {
                    "preset_name": row["preset_name"],
                    "applied_at": row["applied_at"],
                    "applied_by": row["applied_by"]
                }
            return None

    # ---- Per-tenant custom policy rules ----

    def create_policy_rule(
        self,
        tenant_id: str,
        name: str,
        action: str,
        priority: int = 0,
        description: Optional[str] = None,
        condition_tool: Optional[str] = None,
        condition_op: Optional[str] = None,
        condition_risk_level: Optional[str] = None,
        condition_tags: Optional[List[str]] = None,
        enabled: bool = True,
    ) -> str:
        """Create a custom policy rule for a tenant.

        Returns:
            rule_id
        """
        import uuid
        rule_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        tags_json = json.dumps(condition_tags) if condition_tags else None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO policy_rules
                    (id, tenant_id, name, description, condition_tool, condition_op,
                     condition_risk_level, condition_tags, action, priority, enabled,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (rule_id, tenant_id, name, description, condition_tool, condition_op,
                  condition_risk_level, tags_json, action, priority,
                  1 if enabled else 0, now, now))
            conn.commit()
        return rule_id

    def get_policy_rules(self, tenant_id: str, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """Get policy rules for a tenant, ordered by priority descending."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if enabled_only:
                cursor.execute("""
                    SELECT * FROM policy_rules
                    WHERE tenant_id = ? AND enabled = 1
                    ORDER BY priority DESC, created_at ASC
                """, (tenant_id,))
            else:
                cursor.execute("""
                    SELECT * FROM policy_rules
                    WHERE tenant_id = ?
                    ORDER BY priority DESC, created_at ASC
                """, (tenant_id,))
            rows = cursor.fetchall()
            rules = []
            for row in rows:
                d = dict(row)
                if d.get("condition_tags"):
                    d["condition_tags"] = json.loads(d["condition_tags"])
                d["enabled"] = bool(d["enabled"])
                rules.append(d)
            return rules

    def get_policy_rule(self, rule_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get a single policy rule by ID (tenant-scoped)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM policy_rules WHERE id = ? AND tenant_id = ?",
                (rule_id, tenant_id)
            )
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get("condition_tags"):
                d["condition_tags"] = json.loads(d["condition_tags"])
            d["enabled"] = bool(d["enabled"])
            return d

    def update_policy_rule(self, rule_id: str, tenant_id: str, **fields) -> bool:
        """Update a policy rule. Returns True if updated."""
        allowed = {
            "name", "description", "condition_tool", "condition_op",
            "condition_risk_level", "condition_tags", "action", "priority", "enabled"
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return False
        now = datetime.now(UTC).isoformat()
        updates["updated_at"] = now
        if "condition_tags" in updates and isinstance(updates["condition_tags"], list):
            updates["condition_tags"] = json.dumps(updates["condition_tags"])
        if "enabled" in updates:
            updates["enabled"] = 1 if updates["enabled"] else 0
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [rule_id, tenant_id]
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE policy_rules SET {set_clause} WHERE id = ? AND tenant_id = ?",
                values
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_policy_rule(self, rule_id: str, tenant_id: str) -> bool:
        """Delete a policy rule. Returns True if deleted."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM policy_rules WHERE id = ? AND tenant_id = ?",
                (rule_id, tenant_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    # User management methods (auth provider agnostic)
    def create_user(self, user_id: str, email: str, auth_provider: str, auth_subject: str, role: str = "user") -> str:
        """Create a new user with internal UUID.
        
        Args:
            user_id: Internal UUID (generated by caller)
            email: User email address
            auth_provider: Auth provider name ('clerk', 'supabase', etc.)
            auth_subject: Provider's user ID (clerk_user_id, supabase_user_id, etc.)
            role: User role ('user', 'admin', etc.)
            
        Returns:
            user_id
        """
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users 
                (id, email, auth_provider, auth_subject, role, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, email, auth_provider, auth_subject, role, now, now))
            conn.commit()
        return user_id
    
    def get_user_by_auth(self, auth_provider: str, auth_subject: str) -> Optional[Dict[str, Any]]:
        """Get user by auth provider credentials.
        
        Args:
            auth_provider: Auth provider name ('clerk', 'supabase', etc.)
            auth_subject: Provider's user ID
            
        Returns:
            User dictionary or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM users WHERE auth_provider = ? AND auth_subject = ?
            """, (auth_provider, auth_subject))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "email": row["email"],
                    "auth_provider": row["auth_provider"],
                    "auth_subject": row["auth_subject"],
                    "role": row["role"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"]
                }
            return None
    
    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by internal ID.
        
        Args:
            user_id: Internal user UUID
            
        Returns:
            User dictionary or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM users WHERE id = ?
            """, (user_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "email": row["email"],
                    "auth_provider": row["auth_provider"],
                    "auth_subject": row["auth_subject"],
                    "role": row["role"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"]
                }
            return None

    def update_user_email(self, user_id: str, email: str) -> bool:
        """Update a user's email. Returns True if a row was updated."""
        if not email or not email.strip():
            return False
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET email = ?, updated_at = ? WHERE id = ?",
                (email.strip(), now, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0
    
    # Tenant management methods
    def create_tenant(self, tenant_id: str, user_id: str, stripe_customer_id: Optional[str] = None) -> str:
        """Create a new tenant linked to a user.
        
        Args:
            tenant_id: Unique tenant identifier
            user_id: Internal user UUID (from users table)
            stripe_customer_id: Optional Stripe customer ID
            
        Returns:
            tenant_id
        """
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tenants 
                (id, user_id, status, plan, mag_enabled, stripe_customer_id, created_at, updated_at)
                VALUES (?, ?, 'trial', 'free', 0, ?, ?, ?)
            """, (tenant_id, user_id, stripe_customer_id, now, now))
            conn.commit()
        return tenant_id
    
    def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get tenant by ID.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Tenant dictionary or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.*, u.email, u.id as user_id
                FROM tenants t
                JOIN users u ON t.user_id = u.id
                WHERE t.id = ?
            """, (tenant_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "email": row["email"],
                    "status": row["status"],
                    "plan": row["plan"],
                    "mag_enabled": bool(row["mag_enabled"]) if "mag_enabled" in row.keys() else False,
                    "default_intent_id": row["default_intent_id"] if "default_intent_id" in row.keys() else None,
                    "stripe_customer_id": row["stripe_customer_id"],
                    "stripe_subscription_id": row["stripe_subscription_id"],
                    "current_period_start": row["current_period_start"],
                    "current_period_end": row["current_period_end"],
                    "cancel_at_period_end": bool(row["cancel_at_period_end"]),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"]
                }
            return None

    def is_mag_enabled(self, tenant_id: str) -> bool:
        """Check if MAG enforcement is enabled for a tenant."""
        if not tenant_id:
            return False
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT mag_enabled FROM tenants WHERE id = ?", (tenant_id,))
            row = cursor.fetchone()
            if not row:
                return False
            try:
                return bool(row["mag_enabled"])
            except Exception:
                return False
    
    def get_tenant_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get tenant by user ID.
        
        Args:
            user_id: Internal user UUID
            
        Returns:
            Tenant dictionary or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.*, u.email, u.id as user_id
                FROM tenants t
                JOIN users u ON t.user_id = u.id
                WHERE t.user_id = ?
            """, (user_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "email": row["email"],
                    "status": row["status"],
                    "plan": row["plan"],
                    "mag_enabled": bool(row["mag_enabled"]) if "mag_enabled" in row.keys() else False,
                    "stripe_customer_id": row["stripe_customer_id"],
                    "stripe_subscription_id": row["stripe_subscription_id"],
                    "current_period_start": row["current_period_start"],
                    "current_period_end": row["current_period_end"],
                    "cancel_at_period_end": bool(row["cancel_at_period_end"]),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"]
                }
            return None
    
    def get_tenant_by_stripe_customer(self, stripe_customer_id: str) -> Optional[Dict[str, Any]]:
        """Get tenant by Stripe customer ID.
        
        Args:
            stripe_customer_id: Stripe customer ID
            
        Returns:
            Tenant dictionary or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.*, u.email, u.id as user_id
                FROM tenants t
                JOIN users u ON t.user_id = u.id
                WHERE t.stripe_customer_id = ?
            """, (stripe_customer_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "email": row["email"],
                    "status": row["status"],
                    "plan": row["plan"],
                    "mag_enabled": bool(row["mag_enabled"]) if "mag_enabled" in row.keys() else False,
                    "stripe_customer_id": row["stripe_customer_id"],
                    "stripe_subscription_id": row["stripe_subscription_id"],
                    "current_period_start": row["current_period_start"],
                    "current_period_end": row["current_period_end"],
                    "cancel_at_period_end": bool(row["cancel_at_period_end"]),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"]
                }
            return None
    
    def get_tenant_by_stripe_subscription(self, stripe_subscription_id: str) -> Optional[Dict[str, Any]]:
        """Get tenant by Stripe subscription ID.
        
        Args:
            stripe_subscription_id: Stripe subscription ID
            
        Returns:
            Tenant dictionary or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.*, u.email, u.id as user_id
                FROM tenants t
                JOIN users u ON t.user_id = u.id
                WHERE t.stripe_subscription_id = ?
            """, (stripe_subscription_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "email": row["email"],
                    "status": row["status"],
                    "plan": row["plan"],
                    "mag_enabled": bool(row["mag_enabled"]) if "mag_enabled" in row.keys() else False,
                    "stripe_customer_id": row["stripe_customer_id"],
                    "stripe_subscription_id": row["stripe_subscription_id"],
                    "current_period_start": row["current_period_start"],
                    "current_period_end": row["current_period_end"],
                    "cancel_at_period_end": bool(row["cancel_at_period_end"]),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"]
                }
            return None
    
    def update_tenant_subscription(
        self,
        tenant_id: str,
        status: Optional[str] = None,
        plan: Optional[str] = None,
        stripe_subscription_id: Optional[str] = None,
        current_period_start: Optional[str] = None,
        current_period_end: Optional[str] = None,
        cancel_at_period_end: Optional[bool] = None
    ):
        """Update tenant subscription information.
        
        Args:
            tenant_id: Tenant identifier
            status: Subscription status
            plan: Plan name
            stripe_subscription_id: Stripe subscription ID
            current_period_start: Period start timestamp
            current_period_end: Period end timestamp
            cancel_at_period_end: Whether to cancel at period end
        """
        now = datetime.now(UTC).isoformat()
        updates = []
        params = []
        
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if plan is not None:
            updates.append("plan = ?")
            params.append(plan)
        if stripe_subscription_id is not None:
            updates.append("stripe_subscription_id = ?")
            params.append(stripe_subscription_id)
        if current_period_start is not None:
            updates.append("current_period_start = ?")
            params.append(current_period_start)
        if current_period_end is not None:
            updates.append("current_period_end = ?")
            params.append(current_period_end)
        if cancel_at_period_end is not None:
            updates.append("cancel_at_period_end = ?")
            params.append(1 if cancel_at_period_end else 0)
        
        updates.append("updated_at = ?")
        params.append(now)
        params.append(tenant_id)
        
        if updates:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""  # safe: schema-only (updates from allowed tenant columns)
                    UPDATE tenants 
                    SET {', '.join(updates)}
                    WHERE id = ?
                """, params)
                conn.commit()
    
    def get_tenant_vertical(self, tenant_id: str) -> Optional[str]:
        """Return the vertical (healthcare, banking, general) for this tenant."""
        tenant = self.get_tenant(tenant_id)
        return tenant.get("vertical") if tenant else None

    def set_tenant_vertical(self, tenant_id: str, vertical: str) -> None:
        """Set the vertical for this tenant."""
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE tenants SET vertical = ?, updated_at = ? WHERE id = ?",
                (vertical, now, tenant_id),
            )
            conn.commit()

    def get_tenant_default_intent(self, tenant_id: str) -> Optional[str]:
        """Get tenant's default intent ID.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Intent ID or None if not set
        """
        tenant = self.get_tenant(tenant_id)
        if tenant:
            return tenant.get("default_intent_id")
        return None

    def update_tenant_default_intent(self, tenant_id: str, intent_id: str) -> None:
        """Update tenant's default intent ID.
        
        Args:
            tenant_id: Tenant identifier
            intent_id: Intent identifier to set as default
        """
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tenants
                SET default_intent_id = ?, updated_at = ?
                WHERE id = ?
            """, (intent_id, now, tenant_id))
            conn.commit()
    
    def get_integration_status(self, tenant_id: Optional[str], tool_name: str = "clawdbot") -> Dict[str, Any]:
        """Get integration status for a tool.
        
        connected = True only if credential exists AND last successful invoke/probe succeeded
        (i.e. last_error is None). last_ok_at = last_used_at when connected; last_error surfaced.
        """
        credential_id = f"{tool_name}_gateway_{tenant_id}" if tenant_id else f"{tool_name}_gateway"
        credential = self.get_credential(credential_id, tool_name=tool_name, tenant_id=tenant_id)
        if not credential:
            return {
                "connected": False,
                "last_ok_at": None,
                "last_error": None,
                "base_url": None,
                "auth_mode": None,
            }
        data = credential.get("credential_data", {}) or {}
        last_error = credential.get("last_error")
        last_used_at = credential.get("last_used_at")
        connected = last_used_at is not None
        return {
            "connected": connected,
            "last_ok_at": last_used_at,
            "last_error": last_error,
            "base_url": data.get("base_url") or data.get("gateway_url"),
            "auth_mode": data.get("auth_mode") or "token",
        }
    
    # API Key management methods
    def create_api_key(
        self,
        tenant_id: str,
        key_hash: str,
        name: Optional[str] = None,
        role: str = 'user',
        expires_at: Optional[str] = None,
        is_sandbox: bool = False,
    ) -> str:
        """Create a new API key.

        Args:
            tenant_id: Tenant identifier
            key_hash: SHA256 hash of the API key
            name: Optional user-friendly name
            role: RBAC role ('admin', 'operator', 'user', 'read_only', 'auditor'). Default 'user'.
            expires_at: Optional ISO-8601 expiry timestamp. None = never expires.
            is_sandbox: If True, key always observes (never blocks) regardless of shadow mode.

        Returns:
            API key ID
        """
        import uuid
        api_key_id = f"key_{uuid.uuid4().hex[:16]}"
        now = datetime.now(UTC).isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO api_keys
                (id, tenant_id, key_hash, name, status, role, created_at, expires_at, is_sandbox)
                VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?)
            """, (api_key_id, tenant_id, key_hash, name, role, now, expires_at, 1 if is_sandbox else 0))
            conn.commit()
        return api_key_id

    def list_auditor_grants(self, tenant_id: str) -> List[Dict[str, Any]]:
        """List all active auditor access grants for a tenant."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, status, role, created_at, expires_at, last_used_at
                FROM api_keys
                WHERE tenant_id = ? AND role = 'auditor'
                ORDER BY created_at DESC
            """, (tenant_id,))
            rows = cursor.fetchall()
        return [
            {
                "key_id": r["id"],
                "label": r["name"],
                "status": r["status"],
                "created_at": r["created_at"],
                "expires_at": r["expires_at"],
                "last_used_at": r["last_used_at"],
            }
            for r in rows
        ]

    def revoke_api_key_scoped(self, key_id: str, tenant_id: str) -> bool:
        """Revoke an API key by ID, scoped to a tenant. Returns True if a row was updated."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE api_keys SET status = 'revoked'
                WHERE id = ? AND tenant_id = ?
            """, (key_id, tenant_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_api_key_by_hash(self, key_hash: str) -> Optional[Dict[str, Any]]:
        """Get API key by hash.
        
        Args:
            key_hash: SHA256 hash of the API key
            
        Returns:
            API key dictionary or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM api_keys
                WHERE key_hash = ?
                  AND status IN ('active', 'rotating')
                  AND (expires_at IS NULL OR expires_at > ?)
            """, (key_hash, datetime.now(UTC).isoformat()))
            row = cursor.fetchone()
            if row:
                cols = row.keys()
                return {
                    "id": row["id"],
                    "tenant_id": row["tenant_id"],
                    "customer_id": row["tenant_id"],
                    "key_hash": row["key_hash"],
                    "name": row["name"],
                    "status": row["status"],
                    "role": row["role"] if "role" in cols else "user",
                    "is_sandbox": bool(row["is_sandbox"]) if "is_sandbox" in cols else False,
                    "created_at": row["created_at"],
                    "last_used_at": row["last_used_at"],
                }
            return None

    def update_api_key_last_used(self, api_key_id: str):
        """Update API key last used timestamp.
        
        Args:
            api_key_id: API key identifier
        """
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE api_keys 
                SET last_used_at = ?
                WHERE id = ?
            """, (now, api_key_id))
            conn.commit()
    
    def revoke_api_key(self, api_key_id: str) -> bool:
        """Revoke an API key.
        
        Args:
            api_key_id: API key identifier
            
        Returns:
            True if revoked, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE api_keys
                SET status = 'revoked'
                WHERE id = ?
            """, (api_key_id,))
            conn.commit()
            return cursor.rowcount > 0

    def rotate_api_key(self, api_key_id: str, tenant_id: str, new_key_hash: str,
                       new_key_name: Optional[str] = None, overlap_hours: int = 24,
                       role: str = 'user') -> dict:
        """Rotate an API key: creates a new key and marks the old one as rotating
        (still valid for overlap_hours, then expires).

        Returns:
            dict with new_key_id, old_expires_at
        """
        import uuid
        from datetime import timedelta
        now = datetime.now(UTC)
        old_expires_at = (now + timedelta(hours=overlap_hours)).isoformat()
        new_key_id = f"key_{uuid.uuid4().hex[:16]}"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Mark old key as rotating with expiry
            cursor.execute("""
                UPDATE api_keys SET status = 'rotating', expires_at = ?
                WHERE id = ? AND tenant_id = ?
            """, (old_expires_at, api_key_id, tenant_id))
            # Create new active key
            cursor.execute("""
                INSERT INTO api_keys (id, tenant_id, key_hash, name, status, role, created_at)
                VALUES (?, ?, ?, ?, 'active', ?, ?)
            """, (new_key_id, tenant_id, new_key_hash, new_key_name, role, now.isoformat()))
            conn.commit()

        return {"new_key_id": new_key_id, "old_expires_at": old_expires_at}

    def list_api_keys(self, tenant_id: str) -> List[Dict[str, Any]]:
        """List all API keys for a tenant.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            List of API key dictionaries with key preview
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, status, key_hash, created_at, last_used_at
                FROM api_keys 
                WHERE tenant_id = ?
                ORDER BY created_at DESC
            """, (tenant_id,))
            
            keys = []
            for row in cursor.fetchall():
                # Create preview: first 12 chars + "••••••"
                key_hash = row["key_hash"]
                preview = f"edon_{key_hash[:8]}••••••" if key_hash else "edon_••••••"
                
                keys.append({
                    "id": row["id"],
                    "name": row["name"],
                    "status": row["status"],
                    "key_preview": preview,
                    "is_active": row["status"] == "active",
                    "created_at": row["created_at"],
                    "last_used": row["last_used_at"]
                })
            
            return keys

    # Channel token + connect code methods (Telegram/SMS)
    def create_connect_code(
        self,
        tenant_id: str,
        expires_at: str,
        channel: str = "telegram",
    ) -> str:
        """Create a short-lived connect code for a tenant/channel."""
        import secrets
        now = datetime.now(UTC).isoformat()
        code = f"EDON-{secrets.token_hex(3).upper()}"  # 6 hex chars
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO connect_codes (code, tenant_id, channel, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (code, tenant_id, channel, expires_at, now))
            conn.commit()
        return code

    def get_connect_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Fetch a connect code entry."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM connect_codes WHERE code = ?
            """, (code,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "code": row["code"],
                "tenant_id": row["tenant_id"],
                "channel": row["channel"],
                "expires_at": row["expires_at"],
                "used_at": row["used_at"],
                "used_by": row["used_by"],
                "created_at": row["created_at"],
            }

    def mark_connect_code_used(self, code: str, used_by: Optional[str] = None) -> None:
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE connect_codes
                SET used_at = ?, used_by = ?
                WHERE code = ?
            """, (now, used_by, code))
            conn.commit()

    def create_connect_service_code(
        self,
        tenant_id: str,
        service: str,
        expires_at: str,
        chat_id: Optional[str] = None,
    ) -> str:
        """Create a short-lived code for connecting a service (gmail, brave_search, etc.)."""
        import secrets
        now = datetime.now(UTC).isoformat()
        code = f"EDON-{secrets.token_hex(4).upper()}"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO connect_service_codes (code, tenant_id, service, chat_id, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (code, tenant_id, service, chat_id, expires_at, now))
            conn.commit()
        return code

    def get_connect_service_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Fetch a connect service code entry."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM connect_service_codes WHERE code = ?
            """, (code,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "code": row["code"],
                "tenant_id": row["tenant_id"],
                "service": row["service"],
                "chat_id": row["chat_id"],
                "expires_at": row["expires_at"],
                "used_at": row["used_at"],
                "created_at": row["created_at"],
            }

    def mark_connect_service_code_used(self, code: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE connect_service_codes SET used_at = ? WHERE code = ?
            """, (now, code))
            conn.commit()

    def list_connected_services_for_tenant(self, tenant_id: str) -> List[str]:
        """Return list of tool_name values that have at least one credential for this tenant."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT tool_name FROM credentials
                WHERE tenant_id = ? AND tool_name IN ('gmail', 'google_calendar', 'brave_search', 'github', 'elevenlabs')
                ORDER BY tool_name
            """, (tenant_id,))
            return [row["tool_name"] for row in cursor.fetchall()]

    def upsert_channel_binding(
        self,
        tenant_id: str,
        channel: str,
        external_user_id: str,
        external_chat_id: Optional[str] = None,
        username: Optional[str] = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO channel_bindings
                (tenant_id, channel, external_user_id, external_chat_id, username, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
                ON CONFLICT(channel, external_user_id)
                DO UPDATE SET
                  tenant_id = excluded.tenant_id,
                  external_chat_id = excluded.external_chat_id,
                  username = excluded.username,
                  status = 'active',
                  updated_at = excluded.updated_at
            """, (tenant_id, channel, external_user_id, external_chat_id, username, now, now))
            conn.commit()

    def create_channel_token(
        self,
        tenant_id: str,
        channel: str,
        external_user_id: Optional[str] = None,
        token_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a channel token and return {id, raw_token}."""
        import uuid
        import secrets
        import hashlib
        raw_token = secrets.token_hex(24)
        key_hash = token_hash or hashlib.sha256(raw_token.encode()).hexdigest()
        token_id = f"cht_{uuid.uuid4().hex[:16]}"
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO channel_tokens
                (id, tenant_id, channel, external_user_id, token_hash, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'active', ?)
            """, (token_id, tenant_id, channel, external_user_id, key_hash, now))
            conn.commit()
        return {"id": token_id, "raw_token": raw_token}

    def get_channel_token_by_hash(self, key_hash: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM channel_tokens WHERE token_hash = ? AND status = 'active'
            """, (key_hash,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "tenant_id": row["tenant_id"],
                "channel": row["channel"],
                "external_user_id": row["external_user_id"],
                "status": row["status"],
                "created_at": row["created_at"],
                "last_used_at": row["last_used_at"],
            }

    def update_channel_token_last_used(self, token_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE channel_tokens
                SET last_used_at = ?
                WHERE id = ?
            """, (now, token_id))
            conn.commit()

    def get_tenant_channel_connections(self, tenant_id: str) -> List[str]:
        """Return list of channel names (e.g. telegram, slack, discord) that have an active binding for this tenant."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT channel FROM channel_bindings
                WHERE tenant_id = ? AND status = 'active'
            """, (tenant_id,))
            return [row["channel"] for row in cursor.fetchall()]

    def get_tenant_alert_preferences(self, tenant_id: str) -> Dict[str, Any]:
        """Get alert preferences for a tenant. Returns defaults if none set."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT preferences FROM tenant_alert_preferences WHERE tenant_id = ?
            """, (tenant_id,))
            row = cursor.fetchone()
        if not row or not row["preferences"]:
            return {
                "alert_on_blocked": True,
                "alert_on_policy_violation": True,
                "alert_on_drift": True,
                "alert_on_escalation": True,
            }
        import json
        try:
            data = json.loads(row["preferences"])
            return {
                "alert_on_blocked": data.get("alert_on_blocked", True),
                "alert_on_policy_violation": data.get("alert_on_policy_violation", True),
                "alert_on_drift": data.get("alert_on_drift", True),
                "alert_on_escalation": data.get("alert_on_escalation", True),
            }
        except Exception:
            return {
                "alert_on_blocked": True,
                "alert_on_policy_violation": True,
                "alert_on_drift": True,
                "alert_on_escalation": True,
            }

    def set_tenant_alert_preferences(self, tenant_id: str, preferences: Dict[str, Any]) -> None:
        """Set alert preferences for a tenant. Merges with existing so partial updates work."""
        import json
        now = datetime.now(UTC).isoformat()
        allowed = ("alert_on_blocked", "alert_on_policy_violation", "alert_on_drift", "alert_on_escalation")
        current = self.get_tenant_alert_preferences(tenant_id)
        payload = {k: bool(preferences.get(k, current.get(k, True))) for k in allowed}
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tenant_alert_preferences (tenant_id, preferences, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(tenant_id) DO UPDATE SET
                  preferences = excluded.preferences,
                  updated_at = excluded.updated_at
            """, (tenant_id, json.dumps(payload), now))
            conn.commit()

    
    # Usage tracking methods
    def increment_tenant_usage(self, tenant_id: str, count: int = 1):
        """Increment tenant usage counter for current period.
        
        Args:
            tenant_id: Tenant identifier
            count: Number of requests to add
        """
        from datetime import date
        period_start = date.today().isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Try to update existing record
            cursor.execute("""
                UPDATE tenant_usage 
                SET requests_count = requests_count + ?
                WHERE tenant_id = ? AND period_start = ?
            """, (count, tenant_id, period_start))
            
            # If no record exists, create one
            if cursor.rowcount == 0:
                cursor.execute("""
                    INSERT INTO tenant_usage (tenant_id, period_start, requests_count)
                    VALUES (?, ?, ?)
                """, (tenant_id, period_start, count))
            
            conn.commit()
    
    def get_tenant_usage(self, tenant_id: str, period_start: Optional[str] = None) -> int:
        """Get tenant usage for a period.
        
        Args:
            tenant_id: Tenant identifier
            period_start: Period start date (YYYY-MM-DD), defaults to today
            
        Returns:
            Number of requests in the period
        """
        from datetime import date
        if period_start is None:
            period_start = date.today().isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT requests_count 
                FROM tenant_usage 
                WHERE tenant_id = ? AND period_start = ?
            """, (tenant_id, period_start))
            row = cursor.fetchone()
            return row["requests_count"] if row else 0

    # Memory: long-term preferences (KV per tenant)
    def write_preference(self, tenant_id: str, key: str, value: str) -> None:
        """Write a preference (intentional, governor-approved)."""
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO preference_memory (tenant_id, key, value, updated_at)
                VALUES (?, ?, ?, ?)
            """, (tenant_id, key, value, now))
            conn.commit()

    def read_preferences(self, tenant_id: str, keys: Optional[List[str]] = None) -> Dict[str, str]:
        """Read preferences. If keys is None, return all for tenant."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if keys:
                placeholders = ",".join("?" * len(keys))
                cursor.execute(
                    f"""
                    SELECT key, value FROM preference_memory
                    WHERE tenant_id = ? AND key IN ({placeholders})
                    """,
                    (tenant_id, *keys),
                )
            else:
                cursor.execute(
                    "SELECT key, value FROM preference_memory WHERE tenant_id = ?",
                    (tenant_id,),
                )
            rows = cursor.fetchall()
            return {row["key"]: row["value"] for row in rows} if rows else {}

    # Memory: episodic task memory
    def append_episode(
        self,
        tenant_id: str,
        episode_id: str,
        task_summary: str,
        outcome: Optional[str] = None,
        tool: Optional[str] = None,
        op: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Append an episode (intentional, governor-approved)."""
        now = datetime.now(UTC).isoformat()
        ctx_json = json.dumps(context) if context else None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO episodic_memory
                (tenant_id, episode_id, task_summary, outcome, tool, op, context, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (tenant_id, episode_id, task_summary, outcome or "", tool or "", op or "", ctx_json, now))
            conn.commit()

    def query_episodes(
        self,
        tenant_id: str,
        limit: int = 50,
        since: Optional[str] = None,
        tool: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Query episodic memory (most recent first)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            sql = """
                SELECT episode_id, task_summary, outcome, tool, op, context, created_at
                FROM episodic_memory WHERE tenant_id = ?
            """
            params: List[Any] = [tenant_id]
            if since:
                sql += " AND created_at >= ?"
                params.append(since)
            if tool:
                sql += " AND tool = ?"
                params.append(tool)
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            out = []
            for row in rows:
                ctx = json.loads(row["context"]) if row["context"] else None
                out.append({
                    "episode_id": row["episode_id"],
                    "task_summary": row["task_summary"],
                    "outcome": row["outcome"],
                    "tool": row["tool"],
                    "op": row["op"],
                    "context": ctx,
                    "created_at": row["created_at"],
                })
            return out

    # ── Human Review Queue methods ─────────────────────────────────────────────

    def get_review_queue(self, tenant_id: Optional[str] = None, status: str = "pending", limit: int = 50) -> List[Dict[str, Any]]:
        """Get human review queue items."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Ensure table exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS review_queue (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT,
                    action_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    context TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    decision TEXT,
                    reviewer_id TEXT,
                    reviewer_reason TEXT,
                    timeout_seconds INTEGER DEFAULT 300,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
                )
            """)
            conn.commit()
            q = "SELECT * FROM review_queue WHERE status = ?"
            params: List[Any] = [status]
            if tenant_id:
                q += " AND tenant_id = ?"
                params.append(tenant_id)
            q += f" ORDER BY created_at DESC LIMIT {int(limit)}"
            cursor.execute(q, params)
            return [dict(row) for row in cursor.fetchall()]

    def enqueue_review(self, tenant_id: str, action_id: str, agent_id: str,
                       action_type: str, reason: str, context: Optional[dict] = None,
                       timeout_seconds: int = 300) -> str:
        """Add an action to the human review queue."""
        import uuid as _uuid
        review_id = str(_uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS review_queue (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT,
                    action_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    context TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    decision TEXT,
                    reviewer_id TEXT,
                    reviewer_reason TEXT,
                    timeout_seconds INTEGER DEFAULT 300,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                INSERT INTO review_queue (id, tenant_id, action_id, agent_id, action_type, reason, context, timeout_seconds, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (review_id, tenant_id, action_id, agent_id, action_type, reason,
                  json.dumps(context or {}), timeout_seconds, now))
            conn.commit()
        return review_id

    def resolve_review_item(self, review_id: str, decision: str, reviewer_id: str, reason: str = "") -> bool:
        """Resolve a review queue item with a human decision.

        Also backfills human_override_actor_id on the linked audit event so the
        audit trail records which individual (doctor/nurse) approved or denied the action.
        """
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Fetch the action_id linked to this review item before updating
            cursor.execute("SELECT action_id FROM review_queue WHERE id = ? AND status = 'pending'", (review_id,))
            row = cursor.fetchone()
            if not row:
                return False

            action_id = row[0] if isinstance(row, (list, tuple)) else row["action_id"]

            cursor.execute("""
                UPDATE review_queue
                SET status = ?, decision = ?, reviewer_id = ?, reviewer_reason = ?, resolved_at = ?
                WHERE id = ? AND status = 'pending'
            """, (decision + "d", decision, reviewer_id, reason, now, review_id))

            # Backfill the audit event with reviewer identity
            if action_id:
                cursor.execute("""
                    UPDATE audit_events
                    SET human_override = 1,
                        human_override_actor_id = ?,
                        human_override_reason = ?
                    WHERE action_id = ?
                """, (reviewer_id, reason, action_id))

            conn.commit()
            return cursor.rowcount > 0

    # ── Agent registration for max_agents plan enforcement ─────────────────────

    def register_agent(self, tenant_id: str, agent_id: str) -> bool:
        """Register an agent for a tenant.  Returns True if this is a new agent,
        False if the agent was already registered.
        New agents get an automatic display_name: agent_1, agent_2, ... agent_N.
        """
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            count = self.get_agent_count(tenant_id)
            display_name = f"agent_{count + 1}"
            cursor.execute("""
                INSERT OR IGNORE INTO tenant_agents (tenant_id, agent_id, first_seen, display_name)
                VALUES (?, ?, ?, ?)
            """, (tenant_id, agent_id, now, display_name))
            conn.commit()
            return cursor.rowcount > 0

    def get_agent_count(self, tenant_id: str) -> int:
        """Return the number of distinct agents registered for a tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Count of registered agents
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM tenant_agents WHERE tenant_id = ?",
                (tenant_id,),
            )
            row = cursor.fetchone()
            return row[0] if row else 0

    def get_tenant_agents(self, tenant_id: str) -> list[dict]:
        """Return all registered agents for a tenant. Each has agent_id, display_name (e.g. agent_1, agent_2), first_seen.
        Agents without a display_name get one assigned: agent_1, agent_2, ... by first_seen order, and it is persisted.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT agent_id, display_name, first_seen FROM tenant_agents WHERE tenant_id = ? ORDER BY first_seen ASC",
                (tenant_id,),
            )
            rows = cursor.fetchall()
        result = []
        for i, row in enumerate(rows):
            display_name = row["display_name"] if row["display_name"] else None
            if not display_name:
                display_name = f"agent_{i + 1}"
                self.set_agent_display_name(tenant_id, row["agent_id"], display_name)
            result.append({
                "agent_id": row["agent_id"],
                "display_name": display_name,
                "first_seen": row["first_seen"],
            })
        result.reverse()
        return result

    def set_agent_display_name(self, tenant_id: str, agent_id: str, display_name: Optional[str]) -> bool:
        """Set or clear the display name for an agent. Agent must already be registered.

        Returns:
            True if a row was updated, False if agent not found for tenant
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE tenant_agents SET display_name = ? WHERE tenant_id = ? AND agent_id = ?",
                (display_name.strip() if display_name and display_name.strip() else None, tenant_id, agent_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    # ── Audit retention enforcement ────────────────────────────────────────────

    def delete_expired_audit_events(self, tenant_id: str, retention_days: int) -> int:
        """Delete audit events older than retention_days for a tenant.

        Because audit_events has an append-only trigger, this method
        temporarily drops the delete trigger, performs the delete, and then
        recreates the trigger — all within a single connection so no other
        writer can interleave.

        Args:
            tenant_id: Tenant identifier (matched against customer_id column)
            retention_days: Number of days to retain; older rows are deleted

        Returns:
            Number of rows deleted
        """
        from datetime import timedelta
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Temporarily remove the append-only delete trigger
            cursor.execute("DROP TRIGGER IF EXISTS audit_events_append_only_delete")
            # Delete expired rows for this tenant (matched by customer_id)
            cursor.execute("""
                DELETE FROM audit_events
                WHERE customer_id = ? AND created_at < ?
            """, (tenant_id, cutoff))
            deleted = cursor.rowcount
            # Recreate the append-only delete trigger
            cursor.execute("""
                CREATE TRIGGER audit_events_append_only_delete
                BEFORE DELETE ON audit_events
                FOR EACH ROW BEGIN
                    SELECT RAISE(ABORT, 'audit_events is append-only: deletes not allowed');
                END
            """)
            conn.commit()
        return deleted

    # ── Agent Registry methods ─────────────────────────────────────────────────

    def register_agent_full(
        self,
        agent_id: str,
        tenant_id: str,
        name: str,
        agent_type: str = "software",
        description: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        policy_pack: Optional[str] = None,
        mag_enabled: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        vendor_id: Optional[str] = None,
        department: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Register or update a full agent record in the agents table.

        Returns:
            Agent dict as stored.
        """
        now = datetime.now(UTC).isoformat()
        caps_json = json.dumps(capabilities or [])
        meta_json = json.dumps(metadata or {})
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO agents
                    (agent_id, tenant_id, name, agent_type, description, capabilities,
                     policy_pack, mag_enabled, cav_enabled, status, registered_at,
                     last_seen_at, total_actions, total_allowed, total_blocked,
                     total_escalated, metadata, vendor_id, department)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'active', ?, ?, 0, 0, 0, 0, ?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    name = excluded.name,
                    agent_type = excluded.agent_type,
                    description = excluded.description,
                    capabilities = excluded.capabilities,
                    policy_pack = excluded.policy_pack,
                    mag_enabled = excluded.mag_enabled,
                    metadata = excluded.metadata,
                    last_seen_at = excluded.last_seen_at,
                    vendor_id = COALESCE(excluded.vendor_id, agents.vendor_id),
                    department = COALESCE(excluded.department, agents.department)
            """, (
                agent_id, tenant_id, name, agent_type, description, caps_json,
                policy_pack, 1 if mag_enabled else 0, now, now, meta_json, vendor_id, department,
            ))
            conn.commit()
        return self.get_agent(agent_id) or {}

    def get_agent_vendor_id(self, agent_id: str, tenant_id: str) -> Optional[str]:
        """Fast lookup of vendor_id for an agent. Returns None if agent not found or vendor not set."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT vendor_id FROM agents WHERE agent_id=? AND tenant_id=?",
                (agent_id, tenant_id),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def get_agent(self, agent_id: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get a registered agent by ID, optionally scoped to a tenant."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if tenant_id is not None:
                cursor.execute(
                    "SELECT * FROM agents WHERE agent_id = ? AND tenant_id = ?",
                    (agent_id, tenant_id),
                )
            else:
                cursor.execute("SELECT * FROM agents WHERE agent_id = ?", (agent_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "agent_id": row["agent_id"],
                "tenant_id": row["tenant_id"],
                "name": row["name"],
                "agent_type": row["agent_type"],
                "description": row["description"],
                "capabilities": json.loads(row["capabilities"]) if row["capabilities"] else [],
                "policy_pack": row["policy_pack"],
                "mag_enabled": bool(row["mag_enabled"]),
                "cav_enabled": bool(row["cav_enabled"]),
                "status": row["status"],
                "registered_at": row["registered_at"],
                "last_seen_at": row["last_seen_at"],
                "total_actions": row["total_actions"],
                "total_allowed": row["total_allowed"],
                "total_blocked": row["total_blocked"],
                "total_escalated": row["total_escalated"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                "department": row["department"] if "department" in row.keys() else None,
            }

    def list_agents(self, tenant_id: str) -> List[Dict[str, Any]]:
        """List all agents for a tenant."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM agents WHERE tenant_id = ? ORDER BY registered_at DESC",
                (tenant_id,),
            )
            rows = cursor.fetchall()
        result = []
        for row in rows:
            result.append({
                "agent_id": row["agent_id"],
                "tenant_id": row["tenant_id"],
                "name": row["name"],
                "agent_type": row["agent_type"],
                "description": row["description"],
                "capabilities": json.loads(row["capabilities"]) if row["capabilities"] else [],
                "policy_pack": row["policy_pack"],
                "mag_enabled": bool(row["mag_enabled"]),
                "cav_enabled": bool(row["cav_enabled"]),
                "status": row["status"],
                "registered_at": row["registered_at"],
                "last_seen_at": row["last_seen_at"],
                "total_actions": row["total_actions"],
                "total_allowed": row["total_allowed"],
                "total_blocked": row["total_blocked"],
                "total_escalated": row["total_escalated"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                "department": row["department"] if "department" in row.keys() else None,
            })
        return result

    def update_agent_stats(self, agent_id: str, verdict: str, tenant_id: Optional[str] = None) -> None:
        """Increment total_actions and the matching verdict counter; update last_seen_at.

        Updates the agents table (primary registry) when an agents row exists,
        and also upserts agent_stats (used by the Agents API for richer breakdown).
        This is a non-blocking helper — any DB error is logged but not raised.

        Args:
            agent_id:  Agent identifier.
            verdict:   One of ALLOW, BLOCK, ESCALATE, DEGRADE, PAUSE, ERROR (case-insensitive).
            tenant_id: Optional tenant scope.  When None, skips agent_stats upsert.
        """
        if not agent_id:
            return

        now = datetime.now(UTC).isoformat()
        verdict_upper = (verdict or "").upper()

        # Map for the agents table (has total_allowed/total_blocked/total_escalated)
        agents_col_map = {
            "ALLOW":    "total_allowed",
            "BLOCK":    "total_blocked",
            "ESCALATE": "total_escalated",
        }
        # Map for the agent_stats table (finer-grained, includes degrade/pause/error)
        stats_col_map = {
            "ALLOW":    "allow_count",
            "BLOCK":    "block_count",
            "ESCALATE": "escalate_count",
            "DEGRADE":  "degrade_count",
            "PAUSE":    "pause_count",
            "ERROR":    "error_count",
        }

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # ── 1. Update agents table (best-effort; row may not exist) ──────────
                agents_col = agents_col_map.get(verdict_upper)
                if agents_col:
                    cursor.execute(
                        f"UPDATE agents SET total_actions = total_actions + 1, "  # safe: col from allowlist
                        f"{agents_col} = {agents_col} + 1, last_seen_at = ? "
                        f"WHERE agent_id = ?",
                        (now, agent_id),
                    )
                else:
                    cursor.execute(
                        "UPDATE agents SET total_actions = total_actions + 1, last_seen_at = ? WHERE agent_id = ?",
                        (now, agent_id),
                    )

                # ── 2. Upsert agent_stats table (finer-grained, used by Agents API) ─
                if tenant_id:
                    stats_col = stats_col_map.get(verdict_upper, "error_count")
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS agent_stats (
                            tenant_id      TEXT NOT NULL,
                            agent_id       TEXT NOT NULL,
                            total_actions  INTEGER NOT NULL DEFAULT 0,
                            allow_count    INTEGER NOT NULL DEFAULT 0,
                            block_count    INTEGER NOT NULL DEFAULT 0,
                            escalate_count INTEGER NOT NULL DEFAULT 0,
                            degrade_count  INTEGER NOT NULL DEFAULT 0,
                            pause_count    INTEGER NOT NULL DEFAULT 0,
                            error_count    INTEGER NOT NULL DEFAULT 0,
                            last_action_at TEXT,
                            PRIMARY KEY (tenant_id, agent_id)
                        )
                    """)
                    # stats_col is sourced from a fixed allowlist above, not user input.
                    upsert_sql = (
                        f"INSERT INTO agent_stats "
                        f"(tenant_id, agent_id, total_actions, {stats_col}, last_action_at) "
                        f"VALUES (?, ?, 1, 1, ?) "
                        f"ON CONFLICT(tenant_id, agent_id) DO UPDATE SET "
                        f"total_actions  = total_actions + 1, "
                        f"{stats_col}    = {stats_col} + 1, "
                        f"last_action_at = excluded.last_action_at"
                    )
                    cursor.execute(upsert_sql, (tenant_id, agent_id, now))

                conn.commit()
        except Exception as _err:
            import logging as _log
            _log.getLogger(__name__).warning(
                "update_agent_stats failed (non-blocking): agent=%s verdict=%s err=%s",
                agent_id, verdict, _err,
            )

    def update_agent_status(self, agent_id: str, tenant_id: str, status: str) -> bool:
        """Update an agent's lifecycle status (active, paused, retired).

        Returns:
            True if the row was updated.
        """
        valid = {"active", "paused", "retired"}
        if status not in valid:
            raise ValueError(f"Invalid agent status '{status}'. Must be one of {valid}")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE agents SET status = ? WHERE agent_id = ? AND tenant_id = ?",
                (status, agent_id, tenant_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def upsert_agent_behavioral_window(self, agent_id: str, window_json: str) -> None:
        """Store the latest behavioral CAV window snapshot for an agent."""
        now = datetime.now(UTC).isoformat()
        try:
            data = json.loads(window_json)
        except Exception:
            data = {}
        signals = data.get("signals", {})
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO agent_behavioral_windows
                    (agent_id, timestamp, actions_per_min, error_rate, tool_switch_rate,
                     risk_trend, retry_count, session_duration_mins, cav_score, cav_state,
                     raw_window, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                agent_id,
                data.get("timestamp", now),
                signals.get("actions_per_min"),
                signals.get("error_rate"),
                signals.get("tool_switch_rate"),
                signals.get("risk_trend"),
                signals.get("retry_rate"),
                signals.get("session_duration_mins"),
                data.get("cav_score"),
                data.get("cav_state"),
                window_json,
                now,
            ))
            conn.commit()

    def get_agent_behavioral_history(self, agent_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Return recent audit events for a given agent_id (most recent first)."""
        return self.query_audit_events(agent_id=agent_id, limit=limit)

    # ── Sandbox ────────────────────────────────────────────────────────────────

    def get_or_create_sandbox_tenant(self) -> Dict[str, Any]:
        """Idempotently create the sandbox user, tenant, and API key.

        The sandbox tenant (tenant_sandbox_edon) lets developers explore the
        governance API without billing setup.  The API key is the well-known
        dev-only value: ``edon_sandbox_key_dev_only``.

        Returns:
            dict with tenant_id, user_id, status
        """
        SANDBOX_USER_ID = "user_sandbox_edon"
        SANDBOX_TENANT_ID = "tenant_sandbox_edon"
        SANDBOX_KEY = "edon_sandbox_key_dev_only"
        key_hash = hashlib.sha256(SANDBOX_KEY.encode()).hexdigest()
        now = datetime.now(UTC).isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO users
                    (id, email, auth_provider, auth_subject, role, created_at, updated_at)
                VALUES (?, 'sandbox@edon.dev', 'sandbox', ?, 'admin', ?, ?)
            """, (SANDBOX_USER_ID, SANDBOX_USER_ID, now, now))
            cursor.execute("""
                INSERT OR IGNORE INTO tenants
                    (id, user_id, status, plan, mag_enabled, created_at, updated_at)
                VALUES (?, ?, 'active', 'enterprise', 0, ?, ?)
            """, (SANDBOX_TENANT_ID, SANDBOX_USER_ID, now, now))
            cursor.execute("""
                INSERT OR IGNORE INTO api_keys
                    (id, tenant_id, key_hash, name, status, role, created_at)
                VALUES ('key_sandbox', ?, ?, 'Sandbox Dev Key', 'active', 'admin', ?)
            """, (SANDBOX_TENANT_ID, key_hash, now))
            conn.commit()

        return {"tenant_id": SANDBOX_TENANT_ID, "user_id": SANDBOX_USER_ID, "status": "active"}

    def reset_sandbox(self) -> int:
        """Delete all rows from sandbox_audit_events and return the count deleted."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM sandbox_audit_events")
            row = cursor.fetchone()
            count = row[0] if row else 0
            cursor.execute("DELETE FROM sandbox_audit_events")
            conn.commit()
        return count

    def insert_sandbox_event(self, event: Dict[str, Any]) -> None:
        """Insert a single event into sandbox_audit_events."""
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sandbox_audit_events
                    (timestamp, action_id, action_tool, action_op, action_params,
                     action_source, action_estimated_risk, action_computed_risk,
                     decision_verdict, decision_reason_code, decision_explanation,
                     decision_policy_version, policy_rule_id, action_summary,
                     stated_intent, agent_id, customer_id, context,
                     anomaly_score, processing_latency_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.get("timestamp", now),
                event["action_id"],
                event["action_tool"],
                event["action_op"],
                json.dumps(event.get("action_params", {})),
                event.get("action_source", "agent"),
                event.get("action_estimated_risk", "low"),
                event.get("action_computed_risk"),
                event["decision_verdict"],
                event["decision_reason_code"],
                event["decision_explanation"],
                event.get("decision_policy_version", "1.0.0"),
                event.get("policy_rule_id"),
                event.get("action_summary"),
                event.get("stated_intent"),
                event.get("agent_id"),
                event.get("customer_id", "tenant_sandbox_edon"),
                json.dumps(event.get("context", {})),
                event.get("anomaly_score"),
                event.get("processing_latency_ms"),
                now,
            ))
            conn.commit()

    # ── Clinical Safety Mode ───────────────────────────────────────────────────

    def activate_clinical_safety_mode(
        self, tenant_id: str, activated_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """Seed all Clinical Safety Mode rules for a tenant.

        Rules are inserted with protected=1 and regulation=<code>.
        Already-existing rules (matched by rule_code) are updated in-place
        (re-enabled and re-protected) so re-activation is idempotent.

        Returns summary: rules_created, rules_updated.
        """
        from ..clinical_safety import CLINICAL_SAFETY_RULES
        import uuid as _uuid

        created = 0
        updated = 0
        now = datetime.now(UTC).isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            for rule in CLINICAL_SAFETY_RULES:
                tags_json = json.dumps(rule["condition_tags"]) if rule.get("condition_tags") else None
                # Check if rule_code already exists for this tenant
                cursor.execute(
                    "SELECT id FROM policy_rules WHERE tenant_id=? AND rule_code=?",
                    (tenant_id, rule["rule_code"]),
                )
                existing = cursor.fetchone()
                if existing:
                    cursor.execute("""
                        UPDATE policy_rules
                        SET enabled=1, protected=1, regulation=?,
                            name=?, description=?, action=?,
                            condition_tool=?, condition_op=?, condition_risk_level=?,
                            condition_tags=?, priority=?, updated_at=?
                        WHERE tenant_id=? AND rule_code=?
                    """, (
                        rule["regulation"], rule["name"], rule["description"],
                        rule["action"], rule.get("condition_tool"),
                        rule.get("condition_op"), rule.get("condition_risk_level"),
                        tags_json, rule["priority"], now,
                        tenant_id, rule["rule_code"],
                    ))
                    updated += 1
                else:
                    rule_id = str(_uuid.uuid4())
                    cursor.execute("""
                        INSERT INTO policy_rules
                            (id, tenant_id, name, description, condition_tool,
                             condition_op, condition_risk_level, condition_tags,
                             action, priority, enabled, rule_code, protected,
                             regulation, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 1, ?, ?, ?)
                    """, (
                        rule_id, tenant_id, rule["name"], rule["description"],
                        rule.get("condition_tool"), rule.get("condition_op"),
                        rule.get("condition_risk_level"), tags_json,
                        rule["action"], rule["priority"],
                        rule["rule_code"], rule["regulation"], now, now,
                    ))
                    created += 1
            conn.commit()

        # Log to policy changes
        self.log_policy_change(
            tenant_id=tenant_id,
            change_type="apply_pack",
            entity_type="clinical_safety_mode",
            entity_name="Clinical Safety Mode",
            diff_json={"rules_created": created, "rules_updated": updated,
                       "activated_by": activated_by},
            changed_by=activated_by,
        )
        return {"rules_created": created, "rules_updated": updated, "total": created + updated}

    def get_compliance_health(self, tenant_id: str) -> Dict[str, Any]:
        """Check each regulation's required rules are present and enabled.

        Returns overall status and per-regulation breakdown.
        """
        from ..clinical_safety import REQUIRED_RULES_BY_REGULATION, REGULATION_LABELS

        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Load all clinical safety rules for this tenant in one query
            cursor.execute("""
                SELECT rule_code, enabled, protected, regulation
                FROM policy_rules
                WHERE tenant_id=? AND rule_code IS NOT NULL
            """, (tenant_id,))
            rows = cursor.fetchall()

        rule_map: Dict[str, Dict] = {}
        for row in rows:
            rule_map[row[0]] = {
                "enabled": bool(row[1]),
                "protected": bool(row[2]),
                "regulation": row[3],
            }

        regulation_results: Dict[str, Any] = {}
        overall_pass = True

        for reg_code, required_codes in REQUIRED_RULES_BY_REGULATION.items():
            missing = []
            disabled = []
            unprotected = []

            for code in required_codes:
                if code not in rule_map:
                    missing.append(code)
                elif not rule_map[code]["enabled"]:
                    disabled.append(code)
                elif not rule_map[code]["protected"]:
                    unprotected.append(code)

            status = "pass"
            if missing or disabled:
                status = "fail"
                overall_pass = False
            elif unprotected:
                status = "warning"  # Rules exist and enabled, but not protected

            regulation_results[reg_code] = {
                "status": status,
                "label": REGULATION_LABELS.get(reg_code, reg_code),
                "rules_required": len(required_codes),
                "rules_active": len(required_codes) - len(missing) - len(disabled),
                "missing_rules": missing,
                "disabled_rules": disabled,
                "unprotected_rules": unprotected,
            }

        return {
            "overall": "pass" if overall_pass else "fail",
            "clinical_safety_mode_active": len(rule_map) > 0,
            "regulations": regulation_results,
            "checked_at": datetime.now(UTC).isoformat(),
        }

    def get_policy_rule_by_code(
        self, rule_code: str, tenant_id: str
    ) -> Optional[Dict[str, Any]]:
        """Look up a policy rule by its regulation rule_code."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM policy_rules WHERE tenant_id=? AND rule_code=?",
                (tenant_id, rule_code),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    # ── CI/CD Scans ──────────────────────────────────────────────────────────────

    def save_cicd_scan(self, tenant_id: str, scan_id: str, data: dict) -> None:
        """Persist a CI/CD scan result."""
        import json as _json
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cicd_scans (
                    scan_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    repo TEXT,
                    branch TEXT,
                    commit_sha TEXT,
                    gate_passed INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'unknown',
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                INSERT INTO cicd_scans (scan_id, tenant_id, repo, branch, commit_sha, gate_passed, status, data, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scan_id) DO UPDATE SET
                  gate_passed = excluded.gate_passed,
                  status = excluded.status,
                  data = excluded.data
            """, (
                scan_id,
                tenant_id,
                data.get("repo"),
                data.get("branch"),
                data.get("commit_sha"),
                1 if data.get("gate_passed") else 0,
                data.get("status", "unknown"),
                _json.dumps(data),
                now,
            ))
            conn.commit()

    def get_cicd_scan(self, scan_id: str, tenant_id: Optional[str] = None) -> Optional[dict]:
        """Fetch a CI/CD scan by ID."""
        import json as _json
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if tenant_id:
                cursor.execute(
                    "SELECT data FROM cicd_scans WHERE scan_id=? AND tenant_id=?",
                    (scan_id, tenant_id),
                )
            else:
                cursor.execute("SELECT data FROM cicd_scans WHERE scan_id=?", (scan_id,))
            row = cursor.fetchone()
        if not row:
            return None
        try:
            return _json.loads(row[0] if not hasattr(row, "keys") else row["data"])
        except Exception:
            return None

    def list_cicd_scans(self, tenant_id: str, limit: int = 25, repo: Optional[str] = None) -> list:
        """List recent CI/CD scans for a tenant, newest-first."""
        import json as _json
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if repo:
                cursor.execute(
                    "SELECT data FROM cicd_scans WHERE tenant_id=? AND repo=? ORDER BY created_at DESC LIMIT ?",
                    (tenant_id, repo, limit),
                )
            else:
                cursor.execute(
                    "SELECT data FROM cicd_scans WHERE tenant_id=? ORDER BY created_at DESC LIMIT ?",
                    (tenant_id, limit),
                )
            rows = cursor.fetchall()
        result = []
        for row in rows:
            try:
                result.append(_json.loads(row[0] if not hasattr(row, "keys") else row["data"]))
            except Exception:
                pass
        return result

    # ── Hardening Results ─────────────────────────────────────────────────────────

    def save_hardening_result(self, tenant_id: str, result: dict) -> None:
        """Persist the last hardening run result for a tenant."""
        import json as _json
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tenant_settings (
                    tenant_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, key)
                )
            """)
            cursor.execute("""
                INSERT INTO tenant_settings (tenant_id, key, value, updated_at)
                VALUES (?, 'hardening_result', ?, ?)
                ON CONFLICT(tenant_id, key) DO UPDATE SET
                  value = excluded.value, updated_at = excluded.updated_at
            """, (tenant_id, _json.dumps(result), now))
            conn.commit()

    def get_hardening_result(self, tenant_id: str) -> Optional[dict]:
        """Fetch the last hardening run result for a tenant."""
        import json as _json
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tenant_settings (
                    tenant_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, key)
                )
            """)
            conn.commit()
            cursor.execute(
                "SELECT value FROM tenant_settings WHERE tenant_id=? AND key='hardening_result'",
                (tenant_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        try:
            return _json.loads(row[0] if not hasattr(row, "keys") else row["value"])
        except Exception:
            return None

    # ── Kill Switch ──────────────────────────────────────────────────────────────

    def get_kill_switch(self, tenant_id: str) -> dict:
        """Return current kill switch state for tenant from DB."""
        import json as _json
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tenant_settings (
                    tenant_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, key)
                )
            """)
            conn.commit()
            cursor.execute(
                "SELECT value FROM tenant_settings WHERE tenant_id=? AND key='kill_switch'",
                (tenant_id,),
            )
            row = cursor.fetchone()
        if not row:
            return {"active": False, "tenant_id": tenant_id}
        try:
            return _json.loads(row["value"] if hasattr(row, "keys") else row[0])
        except Exception:
            return {"active": False, "tenant_id": tenant_id}

    def set_kill_switch(self, tenant_id: str, state: dict) -> None:
        """Persist kill switch state to DB."""
        import json as _json
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tenant_settings (
                    tenant_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, key)
                )
            """)
            cursor.execute("""
                INSERT INTO tenant_settings (tenant_id, key, value, updated_at)
                VALUES (?, 'kill_switch', ?, ?)
                ON CONFLICT(tenant_id, key) DO UPDATE SET
                  value = excluded.value, updated_at = excluded.updated_at
            """, (tenant_id, _json.dumps(state), now))
            conn.commit()

    # ── Escalations (human review queue) ─────────────────────────────────────────

    def save_escalation(self, decision_id: str, record: dict) -> None:
        """Upsert an escalation record. Called on enqueue and on every status change."""
        import json as _json
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS escalations (
                    decision_id TEXT PRIMARY KEY,
                    tenant_id   TEXT,
                    status      TEXT NOT NULL DEFAULT 'pending',
                    data        TEXT NOT NULL,
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                )
            """)
            conn.execute("""
                INSERT INTO escalations (decision_id, tenant_id, status, data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(decision_id) DO UPDATE SET
                    status = excluded.status,
                    data   = excluded.data,
                    updated_at = excluded.updated_at
            """, (
                decision_id,
                record.get("tenant_id"),
                record.get("status", "pending"),
                _json.dumps(record),
                record.get("created_at", now),
                now,
            ))
            conn.commit()

    def list_escalations(
        self,
        tenant_id: Optional[str] = None,
        status: Optional[str] = "pending",
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """Return escalation records from DB, newest first."""
        import json as _json
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS escalations (
                    decision_id TEXT PRIMARY KEY,
                    tenant_id   TEXT,
                    status      TEXT NOT NULL DEFAULT 'pending',
                    data        TEXT NOT NULL,
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                )
            """)
            q = "SELECT data FROM escalations WHERE 1=1"
            params: List[Any] = []
            if status:
                q += " AND status = ?"
                params.append(status)
            if tenant_id:
                q += " AND tenant_id = ?"
                params.append(tenant_id)
            q += f" ORDER BY created_at DESC LIMIT {int(limit)}"
            cursor = conn.execute(q, params)
            rows = cursor.fetchall()
        out = []
        for row in rows:
            try:
                raw = row["data"] if hasattr(row, "keys") else row[0]
                out.append(_json.loads(raw))
            except Exception:
                pass
        return out

    # ── Per-tenant fine-tuned models ──────────────────────────────────────────────

    def save_tenant_model(
        self,
        tenant_id: str,
        job_id: str,
        model_id: str = "",
        status: str = "training",
    ) -> None:
        """Upsert the fine-tuning job/model record for a tenant."""
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tenant_models (
                    tenant_id  TEXT PRIMARY KEY,
                    job_id     TEXT NOT NULL,
                    model_id   TEXT NOT NULL DEFAULT '',
                    status     TEXT NOT NULL DEFAULT 'training',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                INSERT INTO tenant_models (tenant_id, job_id, model_id, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id) DO UPDATE SET
                    job_id     = excluded.job_id,
                    model_id   = CASE WHEN excluded.model_id != '' THEN excluded.model_id ELSE model_id END,
                    status     = excluded.status,
                    updated_at = excluded.updated_at
            """, (tenant_id, job_id, model_id, status, now, now))
            conn.commit()

    def get_tenant_model(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Return the active fine-tuned model record for a tenant, or None."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tenant_models (
                    tenant_id  TEXT PRIMARY KEY,
                    job_id     TEXT NOT NULL,
                    model_id   TEXT NOT NULL DEFAULT '',
                    status     TEXT NOT NULL DEFAULT 'training',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            cursor = conn.execute(
                "SELECT tenant_id, job_id, model_id, status, created_at, updated_at "
                "FROM tenant_models WHERE tenant_id = ?",
                (tenant_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        if hasattr(row, "keys"):
            return dict(row)
        return {
            "tenant_id": row[0], "job_id": row[1], "model_id": row[2],
            "status": row[3], "created_at": row[4], "updated_at": row[5],
        }

    def count_new_audit_events(self, tenant_id: str, since: str) -> int:
        """Count labeled audit events for a tenant created after `since` (ISO timestamp)."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """SELECT COUNT(*) FROM audit_events
                   WHERE customer_id = ? AND created_at > ?
                   AND decision_explanation IS NOT NULL
                   AND LENGTH(decision_explanation) >= 20""",
                (tenant_id, since),
            )
            row = cursor.fetchone()
        return (row[0] if row else 0)

    # ── Fix proposals (shadow engine) ─────────────────────────────────────────────

    def save_fix_proposal(self, proposal_id: str, data: dict) -> None:
        """Upsert a fix proposal record."""
        import json as _json
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS fix_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    tenant_id   TEXT,
                    status      TEXT NOT NULL DEFAULT 'pending_review',
                    severity    TEXT,
                    data        TEXT NOT NULL,
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                )
            """)
            conn.execute("""
                INSERT INTO fix_proposals (proposal_id, tenant_id, status, severity, data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(proposal_id) DO UPDATE SET
                    status   = excluded.status,
                    data     = excluded.data,
                    updated_at = excluded.updated_at
            """, (
                proposal_id,
                data.get("tenant_id"),
                data.get("status", "pending_review"),
                data.get("severity"),
                _json.dumps(data),
                data.get("created_at", now),
                now,
            ))
            conn.commit()

    def list_fix_proposals(
        self,
        tenant_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """Return fix proposal records from DB, newest first."""
        import json as _json
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS fix_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    tenant_id   TEXT,
                    status      TEXT NOT NULL DEFAULT 'pending_review',
                    severity    TEXT,
                    data        TEXT NOT NULL,
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                )
            """)
            q = "SELECT data FROM fix_proposals WHERE 1=1"
            params: List[Any] = []
            if status:
                q += " AND status = ?"
                params.append(status)
            if tenant_id:
                q += " AND tenant_id = ?"
                params.append(tenant_id)
            q += f" ORDER BY created_at DESC LIMIT {int(limit)}"
            cursor = conn.execute(q, params)
            rows = cursor.fetchall()
        out = []
        for row in rows:
            try:
                raw = row["data"] if hasattr(row, "keys") else row[0]
                out.append(_json.loads(raw))
            except Exception:
                pass
        return out

    # ── Assistant Proposals ──────────────────────────────────────────────────────

    def save_assistant_proposal(self, tenant_id: str, proposal_id: str, data: dict) -> None:
        """Persist a pending assistant proposal so it survives restarts."""
        import json as _json
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS assistant_proposals (
                    proposal_id TEXT NOT NULL PRIMARY KEY,
                    tenant_id   TEXT NOT NULL,
                    status      TEXT NOT NULL DEFAULT 'pending',
                    data        TEXT NOT NULL,
                    created_at  TEXT NOT NULL
                )
            """)
            conn.execute("""
                INSERT INTO assistant_proposals (proposal_id, tenant_id, status, data, created_at)
                VALUES (?, ?, 'pending', ?, ?)
                ON CONFLICT(proposal_id) DO UPDATE SET
                  data=excluded.data, status=excluded.status
            """, (proposal_id, tenant_id, _json.dumps(data), now))
            conn.commit()

    def get_assistant_proposal(self, proposal_id: str, tenant_id: str) -> Optional[dict]:
        """Fetch a pending assistant proposal by ID, scoped to tenant."""
        import json as _json
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS assistant_proposals (
                    proposal_id TEXT NOT NULL PRIMARY KEY,
                    tenant_id   TEXT NOT NULL,
                    status      TEXT NOT NULL DEFAULT 'pending',
                    data        TEXT NOT NULL,
                    created_at  TEXT NOT NULL
                )
            """)
            conn.commit()
            row = conn.execute(
                "SELECT data FROM assistant_proposals WHERE proposal_id=? AND tenant_id=?",
                (proposal_id, tenant_id),
            ).fetchone()
        if not row:
            return None
        try:
            val = row[0] if not hasattr(row, "keys") else row["data"]
            return _json.loads(val)
        except Exception:
            return None

    # ── Assistant conversations & memory ──────────────────────────────────────

    def _ensure_assistant_tables(self, conn) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS assistant_conversations (
                id          TEXT PRIMARY KEY,
                tenant_id   TEXT NOT NULL,
                user_id     TEXT,
                title       TEXT,
                messages    TEXT NOT NULL DEFAULT '[]',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_asst_conv_tenant
            ON assistant_conversations(tenant_id, updated_at DESC)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS assistant_memories (
                id                      TEXT PRIMARY KEY,
                tenant_id               TEXT NOT NULL,
                category                TEXT NOT NULL,
                fact                    TEXT NOT NULL,
                confidence              REAL NOT NULL DEFAULT 1.0,
                source_conversation_id  TEXT,
                created_at              TEXT NOT NULL,
                updated_at              TEXT NOT NULL,
                superseded              INTEGER NOT NULL DEFAULT 0,
                pinned                  INTEGER NOT NULL DEFAULT 0,
                expires_at              TEXT,
                review_status           TEXT NOT NULL DEFAULT 'active',
                reviewed_at             TEXT,
                reviewed_by             TEXT,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_asst_mem_tenant
            ON assistant_memories(tenant_id, superseded, updated_at DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_asst_mem_tenant_active
            ON assistant_memories(tenant_id, pinned DESC, review_status, updated_at DESC)
        """)
        self._migrate_assistant_memory_columns(conn)
        conn.commit()

    def _migrate_assistant_memory_columns(self, conn) -> None:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(assistant_memories)")
        existing = {row["name"] for row in cursor.fetchall()}
        migrations = [
            ("pinned", "INTEGER NOT NULL DEFAULT 0"),
            ("expires_at", "TEXT"),
            ("review_status", "TEXT NOT NULL DEFAULT 'active'"),
            ("reviewed_at", "TEXT"),
            ("reviewed_by", "TEXT"),
        ]
        for column, ddl in migrations:
            if column not in existing:
                cursor.execute(f"ALTER TABLE assistant_memories ADD COLUMN {column} {ddl}")

    def save_conversation(
        self,
        conversation_id: str,
        tenant_id: str,
        messages: list,
        user_id: Optional[str] = None,
        title: Optional[str] = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            self._ensure_assistant_tables(conn)
            conn.execute("""
                INSERT INTO assistant_conversations (id, tenant_id, user_id, title, messages, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    messages   = excluded.messages,
                    title      = COALESCE(excluded.title, assistant_conversations.title),
                    updated_at = excluded.updated_at
            """, (conversation_id, tenant_id, user_id, title, json.dumps(messages), now, now))
            conn.commit()

    def get_conversations(self, tenant_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            self._ensure_assistant_tables(conn)
            rows = conn.execute("""
                SELECT id, title, created_at, updated_at,
                       json_array_length(messages) as turn_count
                FROM assistant_conversations
                WHERE tenant_id = ?
                ORDER BY updated_at DESC LIMIT ?
            """, (tenant_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def get_conversation(self, conversation_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            self._ensure_assistant_tables(conn)
            row = conn.execute(
                "SELECT * FROM assistant_conversations WHERE id=? AND tenant_id=?",
                (conversation_id, tenant_id),
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["messages"] = json.loads(d["messages"])
        except Exception:
            d["messages"] = []
        return d

    def upsert_memory(
        self,
        memory_id: str,
        tenant_id: str,
        category: str,
        fact: str,
        confidence: float = 1.0,
        source_conversation_id: Optional[str] = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            self._ensure_assistant_tables(conn)
            conn.execute("""
                INSERT INTO assistant_memories
                    (id, tenant_id, category, fact, confidence, source_conversation_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    fact       = excluded.fact,
                    confidence = excluded.confidence,
                    updated_at = excluded.updated_at,
                    superseded = 0
            """, (memory_id, tenant_id, category, fact, confidence, source_conversation_id, now, now))
            conn.commit()

    def get_memories(self, tenant_id: str, limit: int = 60, include_expired: bool = False) -> List[Dict[str, Any]]:
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            self._ensure_assistant_tables(conn)
            rows = conn.execute("""
                SELECT id, category, fact, confidence, source_conversation_id, updated_at,
                       pinned, expires_at, review_status, reviewed_at, reviewed_by
                FROM assistant_memories
                WHERE tenant_id = ? AND superseded = 0
                  AND (? = 1 OR expires_at IS NULL OR expires_at > ?)
                ORDER BY pinned DESC, confidence DESC, updated_at DESC
                LIMIT ?
            """, (tenant_id, 1 if include_expired else 0, now, limit)).fetchall()
        return [dict(r) for r in rows]

    def supersede_memory(self, memory_id: str, tenant_id: str) -> None:
        with self._get_connection() as conn:
            self._ensure_assistant_tables(conn)
            conn.execute(
                "UPDATE assistant_memories SET superseded=1 WHERE id=? AND tenant_id=?",
                (memory_id, tenant_id),
            )
            conn.commit()

    def pin_memory(self, memory_id: str, tenant_id: str, pinned: bool = True) -> bool:
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            self._ensure_assistant_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE assistant_memories
                SET pinned = ?, updated_at = ?
                WHERE id = ? AND tenant_id = ?
                """,
                (1 if pinned else 0, now, memory_id, tenant_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def review_memory(self, memory_id: str, tenant_id: str, review_status: str, reviewed_by: str) -> bool:
        now = datetime.now(UTC).isoformat()
        normalized = (review_status or "").strip().lower()
        if normalized not in {"active", "needs_review", "approved", "rejected"}:
            raise ValueError("review_status must be one of: active, needs_review, approved, rejected")
        with self._get_connection() as conn:
            self._ensure_assistant_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE assistant_memories
                SET review_status = ?, reviewed_at = ?, reviewed_by = ?, updated_at = ?
                WHERE id = ? AND tenant_id = ?
                """,
                (normalized, now, reviewed_by, now, memory_id, tenant_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def expire_memory(self, memory_id: str, tenant_id: str, expires_at: Optional[str] = None) -> bool:
        now = datetime.now(UTC).isoformat()
        expires_at = (expires_at or now).strip()
        with self._get_connection() as conn:
            self._ensure_assistant_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE assistant_memories
                SET expires_at = ?, updated_at = ?
                WHERE id = ? AND tenant_id = ?
                """,
                (expires_at, now, memory_id, tenant_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def forget_memory(self, memory_id: str, tenant_id: str) -> bool:
        with self._get_connection() as conn:
            self._ensure_assistant_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM assistant_memories WHERE id = ? AND tenant_id = ?",
                (memory_id, tenant_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_memory(self, memory_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            self._ensure_assistant_tables(conn)
            row = conn.execute(
                """
                SELECT id, tenant_id, category, fact, confidence, source_conversation_id,
                       created_at, updated_at, superseded, pinned, expires_at,
                       review_status, reviewed_at, reviewed_by
                FROM assistant_memories
                WHERE id = ? AND tenant_id = ?
                """,
                (memory_id, tenant_id),
            ).fetchone()
        return dict(row) if row else None

    # ── Tenant listing ─────────────────────────────────────────────────────────

    def list_tenants(self) -> List[Dict[str, Any]]:
        """Return a list of all tenant dicts (id, plan, status, …).

        Returns:
            List of tenant dictionaries
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tenants ORDER BY created_at ASC")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    # ── Alert Rules ─────────────────────────────────────────────────────────────

    def create_alert_rule(
        self,
        tenant_id: str,
        name: str,
        metric: str,
        operator: str,
        threshold: float,
        webhook_url: str,
        window_minutes: int = 60,
        severity: str = "warning",
    ) -> str:
        import uuid as _uuid
        rule_id = str(_uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO alert_rules
                    (id, tenant_id, name, metric, operator, threshold, window_minutes,
                     webhook_url, severity, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """, (rule_id, tenant_id, name, metric, operator, threshold,
                  window_minutes, webhook_url, severity, now, now))
            conn.commit()
        return rule_id

    def list_alert_rules(self, tenant_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM alert_rules WHERE tenant_id = ? ORDER BY created_at ASC",
                (tenant_id,),
            )
            return [dict(r) for r in cursor.fetchall()]

    def get_alert_rule(self, rule_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM alert_rules WHERE id = ? AND tenant_id = ?",
                (rule_id, tenant_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def delete_alert_rule(self, rule_id: str, tenant_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM alert_rules WHERE id = ? AND tenant_id = ?",
                (rule_id, tenant_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def create_alert_incident(
        self,
        tenant_id: str,
        rule_id: str,
        rule_name: str,
        severity: str,
        metric: str,
        threshold: float,
        observed_value: float,
        window_minutes: int,
        webhook_url: str,
        payload: Optional[Dict] = None,
    ) -> str:
        import uuid as _uuid
        incident_id = str(_uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO alert_incidents
                    (id, tenant_id, rule_id, rule_name, severity, metric, threshold,
                     observed_value, window_minutes, webhook_url, webhook_status,
                     webhook_attempts, payload, triggered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?)
            """, (incident_id, tenant_id, rule_id, rule_name, severity, metric,
                  threshold, observed_value, window_minutes, webhook_url,
                  json.dumps(payload or {}), now))
            conn.commit()
        return incident_id

    def update_alert_incident_webhook(
        self, incident_id: str, status: str, attempts: int
    ) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE alert_incidents SET webhook_status=?, webhook_attempts=? WHERE id=?",
                (status, attempts, incident_id),
            )
            conn.commit()

    def list_alert_incidents(
        self,
        tenant_id: str,
        rule_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if rule_id:
                cursor.execute(
                    "SELECT * FROM alert_incidents WHERE tenant_id=? AND rule_id=? "
                    "ORDER BY triggered_at DESC LIMIT ?",
                    (tenant_id, rule_id, limit),
                )
            else:
                cursor.execute(
                    "SELECT * FROM alert_incidents WHERE tenant_id=? "
                    "ORDER BY triggered_at DESC LIMIT ?",
                    (tenant_id, limit),
                )
            return [dict(r) for r in cursor.fetchall()]

    def evaluate_alert_rules(self, tenant_id: str) -> List[Dict[str, Any]]:
        """Check all enabled alert rules for tenant and return ones that should fire.

        Returns list of dicts with rule info + observed_value for each triggered rule.
        """
        rules = [r for r in self.list_alert_rules(tenant_id) if r.get("enabled")]
        if not rules:
            return []

        triggered = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for rule in rules:
                metric = rule["metric"]
                threshold = rule["threshold"]
                operator = rule["operator"]
                window_min = rule.get("window_minutes", 60)
                cutoff = datetime.now(UTC)
                from datetime import timedelta as _td
                cutoff_ts = (cutoff - _td(minutes=window_min)).isoformat()

                if metric == "anomaly_score":
                    cursor.execute("""
                        SELECT AVG(anomaly_score) FROM audit_events
                        WHERE customer_id=? AND timestamp >= ? AND anomaly_score IS NOT NULL
                    """, (tenant_id, cutoff_ts))
                    row = cursor.fetchone()
                    observed = row[0] if row and row[0] is not None else 0.0
                elif metric == "block_rate":
                    cursor.execute("""
                        SELECT COUNT(*) FROM audit_events
                        WHERE customer_id=? AND timestamp >= ?
                    """, (tenant_id, cutoff_ts))
                    total = (cursor.fetchone() or [0])[0] or 1
                    cursor.execute("""
                        SELECT COUNT(*) FROM audit_events
                        WHERE customer_id=? AND timestamp >= ? AND decision_verdict='BLOCK'
                    """, (tenant_id, cutoff_ts))
                    blocked = (cursor.fetchone() or [0])[0]
                    observed = blocked / total
                elif metric == "escalation_count":
                    cursor.execute("""
                        SELECT COUNT(*) FROM audit_events
                        WHERE customer_id=? AND timestamp >= ? AND decision_verdict='ESCALATE'
                    """, (tenant_id, cutoff_ts))
                    observed = (cursor.fetchone() or [0])[0]
                else:
                    continue

                ops = {"gt": observed > threshold, "gte": observed >= threshold,
                       "lt": observed < threshold, "lte": observed <= threshold,
                       "eq": observed == threshold}
                if ops.get(operator, False):
                    triggered.append({**rule, "observed_value": observed})
        return triggered

    # ── Policy Change Log ──────────────────────────────────────────────────────

    def log_policy_change(
        self,
        tenant_id: str,
        change_type: str,
        entity_type: str,
        entity_id: Optional[str] = None,
        entity_name: Optional[str] = None,
        diff_json: Optional[Dict] = None,
        changed_by: Optional[str] = None,
    ) -> str:
        import uuid as _uuid
        change_id = str(_uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO policy_changes
                    (id, tenant_id, changed_by, change_type, entity_type,
                     entity_id, entity_name, diff_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (change_id, tenant_id, changed_by, change_type, entity_type,
                  entity_id, entity_name, json.dumps(diff_json or {}), now))
            conn.commit()
        return change_id

    def list_policy_changes(
        self,
        tenant_id: str,
        entity_type: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if entity_type:
                cursor.execute(
                    "SELECT * FROM policy_changes WHERE tenant_id=? AND entity_type=? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (tenant_id, entity_type, limit),
                )
            else:
                cursor.execute(
                    "SELECT * FROM policy_changes WHERE tenant_id=? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (tenant_id, limit),
                )
            rows = cursor.fetchall()
            result = []
            for r in rows:
                d = dict(r)
                if d.get("diff_json"):
                    try:
                        d["diff_json"] = json.loads(d["diff_json"])
                    except Exception:
                        pass
                result.append(d)
            return result

    # ── Data Retention & Purge ─────────────────────────────────────────────────

    def get_tenant_retention_days(self, tenant_id: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT retention_days FROM tenants WHERE id=?", (tenant_id,)
            )
            row = cursor.fetchone()
            return int(row[0]) if row and row[0] is not None else 365

    def set_tenant_retention_days(self, tenant_id: str, retention_days: int) -> None:
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE tenants SET retention_days=?, updated_at=? WHERE id=?",
                (retention_days, now, tenant_id),
            )
            conn.commit()

    def purge_old_events(self, tenant_id: str, retention_days: int) -> int:
        """Delete audit events older than retention_days for tenant. Returns count deleted.

        NOTE: audit_events has append-only triggers — purge is done by temporarily
        disabling them for the connection (SQLite doesn't support DROP TRIGGER in tx;
        use a dedicated DELETE with RAISE-suppression via a separate connection config).
        For compliance, audit events within retention window are preserved; only events
        beyond retention_days are removed and logged in purge_log.
        """
        from datetime import timedelta as _td
        cutoff = (datetime.now(UTC) - _td(days=retention_days)).isoformat()
        # We need to bypass the append-only trigger for purge.
        # Connect without the trigger enabled by dropping+recreating it.
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            cursor = conn.cursor()
            # Temporarily drop append-only delete trigger
            cursor.execute("DROP TRIGGER IF EXISTS audit_events_append_only_delete")
            cursor.execute(
                "SELECT COUNT(*) FROM audit_events WHERE customer_id=? AND timestamp < ?",
                (tenant_id, cutoff),
            )
            count = (cursor.fetchone() or [0])[0]
            if count > 0:
                cursor.execute(
                    "DELETE FROM audit_events WHERE customer_id=? AND timestamp < ?",
                    (tenant_id, cutoff),
                )
            # Recreate trigger
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS audit_events_append_only_delete
                BEFORE DELETE ON audit_events
                FOR EACH ROW BEGIN
                    SELECT RAISE(ABORT, 'audit_events is append-only: deletes not allowed');
                END
            """)
            # Log the purge
            now = datetime.now(UTC).isoformat()
            cursor.execute("""
                INSERT INTO purge_log (tenant_id, purged_count, retention_days, purged_before, purged_at)
                VALUES (?, ?, ?, ?, ?)
            """, (tenant_id, count, retention_days, cutoff, now))
            conn.commit()
            return count
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def list_purge_log(self, tenant_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM purge_log WHERE tenant_id=? ORDER BY purged_at DESC LIMIT ?",
                (tenant_id, limit),
            )
            return [dict(r) for r in cursor.fetchall()]

    # ── DSAR (Subject Data Access / Deletion) ──────────────────────────────────

    def create_dsar_request(
        self,
        tenant_id: str,
        subject_id: str,
        request_type: str,
        notes: Optional[str] = None,
    ) -> str:
        import uuid as _uuid
        req_id = str(_uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO dsar_requests
                    (id, tenant_id, subject_id, request_type, status, requested_at, notes)
                VALUES (?, ?, ?, ?, 'pending', ?, ?)
            """, (req_id, tenant_id, subject_id, request_type, now, notes))
            conn.commit()
        return req_id

    def get_subject_audit_events(
        self, tenant_id: str, subject_id: str
    ) -> List[Dict[str, Any]]:
        """Return all audit events for subject_id (matched against agent_id field)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM audit_events
                WHERE customer_id=? AND agent_id=?
                ORDER BY timestamp ASC
            """, (tenant_id, subject_id))
            return [dict(r) for r in cursor.fetchall()]

    def anonymize_subject_data(self, tenant_id: str, subject_id: str) -> int:
        """Anonymize PHI fields for subject in audit_events (GDPR erasure).

        Preserves chain integrity — does NOT hard-delete rows. Scrubs agent_id,
        action_params, context, user_message, stated_intent fields.
        Returns count of rows anonymized.
        """
        anon = "[REDACTED-DSAR]"
        # Need to bypass append-only UPDATE trigger for anonymization
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            cursor = conn.cursor()
            cursor.execute("DROP TRIGGER IF EXISTS audit_events_append_only_update")
            cursor.execute(
                "SELECT COUNT(*) FROM audit_events WHERE customer_id=? AND agent_id=?",
                (tenant_id, subject_id),
            )
            count = (cursor.fetchone() or [0])[0]
            if count > 0:
                cursor.execute("""
                    UPDATE audit_events
                    SET agent_id=?, action_params='{}', context='{}',
                        user_message=?, stated_intent=?
                    WHERE customer_id=? AND agent_id=?
                """, (anon, anon, anon, tenant_id, subject_id))
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS audit_events_append_only_update
                BEFORE UPDATE ON audit_events
                FOR EACH ROW BEGIN
                    SELECT RAISE(ABORT, 'audit_events is append-only: updates not allowed');
                END
            """)
            # Mark DSAR completed
            now = datetime.now(UTC).isoformat()
            cursor.execute("""
                UPDATE dsar_requests SET status='completed', completed_at=?
                WHERE tenant_id=? AND subject_id=? AND request_type='deletion'
                AND status='pending'
            """, (now, tenant_id, subject_id))
            conn.commit()
            return count
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def list_dsar_requests(self, tenant_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM dsar_requests WHERE tenant_id=? ORDER BY requested_at DESC LIMIT ?",
                (tenant_id, limit),
            )
            return [dict(r) for r in cursor.fetchall()]

    # ── Device Registry ────────────────────────────────────────────────────────

    def register_device(
        self,
        tenant_id: str,
        device_id: str,
        device_type: str,
        name: str,
        vendor_id: Optional[str] = None,
        serial_number: Optional[str] = None,
        make: Optional[str] = None,
        model: Optional[str] = None,
        department: Optional[str] = None,
        location: Optional[str] = None,
        requires_supervision: bool = False,
        metadata: Optional[Dict] = None,
    ) -> str:
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO devices
                    (device_id, tenant_id, vendor_id, device_type, name, serial_number,
                     make, model, department, location, status, requires_supervision,
                     metadata, registered_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'available', ?, ?, ?, ?)
            """, (device_id, tenant_id, vendor_id, device_type, name, serial_number,
                  make, model, department, location,
                  1 if requires_supervision else 0,
                  json.dumps(metadata or {}), now, now))
            conn.commit()
        return device_id

    def get_device(self, device_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM devices WHERE device_id=? AND tenant_id=?",
                (device_id, tenant_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get("metadata"):
                try:
                    d["metadata"] = json.loads(d["metadata"])
                except Exception:
                    pass
            return d

    def list_devices(
        self,
        tenant_id: str,
        department: Optional[str] = None,
        device_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            q = "SELECT * FROM devices WHERE tenant_id=?"
            params: list = [tenant_id]
            if department:
                q += " AND department=?"
                params.append(department)
            if device_type:
                q += " AND device_type=?"
                params.append(device_type)
            if status:
                q += " AND status=?"
                params.append(status)
            q += " ORDER BY department, name ASC"
            cursor.execute(q, params)
            rows = cursor.fetchall()
            result = []
            for row in rows:
                d = dict(row)
                if d.get("metadata"):
                    try:
                        d["metadata"] = json.loads(d["metadata"])
                    except Exception:
                        pass
                result.append(d)
            return result

    def update_device(self, device_id: str, tenant_id: str, **kwargs) -> bool:
        allowed = {
            "name", "vendor_id", "serial_number", "make", "model",
            "department", "location", "status", "requires_supervision", "metadata",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        if "metadata" in updates and isinstance(updates["metadata"], dict):
            updates["metadata"] = json.dumps(updates["metadata"])
        if "requires_supervision" in updates:
            updates["requires_supervision"] = 1 if updates["requires_supervision"] else 0
        now = datetime.now(UTC).isoformat()
        updates["updated_at"] = now
        set_clause = ", ".join(f"{k}=?" for k in updates)
        values = list(updates.values()) + [device_id, tenant_id]
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE devices SET {set_clause} WHERE device_id=? AND tenant_id=?",  # noqa: S608
                values,
            )
            conn.commit()
            return cursor.rowcount > 0

    def deregister_device(self, device_id: str, tenant_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM devices WHERE device_id=? AND tenant_id=?",
                (device_id, tenant_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    # ── Agent-Device Bindings ──────────────────────────────────────────────────

    def create_device_binding(
        self,
        tenant_id: str,
        agent_id: str,
        device_id: str,
        permission_level: str = "full_control",
        authorized_by: Optional[str] = None,
        valid_from: Optional[str] = None,
        valid_until: Optional[str] = None,
        shift_start: Optional[str] = None,
        shift_end: Optional[str] = None,
        requires_supervision: bool = False,
    ) -> str:
        import uuid as _uuid
        binding_id = str(_uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO agent_device_bindings
                    (id, tenant_id, agent_id, device_id, permission_level,
                     authorized_by, valid_from, valid_until, shift_start, shift_end,
                     requires_supervision, enabled, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(agent_id, device_id) DO UPDATE SET
                    permission_level=excluded.permission_level,
                    authorized_by=excluded.authorized_by,
                    valid_from=excluded.valid_from,
                    valid_until=excluded.valid_until,
                    shift_start=excluded.shift_start,
                    shift_end=excluded.shift_end,
                    requires_supervision=excluded.requires_supervision,
                    enabled=1
            """, (binding_id, tenant_id, agent_id, device_id, permission_level,
                  authorized_by, valid_from, valid_until, shift_start, shift_end,
                  1 if requires_supervision else 0, now))
            conn.commit()
        return binding_id

    def get_device_binding(
        self, agent_id: str, device_id: str
    ) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM agent_device_bindings WHERE agent_id=? AND device_id=? AND enabled=1",
                (agent_id, device_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_device_bindings(
        self,
        tenant_id: str,
        device_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if device_id:
                cursor.execute(
                    "SELECT * FROM agent_device_bindings WHERE tenant_id=? AND device_id=? ORDER BY created_at ASC",
                    (tenant_id, device_id),
                )
            elif agent_id:
                cursor.execute(
                    "SELECT * FROM agent_device_bindings WHERE tenant_id=? AND agent_id=? ORDER BY created_at ASC",
                    (tenant_id, agent_id),
                )
            else:
                cursor.execute(
                    "SELECT * FROM agent_device_bindings WHERE tenant_id=? ORDER BY device_id, agent_id ASC",
                    (tenant_id,),
                )
            return [dict(r) for r in cursor.fetchall()]

    def revoke_device_binding(
        self, agent_id: str, device_id: str, tenant_id: str
    ) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM agent_device_bindings WHERE agent_id=? AND device_id=? AND tenant_id=?",
                (agent_id, device_id, tenant_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    # ── Device Lock / Mutex ────────────────────────────────────────────────────

    def acquire_device_lock(
        self, device_id: str, tenant_id: str, agent_id: str, action_id: Optional[str] = None
    ) -> Optional[str]:
        """Attempt to acquire exclusive control of a device.

        Returns session_id if successful, None if device is already locked by another agent.
        Idempotent: if the same agent already holds the lock, returns existing session_id.
        """
        import uuid as _uuid
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT status, current_agent_id, current_session_id FROM devices "
                "WHERE device_id=? AND tenant_id=?",
                (device_id, tenant_id),
            )
            row = cursor.fetchone()
            if not row:
                return None  # Device not found

            status, current_agent, current_session = row
            # Already locked by this agent — idempotent
            if current_agent == agent_id and current_session:
                return current_session
            # Locked by another agent
            if status == "in_use" and current_agent and current_agent != agent_id:
                return None

            session_id = str(_uuid.uuid4())
            cursor.execute("""
                UPDATE devices
                SET status='in_use', current_agent_id=?, current_session_id=?,
                    session_started_at=?, updated_at=?
                WHERE device_id=? AND tenant_id=?
            """, (agent_id, session_id, now, now, device_id, tenant_id))
            # Log session start
            cursor.execute("""
                INSERT INTO device_sessions
                    (session_id, tenant_id, device_id, agent_id, action_id, started_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (session_id, tenant_id, device_id, agent_id, action_id, now))
            conn.commit()
            return session_id

    def release_device_lock(
        self,
        device_id: str,
        tenant_id: str,
        agent_id: str,
        end_reason: str = "released",
        force: bool = False,
    ) -> bool:
        """Release device lock. Returns True if released, False if not held by agent."""
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT current_agent_id, current_session_id, session_started_at "
                "FROM devices WHERE device_id=? AND tenant_id=?",
                (device_id, tenant_id),
            )
            row = cursor.fetchone()
            if not row:
                return False
            current_agent, session_id, started_at = row
            if not force and current_agent != agent_id:
                return False

            # Calculate duration
            duration = None
            if started_at:
                try:
                    start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                    end_dt = datetime.fromisoformat(now)
                    duration = (end_dt - start_dt).total_seconds()
                except Exception:
                    pass

            # Release device
            cursor.execute("""
                UPDATE devices
                SET status='available', current_agent_id=NULL, current_session_id=NULL,
                    session_started_at=NULL, updated_at=?
                WHERE device_id=? AND tenant_id=?
            """, (now, device_id, tenant_id))
            # Close session record
            if session_id:
                cursor.execute("""
                    UPDATE device_sessions
                    SET ended_at=?, end_reason=?, duration_seconds=?
                    WHERE session_id=?
                """, (now, end_reason, duration, session_id))
            conn.commit()
            return True

    def list_device_sessions(
        self, device_id: str, tenant_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ds.*, d.name as device_name, d.device_type
                FROM device_sessions ds
                JOIN devices d ON d.device_id = ds.device_id
                WHERE ds.device_id=? AND ds.tenant_id=?
                ORDER BY ds.started_at DESC LIMIT ?
            """, (device_id, tenant_id, limit))
            return [dict(r) for r in cursor.fetchall()]

    def get_authorization_matrix(self, tenant_id: str) -> List[Dict[str, Any]]:
        """Return cross-join of agents × devices for this tenant with binding and vendor info."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    d.device_id, d.name as device_name, d.device_type,
                    d.department, d.location, d.status,
                    d.current_agent_id,
                    d.vendor_id as device_vendor_id,
                    b.agent_id, b.permission_level, b.requires_supervision,
                    b.valid_until, b.shift_start, b.shift_end, b.enabled as binding_enabled,
                    a.vendor_id as agent_vendor_id,
                    a.name as agent_name,
                    a.agent_type
                FROM devices d
                LEFT JOIN agent_device_bindings b ON b.device_id = d.device_id
                LEFT JOIN agents a ON a.agent_id = b.agent_id AND a.tenant_id = d.tenant_id
                WHERE d.tenant_id=?
                ORDER BY d.department, d.name, b.agent_id
            """, (tenant_id,))
            return [dict(r) for r in cursor.fetchall()]

    def get_vendor_summary(self, tenant_id: str) -> List[Dict[str, Any]]:
        """Return per-vendor action counts, block rates, escalations, and device control."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Audit stats per vendor
            cursor.execute("""
                SELECT
                    a.vendor_id,
                    COUNT(ae.id)                                          AS total_actions,
                    SUM(CASE WHEN ae.decision_verdict='ALLOW'    THEN 1 ELSE 0 END) AS allowed,
                    SUM(CASE WHEN ae.decision_verdict='BLOCK'    THEN 1 ELSE 0 END) AS blocked,
                    SUM(CASE WHEN ae.decision_verdict='ESCALATE' THEN 1 ELSE 0 END) AS escalated,
                    ROUND(
                        CAST(SUM(CASE WHEN ae.decision_verdict='BLOCK' THEN 1 ELSE 0 END) AS REAL)
                        / MAX(COUNT(ae.id), 1) * 100, 2
                    )                                                     AS block_rate_pct,
                    MAX(ae.timestamp)                                     AS last_action_at,
                    COUNT(DISTINCT ae.agent_id)                           AS distinct_agents,
                    COUNT(DISTINCT ae.device_id)                          AS distinct_devices
                FROM agents a
                LEFT JOIN audit_events ae
                    ON ae.agent_id = a.agent_id AND ae.customer_id = a.tenant_id
                WHERE a.tenant_id=? AND a.vendor_id IS NOT NULL
                GROUP BY a.vendor_id
                ORDER BY total_actions DESC
            """, (tenant_id,))
            rows = cursor.fetchall()
            summaries = [dict(r) for r in rows]

            # Enrich each vendor with the devices it currently controls and is authorized for
            for s in summaries:
                vid = s["vendor_id"]
                cursor.execute("""
                    SELECT DISTINCT d.device_id, d.name, d.device_type, d.department,
                                    d.status, d.current_agent_id
                    FROM agent_device_bindings b
                    JOIN agents a ON a.agent_id = b.agent_id AND a.tenant_id = b.tenant_id
                    JOIN devices d ON d.device_id = b.device_id
                    WHERE a.tenant_id=? AND a.vendor_id=? AND b.enabled=1
                    ORDER BY d.department, d.name
                """, (tenant_id, vid))
                s["authorized_devices"] = [dict(r) for r in cursor.fetchall()]
                s["currently_controlling"] = [
                    d for d in s["authorized_devices"]
                    if d.get("status") == "in_use" and d.get("current_agent_id")
                ]
            return summaries

    def check_device_binding_valid(
        self, agent_id: str, device_id: str, tenant_id: str
    ) -> Dict[str, Any]:
        """Full binding validity check. Returns dict with allowed bool + reason."""
        now_dt = datetime.now(UTC)
        now_ts = now_dt.isoformat()
        now_time = now_dt.strftime("%H:%M")

        binding = self.get_device_binding(agent_id, device_id)
        if not binding:
            return {"allowed": False, "reason": f"Agent '{agent_id}' has no binding for device '{device_id}'"}
        if not binding.get("enabled"):
            return {"allowed": False, "reason": "Binding is disabled"}

        valid_from = binding.get("valid_from")
        valid_until = binding.get("valid_until")
        if valid_from and now_ts < valid_from:
            return {"allowed": False, "reason": f"Binding not valid until {valid_from}"}
        if valid_until and now_ts > valid_until:
            return {"allowed": False, "reason": f"Binding expired at {valid_until}"}

        shift_start = binding.get("shift_start")
        shift_end = binding.get("shift_end")
        if shift_start and shift_end:
            if not (shift_start <= now_time <= shift_end):
                return {
                    "allowed": False,
                    "reason": f"Outside authorized shift window ({shift_start}–{shift_end})",
                }

        requires_supervision = bool(binding.get("requires_supervision"))
        permission_level = binding.get("permission_level", "full_control")
        return {
            "allowed": True,
            "requires_supervision": requires_supervision,
            "permission_level": permission_level,
            "binding": binding,
        }


    # ── Webhook Management ─────────────────────────────────────────────────────

    def save_webhook(
        self,
        webhook_id: str,
        tenant_id: str,
        name: str,
        url: str,
        events: List[str],
        secret: Optional[str] = None,
        enabled: bool = True,
        **_kwargs,  # absorb legacy kwargs (retry_count, etc.)
    ) -> None:
        """Persist a webhook registration."""
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO webhooks
                    (id, tenant_id, name, url, events, secret, enabled, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (webhook_id, tenant_id, name, url, json.dumps(events), secret,
                 1 if enabled else 0, now),
            )
            conn.commit()

    def get_webhooks(self, tenant_id: str) -> List[Dict[str, Any]]:
        """Return all enabled webhooks for a tenant."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM webhooks WHERE tenant_id = ? AND enabled = 1 ORDER BY created_at ASC",
                (tenant_id,),
            )
            rows = cursor.fetchall()
            result = []
            for row in rows:
                d = dict(row)
                try:
                    d["events"] = json.loads(d["events"])
                except Exception:
                    d["events"] = []
                result.append(d)
            return result

    def get_webhook(self, webhook_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Return a single webhook by id + tenant."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM webhooks WHERE id = ? AND tenant_id = ?",
                (webhook_id, tenant_id),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            d = dict(row)
            try:
                d["events"] = json.loads(d["events"])
            except Exception:
                d["events"] = []
            return d

    def delete_webhook(self, webhook_id: str, tenant_id: str) -> bool:
        """Soft-delete (disable) a webhook. Returns True if it existed."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE webhooks SET enabled = 0 WHERE id = ? AND tenant_id = ?",
                (webhook_id, tenant_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def save_webhook_delivery(
        self,
        delivery_id: str,
        webhook_id: str,
        event_type: str,
        payload: Dict[str, Any],
        status: str,
        response_status: Optional[int],
        attempts: int,
    ) -> None:
        """Record the result of a webhook delivery attempt."""
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO webhook_deliveries
                    (id, webhook_id, event_type, payload, status, response_status, attempts, delivered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (delivery_id, webhook_id, event_type, json.dumps(payload),
                 status, response_status, attempts, now),
            )
            conn.commit()

    def get_webhook_deliveries(self, webhook_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent deliveries for a webhook."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM webhook_deliveries WHERE webhook_id = ? ORDER BY delivered_at DESC LIMIT ?",
                (webhook_id, limit),
            )
            rows = cursor.fetchall()
            result = []
            for row in rows:
                d = dict(row)
                try:
                    d["payload"] = json.loads(d["payload"])
                except Exception:
                    pass
                result.append(d)
            return result

    def save_support_case(self, case: Dict[str, Any]) -> Dict[str, Any]:
        """Persist a tenant-scoped support case."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO support_cases (
                    case_id, tenant_id, support_code, severity, status, assigned_owner,
                    summary, issue_type, affected_system, workflow_id, connector,
                    decision_id, action_id, trace_id, conversation_id, request_id,
                    created_by, created_at, updated_at, timeline_json,
                    evidence_bundle_json, issue_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case["case_id"],
                    case["tenant_id"],
                    case.get("support_code"),
                    case["severity"],
                    case.get("status", "open"),
                    case.get("assigned_owner"),
                    case["summary"],
                    case.get("issue_type", "incident"),
                    case.get("affected_system"),
                    case.get("workflow_id"),
                    case.get("connector"),
                    case.get("decision_id"),
                    case.get("action_id"),
                    case.get("trace_id"),
                    case.get("conversation_id"),
                    case.get("request_id"),
                    case.get("created_by"),
                    case["created_at"],
                    case["updated_at"],
                    json.dumps(case.get("timeline", [])),
                    json.dumps(case.get("evidence_bundle", {})),
                    json.dumps(case.get("issue_payload", {})),
                ),
            )
            conn.commit()
        return case

    def list_support_cases(self, tenant_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent support cases for a tenant."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM support_cases WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?",
                (tenant_id, limit),
            )
            rows = cursor.fetchall()
        return [self._decode_support_case(row) for row in rows]

    def get_support_case(self, case_id: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Return a single support case."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if tenant_id is None:
                cursor.execute("SELECT * FROM support_cases WHERE case_id = ?", (case_id,))
            else:
                cursor.execute(
                    "SELECT * FROM support_cases WHERE case_id = ? AND tenant_id = ?",
                    (case_id, tenant_id),
                )
            row = cursor.fetchone()
        return self._decode_support_case(row) if row else None

    def _decode_support_case(self, row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        result = dict(row)
        for key, default in (
            ("timeline_json", []),
            ("evidence_bundle_json", {}),
            ("issue_payload_json", {}),
        ):
            raw = result.pop(key, None)
            try:
                result[key.replace("_json", "")] = json.loads(raw) if raw else default
            except Exception:
                result[key.replace("_json", "")] = default
        return result


# Global database instance
_db_instance: Optional[Database] = None


def get_db() -> Database:
    """Get global database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(db_path=_resolve_db_path())
    return _db_instance
