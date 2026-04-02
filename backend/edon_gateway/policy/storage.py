"""Policy Storage - Database persistence for policy rules.

This module provides database storage for policy rules with versioning support.
It integrates with the existing EDON Gateway database infrastructure.
"""

import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, UTC
from pathlib import Path

from .schemas import PolicyRule, PolicySet

logger = logging.getLogger(__name__)


class PolicyStorage:
    """Database storage for policy rules.

    This class provides CRUD operations for policy rules and policy sets,
    with support for versioning and audit trails.
    """

    def __init__(self, db_connection):
        """Initialize policy storage.

        Args:
            db_connection: Database connection from persistence layer
        """
        self.db = db_connection
        self._init_schema()

    def _init_schema(self):
        """Initialize database schema for policy storage."""
        cursor = self.db.cursor()

        # Policy sets table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS policy_sets (
                set_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                domain TEXT,
                version INTEGER NOT NULL DEFAULT 1,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # Policy rules table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS policy_rules (
                rule_id TEXT PRIMARY KEY,
                set_id TEXT,
                name TEXT NOT NULL,
                rule_type TEXT NOT NULL,
                field TEXT NOT NULL,
                action TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 50,
                threshold REAL,
                threshold_operator TEXT,
                range_min REAL,
                range_max REAL,
                value TEXT,
                description TEXT,
                domain TEXT,
                version INTEGER NOT NULL DEFAULT 1,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (set_id) REFERENCES policy_sets (set_id) ON DELETE CASCADE
            )
        """)

        # Policy rule history (for versioning and audit)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS policy_rule_history (
                history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id TEXT NOT NULL,
                set_id TEXT,
                name TEXT NOT NULL,
                rule_type TEXT NOT NULL,
                field TEXT NOT NULL,
                action TEXT NOT NULL,
                priority INTEGER NOT NULL,
                threshold REAL,
                threshold_operator TEXT,
                range_min REAL,
                range_max REAL,
                value TEXT,
                description TEXT,
                domain TEXT,
                version INTEGER NOT NULL,
                enabled INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                archived_at TEXT NOT NULL,
                archived_by TEXT,
                change_reason TEXT
            )
        """)

        # Policy decisions audit log
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS policy_decisions (
                decision_id TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                context TEXT NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT,
                confidence REAL,
                matched_rules TEXT,
                constraints TEXT,
                timestamp TEXT NOT NULL
            )
        """)

        # Create indices for performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_policy_rules_set_id ON policy_rules(set_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_policy_rules_enabled ON policy_rules(enabled)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_policy_rules_priority ON policy_rules(priority DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_policy_rule_history_rule_id ON policy_rule_history(rule_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_policy_decisions_timestamp ON policy_decisions(timestamp)")

        self.db.commit()
        logger.info("Policy storage schema initialized")

    # Policy Set operations

    def create_policy_set(self, policy_set: PolicySet) -> bool:
        """Create a new policy set.

        Args:
            policy_set: PolicySet to create

        Returns:
            True if successful, False otherwise
        """
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                INSERT INTO policy_sets (
                    set_id, name, description, domain, version,
                    enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                policy_set.set_id,
                policy_set.name,
                policy_set.description,
                policy_set.domain,
                policy_set.version,
                1 if policy_set.enabled else 0,
                policy_set.created_at.isoformat(),
                policy_set.updated_at.isoformat(),
            ))

            # Insert all rules
            for rule in policy_set.rules:
                self._insert_rule(rule, policy_set.set_id)

            self.db.commit()
            logger.info(f"Created policy set '{policy_set.name}' with {len(policy_set.rules)} rules")
            return True
        except Exception as e:
            logger.error(f"Error creating policy set: {e}")
            self.db.rollback()
            return False

    def get_policy_set(self, set_id: str) -> Optional[PolicySet]:
        """Get a policy set by ID.

        Args:
            set_id: Policy set ID

        Returns:
            PolicySet if found, None otherwise
        """
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT set_id, name, description, domain, version,
                   enabled, created_at, updated_at
            FROM policy_sets
            WHERE set_id = ?
        """, (set_id,))

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

        # Load rules
        policy_set.rules = self.get_rules_by_set(set_id)

        return policy_set

    def get_all_policy_sets(self) -> List[PolicySet]:
        """Get all policy sets.

        Returns:
            List of PolicySet objects
        """
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT set_id, name, description, domain, version,
                   enabled, created_at, updated_at
            FROM policy_sets
            ORDER BY name
        """)

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
            policy_set.rules = self.get_rules_by_set(policy_set.set_id)
            policy_sets.append(policy_set)

        return policy_sets

    def update_policy_set(self, policy_set: PolicySet) -> bool:
        """Update an existing policy set.

        Args:
            policy_set: PolicySet to update

        Returns:
            True if successful, False otherwise
        """
        try:
            cursor = self.db.cursor()
            policy_set.updated_at = datetime.now(UTC)
            policy_set.version += 1

            cursor.execute("""
                UPDATE policy_sets
                SET name = ?, description = ?, domain = ?,
                    version = ?, enabled = ?, updated_at = ?
                WHERE set_id = ?
            """, (
                policy_set.name,
                policy_set.description,
                policy_set.domain,
                policy_set.version,
                1 if policy_set.enabled else 0,
                policy_set.updated_at.isoformat(),
                policy_set.set_id,
            ))

            self.db.commit()
            logger.info(f"Updated policy set '{policy_set.name}' to version {policy_set.version}")
            return True
        except Exception as e:
            logger.error(f"Error updating policy set: {e}")
            self.db.rollback()
            return False

    def delete_policy_set(self, set_id: str) -> bool:
        """Delete a policy set and all its rules.

        Args:
            set_id: Policy set ID

        Returns:
            True if successful, False otherwise
        """
        try:
            cursor = self.db.cursor()
            cursor.execute("DELETE FROM policy_sets WHERE set_id = ?", (set_id,))
            self.db.commit()
            logger.info(f"Deleted policy set '{set_id}'")
            return True
        except Exception as e:
            logger.error(f"Error deleting policy set: {e}")
            self.db.rollback()
            return False

    # Policy Rule operations

    def create_rule(self, rule: PolicyRule, set_id: Optional[str] = None) -> bool:
        """Create a new policy rule.

        Args:
            rule: PolicyRule to create
            set_id: Optional policy set ID to associate with

        Returns:
            True if successful, False otherwise
        """
        try:
            self._insert_rule(rule, set_id)
            self.db.commit()
            logger.info(f"Created policy rule '{rule.name}'")
            return True
        except Exception as e:
            logger.error(f"Error creating policy rule: {e}")
            self.db.rollback()
            return False

    def _insert_rule(self, rule: PolicyRule, set_id: Optional[str] = None):
        """Internal method to insert a rule."""
        cursor = self.db.cursor()

        # Serialize complex value field as JSON if needed
        value_str = None
        if rule.value is not None:
            if isinstance(rule.value, (dict, list)):
                value_str = json.dumps(rule.value)
            else:
                value_str = str(rule.value)

        cursor.execute("""
            INSERT INTO policy_rules (
                rule_id, set_id, name, rule_type, field, action,
                priority, threshold, threshold_operator, range_min,
                range_max, value, description, domain, version,
                enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            rule.rule_id,
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

    def get_rule(self, rule_id: str) -> Optional[PolicyRule]:
        """Get a policy rule by ID.

        Args:
            rule_id: Policy rule ID

        Returns:
            PolicyRule if found, None otherwise
        """
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT rule_id, name, rule_type, field, action, priority,
                   threshold, threshold_operator, range_min, range_max,
                   value, description, domain, version, enabled,
                   created_at, updated_at
            FROM policy_rules
            WHERE rule_id = ?
        """, (rule_id,))

        row = cursor.fetchone()
        if not row:
            return None

        return self._rule_from_row(row)

    def get_rules_by_set(self, set_id: str) -> List[PolicyRule]:
        """Get all rules for a policy set.

        Args:
            set_id: Policy set ID

        Returns:
            List of PolicyRule objects
        """
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT rule_id, name, rule_type, field, action, priority,
                   threshold, threshold_operator, range_min, range_max,
                   value, description, domain, version, enabled,
                   created_at, updated_at
            FROM policy_rules
            WHERE set_id = ?
            ORDER BY priority DESC
        """, (set_id,))

        return [self._rule_from_row(row) for row in cursor.fetchall()]

    def get_all_rules(self) -> List[PolicyRule]:
        """Get all policy rules.

        Returns:
            List of PolicyRule objects
        """
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT rule_id, name, rule_type, field, action, priority,
                   threshold, threshold_operator, range_min, range_max,
                   value, description, domain, version, enabled,
                   created_at, updated_at
            FROM policy_rules
            ORDER BY priority DESC
        """)

        return [self._rule_from_row(row) for row in cursor.fetchall()]

    def update_rule(self, rule: PolicyRule, change_reason: Optional[str] = None) -> bool:
        """Update an existing policy rule.

        This archives the old version in the history table for audit purposes.

        Args:
            rule: PolicyRule to update
            change_reason: Optional reason for the change

        Returns:
            True if successful, False otherwise
        """
        try:
            # Archive old version
            old_rule = self.get_rule(rule.rule_id)
            if old_rule:
                self._archive_rule(old_rule, change_reason)

            # Update rule
            cursor = self.db.cursor()
            rule.updated_at = datetime.now(UTC)
            rule.version += 1

            value_str = None
            if rule.value is not None:
                if isinstance(rule.value, (dict, list)):
                    value_str = json.dumps(rule.value)
                else:
                    value_str = str(rule.value)

            cursor.execute("""
                UPDATE policy_rules
                SET name = ?, rule_type = ?, field = ?, action = ?,
                    priority = ?, threshold = ?, threshold_operator = ?,
                    range_min = ?, range_max = ?, value = ?,
                    description = ?, domain = ?, version = ?,
                    enabled = ?, updated_at = ?
                WHERE rule_id = ?
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
            ))

            self.db.commit()
            logger.info(f"Updated policy rule '{rule.name}' to version {rule.version}")
            return True
        except Exception as e:
            logger.error(f"Error updating policy rule: {e}")
            self.db.rollback()
            return False

    def delete_rule(self, rule_id: str, change_reason: Optional[str] = None) -> bool:
        """Delete a policy rule.

        This archives the rule in the history table for audit purposes.

        Args:
            rule_id: Policy rule ID
            change_reason: Optional reason for deletion

        Returns:
            True if successful, False otherwise
        """
        try:
            # Archive before deletion
            rule = self.get_rule(rule_id)
            if rule:
                self._archive_rule(rule, change_reason or "Deleted")

            cursor = self.db.cursor()
            cursor.execute("DELETE FROM policy_rules WHERE rule_id = ?", (rule_id,))
            self.db.commit()
            logger.info(f"Deleted policy rule '{rule_id}'")
            return True
        except Exception as e:
            logger.error(f"Error deleting policy rule: {e}")
            self.db.rollback()
            return False

    def _archive_rule(self, rule: PolicyRule, change_reason: Optional[str] = None):
        """Archive a rule to history table."""
        cursor = self.db.cursor()

        value_str = None
        if rule.value is not None:
            if isinstance(rule.value, (dict, list)):
                value_str = json.dumps(rule.value)
            else:
                value_str = str(rule.value)

        cursor.execute("""
            INSERT INTO policy_rule_history (
                rule_id, set_id, name, rule_type, field, action,
                priority, threshold, threshold_operator, range_min,
                range_max, value, description, domain, version,
                enabled, created_at, updated_at, archived_at, change_reason
            ) SELECT rule_id, set_id, name, rule_type, field, action,
                     priority, threshold, threshold_operator, range_min,
                     range_max, value, description, domain, version,
                     enabled, created_at, updated_at, ?, ?
              FROM policy_rules WHERE rule_id = ?
        """, (
            datetime.now(UTC).isoformat(),
            change_reason,
            rule.rule_id,
        ))

    def _rule_from_row(self, row) -> PolicyRule:
        """Convert database row to PolicyRule."""
        from .schemas import RuleType, PolicyAction

        # Parse value field
        value = row[10]
        if value is not None:
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass  # Keep as string

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

    # Decision audit operations

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
        timestamp: datetime
    ) -> bool:
        """Log a policy decision to the audit log.

        Args:
            decision_id: Decision ID
            action: Action that was evaluated
            context: Context data
            decision: Decision outcome
            reason: Reason for decision
            confidence: Confidence score
            matched_rules: List of matched rule IDs
            constraints: Applied constraints
            timestamp: Decision timestamp

        Returns:
            True if successful, False otherwise
        """
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                INSERT INTO policy_decisions (
                    decision_id, action, context, decision, reason,
                    confidence, matched_rules, constraints, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                decision_id,
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
            logger.error(f"Error logging decision: {e}")
            self.db.rollback()
            return False
