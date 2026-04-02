"""Policy schema definitions for EDON Gateway.

This module defines the core data structures for policy rules and decisions.
Inspired by the MAG authority engine but adapted for the Python gateway.
"""

from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from typing import Dict, List, Optional, Any
import uuid


class Decision(str, Enum):
    """Policy decision outcomes.

    These align with the MAG authority engine decisions:
    - ALLOW: Action is approved without restrictions
    - BLOCK: Action is denied (equivalent to MAG's "deny")
    - DEGRADE: Action is allowed with constraints/modifications
    - HUMAN_REQUIRED: Action requires human approval (equivalent to MAG's "require_approval")
    """
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    DEGRADE = "DEGRADE"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"


class RuleType(str, Enum):
    """Types of policy rules."""
    THRESHOLD = "threshold"  # If value > X then action
    RANGE = "range"  # If value outside [X, Y] then action
    EQUALS = "equals"  # If value == X then action
    CONTAINS = "contains"  # If value contains X then action
    GEOFENCE = "geofence"  # If coordinates within zone then action
    TIME_WINDOW = "time_window"  # If time within window then action


class PolicyAction(str, Enum):
    """Actions that can be taken when a rule matches."""
    ALLOW = "allow"
    BLOCK = "block"
    DEGRADE = "degrade"
    REQUIRE_APPROVAL = "require_approval"


@dataclass
class PolicyRule:
    """A single policy rule for evaluation.

    Examples:
        # Threshold rule: Block if estimated cost > $100
        PolicyRule(
            rule_id="cost_threshold",
            name="Cost threshold exceeded",
            rule_type=RuleType.THRESHOLD,
            field="estimated_cost",
            threshold=100,
            action=PolicyAction.BLOCK,
            priority=90
        )

        # Range rule: Degrade if velocity outside [0, 50] m/s
        PolicyRule(
            rule_id="velocity_range",
            name="Velocity out of safe range",
            rule_type=RuleType.RANGE,
            field="velocity_ms",
            range_min=0,
            range_max=50,
            action=PolicyAction.DEGRADE,
            priority=80
        )

        # Equals rule: Block if action is "delete_all"
        PolicyRule(
            rule_id="dangerous_action",
            name="Dangerous action detected",
            rule_type=RuleType.EQUALS,
            field="action",
            value="delete_all",
            action=PolicyAction.BLOCK,
            priority=100
        )
    """
    rule_id: str
    name: str
    rule_type: RuleType
    field: str  # Dot-notation path to field in context (e.g., "intent.action", "context.risk_score")
    action: PolicyAction
    priority: int = 50  # Higher priority rules are evaluated first

    # Threshold rule parameters
    threshold: Optional[float] = None
    threshold_operator: str = "greater_than"  # "greater_than", "less_than", "greater_equal", "less_equal"

    # Range rule parameters
    range_min: Optional[float] = None
    range_max: Optional[float] = None

    # Equals/Contains rule parameters
    value: Optional[Any] = None

    # Metadata
    description: Optional[str] = None
    domain: Optional[str] = None  # Domain pack identifier (e.g., "dod", "healthcare")
    version: int = 1
    enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "rule_type": self.rule_type.value,
            "field": self.field,
            "action": self.action.value,
            "priority": self.priority,
            "threshold": self.threshold,
            "threshold_operator": self.threshold_operator,
            "range_min": self.range_min,
            "range_max": self.range_max,
            "value": self.value,
            "description": self.description,
            "domain": self.domain,
            "version": self.version,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PolicyRule":
        """Create PolicyRule from dictionary."""
        # Convert string enums back to enum types
        if isinstance(data.get("rule_type"), str):
            data["rule_type"] = RuleType(data["rule_type"])
        if isinstance(data.get("action"), str):
            data["action"] = PolicyAction(data["action"])

        # Convert ISO datetime strings back to datetime objects
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if isinstance(data.get("updated_at"), str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])

        return cls(**data)


@dataclass
class PolicySet:
    """A collection of policy rules for a specific domain or context.

    Policy sets allow grouping related rules together and managing them
    as a unit. This is useful for domain-specific policies (e.g., DoD, healthcare)
    or environment-specific policies (e.g., production, staging).
    """
    set_id: str
    name: str
    description: str
    rules: List[PolicyRule] = field(default_factory=list)
    domain: Optional[str] = None
    version: int = 1
    enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def add_rule(self, rule: PolicyRule):
        """Add a rule to the policy set."""
        self.rules.append(rule)
        self.rules.sort(key=lambda r: r.priority, reverse=True)
        self.updated_at = datetime.now(UTC)

    def remove_rule(self, rule_id: str):
        """Remove a rule from the policy set."""
        self.rules = [r for r in self.rules if r.rule_id != rule_id]
        self.updated_at = datetime.now(UTC)

    def get_rule(self, rule_id: str) -> Optional[PolicyRule]:
        """Get a rule by ID."""
        for rule in self.rules:
            if rule.rule_id == rule_id:
                return rule
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "set_id": self.set_id,
            "name": self.name,
            "description": self.description,
            "rules": [r.to_dict() for r in self.rules],
            "domain": self.domain,
            "version": self.version,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PolicySet":
        """Create PolicySet from dictionary."""
        # Convert rules dicts back to PolicyRule objects
        if "rules" in data:
            data["rules"] = [PolicyRule.from_dict(r) for r in data["rules"]]

        # Convert ISO datetime strings back to datetime objects
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if isinstance(data.get("updated_at"), str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])

        return cls(**data)


@dataclass
class PolicyDecision:
    """The result of policy evaluation.

    This is returned by the PolicyEngine after evaluating an action against
    all applicable policy rules.
    """
    decision: Decision
    reason: str
    confidence: float = 1.0
    matched_rules: List[str] = field(default_factory=list)  # IDs of rules that matched
    constraints: List[Dict[str, Any]] = field(default_factory=list)  # Applied constraints
    safe_alternative: Optional[Dict[str, Any]] = None  # Suggested alternative if degraded
    required_approvals: List[str] = field(default_factory=list)  # Required approvers
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "decision_id": self.decision_id,
            "decision": self.decision.value,
            "reason": self.reason,
            "confidence": self.confidence,
            "matched_rules": self.matched_rules,
            "constraints": self.constraints,
            "safe_alternative": self.safe_alternative,
            "required_approvals": self.required_approvals,
            "timestamp": self.timestamp.isoformat(),
        }
