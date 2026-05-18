"""Policy Storage - Database persistence for policy rules.

tenant_id is enforced at the DB query level on every read, write, update,
and delete. No cross-tenant data is ever returned regardless of what the
application layer passes in.
"""

import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, UTC

from .schemas import PolicyRule, PolicySet

logger = logging.getLogger(__name__)

_DEFAULT_TENANT = "default"


class PolicyStorage:
    """Database storage for policy rules, scoped to a tenant on every query."""

    def __init__(self, db_connection):
        self.db = db_connection
        self._init_schema()
        self._migrate_schema()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _init_schema(self):
        cursor = self.db.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS policy_sets (
                set_id      TEXT NOT NULL,
                tenant_id   TEXT NOT NULL DEFAULT 'default',
                name        TEXT NOT NULL,
                description TEXT,
                domain      TEXT,
                version     INTEGER NOT NULL DEFAULT 1,
                enabled     INTEGER NOT NULL DEFAULT 1,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                PRIMARY KEY (set_id, tenant_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS policy_rules (
                rule_id             TEXT NOT NULL,
                tenant_id           TEXT NOT NULL DEFAULT 'default',
                set_id              TEXT,
                name                TEXT NOT NULL,
                rule_type           TEXT NOT NULL,
                field               TEXT NOT NULL,
                action              TEXT NOT NULL,
                priority            INTEGER NOT NULL DEFAULT 50,
                threshold           REAL,
                threshold_operator  TEXT,
                range_min           REAL,
                range_max           REAL,
                value               TEXT,
                description         TEXT,
                domain              TEXT,
                version             INTEGER NOT NULL DEFAULT 1,
                enabled             INTEGER NOT NULL DEFAULT 1,
                created_at          TEXT NOT NULL,
                updated_at          TEXT NOT NULL,
                PRIMARY KEY (rule_id, tenant_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS policy_rule_history (
                history_id          INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id             TEXT NOT NULL,
                tenant_id           TEXT NOT NULL DEFAULT 'default',
                set_id              TEXT,
                name                TEXT NOT NULL,
                rule_type           TEXT NOT NULL,
                field               TEXT NOT NULL,
                action              TEXT NOT NULL,
                priority            INTEGER NOT NULL,
                threshold           REAL,
                threshold_operator  TEXT,
                range_min           REAL,
                range_max           REAL,
                value               TEXT,
                description         TEXT,
                domain              TEXT,
                version             INTEGER NOT NULL,
                enabled             INTEGER NOT NULL,
                created_at          TEXT NOT NULL,
                updated_at          TEXT NOT NULL,
                archived_at         TEXT NOT NULL,
                archived_by         TEXT,
                change_reason       TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS policy_decisions (
                decision_id     TEXT NOT NULL,
                tenant_id       TEXT NOT NULL DEFAULT 'default',
                action          TEXT NOT NULL,
                context         TEXT NOT NULL,
                decision        TEXT NOT NULL,
                reason          TEXT,
                confidence      REAL,
                matched_rules   TEXT,
                constraints     TEXT,
                timestamp       TEXT NOT NULL,
                PRIMARY KEY (decision_id, tenant_id)
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_policy_sets_tenant ON policy_sets(tenant_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_policy_rules_tenant ON policy_rules(tenant_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_policy_rules_tenant_set ON policy_rules(tenant_id, set_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_policy_rules_tenant_enabled ON policy_rules(tenant_id, enabled)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_policy_rules_priority ON policy_rules(priority DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_policy_rule_history_tenant ON policy_rule_history(tenant_id, rule_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_policy_decisions_tenant ON policy_decisions(tenant_id, timestamp)")

        self.db.commit()
        logger.info("Policy storage schema initialized")

    def _migrate_schema(self):
        """Add tenant_id column to pre-existing tables that were created without it."""
        migrations = [
            ("policy_sets",        "tenant_id TEXT NOT NULL DEFAULT 'default'"),
            ("policy_rules",       "tenant_id TEXT NOT NULL DEFAULT 'default'"),
            ("policy_rule_history","tenant_id TEXT NOT NULL DEFAULT 'default'"),
            ("policy_decisions",   "tenant_id TEXT NOT NULL DEFAULT 'default'"),
        ]
        cursor = self.db.cursor()
        for table, column_def in migrations:
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
                self.db.commit()
                logger.info("Migrated %s: added tenant_id", table)
            except Exception:
                # Column already exists — expected on all runs after the first
                self.db.rollback()

    # ── Policy Sets ───────────────────────────────────────────────────────────

    def create_policy_set(self, policy_set: PolicySet, tenant_id: str = _DEFAULT_TENANT) -> bool:
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                INSERT INTO policy_sets (
                    set_id, tenant_id, name, description, domain,
                    version, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                policy_set.set_id,
                tenant_id,
                policy_set.name,
                policy_set.description,
                policy_set.domain,
                policy_set.version,
                1 if policy_set.enabled else 0,
                policy_set.created_at.isoformat(),
                policy_set.updated_at.isoformat(),
            ))
            for rule in policy_set.rules:
                self._insert_rule(rule, policy_set.set_id, tenant_id)
            self.db.commit()
            logger.info("Created policy set '%s' for tenant '%s'", policy_set.name, tenant_id)
            return True
        except Exception as e:
            logger.error("Error creating policy set: %s", e)
            self.db.rollback()
            return False

    def get_policy_set(self, set_id: str, tenant_id: str = _DEFAULT_TENANT) -> Optional[PolicySet]:
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT set_id, name, description, domain, version,
                   enabled, created_at, updated_at
            FROM policy_sets
            WHERE set_id = ? AND tenant_id = ?
        """, (set_id, tenant_id))

        row = cursor.fetchone()
        if not row:
            return None

        policy_set = PolicySet(
            set_id=row[0],
            name=row[1],
            description=row[2],
            domain=row[3],
            version=row[4],
            enabled=bool(row[5]),
            created_at=datetime.fromisoformat(row[6]),
            updated_at=datetime.fromisoformat(row[7]),
        )
        policy_set.rules = self.get_rules_by_set(set_id, tenant_id)
        return policy_set

    def get_all_policy_sets(self, tenant_id: str = _DEFAULT_TENANT) -> List[PolicySet]:
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT set_id, name, description, domain, version,
                   enabled, created_at, updated_at
            FROM policy_sets
            WHERE tenant_id = ?
            ORDER BY name
        """, (tenant_id,))

        policy_sets = []
        for row in cursor.fetchall():
            policy_set = PolicySet(
                set_id=row[0],
                name=row[1],
                description=row[2],
                domain=row[3],
                version=row[4],
                enabled=bool(row[5]),
                created_at=datetime.fromisoformat(row[6]),
                updated_at=datetime.fromisoformat(row[7]),
            )
            policy_set.rules = self.get_rules_by_set(policy_set.set_id, tenant_id)
            policy_sets.append(policy_set)
        return policy_sets

    def update_policy_set(self, policy_set: PolicySet, tenant_id: str = _DEFAULT_TENANT) -> bool:
        try:
            cursor = self.db.cursor()
            policy_set.updated_at = datetime.now(UTC)
            policy_set.version += 1
            cursor.execute("""
                UPDATE policy_sets
                SET name = ?, description = ?, domain = ?,
                    version = ?, enabled = ?, updated_at = ?
                WHERE set_id = ? AND tenant_id = ?
            """, (
                policy_set.name,
                policy_set.description,
                policy_set.domain,
                policy_set.version,
                1 if policy_set.enabled else 0,
                policy_set.updated_at.isoformat(),
                policy_set.set_id,
                tenant_id,
            ))
            self.db.commit()
            logger.info("Updated policy set '%s' to version %s", policy_set.name, policy_set.version)
            return True
        except Exception as e:
            logger.error("Error updating policy set: %s", e)
            self.db.rollback()
            return False

    def delete_policy_set(self, set_id: str, tenant_id: str = _DEFAULT_TENANT) -> bool:
        try:
            cursor = self.db.cursor()
            cursor.execute(
                "DELETE FROM policy_sets WHERE set_id = ? AND tenant_id = ?",
                (set_id, tenant_id),
            )
            self.db.commit()
            logger.info("Deleted policy set '%s' for tenant '%s'", set_id, tenant_id)
            return True
        except Exception as e:
            logger.error("Error deleting policy set: %s", e)
            self.db.rollback()
            return False

    # ── Policy Rules ──────────────────────────────────────────────────────────

    def create_rule(self, rule: PolicyRule, set_id: Optional[str] = None, tenant_id: str = _DEFAULT_TENANT) -> bool:
        try:
            self._insert_rule(rule, set_id, tenant_id)
            self.db.commit()
            logger.info("Created policy rule '%s' for tenant '%s'", rule.name, tenant_id)
            return True
        except Exception as e:
            logger.error("Error creating policy rule: %s", e)
            self.db.rollback()
            return False

    def _insert_rule(self, rule: PolicyRule, set_id: Optional[str], tenant_id: str):
        cursor = self.db.cursor()
        value_str = None
        if rule.value is not None:
            value_str = json.dumps(rule.value) if isinstance(rule.value, (dict, list)) else str(rule.value)

        cursor.execute("""
            INSERT INTO policy_rules (
                rule_id, tenant_id, set_id, name, rule_type, field, action,
                priority, threshold, threshold_operator, range_min,
                range_max, value, description, domain, version,
                enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            rule.rule_id,
            tenant_id,
            set_id,
            rule.name,
            rule.rule_type.value,
            rule.field,
            rule.action.value,
            rule.priority,
            rule.threshold,
            rule.threshold_operator,
            rule.range_min,
            rule.range_max,
            value_str,
            rule.description,
            rule.domain,
            rule.version,
            1 if rule.enabled else 0,
            rule.created_at.isoformat(),
            rule.updated_at.isoformat(),
        ))

    def get_rule(self, rule_id: str, tenant_id: str = _DEFAULT_TENANT) -> Optional[PolicyRule]:
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT rule_id, name, rule_type, field, action, priority,
                   threshold, threshold_operator, range_min, range_max,
                   value, description, domain, version, enabled,
                   created_at, updated_at
            FROM policy_rules
            WHERE rule_id = ? AND tenant_id = ?
        """, (rule_id, tenant_id))

        row = cursor.fetchone()
        return self._rule_from_row(row) if row else None

    def get_rules_by_set(self, set_id: str, tenant_id: str = _DEFAULT_TENANT) -> List[PolicyRule]:
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT rule_id, name, rule_type, field, action, priority,
                   threshold, threshold_operator, range_min, range_max,
                   value, description, domain, version, enabled,
                   created_at, updated_at
            FROM policy_rules
            WHERE set_id = ? AND tenant_id = ?
            ORDER BY priority DESC
        """, (set_id, tenant_id))

        return [self._rule_from_row(row) for row in cursor.fetchall()]

    def get_all_rules(self, tenant_id: str = _DEFAULT_TENANT) -> List[PolicyRule]:
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT rule_id, name, rule_type, field, action, priority,
                   threshold, threshold_operator, range_min, range_max,
                   value, description, domain, version, enabled,
                   created_at, updated_at
            FROM policy_rules
            WHERE tenant_id = ?
            ORDER BY priority DESC
        """, (tenant_id,))

        return [self._rule_from_row(row) for row in cursor.fetchall()]

    def update_rule(self, rule: PolicyRule, tenant_id: str = _DEFAULT_TENANT, change_reason: Optional[str] = None) -> bool:
        try:
            old_rule = self.get_rule(rule.rule_id, tenant_id)
            if old_rule:
                self._archive_rule(old_rule, tenant_id, change_reason)

            cursor = self.db.cursor()
            rule.updated_at = datetime.now(UTC)
            rule.version += 1

            value_str = None
            if rule.value is not None:
                value_str = json.dumps(rule.value) if isinstance(rule.value, (dict, list)) else str(rule.value)

            cursor.execute("""
                UPDATE policy_rules
                SET name = ?, rule_type = ?, field = ?, action = ?,
                    priority = ?, threshold = ?, threshold_operator = ?,
                    range_min = ?, range_max = ?, value = ?,
                    description = ?, domain = ?, version = ?,
                    enabled = ?, updated_at = ?
                WHERE rule_id = ? AND tenant_id = ?
            """, (
                rule.name,
                rule.rule_type.value,
                rule.field,
                rule.action.value,
                rule.priority,
                rule.threshold,
                rule.threshold_operator,
                rule.range_min,
                rule.range_max,
                value_str,
                rule.description,
                rule.domain,
                rule.version,
                1 if rule.enabled else 0,
                rule.updated_at.isoformat(),
                rule.rule_id,
                tenant_id,
            ))
            self.db.commit()
            logger.info("Updated policy rule '%s' to version %s", rule.name, rule.version)
            return True
        except Exception as e:
            logger.error("Error updating policy rule: %s", e)
            self.db.rollback()
            return False

    def delete_rule(self, rule_id: str, tenant_id: str = _DEFAULT_TENANT, change_reason: Optional[str] = None) -> bool:
        try:
            rule = self.get_rule(rule_id, tenant_id)
            if rule:
                self._archive_rule(rule, tenant_id, change_reason or "Deleted")

            cursor = self.db.cursor()
            cursor.execute(
                "DELETE FROM policy_rules WHERE rule_id = ? AND tenant_id = ?",
                (rule_id, tenant_id),
            )
            self.db.commit()
            logger.info("Deleted policy rule '%s' for tenant '%s'", rule_id, tenant_id)
            return True
        except Exception as e:
            logger.error("Error deleting policy rule: %s", e)
            self.db.rollback()
            return False

    def _archive_rule(self, rule: PolicyRule, tenant_id: str, change_reason: Optional[str] = None):
        cursor = self.db.cursor()
        cursor.execute("""
            INSERT INTO policy_rule_history (
                rule_id, tenant_id, set_id, name, rule_type, field, action,
                priority, threshold, threshold_operator, range_min,
                range_max, value, description, domain, version,
                enabled, created_at, updated_at, archived_at, change_reason
            ) SELECT rule_id, tenant_id, set_id, name, rule_type, field, action,
                     priority, threshold, threshold_operator, range_min,
                     range_max, value, description, domain, version,
                     enabled, created_at, updated_at, ?, ?
              FROM policy_rules WHERE rule_id = ? AND tenant_id = ?
        """, (datetime.now(UTC).isoformat(), change_reason, rule.rule_id, tenant_id))

    def _rule_from_row(self, row) -> PolicyRule:
        from .schemas import RuleType, PolicyAction

        value = row[10]
        if value is not None:
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass

        return PolicyRule(
            rule_id=row[0],
            name=row[1],
            rule_type=RuleType(row[2]),
            field=row[3],
            action=PolicyAction(row[4]),
            priority=row[5],
            threshold=row[6],
            threshold_operator=row[7],
            range_min=row[8],
            range_max=row[9],
            value=value,
            description=row[11],
            domain=row[12],
            version=row[13],
            enabled=bool(row[14]),
            created_at=datetime.fromisoformat(row[15]),
            updated_at=datetime.fromisoformat(row[16]),
        )

    # ── Decision audit ────────────────────────────────────────────────────────

    def log_decision(
        self,
        decision_id: str,
        action: str,
        context: Dict[str, Any],
        decision: str,
        reason: str,
        confidence: float,
        matched_rules: List[str],
        constraints: List[Dict[str, Any]],
        timestamp: datetime,
        tenant_id: str = _DEFAULT_TENANT,
    ) -> bool:
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                INSERT INTO policy_decisions (
                    decision_id, tenant_id, action, context, decision, reason,
                    confidence, matched_rules, constraints, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                decision_id,
                tenant_id,
                action,
                json.dumps(context),
                decision,
                reason,
                confidence,
                json.dumps(matched_rules),
                json.dumps(constraints),
                timestamp.isoformat(),
            ))
            self.db.commit()
            return True
        except Exception as e:
            logger.error("Error logging decision: %s", e)
            self.db.rollback()
            return False
