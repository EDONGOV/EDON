"""PostgreSQL database adapter for EDON Gateway.

Activated when DATABASE_URL env var starts with postgresql:// or postgres://.
Falls back to SQLite (database.py) when DATABASE_URL is not set.

Implements the same public interface as Database (database.py) so all
gateway code works without modification.

Key differences from SQLite:
- Connection pooling (ThreadedConnectionPool, min=2, max=20)
- Uses %s placeholders instead of ?
- Uses SERIAL for auto-increment PKs
- Uses ON CONFLICT (...) DO UPDATE instead of INSERT OR REPLACE
- No SQLite PRAGMA calls
- PostgreSQL-style UPSERT and triggers
"""

import os
import json
import hashlib
import hmac
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, UTC
from contextlib import contextmanager

logger = logging.getLogger(__name__)

try:
    import psycopg2
    import psycopg2.extras
    import psycopg2.pool
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    logger.warning("psycopg2 not installed. PostgreSQL support unavailable.")


class PostgreSQLDatabase:
    """PostgreSQL database for EDON Gateway persistence.

    Drop-in replacement for Database (SQLite) when DATABASE_URL is set to
    a PostgreSQL connection string.
    """

    def __init__(self, database_url: str):
        if not PSYCOPG2_AVAILABLE:
            raise RuntimeError(
                "psycopg2 not installed. Run: pip install psycopg2-binary>=2.9.0"
            )
        self._database_url = database_url
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=20,
            dsn=database_url,
        )
        logger.info("PostgreSQL connection pool created (min=2, max=20)")
        self._init_schema()

    @contextmanager
    def _get_connection(self):
        """Get a connection from the pool, return it on exit."""
        conn = self._pool.getconn()
        try:
            conn.autocommit = False
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Database error: {str(e)}") from e
        finally:
            self._pool.putconn(conn)

    def _q(self, sql: str) -> str:
        """Convert SQLite ? placeholders to PostgreSQL %s."""
        return sql.replace("?", "%s")

    def _row_to_dict(self, cursor, row) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))

    def _rows_to_dicts(self, cursor, rows) -> List[Dict[str, Any]]:
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    def ping(self) -> bool:
        """Check DB connectivity. Returns True if healthy."""
        try:
            with self._get_connection() as conn:
                conn.cursor().execute("SELECT 1")
            return True
        except Exception:
            return False

    def _init_schema(self):
        """Create tables if they don't exist (PostgreSQL-compatible DDL)."""
        with self._get_connection() as conn:
            cur = conn.cursor()

            cur.execute("""
                CREATE TABLE IF NOT EXISTS intents (
                    intent_id TEXT PRIMARY KEY,
                    objective TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    constraints TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    approved_by_user BOOLEAN NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    id BIGSERIAL PRIMARY KEY,
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
                    human_override BOOLEAN NOT NULL DEFAULT FALSE,
                    human_override_actor_id TEXT,
                    human_override_reason TEXT,
                    processing_latency_ms REAL,
                    edge_node_id TEXT,
                    is_payload_encrypted BOOLEAN NOT NULL DEFAULT FALSE
                )
            """)
            # Append-only enforcement for audit trail integrity.
            cur.execute("""
                CREATE OR REPLACE FUNCTION enforce_audit_events_append_only()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    RAISE EXCEPTION 'audit_events is append-only: % not allowed', TG_OP;
                END;
                $$;
            """)
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_trigger
                        WHERE tgname = 'audit_events_append_only_update'
                    ) THEN
                        CREATE TRIGGER audit_events_append_only_update
                        BEFORE UPDATE ON audit_events
                        FOR EACH ROW
                        EXECUTE FUNCTION enforce_audit_events_append_only();
                    END IF;
                END$$;
            """)
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_trigger
                        WHERE tgname = 'audit_events_append_only_delete'
                    ) THEN
                        CREATE TRIGGER audit_events_append_only_delete
                        BEFORE DELETE ON audit_events
                        FOR EACH ROW
                        EXECUTE FUNCTION enforce_audit_events_append_only();
                    END IF;
                END$$;
            """)

            cur.execute("""
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

            cur.execute("""
                CREATE TABLE IF NOT EXISTS active_policy_preset (
                    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
                    preset_name TEXT NOT NULL,
                    applied_at TEXT NOT NULL,
                    applied_by TEXT
                )
            """)

            cur.execute("""
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

            cur.execute("""
                CREATE TABLE IF NOT EXISTS tenants (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'trial',
                    plan TEXT NOT NULL DEFAULT 'free',
                    mag_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                    stripe_customer_id TEXT UNIQUE,
                    stripe_subscription_id TEXT UNIQUE,
                    current_period_start TEXT,
                    current_period_end TEXT,
                    cancel_at_period_end BOOLEAN DEFAULT FALSE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    key_hash TEXT NOT NULL UNIQUE,
                    name TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at TEXT NOT NULL,
                    last_used_at TEXT
                )
            """)

            # Migration: add expires_at to api_keys if not present
            # Use IF NOT EXISTS to avoid transaction abort on second run (PostgreSQL 9.6+)
            cur.execute("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS expires_at TEXT")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS channel_tokens (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    external_user_id TEXT,
                    token_hash TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    last_used_at TEXT
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS credentials (
                    credential_id TEXT PRIMARY KEY,
                    tool_name TEXT NOT NULL,
                    credential_type TEXT NOT NULL,
                    credential_data TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_used_at TEXT,
                    encrypted BOOLEAN NOT NULL DEFAULT FALSE,
                    tenant_id TEXT,
                    last_error TEXT
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS rate_limits (
                    key TEXT PRIMARY KEY,
                    count INTEGER NOT NULL DEFAULT 0,
                    window_start TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS tenant_usage (
                    id BIGSERIAL PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    period_start TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS policy_versions (
                    version TEXT PRIMARY KEY,
                    description TEXT,
                    created_at TEXT NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS connect_codes (
                    code TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    channel TEXT NOT NULL DEFAULT 'telegram',
                    expires_at TEXT NOT NULL,
                    used_at TEXT,
                    used_by TEXT,
                    created_at TEXT NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS preference_memory (
                    tenant_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, key)
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS tenant_alert_preferences (
                    tenant_id TEXT NOT NULL PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
                    preferences TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS policy_rules (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    description TEXT,
                    condition_tool TEXT,
                    condition_op TEXT,
                    condition_risk_level TEXT,
                    condition_tags TEXT,
                    action TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 0,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_policy_rules_tenant
                ON policy_rules(tenant_id, enabled, priority DESC)
            """)

            # Create indexes for performance
            _indexes = [
                "CREATE INDEX IF NOT EXISTS idx_audit_agent ON audit_events(agent_id)",
                "CREATE INDEX IF NOT EXISTS idx_audit_customer ON audit_events(customer_id)",
                "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp)",
                "CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash)",
                "CREATE INDEX IF NOT EXISTS idx_api_keys_tenant ON api_keys(tenant_id)",
                "CREATE INDEX IF NOT EXISTS idx_tenants_user ON tenants(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_channel_tokens_hash ON channel_tokens(token_hash)",
            ]
            for idx in _indexes:
                cur.execute(idx)

            for col, typ in [
                ("policy_rule_id", "TEXT"),
                ("action_summary", "TEXT"),
                ("stated_intent", "TEXT"),
                ("user_message", "TEXT"),
                ("chain_sig", "TEXT"),
            ]:
                cur.execute(f"ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS {col} {typ}")  # safe: schema-only
            cur.execute("UPDATE api_keys SET role = 'user' WHERE role = 'agent'")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS tenant_agents (
                    tenant_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    first_seen TEXT NOT NULL,
                    display_name TEXT,
                    PRIMARY KEY (tenant_id, agent_id)
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_tenant_agents_tenant
                ON tenant_agents(tenant_id)
            """)
            # Migration: add display_name if missing
            cur.execute("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'tenant_agents' AND column_name = 'display_name'
            """)
            if cur.fetchone() is None:
                cur.execute("ALTER TABLE tenant_agents ADD COLUMN display_name TEXT")
            conn.commit()
            logger.info("PostgreSQL schema initialized")

    # ---- Intent methods ----

    def save_intent(self, intent_id: str, objective: str, scope: Dict,
                    constraints: Dict, risk_level: str, approved_by_user: bool,
                    customer_id: Optional[str] = None):
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO intents (intent_id, objective, scope, constraints, risk_level, approved_by_user, customer_id, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (intent_id) DO UPDATE SET
                    objective=EXCLUDED.objective, scope=EXCLUDED.scope,
                    constraints=EXCLUDED.constraints, risk_level=EXCLUDED.risk_level,
                    approved_by_user=EXCLUDED.approved_by_user,
                    customer_id=EXCLUDED.customer_id, updated_at=EXCLUDED.updated_at
            """, (intent_id, objective, json.dumps(scope), json.dumps(constraints),
                  risk_level, approved_by_user, customer_id, now, now))

    def get_intent(self, intent_id: str, customer_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            if customer_id is not None:
                cur.execute(
                    "SELECT * FROM intents WHERE intent_id = %s AND customer_id = %s",
                    (intent_id, customer_id),
                )
            else:
                cur.execute("SELECT * FROM intents WHERE intent_id = %s", (intent_id,))
            row = cur.fetchone()
            if row is None:
                return None
            d = self._row_to_dict(cur, row)
            if d is None:
                return None
            d["scope"] = json.loads(d["scope"])
            d["constraints"] = json.loads(d["constraints"])
            return d

    def list_intents(self, limit: int = 100, customer_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            if customer_id is not None:
                cur.execute(
                    "SELECT * FROM intents WHERE customer_id = %s ORDER BY created_at DESC LIMIT %s",
                    (customer_id, limit),
                )
            else:
                cur.execute("SELECT * FROM intents ORDER BY created_at DESC LIMIT %s", (limit,))
            rows = cur.fetchall()
            result = []
            for row in rows:
                d = self._row_to_dict(cur, row)
                if d is not None:
                    d["scope"] = json.loads(d["scope"])
                    d["constraints"] = json.loads(d["constraints"])
                    result.append(d)
            return result

    def get_latest_intent(self, customer_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            if customer_id is not None:
                cur.execute(
                    "SELECT * FROM intents WHERE customer_id = %s ORDER BY created_at DESC LIMIT 1",
                    (customer_id,),
                )
            else:
                cur.execute("SELECT * FROM intents ORDER BY created_at DESC LIMIT 1")
            row = cur.fetchone()
            if row is None:
                return None
            d = self._row_to_dict(cur, row)
            if d is None:
                return None
            d["scope"] = json.loads(d["scope"])
            d["constraints"] = json.loads(d["constraints"])
            return d

    # ---- Webhook methods ----

    def save_webhook(
        self,
        webhook_id: str,
        tenant_id: str,
        url: str,
        secret: Optional[str],
        events: List[str],
        retry_count: int = 3,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO webhooks (id, tenant_id, url, secret, events, retry_count, status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, 'active', %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    url=EXCLUDED.url, secret=EXCLUDED.secret, events=EXCLUDED.events,
                    retry_count=EXCLUDED.retry_count, updated_at=EXCLUDED.updated_at
            """, (webhook_id, tenant_id, url, secret, json.dumps(events), retry_count, now, now))

    def get_webhooks(self, tenant_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM webhooks WHERE tenant_id=%s AND status='active'", (tenant_id,))
            rows = cur.fetchall()
            result = []
            for row in rows:
                d = self._row_to_dict(cur, row)
                if d is not None:
                    d["events"] = json.loads(d.get("events") or "[]")
                    result.append(d)
            return result

    def delete_webhook(self, webhook_id: str, tenant_id: str) -> bool:
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE webhooks SET status='deleted', updated_at=%s WHERE id=%s AND tenant_id=%s",
                (now, webhook_id, tenant_id),
            )
            return cur.rowcount > 0

    def save_webhook_delivery(
        self,
        delivery_id: str,
        webhook_id: str,
        event_type: str,
        payload: Dict[str, Any],
        status: str,
        response_status: Optional[int] = None,
        attempts: int = 1,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        delivered_at = now if status == "delivered" else None
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO webhook_deliveries
                (id, webhook_id, event_type, payload, status, response_status, attempts, created_at, delivered_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET status=EXCLUDED.status,
                    response_status=EXCLUDED.response_status, attempts=EXCLUDED.attempts,
                    delivered_at=EXCLUDED.delivered_at
            """, (delivery_id, webhook_id, event_type, json.dumps(payload),
                  status, response_status, attempts, now, delivered_at))

    def get_webhook_deliveries(self, webhook_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM webhook_deliveries WHERE webhook_id=%s ORDER BY created_at DESC LIMIT %s",
                (webhook_id, limit),
            )
            rows = cur.fetchall()
            result = []
            for row in rows:
                d = self._row_to_dict(cur, row)
                if d is not None:
                    result.append(d)
            return result

    # ---- Audit trail ----

    def _get_previous_chain_hash(self) -> str:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT chain_hash FROM audit_events ORDER BY id DESC LIMIT 1")
            row = cur.fetchone()
            if row and row[0]:
                return row[0]
        return ""

    def _compute_chain_hash(self, prev_hash: str, entry_payload: str) -> str:
        return hashlib.sha256((prev_hash + entry_payload).encode("utf-8")).hexdigest()

    def _compute_chain_signature(self, chain_hash: str) -> Optional[str]:
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
    ) -> str:
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
        context_json = json.dumps(context)

        is_payload_encrypted = False
        if os.getenv("EDON_ENCRYPT_AUDIT_PAYLOAD", "false").lower() == "true":
            try:
                from ..security.encryption import encrypt_field
                params_json = encrypt_field(params_json)
                is_payload_encrypted = True
            except Exception as _enc_err:
                logger.warning("Audit payload encryption failed: %s", _enc_err)

        entry_payload = "|".join([
            ts, action_id, tool, op, params_json, source, str(est_risk), str(comp_risk),
            verdict, reason_code, explanation, policy_version, policy_rule_id or "", action_summary or "", stated_intent or "", user_message or "",
            intent_id or "", agent_id or "", context_json, now,
            customer_id or "", str(anomaly_score) if anomaly_score is not None else "",
            "1" if human_override else "0", human_override_actor_id or "", human_override_reason or "",
            str(processing_latency_ms) if processing_latency_ms is not None else "", edge_node_id or "",
        ])
        prev_hash = self._get_previous_chain_hash()
        chain_hash = self._compute_chain_hash(prev_hash, entry_payload)
        chain_sig = self._compute_chain_signature(chain_hash)

        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO audit_events (
                    timestamp, action_id, action_tool, action_op, action_params,
                    action_source, action_estimated_risk, action_computed_risk,
                    decision_verdict, decision_reason_code, decision_explanation,
                    decision_policy_version, policy_rule_id, action_summary, stated_intent, user_message,
                    intent_id, agent_id, context, created_at,
                    chain_hash, chain_sig, customer_id, anomaly_score, human_override,
                    human_override_actor_id, human_override_reason, processing_latency_ms,
                    edge_node_id, is_payload_encrypted
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                ts, action_id, tool, op, params_json, source, est_risk, comp_risk,
                verdict, reason_code, explanation, policy_version, policy_rule_id, action_summary, stated_intent, user_message,
                intent_id, agent_id,
                context_json, now, chain_hash, chain_sig, customer_id, anomaly_score, human_override,
                human_override_actor_id, human_override_reason, processing_latency_ms,
                edge_node_id, is_payload_encrypted,
            ))

            decision_id = f"dec-{action_id}-{now}" if action_id else f"dec-{now}"
            cur.execute("""
                INSERT INTO decisions (decision_id, action_id, verdict, reason_code, explanation,
                    policy_version, intent_id, agent_id, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (decision_id) DO NOTHING
            """, (
                decision_id, action_id,
                decision.get("verdict", ""), decision.get("reason_code", ""),
                decision.get("explanation", ""), decision.get("policy_version", "1.0.0"),
                intent_id, agent_id, now,
            ))
            conn.commit()

        return decision_id

    def query_audit_events(
        self,
        agent_id: Optional[str] = None,
        verdict: Optional[str] = None,
        intent_id: Optional[str] = None,
        customer_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        conditions = []
        params = []
        if agent_id:
            conditions.append("agent_id = %s")
            params.append(agent_id)
        if customer_id:
            conditions.append("customer_id = %s")
            params.append(customer_id)
        if verdict:
            conditions.append("decision_verdict = %s")
            params.append(verdict)
        if intent_id:
            conditions.append("intent_id = %s")
            params.append(intent_id)
        if start_time:
            conditions.append("timestamp >= %s")
            params.append(start_time)
        if end_time:
            conditions.append("timestamp <= %s")
            params.append(end_time)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend([limit, offset])

        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT * FROM audit_events {where} ORDER BY id DESC LIMIT %s OFFSET %s",  # safe: schema-only
                params,
            )
            rows = cur.fetchall()
            result = self._rows_to_dicts(cur, rows)

            # Decrypt if needed
            for row in result:
                if row.get("is_payload_encrypted"):
                    try:
                        from ..security.encryption import decrypt_field
                        row["action_params"] = decrypt_field(row["action_params"])
                    except Exception:
                        row["action_params"] = "[DECRYPTION FAILED]"
            normalized: List[Dict[str, Any]] = []
            for row in result:
                params = row.get("action_params")
                if isinstance(params, str):
                    try:
                        params = json.loads(params)
                    except Exception:
                        params = {}
                normalized.append(
                    {
                        "id": f"dec-{row.get('action_id', '')}-{row.get('created_at', '')}",
                        "timestamp": row.get("timestamp"),
                        "created_at": row.get("created_at"),
                        "agent_id": row.get("agent_id") or "",
                        "intent_id": row.get("intent_id") or "",
                        "verdict": row.get("decision_verdict") or "",
                        "reason_code": row.get("decision_reason_code") or "",
                        "explanation": row.get("decision_explanation") or "",
                        "policy_version": row.get("decision_policy_version") or "",
                        "latency_ms": row.get("processing_latency_ms"),
                        "action_summary": row.get("action_summary"),
                        "stated_intent": row.get("stated_intent"),
                        "user_message": row.get("user_message"),
                        "action": {
                            "id": row.get("action_id"),
                            "tool": row.get("action_tool"),
                            "op": row.get("action_op"),
                            "params": params or {},
                            "source": row.get("action_source"),
                            "estimated_risk": row.get("action_estimated_risk"),
                            "computed_risk": row.get("action_computed_risk"),
                        },
                        "decision": {
                            "verdict": row.get("decision_verdict"),
                            "reason_code": row.get("decision_reason_code"),
                            "explanation": row.get("decision_explanation"),
                            "policy_version": row.get("decision_policy_version"),
                            "policy_rule_id": row.get("policy_rule_id"),
                        },
                        "context": json.loads(row.get("context") or "{}"),
                    }
                )
            return normalized

    def verify_audit_chain(self, limit: Optional[int] = None) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            q = "SELECT id, chain_hash, chain_sig, timestamp, action_id, action_tool, action_op, action_params, action_source, action_estimated_risk, action_computed_risk, decision_verdict, decision_reason_code, decision_explanation, decision_policy_version, policy_rule_id, action_summary, stated_intent, user_message, intent_id, agent_id, context, created_at, customer_id, anomaly_score, human_override, human_override_actor_id, human_override_reason, processing_latency_ms, edge_node_id FROM audit_events ORDER BY id ASC"
            if limit:
                q += f" LIMIT {int(limit)}"
            cur.execute(q)
            rows = cur.fetchall()

        prev_hash = ""
        checked = 0
        allow_unsigned_legacy = (os.getenv("EDON_AUDIT_ALLOW_UNSIGNED_LEGACY", "true").lower() == "true")
        for row in rows:
            if row[1] is None or row[1] == "":
                continue
            context_json = row[21] or "{}"
            params_json = row[7] if isinstance(row[7], str) else json.dumps(row[7] or {})
            entry_payload = "|".join([
                row[3] or "", row[4] or "", row[5] or "", row[6] or "", params_json,
                row[8] or "", str(row[9] or ""), str(row[10]),
                row[11] or "", row[12] or "", row[13] or "",
                row[14] or "", row[15] or "", row[16] or "", row[17] or "", row[18] or "", row[19] or "", row[20] or "", context_json,
                row[22] or "",
                row[23] or "", str(row[24]) if row[24] is not None else "",
                "1" if row[25] else "0", row[26] or "", row[27] or "",
                str(row[28]) if row[28] is not None else "", row[29] or "",
            ])
            expected = self._compute_chain_hash(prev_hash, entry_payload)
            if row[1] != expected:
                return {"valid": False, "checked": checked, "broken_at_id": row[0], "message": f"Chain broken at id={row[0]}"}
            expected_sig = self._compute_chain_signature(row[1])
            stored_sig = row[2]
            if expected_sig:
                if not stored_sig:
                    if not allow_unsigned_legacy:
                        return {"valid": False, "checked": checked, "broken_at_id": row[0], "message": f"Unsigned chain row at id={row[0]}"}
                elif not hmac.compare_digest(str(stored_sig), str(expected_sig)):
                    return {"valid": False, "checked": checked, "broken_at_id": row[0], "message": f"Chain signature mismatch at id={row[0]}"}
            prev_hash = row[1]
            checked += 1

        return {"valid": True, "checked": checked, "broken_at_id": None, "message": "Chain valid"}

    # ---- Decision methods ----

    def get_decision(self, decision_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM decisions WHERE decision_id = %s", (decision_id,))
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def query_decisions(
        self,
        action_id: Optional[str] = None,
        verdict: Optional[str] = None,
        intent_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        conditions = []
        params = []
        if action_id:
            conditions.append("action_id = %s"); params.append(action_id)
        if verdict:
            conditions.append("verdict = %s"); params.append(verdict)
        if intent_id:
            conditions.append("intent_id = %s"); params.append(intent_id)
        if agent_id:
            conditions.append("agent_id = %s"); params.append(agent_id)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(f"SELECT * FROM decisions {where} ORDER BY created_at DESC LIMIT %s", params)  # safe: schema-only
            return self._rows_to_dicts(cur, cur.fetchall())

    def get_decision_by_action_id(self, action_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM decisions WHERE action_id = %s ORDER BY created_at DESC LIMIT 1", (action_id,))
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    # ---- Policy preset ----

    def set_active_policy_preset(self, preset_name: str, applied_by: Optional[str] = None):
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO active_policy_preset (id, preset_name, applied_at, applied_by)
                VALUES (1, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    preset_name=EXCLUDED.preset_name,
                    applied_at=EXCLUDED.applied_at,
                    applied_by=EXCLUDED.applied_by
            """, (preset_name, now, applied_by))

    def get_active_policy_preset(self) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM active_policy_preset WHERE id = 1")
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    # ---- Per-tenant custom policy rules ----

    def create_policy_rule(
        self,
        tenant_id: str,
        name: str,
        action: str,
        priority: int = 0,
        description=None,
        condition_tool=None,
        condition_op=None,
        condition_risk_level=None,
        condition_tags=None,
        enabled: bool = True,
    ) -> str:
        import uuid, json
        rule_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        tags_json = json.dumps(condition_tags) if condition_tags else None
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO policy_rules
                    (id, tenant_id, name, description, condition_tool, condition_op,
                     condition_risk_level, condition_tags, action, priority, enabled,
                     created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (rule_id, tenant_id, name, description, condition_tool, condition_op,
                  condition_risk_level, tags_json, action, priority,
                  True if enabled else False, now, now))
        return rule_id

    def get_policy_rules(self, tenant_id: str, enabled_only: bool = True):
        import json
        with self._get_connection() as conn:
            cur = conn.cursor()
            if enabled_only:
                cur.execute("""
                    SELECT * FROM policy_rules
                    WHERE tenant_id = %s AND enabled = TRUE
                    ORDER BY priority DESC, created_at ASC
                """, (tenant_id,))
            else:
                cur.execute("""
                    SELECT * FROM policy_rules
                    WHERE tenant_id = %s
                    ORDER BY priority DESC, created_at ASC
                """, (tenant_id,))
            rows = cur.fetchall()
            rules = []
            for row in self._rows_to_dicts(cur, rows):
                if row.get("condition_tags") and isinstance(row["condition_tags"], str):
                    row["condition_tags"] = json.loads(row["condition_tags"])
                rules.append(row)
            return rules

    def get_policy_rule(self, rule_id: str, tenant_id: str):
        import json
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM policy_rules WHERE id = %s AND tenant_id = %s",
                (rule_id, tenant_id)
            )
            row = cur.fetchone()
            if not row:
                return None
            d = self._row_to_dict(cur, row)
            if d is None:
                return None
            if d.get("condition_tags") and isinstance(d["condition_tags"], str):
                d["condition_tags"] = json.loads(d["condition_tags"])
            return d

    def update_policy_rule(self, rule_id: str, tenant_id: str, **fields) -> bool:
        import json
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
        set_clause = ", ".join(f"{k} = %s" for k in updates)
        values = list(updates.values()) + [rule_id, tenant_id]
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                f"UPDATE policy_rules SET {set_clause} WHERE id = %s AND tenant_id = %s",
                values
            )
            return cur.rowcount > 0

    def delete_policy_rule(self, rule_id: str, tenant_id: str) -> bool:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM policy_rules WHERE id = %s AND tenant_id = %s",
                (rule_id, tenant_id)
            )
            return cur.rowcount > 0

    # ---- Users ----

    def create_user(self, user_id: str, email: str, auth_provider: str, auth_subject: str, role: str = "user") -> str:
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO users (id, email, auth_provider, auth_subject, role, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (auth_provider, auth_subject) DO NOTHING
            """, (user_id, email, auth_provider, auth_subject, role, now, now))
        return user_id

    def get_user_by_auth(self, auth_provider: str, auth_subject: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE auth_provider=%s AND auth_subject=%s",
                        (auth_provider, auth_subject))
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def update_user_email(self, user_id: str, email: str) -> bool:
        """Update a user's email. Returns True if a row was updated."""
        if not email or not email.strip():
            return False
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE users SET email = %s, updated_at = %s WHERE id = %s", (email.strip(), now, user_id))
            return cur.rowcount > 0

    # ---- Tenants ----

    def create_tenant(self, tenant_id: str, user_id: str, stripe_customer_id: Optional[str] = None) -> str:
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO tenants (id, user_id, status, plan, mag_enabled, stripe_customer_id, created_at, updated_at)
                VALUES (%s, %s, 'trial', 'free', FALSE, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (tenant_id, user_id, stripe_customer_id, now, now))
        return tenant_id

    def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM tenants WHERE id = %s", (tenant_id,))
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def get_tenant_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM tenants WHERE user_id = %s ORDER BY created_at DESC LIMIT 1", (user_id,))
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def is_mag_enabled(self, tenant_id: str) -> bool:
        tenant = self.get_tenant(tenant_id)
        return bool(tenant and tenant.get("mag_enabled"))

    def update_tenant_subscription(self, tenant_id: str, **kwargs):
        now = datetime.now(UTC).isoformat()
        kwargs["updated_at"] = now
        sets = ", ".join(f"{k} = %s" for k in kwargs)
        values = list(kwargs.values()) + [tenant_id]
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(f"UPDATE tenants SET {sets} WHERE id = %s", values)  # safe: schema-only

    def get_tenant_by_stripe_customer(self, stripe_customer_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM tenants WHERE stripe_customer_id = %s", (stripe_customer_id,))
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def get_tenant_by_stripe_subscription(self, stripe_subscription_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM tenants WHERE stripe_subscription_id = %s", (stripe_subscription_id,))
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def get_tenant_default_intent(self, tenant_id: str) -> Optional[str]:
        result = self.read_preference(tenant_id, "default_intent_id")
        return result

    def update_tenant_default_intent(self, tenant_id: str, intent_id: str) -> None:
        self.write_preference(tenant_id, "default_intent_id", intent_id)

    def get_integration_status(self, tenant_id: Optional[str], tool_name: str = "clawdbot") -> Dict[str, Any]:
        cred = self.get_credential(f"{tenant_id}_{tool_name}", tool_name, tenant_id) if tenant_id else None
        if not cred:
            return {"connected": False, "last_ok_at": None, "last_error": None, "base_url": None, "auth_mode": None}
        data = cred.get("credential_data") or {}
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                data = {}
        return {
            "connected": cred.get("last_used_at") is not None,
            "last_ok_at": cred.get("last_used_at"),
            "last_error": cred.get("last_error"),
            "base_url": data.get("base_url") or data.get("gateway_url"),
            "auth_mode": data.get("auth_mode") or "token",
        }

    # ---- API Keys ----

    def create_api_key(
        self,
        tenant_id: str,
        key_hash: str,
        name: Optional[str] = None,
        role: str = 'user',
        expires_at: Optional[str] = None,
    ) -> str:
        import uuid
        api_key_id = f"key_{uuid.uuid4().hex[:16]}"
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO api_keys (id, tenant_id, key_hash, name, status, role, created_at, expires_at)
                VALUES (%s, %s, %s, %s, 'active', %s, %s, %s)
            """, (api_key_id, tenant_id, key_hash, name, role, now, expires_at))
        return api_key_id

    def list_auditor_grants(self, tenant_id: str) -> list:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, name, status, role, created_at, expires_at, last_used_at
                FROM api_keys WHERE tenant_id = %s AND role = 'auditor'
                ORDER BY created_at DESC
            """, (tenant_id,))
            rows = cur.fetchall()
            return [
                {
                    "key_id": r[0], "label": r[1], "status": r[2], "role": r[3],
                    "created_at": r[4], "expires_at": r[5], "last_used_at": r[6],
                }
                for r in rows
            ]

    def revoke_api_key_scoped(self, key_id: str, tenant_id: str) -> bool:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE api_keys SET status = 'revoked' WHERE id = %s AND tenant_id = %s",
                (key_id, tenant_id),
            )
            return cur.rowcount > 0

    def get_api_key_by_hash(self, key_hash: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM api_keys
                WHERE key_hash = %s
                  AND status IN ('active', 'rotating')
                  AND (expires_at IS NULL OR expires_at > %s)
            """, (key_hash, datetime.now(UTC).isoformat()))
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def update_api_key_last_used(self, api_key_id: str):
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE api_keys SET last_used_at = %s WHERE id = %s", (now, api_key_id))

    def revoke_api_key(self, api_key_id: str) -> bool:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE api_keys SET status = 'revoked' WHERE id = %s", (api_key_id,))
            return cur.rowcount > 0

    def rotate_api_key(self, api_key_id: str, tenant_id: str, new_key_hash: str,
                       new_key_name=None, overlap_hours: int = 24,
                       role: str = 'user') -> dict:
        """Rotate an API key: creates a new key and marks old as rotating (with expiry)."""
        import uuid
        from datetime import timedelta
        now = datetime.now(UTC)
        old_expires_at = (now + timedelta(hours=overlap_hours)).isoformat()
        new_key_id = f"key_{uuid.uuid4().hex[:16]}"

        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE api_keys SET status = 'rotating', expires_at = %s
                WHERE id = %s AND tenant_id = %s
            """, (old_expires_at, api_key_id, tenant_id))
            cur.execute("""
                INSERT INTO api_keys (id, tenant_id, key_hash, name, status, role, created_at)
                VALUES (%s, %s, %s, %s, 'active', %s, %s)
            """, (new_key_id, tenant_id, new_key_hash, new_key_name, role, now.isoformat()))

        return {"new_key_id": new_key_id, "old_expires_at": old_expires_at}

    def list_api_keys(self, tenant_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM api_keys WHERE tenant_id = %s ORDER BY created_at DESC", (tenant_id,))
            return self._rows_to_dicts(cur, cur.fetchall())

    # ---- Channel tokens ----

    def create_channel_token(self, tenant_id: str, channel: str, token_hash: str,
                              external_user_id: Optional[str] = None) -> str:
        import uuid
        token_id = f"chan_{uuid.uuid4().hex[:16]}"
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO channel_tokens (id, tenant_id, channel, external_user_id, token_hash, status, created_at)
                VALUES (%s, %s, %s, %s, %s, 'active', %s)
                ON CONFLICT (token_hash) DO NOTHING
            """, (token_id, tenant_id, channel, external_user_id, token_hash, now))
        return token_id

    def get_channel_token_by_hash(self, key_hash: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM channel_tokens WHERE token_hash = %s AND status = 'active'", (key_hash,))
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def update_channel_token_last_used(self, token_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE channel_tokens SET last_used_at = %s WHERE id = %s", (now, token_id))

    def get_tenant_channel_connections(self, tenant_id: str) -> List[str]:
        """Return list of channel names (e.g. telegram, slack, discord) that have an active token for this tenant."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT DISTINCT channel FROM channel_tokens WHERE tenant_id = %s AND status = 'active'",
                (tenant_id,)
            )
            return [r[0] for r in cur.fetchall()]

    def get_tenant_alert_preferences(self, tenant_id: str) -> Dict[str, Any]:
        """Get alert preferences for a tenant. Returns defaults if none set."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT preferences FROM tenant_alert_preferences WHERE tenant_id = %s", (tenant_id,))
            row = cur.fetchone()
        if not row:
            return {
                "alert_on_blocked": True,
                "alert_on_policy_violation": True,
                "alert_on_drift": True,
                "alert_on_escalation": True,
            }
        raw = row[0] if isinstance(row[0], str) else (row.get("preferences") or "")
        if not raw:
            return {
                "alert_on_blocked": True,
                "alert_on_policy_violation": True,
                "alert_on_drift": True,
                "alert_on_escalation": True,
            }
        try:
            data = json.loads(raw)
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
        now = datetime.now(UTC).isoformat()
        allowed = ("alert_on_blocked", "alert_on_policy_violation", "alert_on_drift", "alert_on_escalation")
        current = self.get_tenant_alert_preferences(tenant_id)
        payload = {k: bool(preferences.get(k, current.get(k, True))) for k in allowed}
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO tenant_alert_preferences (tenant_id, preferences, updated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (tenant_id) DO UPDATE SET
                    preferences = EXCLUDED.preferences,
                    updated_at = EXCLUDED.updated_at
            """, (tenant_id, json.dumps(payload), now))
            conn.commit()

    # ---- Credentials ----

    def save_credential(self, credential_id: str, tool_name: str, credential_type: str,
                        credential_data: Any, encrypted: bool = False,
                        tenant_id: Optional[str] = None) -> None:
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO credentials (credential_id, tool_name, credential_type, credential_data,
                    status, created_at, updated_at, encrypted, tenant_id)
                VALUES (%s, %s, %s, %s, 'active', %s, %s, %s, %s)
                ON CONFLICT (credential_id) DO UPDATE SET
                    credential_data=EXCLUDED.credential_data,
                    updated_at=EXCLUDED.updated_at,
                    encrypted=EXCLUDED.encrypted,
                    tenant_id=EXCLUDED.tenant_id
            """, (credential_id, tool_name, credential_type,
                  json.dumps(credential_data) if not isinstance(credential_data, str) else credential_data,
                  now, now, encrypted, tenant_id))

    def get_credential(self, credential_id: str, tool_name: Optional[str] = None,
                       tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            query = "SELECT * FROM credentials WHERE credential_id = %s AND status = 'active'"
            params: List[Any] = [credential_id]
            if tool_name:
                query += " AND tool_name = %s"
                params.append(tool_name)
            if tenant_id is not None:
                query += " AND tenant_id = %s"
                params.append(tenant_id)
            else:
                query += " AND tenant_id IS NULL"
            query += " ORDER BY updated_at DESC LIMIT 1"
            cur.execute(query, tuple(params))
            row = cur.fetchone()
            if row is None:
                return None
            d = self._row_to_dict(cur, row)
            if d is None:
                return None
            try:
                d["credential_data"] = json.loads(d["credential_data"])
            except Exception:
                pass
            return d

    def get_credentials_by_tool(self, tool_name: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM credentials WHERE tool_name = %s AND status = 'active'", (tool_name,))
            result = []
            for row in cur.fetchall():
                d = self._row_to_dict(cur, row)
                if d is None:
                    continue
                try:
                    d["credential_data"] = json.loads(d["credential_data"])
                except Exception:
                    pass
                result.append(d)
            return result

    def update_credential_last_used(self, credential_id: str, tenant_id: Optional[str] = None):
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            if tenant_id is not None:
                cur.execute("UPDATE credentials SET last_used_at = %s WHERE credential_id = %s AND tenant_id = %s", (now, credential_id, tenant_id))
            else:
                cur.execute("UPDATE credentials SET last_used_at = %s WHERE credential_id = %s AND tenant_id IS NULL", (now, credential_id))

    def update_credential_status(
        self,
        credential_id: str,
        tenant_id: Optional[str],
        success: bool,
        error_message: Optional[str] = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        err_safe = (error_message or "")[:500] if error_message else None
        with self._get_connection() as conn:
            cur = conn.cursor()
            if tenant_id is not None:
                if success:
                    cur.execute(
                        "UPDATE credentials SET last_used_at = %s, last_error = NULL, updated_at = %s WHERE credential_id = %s AND tenant_id = %s",
                        (now, now, credential_id, tenant_id),
                    )
                else:
                    cur.execute(
                        "UPDATE credentials SET last_error = %s, updated_at = %s WHERE credential_id = %s AND tenant_id = %s",
                        (err_safe, now, credential_id, tenant_id),
                    )
            else:
                if success:
                    cur.execute(
                        "UPDATE credentials SET last_used_at = %s, last_error = NULL, updated_at = %s WHERE credential_id = %s AND tenant_id IS NULL",
                        (now, now, credential_id),
                    )
                else:
                    cur.execute(
                        "UPDATE credentials SET last_error = %s, updated_at = %s WHERE credential_id = %s AND tenant_id IS NULL",
                        (err_safe, now, credential_id),
                    )

    def delete_credential(self, credential_id: str, tenant_id: Optional[str] = None) -> bool:
        with self._get_connection() as conn:
            cur = conn.cursor()
            if tenant_id is not None:
                cur.execute("DELETE FROM credentials WHERE credential_id = %s AND tenant_id = %s", (credential_id, tenant_id))
            else:
                cur.execute("DELETE FROM credentials WHERE credential_id = %s AND tenant_id IS NULL", (credential_id,))
            return cur.rowcount > 0

    # ---- Rate limiting / counters ----

    def increment_counter(self, key: str, amount: int = 1) -> int:
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO rate_limits (key, count, window_start, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (key) DO UPDATE SET
                    count = rate_limits.count + EXCLUDED.count,
                    updated_at = EXCLUDED.updated_at
                RETURNING count
            """, (key, amount, now, now))
            row = cur.fetchone()
            return row[0] if row else amount

    def get_counter(self, key: str) -> int:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT count FROM rate_limits WHERE key = %s", (key,))
            row = cur.fetchone()
            return row[0] if row else 0

    # ---- Tenant usage ----

    def increment_tenant_usage(self, tenant_id: str, count: int = 1):
        now = datetime.now(UTC).isoformat()
        period_start = now[:7]  # YYYY-MM
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO tenant_usage (tenant_id, count, period_start, created_at)
                VALUES (%s, %s, %s, %s)
            """, (tenant_id, count, period_start, now))

    def get_tenant_usage(self, tenant_id: str, period_start: Optional[str] = None) -> int:
        with self._get_connection() as conn:
            cur = conn.cursor()
            if period_start:
                cur.execute(
                    "SELECT COALESCE(SUM(count), 0) FROM tenant_usage WHERE tenant_id=%s AND period_start>=%s",
                    (tenant_id, period_start)
                )
            else:
                now_month = datetime.now(UTC).isoformat()[:7]
                cur.execute(
                    "SELECT COALESCE(SUM(count), 0) FROM tenant_usage WHERE tenant_id=%s AND period_start>=%s",
                    (tenant_id, now_month)
                )
            row = cur.fetchone()
            return int(row[0]) if row else 0

    # ---- Token binding ----

    def bind_token_to_agent(self, token: str, agent_id: str):
        pass  # Token binding is ephemeral in PG version; use Redis for production

    def get_agent_id_for_token(self, token: str) -> Optional[str]:
        return None

    def update_token_last_used(self, token: str):
        pass

    # ---- Preferences / memory ----

    def write_preference(self, tenant_id: str, key: str, value: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO preference_memory (tenant_id, key, value, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tenant_id, key) DO UPDATE SET value=EXCLUDED.value, updated_at=EXCLUDED.updated_at
            """, (tenant_id, key, value, now))

    def read_preference(self, tenant_id: str, key: str) -> Optional[str]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM preference_memory WHERE tenant_id=%s AND key=%s", (tenant_id, key))
            row = cur.fetchone()
            return row[0] if row else None

    # ---- Stubs for less-critical methods (delegated to SQLite if needed) ----

    def create_connect_code(self, tenant_id: str, code: str, channel: str = 'telegram',
                             expires_at: Optional[str] = None) -> None:
        now = datetime.now(UTC).isoformat()
        expires = expires_at or now
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO connect_codes (code, tenant_id, channel, expires_at, created_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (code) DO NOTHING
            """, (code, tenant_id, channel, expires, now))

    def get_connect_code(self, code: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM connect_codes WHERE code = %s", (code,))
            row = cur.fetchone()
            return self._row_to_dict(cur, row) if row else None

    def mark_connect_code_used(self, code: str, used_by: Optional[str] = None) -> None:
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE connect_codes SET used_at=%s, used_by=%s WHERE code=%s", (now, used_by, code))

    def upsert_channel_binding(self, tenant_id: str, channel: str, external_user_id: str,
                                token_hash: str) -> None:
        self.create_channel_token(tenant_id, channel, token_hash, external_user_id)

    def list_connected_services_for_tenant(self, tenant_id: str) -> list:
        """List connected services for tenant. Returns empty list — integration service codes not implemented in PostgreSQL adapter."""
        return []

    # ---- Dummy methods for full interface compatibility ----

    def create_connect_service_code(self, *args, **kwargs):
        pass

    def get_connect_service_code(self, code: str) -> Optional[Dict[str, Any]]:
        return None

    def mark_connect_service_code_used(self, code: str) -> None:
        pass

    # ---- Agent registration for max_agents plan enforcement ----

    def register_agent(self, tenant_id: str, agent_id: str) -> bool:
        """Register an agent for a tenant. New agents get display_name agent_1, agent_2, ..."""
        from datetime import datetime, UTC
        now = datetime.now(UTC).isoformat()
        count = self.get_agent_count(tenant_id)
        display_name = f"agent_{count + 1}"
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO tenant_agents (tenant_id, agent_id, first_seen, display_name) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (tenant_id, agent_id, now, display_name)
                )
                conn.commit()
                return cur.rowcount > 0

    def get_agent_count(self, tenant_id: str) -> int:
        """Get count of distinct registered agents for a tenant."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM tenant_agents WHERE tenant_id = %s",
                    (tenant_id,)
                )
                row = cur.fetchone()
                return row[0] if row else 0

    def get_tenant_agents(self, tenant_id: str) -> List[Dict[str, Any]]:
        """Return all registered agents with display_name (agent_1, agent_2, ...). Backfills display_name if missing."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT agent_id, display_name, first_seen FROM tenant_agents WHERE tenant_id = %s ORDER BY first_seen ASC",
                    (tenant_id,)
                )
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description]
        result = []
        for i, r in enumerate(rows):
            aid = r[cols.index("agent_id")]
            dname = r[cols.index("display_name")]
            first_seen = r[cols.index("first_seen")]
            if not dname:
                dname = f"agent_{i + 1}"
                self.set_agent_display_name(tenant_id, aid, dname)
            result.append({"agent_id": aid, "display_name": dname, "first_seen": first_seen})
        result.reverse()
        return result

    def set_agent_display_name(self, tenant_id: str, agent_id: str, display_name: Optional[str]) -> bool:
        """Set or clear display name for an agent."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE tenant_agents SET display_name = %s WHERE tenant_id = %s AND agent_id = %s",
                    (display_name.strip() if display_name and display_name.strip() else None, tenant_id, agent_id),
                )
                conn.commit()
                return cur.rowcount > 0

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
                with conn.cursor() as cur:
                    # ── 1. Update agents table (best-effort; row may not exist) ──────
                    agents_col = agents_col_map.get(verdict_upper)
                    if agents_col:
                        # agents_col is sourced from a fixed allowlist above, not user input.
                        cur.execute(
                            f"UPDATE agents SET total_actions = total_actions + 1, "
                            f"{agents_col} = {agents_col} + 1, last_seen_at = %s "
                            f"WHERE agent_id = %s",
                            (now, agent_id),
                        )
                    else:
                        cur.execute(
                            "UPDATE agents SET total_actions = total_actions + 1, last_seen_at = %s WHERE agent_id = %s",
                            (now, agent_id),
                        )

                    # ── 2. Upsert agent_stats table (finer-grained, used by Agents API) ─
                    if tenant_id:
                        stats_col = stats_col_map.get(verdict_upper, "error_count")
                        # stats_col is sourced from a fixed allowlist above, not user input.
                        cur.execute(f"""  # safe: schema-only
                            INSERT INTO agent_stats
                                (tenant_id, agent_id, total_actions, {stats_col}, last_action_at)
                            VALUES (%s, %s, 1, 1, %s)
                            ON CONFLICT (tenant_id, agent_id) DO UPDATE SET
                                total_actions  = agent_stats.total_actions + 1,
                                {stats_col}    = agent_stats.{stats_col} + 1,
                                last_action_at = EXCLUDED.last_action_at
                        """, (tenant_id, agent_id, now))

                    conn.commit()
        except Exception as _err:
            logger.warning(
                "update_agent_stats failed (non-blocking): agent=%s verdict=%s err=%s",
                agent_id, verdict, _err,
            )

    # ---- Audit retention enforcement ----

    def delete_expired_audit_events(self, tenant_id: str, retention_days: int) -> int:
        """Delete audit events older than retention_days for a tenant. Returns count deleted."""
        from datetime import datetime, UTC, timedelta
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM audit_events WHERE tenant_id = %s AND timestamp < %s",
                    (tenant_id, cutoff)
                )
                conn.commit()
                return cur.rowcount

    # ---- Tenant listing ----

    def list_tenants(self) -> List[Dict[str, Any]]:
        """Return a list of all tenant dicts."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, plan, status FROM tenants")
                rows = cur.fetchall()
                return [{"id": r[0], "plan": r[1], "status": r[2]} for r in rows]

    # ── Human Review Queue ──────────────────────────────────────────────────────

    def get_review_queue(self, tenant_id: Optional[str] = None, status: str = "pending", limit: int = 50) -> List[Dict[str, Any]]:
        """Get human review queue items."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                q = "SELECT * FROM review_queue WHERE status = %s"
                params: List[Any] = [status]
                if tenant_id:
                    q += " AND tenant_id = %s"
                    params.append(tenant_id)
                q += f" ORDER BY created_at DESC LIMIT {int(limit)}"
                cur.execute(q, params)
                rows = cur.fetchall()
                if not rows:
                    return []
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, r)) for r in rows]

    def enqueue_review(self, tenant_id: str, action_id: str, agent_id: str,
                       action_type: str, reason: str, context: Optional[dict] = None,
                       timeout_seconds: int = 300) -> str:
        """Add an action to the human review queue."""
        import uuid as _uuid
        review_id = str(_uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO review_queue
                        (id, tenant_id, action_id, agent_id, action_type, reason, context, timeout_seconds, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (review_id, tenant_id, action_id, agent_id, action_type, reason,
                      json.dumps(context or {}), timeout_seconds, now))
                conn.commit()
        return review_id

    def resolve_review_item(self, review_id: str, decision: str, reviewer_id: str, reason: str = "") -> bool:
        """Resolve a review queue item with a human decision."""
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE review_queue
                    SET status = %s, decision = %s, reviewer_id = %s, reviewer_reason = %s, resolved_at = %s
                    WHERE id = %s AND status = 'pending'
                """, (decision + "d", decision, reviewer_id, reason, now, review_id))
                conn.commit()
                return cur.rowcount > 0

    # ── Sandbox helpers ─────────────────────────────────────────────────────────

    def get_or_create_sandbox_tenant(self) -> Dict[str, Any]:
        """Get or create the sandbox tenant with a pre-seeded API key."""
        import hashlib as _hashlib
        SANDBOX_TENANT_ID = "tenant_sandbox_edon"
        SANDBOX_USER_ID = "user_sandbox_edon"
        SANDBOX_API_KEY = "edon_sandbox_key_dev_only"
        SANDBOX_KEY_HASH = _hashlib.sha256(SANDBOX_API_KEY.encode()).hexdigest()
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (id, email, auth_provider, auth_subject, role, created_at, updated_at)
                    VALUES (%s, %s, 'sandbox', %s, 'admin', %s, %s)
                    ON CONFLICT (id) DO NOTHING
                """, (SANDBOX_USER_ID, "sandbox@edon.dev", SANDBOX_USER_ID, now, now))
                cur.execute("""
                    INSERT INTO tenants (id, user_id, status, plan, created_at, updated_at)
                    VALUES (%s, %s, 'active', 'free', %s, %s)
                    ON CONFLICT (id) DO NOTHING
                """, (SANDBOX_TENANT_ID, SANDBOX_USER_ID, now, now))
                cur.execute("""
                    INSERT INTO api_keys (id, tenant_id, key_hash, name, status, role, created_at)
                    VALUES (%s, %s, %s, 'sandbox-key', 'active', 'admin', %s)
                    ON CONFLICT (id) DO NOTHING
                """, ("key_sandbox_edon", SANDBOX_TENANT_ID, SANDBOX_KEY_HASH, now))
                conn.commit()
        return {
            "tenant_id": SANDBOX_TENANT_ID,
            "api_key": SANDBOX_API_KEY,
            "key_hash": SANDBOX_KEY_HASH,
            "status": "active",
            "plan": "free",
            "is_sandbox": True,
        }

    def reset_sandbox(self) -> int:
        """Clear all sandbox audit events. Returns count deleted."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM sandbox_audit_events")
                row = cur.fetchone()
                count = row[0] if row else 0
                cur.execute("DELETE FROM sandbox_audit_events")
                conn.commit()
        return count

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
    ) -> Dict[str, Any]:
        """Register or update a full agent record (upsert)."""
        import json as _json
        now = datetime.now(UTC).isoformat()
        caps_json = _json.dumps(capabilities or [])
        meta_json = _json.dumps(metadata or {})
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO agents
                        (agent_id, tenant_id, name, agent_type, description, capabilities,
                         policy_pack, mag_enabled, cav_enabled, status, registered_at,
                         last_seen_at, total_actions, total_allowed, total_blocked,
                         total_escalated, metadata, vendor_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, 'active', %s, %s, 0, 0, 0, 0, %s, %s)
                    ON CONFLICT (agent_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        agent_type = EXCLUDED.agent_type,
                        description = EXCLUDED.description,
                        capabilities = EXCLUDED.capabilities,
                        policy_pack = EXCLUDED.policy_pack,
                        mag_enabled = EXCLUDED.mag_enabled,
                        metadata = EXCLUDED.metadata,
                        last_seen_at = EXCLUDED.last_seen_at,
                        vendor_id = COALESCE(EXCLUDED.vendor_id, agents.vendor_id)
                """, (
                    agent_id, tenant_id, name, agent_type, description, caps_json,
                    policy_pack, 1 if mag_enabled else 0, now, now, meta_json, vendor_id,
                ))
                conn.commit()
        return {"agent_id": agent_id, "tenant_id": tenant_id, "name": name,
                "status": "active", "vendor_id": vendor_id}

    def get_agent_vendor_id(self, agent_id: str, tenant_id: str) -> Optional[str]:
        """Fast lookup of vendor_id for an agent."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT vendor_id FROM agents WHERE agent_id=%s AND tenant_id=%s",
                    (agent_id, tenant_id),
                )
                row = cur.fetchone()
                return row[0] if row else None

    def insert_sandbox_event(self, event: Dict[str, Any]) -> None:
        """Insert a single event into sandbox_audit_events."""
        import json as _json
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO sandbox_audit_events
                        (timestamp, action_id, action_tool, action_op, action_params,
                         action_source, action_estimated_risk, action_computed_risk,
                         decision_verdict, decision_reason_code, decision_explanation,
                         decision_policy_version, policy_rule_id, action_summary,
                         stated_intent, agent_id, customer_id, context,
                         anomaly_score, processing_latency_ms, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    event.get("timestamp", now),
                    event["action_id"],
                    event["action_tool"],
                    event["action_op"],
                    _json.dumps(event.get("action_params", {})),
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
                    _json.dumps(event.get("context", {})),
                    event.get("anomaly_score"),
                    event.get("processing_latency_ms"),
                    now,
                ))
                conn.commit()

    # ── IP allowlist helpers ────────────────────────────────────────────────────

    def get_ip_allowlist(self, tenant_id: str) -> List[str]:
        """Return list of CIDR strings for a tenant. Empty list means no restriction."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT cidr FROM ip_allowlists WHERE tenant_id = %s ORDER BY cidr",
                    (tenant_id,),
                )
                rows = cur.fetchall()
                return [r[0] for r in rows]

    def add_ip_to_allowlist(self, tenant_id: str, cidr: str) -> None:
        """Add a CIDR to the tenant's IP allowlist. Silently ignores duplicates."""
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO ip_allowlists (tenant_id, cidr, created_at) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                    (tenant_id, cidr, now),
                )
                conn.commit()

    def remove_ip_from_allowlist(self, tenant_id: str, cidr: str) -> bool:
        """Remove a CIDR from the tenant's IP allowlist. Returns True if a row was deleted."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM ip_allowlists WHERE tenant_id = %s AND cidr = %s",
                    (tenant_id, cidr),
                )
                conn.commit()
                return cur.rowcount > 0

    # ── Alert Rules ─────────────────────────────────────────────────────────────

    def create_alert_rule(
        self, tenant_id: str, name: str, metric: str, operator: str,
        threshold: float, webhook_url: str, window_minutes: int = 60,
        severity: str = "warning",
    ) -> str:
        import uuid as _uuid
        rule_id = str(_uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO alert_rules
                        (id, tenant_id, name, metric, operator, threshold, window_minutes,
                         webhook_url, severity, enabled, created_at, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,true,%s,%s)
                """, (rule_id, tenant_id, name, metric, operator, threshold,
                      window_minutes, webhook_url, severity, now, now))
                conn.commit()
        return rule_id

    def list_alert_rules(self, tenant_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM alert_rules WHERE tenant_id=%s ORDER BY created_at ASC",
                    (tenant_id,),
                )
                return [dict(r) for r in cur.fetchall()]

    def get_alert_rule(self, rule_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM alert_rules WHERE id=%s AND tenant_id=%s",
                    (rule_id, tenant_id),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def delete_alert_rule(self, rule_id: str, tenant_id: str) -> bool:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM alert_rules WHERE id=%s AND tenant_id=%s",
                    (rule_id, tenant_id),
                )
                conn.commit()
                return cur.rowcount > 0

    def create_alert_incident(
        self, tenant_id: str, rule_id: str, rule_name: str, severity: str,
        metric: str, threshold: float, observed_value: float, window_minutes: int,
        webhook_url: str, payload: Optional[Dict] = None,
    ) -> str:
        import uuid as _uuid
        incident_id = str(_uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO alert_incidents
                        (id, tenant_id, rule_id, rule_name, severity, metric, threshold,
                         observed_value, window_minutes, webhook_url, webhook_status,
                         webhook_attempts, payload, triggered_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',0,%s,%s)
                """, (incident_id, tenant_id, rule_id, rule_name, severity, metric,
                      threshold, observed_value, window_minutes, webhook_url,
                      json.dumps(payload or {}), now))
                conn.commit()
        return incident_id

    def update_alert_incident_webhook(self, incident_id: str, status: str, attempts: int) -> None:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE alert_incidents SET webhook_status=%s, webhook_attempts=%s WHERE id=%s",
                    (status, attempts, incident_id),
                )
                conn.commit()

    def list_alert_incidents(
        self, tenant_id: str, rule_id: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if rule_id:
                    cur.execute(
                        "SELECT * FROM alert_incidents WHERE tenant_id=%s AND rule_id=%s "
                        "ORDER BY triggered_at DESC LIMIT %s",
                        (tenant_id, rule_id, limit),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM alert_incidents WHERE tenant_id=%s "
                        "ORDER BY triggered_at DESC LIMIT %s",
                        (tenant_id, limit),
                    )
                return [dict(r) for r in cur.fetchall()]

    def evaluate_alert_rules(self, tenant_id: str) -> List[Dict[str, Any]]:
        """Delegate to list_alert_rules — evaluation logic is same as SQLite version."""
        # Import SQLite version for shared logic (only metric queries differ)
        rules = [r for r in self.list_alert_rules(tenant_id) if r.get("enabled")]
        if not rules:
            return []
        from datetime import timedelta as _td
        triggered = []
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                for rule in rules:
                    metric = rule["metric"]
                    threshold = float(rule["threshold"])
                    operator = rule["operator"]
                    window_min = int(rule.get("window_minutes", 60))
                    cutoff_ts = (datetime.now(UTC) - _td(minutes=window_min)).isoformat()
                    if metric == "anomaly_score":
                        cur.execute(
                            "SELECT AVG(anomaly_score) FROM audit_events "
                            "WHERE customer_id=%s AND timestamp>=%s AND anomaly_score IS NOT NULL",
                            (tenant_id, cutoff_ts),
                        )
                        row = cur.fetchone()
                        observed = float(row[0]) if row and row[0] is not None else 0.0
                    elif metric == "block_rate":
                        cur.execute(
                            "SELECT COUNT(*) FROM audit_events WHERE customer_id=%s AND timestamp>=%s",
                            (tenant_id, cutoff_ts),
                        )
                        total = (cur.fetchone() or [1])[0] or 1
                        cur.execute(
                            "SELECT COUNT(*) FROM audit_events "
                            "WHERE customer_id=%s AND timestamp>=%s AND decision_verdict='BLOCK'",
                            (tenant_id, cutoff_ts),
                        )
                        blocked = (cur.fetchone() or [0])[0]
                        observed = blocked / total
                    elif metric == "escalation_count":
                        cur.execute(
                            "SELECT COUNT(*) FROM audit_events "
                            "WHERE customer_id=%s AND timestamp>=%s AND decision_verdict='ESCALATE'",
                            (tenant_id, cutoff_ts),
                        )
                        observed = (cur.fetchone() or [0])[0]
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
        self, tenant_id: str, change_type: str, entity_type: str,
        entity_id: Optional[str] = None, entity_name: Optional[str] = None,
        diff_json: Optional[Dict] = None, changed_by: Optional[str] = None,
    ) -> str:
        import uuid as _uuid
        change_id = str(_uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO policy_changes
                        (id, tenant_id, changed_by, change_type, entity_type,
                         entity_id, entity_name, diff_json, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (change_id, tenant_id, changed_by, change_type, entity_type,
                      entity_id, entity_name, json.dumps(diff_json or {}), now))
                conn.commit()
        return change_id

    def list_policy_changes(
        self, tenant_id: str, entity_type: Optional[str] = None, limit: int = 200
    ) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if entity_type:
                    cur.execute(
                        "SELECT * FROM policy_changes WHERE tenant_id=%s AND entity_type=%s "
                        "ORDER BY created_at DESC LIMIT %s",
                        (tenant_id, entity_type, limit),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM policy_changes WHERE tenant_id=%s "
                        "ORDER BY created_at DESC LIMIT %s",
                        (tenant_id, limit),
                    )
                rows = cur.fetchall()
                result = []
                for r in rows:
                    d = dict(r)
                    if d.get("diff_json") and isinstance(d["diff_json"], str):
                        try:
                            d["diff_json"] = json.loads(d["diff_json"])
                        except Exception:
                            pass
                    result.append(d)
                return result

    # ── Data Retention & Purge ─────────────────────────────────────────────────

    def get_tenant_retention_days(self, tenant_id: str) -> int:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT retention_days FROM tenants WHERE id=%s", (tenant_id,))
                row = cur.fetchone()
                return int(row[0]) if row and row[0] is not None else 365

    def set_tenant_retention_days(self, tenant_id: str, retention_days: int) -> None:
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE tenants SET retention_days=%s, updated_at=%s WHERE id=%s",
                    (retention_days, now, tenant_id),
                )
                conn.commit()

    def purge_old_events(self, tenant_id: str, retention_days: int) -> int:
        from datetime import timedelta as _td
        cutoff = (datetime.now(UTC) - _td(days=retention_days)).isoformat()
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM audit_events WHERE customer_id=%s AND timestamp<%s",
                    (tenant_id, cutoff),
                )
                count = (cur.fetchone() or [0])[0]
                if count > 0:
                    cur.execute(
                        "DELETE FROM audit_events WHERE customer_id=%s AND timestamp<%s",
                        (tenant_id, cutoff),
                    )
                now = datetime.now(UTC).isoformat()
                cur.execute(
                    "INSERT INTO purge_log (tenant_id,purged_count,retention_days,purged_before,purged_at) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (tenant_id, count, retention_days, cutoff, now),
                )
                conn.commit()
        return count

    def list_purge_log(self, tenant_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM purge_log WHERE tenant_id=%s ORDER BY purged_at DESC LIMIT %s",
                    (tenant_id, limit),
                )
                return [dict(r) for r in cur.fetchall()]

    # ── DSAR ──────────────────────────────────────────────────────────────────

    def create_dsar_request(
        self, tenant_id: str, subject_id: str, request_type: str,
        notes: Optional[str] = None,
    ) -> str:
        import uuid as _uuid
        req_id = str(_uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO dsar_requests
                        (id,tenant_id,subject_id,request_type,status,requested_at,notes)
                    VALUES (%s,%s,%s,%s,'pending',%s,%s)
                """, (req_id, tenant_id, subject_id, request_type, now, notes))
                conn.commit()
        return req_id

    def get_subject_audit_events(self, tenant_id: str, subject_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM audit_events WHERE customer_id=%s AND agent_id=%s ORDER BY timestamp ASC",
                    (tenant_id, subject_id),
                )
                return [dict(r) for r in cur.fetchall()]

    def anonymize_subject_data(self, tenant_id: str, subject_id: str) -> int:
        anon = "[REDACTED-DSAR]"
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM audit_events WHERE customer_id=%s AND agent_id=%s",
                    (tenant_id, subject_id),
                )
                count = (cur.fetchone() or [0])[0]
                if count > 0:
                    cur.execute("""
                        UPDATE audit_events
                        SET agent_id=%s, action_params='{}', context='{}',
                            user_message=%s, stated_intent=%s
                        WHERE customer_id=%s AND agent_id=%s
                    """, (anon, anon, anon, tenant_id, subject_id))
                now = datetime.now(UTC).isoformat()
                cur.execute(
                    "UPDATE dsar_requests SET status='completed', completed_at=%s "
                    "WHERE tenant_id=%s AND subject_id=%s AND request_type='deletion' AND status='pending'",
                    (now, tenant_id, subject_id),
                )
                conn.commit()
        return count

    def list_dsar_requests(self, tenant_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM dsar_requests WHERE tenant_id=%s ORDER BY requested_at DESC LIMIT %s",
                    (tenant_id, limit),
                )
                return [dict(r) for r in cur.fetchall()]

    # ── Device Registry ────────────────────────────────────────────────────────

    def register_device(
        self, tenant_id: str, device_id: str, device_type: str, name: str,
        vendor_id: Optional[str] = None, serial_number: Optional[str] = None,
        make: Optional[str] = None, model: Optional[str] = None,
        department: Optional[str] = None, location: Optional[str] = None,
        requires_supervision: bool = False, metadata: Optional[Dict] = None,
    ) -> str:
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO devices
                        (device_id,tenant_id,vendor_id,device_type,name,serial_number,
                         make,model,department,location,status,requires_supervision,
                         metadata,registered_at,updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'available',%s,%s,%s,%s)
                """, (device_id, tenant_id, vendor_id, device_type, name, serial_number,
                      make, model, department, location,
                      requires_supervision, json.dumps(metadata or {}), now, now))
                conn.commit()
        return device_id

    def get_device(self, device_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM devices WHERE device_id=%s AND tenant_id=%s",
                    (device_id, tenant_id),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def list_devices(
        self, tenant_id: str, department: Optional[str] = None,
        device_type: Optional[str] = None, status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                q = "SELECT * FROM devices WHERE tenant_id=%s"
                params: list = [tenant_id]
                if department:
                    q += " AND department=%s"; params.append(department)
                if device_type:
                    q += " AND device_type=%s"; params.append(device_type)
                if status:
                    q += " AND status=%s"; params.append(status)
                q += " ORDER BY department, name ASC"
                cur.execute(q, params)
                return [dict(r) for r in cur.fetchall()]

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
        now = datetime.now(UTC).isoformat()
        updates["updated_at"] = now
        set_clause = ", ".join(f"{k}=%s" for k in updates)
        values = list(updates.values()) + [device_id, tenant_id]
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE devices SET {set_clause} WHERE device_id=%s AND tenant_id=%s",  # noqa: S608
                    values,
                )
                conn.commit()
                return cur.rowcount > 0

    def deregister_device(self, device_id: str, tenant_id: str) -> bool:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM devices WHERE device_id=%s AND tenant_id=%s",
                    (device_id, tenant_id),
                )
                conn.commit()
                return cur.rowcount > 0

    def create_device_binding(
        self, tenant_id: str, agent_id: str, device_id: str,
        permission_level: str = "full_control", authorized_by: Optional[str] = None,
        valid_from: Optional[str] = None, valid_until: Optional[str] = None,
        shift_start: Optional[str] = None, shift_end: Optional[str] = None,
        requires_supervision: bool = False,
    ) -> str:
        import uuid as _uuid
        binding_id = str(_uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO agent_device_bindings
                        (id,tenant_id,agent_id,device_id,permission_level,authorized_by,
                         valid_from,valid_until,shift_start,shift_end,requires_supervision,enabled,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,%s)
                    ON CONFLICT(agent_id,device_id) DO UPDATE SET
                        permission_level=EXCLUDED.permission_level,
                        authorized_by=EXCLUDED.authorized_by,
                        valid_from=EXCLUDED.valid_from, valid_until=EXCLUDED.valid_until,
                        shift_start=EXCLUDED.shift_start, shift_end=EXCLUDED.shift_end,
                        requires_supervision=EXCLUDED.requires_supervision, enabled=true
                """, (binding_id, tenant_id, agent_id, device_id, permission_level,
                      authorized_by, valid_from, valid_until, shift_start, shift_end,
                      requires_supervision, now))
                conn.commit()
        return binding_id

    def get_device_binding(self, agent_id: str, device_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM agent_device_bindings WHERE agent_id=%s AND device_id=%s AND enabled=true",
                    (agent_id, device_id),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def list_device_bindings(
        self, tenant_id: str, device_id: Optional[str] = None, agent_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if device_id:
                    cur.execute(
                        "SELECT * FROM agent_device_bindings WHERE tenant_id=%s AND device_id=%s ORDER BY created_at ASC",
                        (tenant_id, device_id),
                    )
                elif agent_id:
                    cur.execute(
                        "SELECT * FROM agent_device_bindings WHERE tenant_id=%s AND agent_id=%s ORDER BY created_at ASC",
                        (tenant_id, agent_id),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM agent_device_bindings WHERE tenant_id=%s ORDER BY device_id, agent_id ASC",
                        (tenant_id,),
                    )
                return [dict(r) for r in cur.fetchall()]

    def revoke_device_binding(self, agent_id: str, device_id: str, tenant_id: str) -> bool:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM agent_device_bindings WHERE agent_id=%s AND device_id=%s AND tenant_id=%s",
                    (agent_id, device_id, tenant_id),
                )
                conn.commit()
                return cur.rowcount > 0

    def acquire_device_lock(
        self, device_id: str, tenant_id: str, agent_id: str, action_id: Optional[str] = None
    ) -> Optional[str]:
        import uuid as _uuid
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status, current_agent_id, current_session_id FROM devices "
                    "WHERE device_id=%s AND tenant_id=%s FOR UPDATE",
                    (device_id, tenant_id),
                )
                row = cur.fetchone()
                if not row:
                    return None
                status, current_agent, current_session = row
                if current_agent == agent_id and current_session:
                    return current_session
                if status == "in_use" and current_agent and current_agent != agent_id:
                    return None
                session_id = str(_uuid.uuid4())
                cur.execute("""
                    UPDATE devices
                    SET status='in_use', current_agent_id=%s, current_session_id=%s,
                        session_started_at=%s, updated_at=%s
                    WHERE device_id=%s AND tenant_id=%s
                """, (agent_id, session_id, now, now, device_id, tenant_id))
                cur.execute("""
                    INSERT INTO device_sessions
                        (session_id,tenant_id,device_id,agent_id,action_id,started_at)
                    VALUES (%s,%s,%s,%s,%s,%s)
                """, (session_id, tenant_id, device_id, agent_id, action_id, now))
                conn.commit()
                return session_id

    def release_device_lock(
        self, device_id: str, tenant_id: str, agent_id: str,
        end_reason: str = "released", force: bool = False,
    ) -> bool:
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT current_agent_id, current_session_id, session_started_at "
                    "FROM devices WHERE device_id=%s AND tenant_id=%s FOR UPDATE",
                    (device_id, tenant_id),
                )
                row = cur.fetchone()
                if not row:
                    return False
                current_agent, session_id, started_at = row
                if not force and current_agent != agent_id:
                    return False
                duration = None
                if started_at:
                    try:
                        from datetime import timedelta as _td
                        start_dt = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
                        end_dt = datetime.fromisoformat(now)
                        duration = (end_dt - start_dt).total_seconds()
                    except Exception:
                        pass
                cur.execute("""
                    UPDATE devices
                    SET status='available', current_agent_id=NULL, current_session_id=NULL,
                        session_started_at=NULL, updated_at=%s
                    WHERE device_id=%s AND tenant_id=%s
                """, (now, device_id, tenant_id))
                if session_id:
                    cur.execute("""
                        UPDATE device_sessions SET ended_at=%s, end_reason=%s, duration_seconds=%s
                        WHERE session_id=%s
                    """, (now, end_reason, duration, session_id))
                conn.commit()
                return True

    def list_device_sessions(self, device_id: str, tenant_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT ds.*, d.name as device_name, d.device_type
                    FROM device_sessions ds
                    JOIN devices d ON d.device_id = ds.device_id
                    WHERE ds.device_id=%s AND ds.tenant_id=%s
                    ORDER BY ds.started_at DESC LIMIT %s
                """, (device_id, tenant_id, limit))
                return [dict(r) for r in cur.fetchall()]

    def get_authorization_matrix(self, tenant_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        d.device_id, d.name as device_name, d.device_type,
                        d.department, d.location, d.status, d.current_agent_id,
                        d.vendor_id as device_vendor_id,
                        b.agent_id, b.permission_level, b.requires_supervision,
                        b.valid_until, b.shift_start, b.shift_end, b.enabled as binding_enabled,
                        a.vendor_id as agent_vendor_id,
                        a.name as agent_name,
                        a.agent_type
                    FROM devices d
                    LEFT JOIN agent_device_bindings b ON b.device_id = d.device_id
                    LEFT JOIN agents a ON a.agent_id = b.agent_id AND a.tenant_id = d.tenant_id
                    WHERE d.tenant_id=%s
                    ORDER BY d.department, d.name, b.agent_id
                """, (tenant_id,))
                return [dict(r) for r in cur.fetchall()]

    def get_vendor_summary(self, tenant_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        a.vendor_id,
                        COUNT(ae.id)                                          AS total_actions,
                        SUM(CASE WHEN ae.decision_verdict='ALLOW'    THEN 1 ELSE 0 END) AS allowed,
                        SUM(CASE WHEN ae.decision_verdict='BLOCK'    THEN 1 ELSE 0 END) AS blocked,
                        SUM(CASE WHEN ae.decision_verdict='ESCALATE' THEN 1 ELSE 0 END) AS escalated,
                        ROUND(
                            CAST(SUM(CASE WHEN ae.decision_verdict='BLOCK' THEN 1 ELSE 0 END) AS NUMERIC)
                            / GREATEST(COUNT(ae.id), 1) * 100, 2
                        )                                                     AS block_rate_pct,
                        MAX(ae.timestamp)                                     AS last_action_at,
                        COUNT(DISTINCT ae.agent_id)                           AS distinct_agents,
                        COUNT(DISTINCT ae.device_id)                          AS distinct_devices
                    FROM agents a
                    LEFT JOIN audit_events ae
                        ON ae.agent_id = a.agent_id AND ae.customer_id = a.tenant_id
                    WHERE a.tenant_id=%s AND a.vendor_id IS NOT NULL
                    GROUP BY a.vendor_id
                    ORDER BY total_actions DESC
                """, (tenant_id,))
                summaries = [dict(r) for r in cur.fetchall()]
                for s in summaries:
                    vid = s["vendor_id"]
                    cur.execute("""
                        SELECT DISTINCT d.device_id, d.name, d.device_type, d.department,
                                        d.status, d.current_agent_id
                        FROM agent_device_bindings b
                        JOIN agents a ON a.agent_id = b.agent_id AND a.tenant_id = b.tenant_id
                        JOIN devices d ON d.device_id = b.device_id
                        WHERE a.tenant_id=%s AND a.vendor_id=%s AND b.enabled=true
                        ORDER BY d.department, d.name
                    """, (tenant_id, vid))
                    s["authorized_devices"] = [dict(r) for r in cur.fetchall()]
                    s["currently_controlling"] = [
                        d for d in s["authorized_devices"]
                        if d.get("status") == "in_use" and d.get("current_agent_id")
                    ]
                return summaries

    def check_device_binding_valid(
        self, agent_id: str, device_id: str, tenant_id: str
    ) -> Dict[str, Any]:
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
        if valid_from and now_ts < str(valid_from):
            return {"allowed": False, "reason": f"Binding not valid until {valid_from}"}
        if valid_until and now_ts > str(valid_until):
            return {"allowed": False, "reason": f"Binding expired at {valid_until}"}
        shift_start = binding.get("shift_start")
        shift_end = binding.get("shift_end")
        if shift_start and shift_end:
            if not (str(shift_start) <= now_time <= str(shift_end)):
                return {"allowed": False, "reason": f"Outside authorized shift window ({shift_start}–{shift_end})"}
        return {
            "allowed": True,
            "requires_supervision": bool(binding.get("requires_supervision")),
            "permission_level": binding.get("permission_level", "full_control"),
            "binding": binding,
        }

    # ── Clinical Safety Mode ────────────────────────────────────────────────────

    def activate_clinical_safety_mode(
        self, tenant_id: str, activated_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """Seed all Clinical Safety Mode rules for a tenant (PostgreSQL)."""
        from ..clinical_safety import CLINICAL_SAFETY_RULES
        import uuid as _uuid

        created = 0
        updated = 0
        now = datetime.now(UTC).isoformat()

        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                for rule in CLINICAL_SAFETY_RULES:
                    tags_json = json.dumps(rule["condition_tags"]) if rule.get("condition_tags") else None
                    cur.execute(
                        "SELECT id FROM policy_rules WHERE tenant_id=%s AND rule_code=%s",
                        (tenant_id, rule["rule_code"]),
                    )
                    existing = cur.fetchone()
                    if existing:
                        cur.execute("""
                            UPDATE policy_rules
                            SET enabled=true, protected=true, regulation=%s,
                                name=%s, description=%s, action=%s,
                                condition_tool=%s, condition_op=%s,
                                condition_risk_level=%s, condition_tags=%s,
                                priority=%s, updated_at=%s
                            WHERE tenant_id=%s AND rule_code=%s
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
                        cur.execute("""
                            INSERT INTO policy_rules
                                (id, tenant_id, name, description, condition_tool,
                                 condition_op, condition_risk_level, condition_tags,
                                 action, priority, enabled, rule_code, protected,
                                 regulation, created_at, updated_at)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,%s,true,%s,%s,%s)
                        """, (
                            rule_id, tenant_id, rule["name"], rule["description"],
                            rule.get("condition_tool"), rule.get("condition_op"),
                            rule.get("condition_risk_level"), tags_json,
                            rule["action"], rule["priority"],
                            rule["rule_code"], rule["regulation"], now, now,
                        ))
                        created += 1
            conn.commit()

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
        """Check each regulation's required rules are present and enabled (PostgreSQL)."""
        from ..clinical_safety import REQUIRED_RULES_BY_REGULATION, REGULATION_LABELS

        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT rule_code, enabled, protected, regulation
                    FROM policy_rules
                    WHERE tenant_id=%s AND rule_code IS NOT NULL
                """, (tenant_id,))
                rows = cur.fetchall()

        rule_map: Dict[str, Dict] = {}
        for row in rows:
            rule_map[row["rule_code"]] = {
                "enabled": bool(row["enabled"]),
                "protected": bool(row["protected"]),
                "regulation": row["regulation"],
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
                status = "warning"

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
        """Look up a policy rule by its regulation rule_code (PostgreSQL)."""
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM policy_rules WHERE tenant_id=%s AND rule_code=%s",
                    (tenant_id, rule_code),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    # ── Shadow Mode ─────────────────────────────────────────────────────────────

    def get_shadow_mode(self, tenant_id: str) -> bool:
        """Return True if shadow mode is enabled for the tenant."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS tenant_settings (
                        tenant_id TEXT NOT NULL,
                        key TEXT NOT NULL,
                        value TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (tenant_id, key)
                    )
                """)
                conn.commit()
                cur.execute(
                    "SELECT value FROM tenant_settings WHERE tenant_id=%s AND key='shadow_mode'",
                    (tenant_id,),
                )
                row = cur.fetchone()
                return row is not None and row[0] == "true"

    def set_shadow_mode(self, tenant_id: str, enabled: bool) -> None:
        """Enable or disable shadow mode for the tenant."""
        now = datetime.now(UTC).isoformat()
        value = "true" if enabled else "false"
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO tenant_settings (tenant_id, key, value, updated_at)
                    VALUES (%s, 'shadow_mode', %s, %s)
                    ON CONFLICT (tenant_id, key) DO UPDATE
                        SET value=EXCLUDED.value, updated_at=EXCLUDED.updated_at
                """, (tenant_id, value, now))
                conn.commit()
