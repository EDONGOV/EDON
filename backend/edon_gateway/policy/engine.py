"""Policy Engine - Core governance evaluation engine.

This module implements the PolicyEngine class, which evaluates actions against
policy rules and returns decisions. It's inspired by the MAG authority engine
but adapted for the Python gateway context.
"""

import os
import logging
import concurrent.futures
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, UTC
from collections import OrderedDict

# Policy evaluation timeout (default 10000ms, configurable via EDON_POLICY_TIMEOUT_MS)
_POLICY_TIMEOUT_SEC: float = float(os.getenv("EDON_POLICY_TIMEOUT_MS", "10000")) / 1000.0

# Fail-safe mode: "block" (safe default) or "allow"/"allow_with_log"
_POLICY_FAIL_SAFE: str = os.getenv("EDON_POLICY_FAIL_SAFE", "block").strip().lower()

from .schemas import (
    PolicyRule,
    PolicySet,
    PolicyDecision as _SchemaPolicyDecision,
    Decision,
    RuleType,
    PolicyAction,
)

logger = logging.getLogger(__name__)

# Fail-safe configuration (legacy alias kept for backward compat)
# When policy engine encounters an error, it can either:
# - "block": Block the action (safe default)
# - "allow_with_log": Allow the action but log the error
FAIL_SAFE_MODE = _POLICY_FAIL_SAFE


@dataclass
class PolicyDecision:
    """Lightweight policy decision for simple rule-based evaluation.

    This dataclass provides a dict-compatible interface so callers can use
    either attribute access (decision.verdict) or dict-style access
    (decision["verdict"] or decision.get("verdict", default)).

    Fields:
        verdict:  "ALLOW", "BLOCK", "ALLOW_WITH_LOG", etc.
        reason:   Human-readable explanation.
        rule_id:  ID of the rule that triggered this decision (if any).
        metadata: Additional key/value data.
    """
    verdict: str = "ALLOW"
    reason: str = ""
    rule_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-style .get() for backward compatibility."""
        return getattr(self, key, self.metadata.get(key, default))

    def __getitem__(self, key: str) -> Any:
        """Dict-style [] access for backward compatibility."""
        try:
            return getattr(self, key)
        except AttributeError:
            return self.metadata[key]


class PolicyEngine:
    """Policy evaluation engine.

    The PolicyEngine evaluates actions against a set of policy rules and
    returns decisions (ALLOW, BLOCK, DEGRADE, HUMAN_REQUIRED).

    Key features:
    - Rule-based evaluation with priority ordering
    - In-memory caching for performance
    - Fail-safe behavior (configurable)
    - Support for multiple rule types (threshold, range, equals, contains)

    Example:
        engine = PolicyEngine()

        # Add a rule
        rule = PolicyRule(
            rule_id="cost_limit",
            name="Block high-cost actions",
            rule_type=RuleType.THRESHOLD,
            field="estimated_cost",
            threshold=100,
            action=PolicyAction.BLOCK,
            priority=90
        )
        engine.add_rule(rule)

        # Evaluate an action
        context = {"estimated_cost": 150}
        decision = engine.evaluate("purchase", context)
        # decision.decision == Decision.BLOCK
    """

    def __init__(self, policy_sets: Optional[List[PolicySet]] = None, rules: Optional[List[Dict[str, Any]]] = None):
        """Initialize policy engine.

        Args:
            policy_sets: Optional list of PolicySet objects to load.
            rules: Optional list of plain-dict rules for simple evaluation
                   (used by lightweight callers that don't need full PolicySet).
        """
        self.policy_sets: Dict[str, PolicySet] = {}
        self.rules_cache: OrderedDict[str, PolicyRule] = OrderedDict()
        self._cache_size = 1000  # Max cached rules
        # Simple dict-based rules list (for lightweight evaluate/evaluate_impl path)
        self.rules: List[Dict[str, Any]] = list(rules) if rules else []

        if policy_sets:
            for policy_set in policy_sets:
                self.add_policy_set(policy_set)

        logger.info(f"PolicyEngine initialized with {len(self.rules_cache)} rules")

    def add_policy_set(self, policy_set: PolicySet):
        """Add a policy set to the engine.

        Args:
            policy_set: PolicySet to add
        """
        self.policy_sets[policy_set.set_id] = policy_set
        # Add all rules to cache
        for rule in policy_set.rules:
            if rule.enabled:
                self._add_to_cache(rule)
        logger.info(f"Added policy set '{policy_set.name}' with {len(policy_set.rules)} rules")

    def add_rule(self, rule: PolicyRule):
        """Add a single rule to the engine.

        Args:
            rule: PolicyRule to add
        """
        if rule.enabled:
            self._add_to_cache(rule)
            logger.debug(f"Added rule '{rule.name}' (priority={rule.priority})")

    def remove_rule(self, rule_id: str):
        """Remove a rule from the engine.

        Args:
            rule_id: ID of rule to remove
        """
        if rule_id in self.rules_cache:
            del self.rules_cache[rule_id]
            logger.debug(f"Removed rule '{rule_id}'")

    def _add_to_cache(self, rule: PolicyRule):
        """Add a rule to the cache with LRU eviction."""
        # Remove if already exists to reinsert with updated priority
        if rule.rule_id in self.rules_cache:
            del self.rules_cache[rule.rule_id]

        # Add rule
        self.rules_cache[rule.rule_id] = rule

        # Evict oldest if cache is full
        if len(self.rules_cache) > self._cache_size:
            self.rules_cache.popitem(last=False)

        # Sort cache by priority (higher priority first)
        self.rules_cache = OrderedDict(
            sorted(self.rules_cache.items(), key=lambda x: x[1].priority, reverse=True)
        )

    def evaluate(
        self,
        action: str,
        context: Dict[str, Any],
        intent: Optional[Dict[str, Any]] = None
    ) -> "PolicyDecision":
        """Evaluate an action against all policy rules.

        This is the main entry point for policy evaluation. It evaluates the
        action against all rules in priority order and returns the first
        matching decision.

        Runs ``_evaluate_impl`` in a thread with ``_POLICY_TIMEOUT_SEC`` timeout.
        On timeout or exception, applies ``_POLICY_FAIL_SAFE``:
          - "allow" / "allow_with_log" -> PolicyDecision(verdict="ALLOW_WITH_LOG")
          - anything else              -> PolicyDecision(verdict="BLOCK")

        Args:
            action: The action being evaluated (e.g., "purchase", "delete", "send_email")
            context: Context data containing fields referenced by rules
            intent: Optional intent data for more sophisticated evaluation

        Returns:
            PolicyDecision with the evaluation result

        Example:
            context = {
                "estimated_cost": 150,
                "risk_score": 0.8,
                "user_id": "user_123"
            }
            decision = engine.evaluate("purchase", context)
        """
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self._evaluate_impl, action, context, intent)
                try:
                    return future.result(timeout=_POLICY_TIMEOUT_SEC)
                except concurrent.futures.TimeoutError:
                    logger.error(
                        "Policy engine timeout (%.0fms) evaluating action='%s'; applying fail-safe.",
                        _POLICY_TIMEOUT_SEC * 1000,
                        action,
                    )
                    return self._apply_fail_safe(
                        reason=f"Policy evaluation timed out after {_POLICY_TIMEOUT_SEC * 1000:.0f}ms"
                    )
        except Exception as e:
            logger.exception(f"Policy engine error during evaluate: {e}")
            return self._apply_fail_safe(reason=str(e))

    def _apply_fail_safe(self, reason: str = "") -> "PolicyDecision":
        """Return a fail-safe PolicyDecision based on _POLICY_FAIL_SAFE setting."""
        if _POLICY_FAIL_SAFE in ("allow", "allow_with_log"):
            return PolicyDecision(verdict="ALLOW_WITH_LOG", reason=reason)
        return PolicyDecision(verdict="BLOCK", reason=reason)

    def _evaluate_impl(
        self,
        action: str,
        context: Dict[str, Any],
        intent: Optional[Dict[str, Any]] = None,
    ) -> "PolicyDecision":
        """Internal evaluation implementation.

        Supports two evaluation paths:
        1. Simple dict-based rules (self.rules list) — lightweight path.
        2. Full PolicyRule/PolicySet cache (self.rules_cache) — full path.
        """
        # ── Simple dict-based rules path ─────────────────────────────────
        if self.rules is not None and len(self.rules) == 0 and not self.rules_cache:
            return PolicyDecision(verdict="ALLOW", reason="No policy rules configured")

        if self.rules:
            return self._evaluate_simple_rules(action, context, intent)

        # ── Full PolicyRule/PolicySet cache path ──────────────────────────
        # Merge context and intent for field lookup
        eval_context = {
            "action": action,
            "context": context,
            "intent": intent or {},
        }

        matched_rules: List[str] = []
        constraints: List[Dict[str, Any]] = []

        # Evaluate rules in priority order (highest first)
        for rule_id, rule in self.rules_cache.items():
            if not rule.enabled:
                continue

            # Evaluate rule
            matches, reason = self._evaluate_rule(rule, eval_context)

            if matches:
                matched_rules.append(rule_id)
                logger.debug(f"Rule '{rule.name}' matched: {reason}")

                # Map PolicyAction to Decision / PolicyDecision verdict
                if rule.action == PolicyAction.BLOCK:
                    return PolicyDecision(
                        verdict="BLOCK",
                        reason=f"{rule.name}: {reason}",
                        rule_id=rule_id,
                    )
                elif rule.action == PolicyAction.REQUIRE_APPROVAL:
                    return PolicyDecision(
                        verdict="HUMAN_REQUIRED",
                        reason=f"{rule.name}: {reason}",
                        rule_id=rule_id,
                    )
                elif rule.action == PolicyAction.DEGRADE:
                    return PolicyDecision(
                        verdict="DEGRADE",
                        reason=f"{rule.name}: {reason}",
                        rule_id=rule_id,
                    )
                elif rule.action == PolicyAction.ALLOW:
                    return PolicyDecision(
                        verdict="ALLOW",
                        reason=f"{rule.name}: {reason}",
                        rule_id=rule_id,
                    )

        # No rules matched — default allow
        return PolicyDecision(verdict="ALLOW", reason="No matching policy rules - default allow")

    def _evaluate_simple_rules(
        self,
        action: str,
        context: Dict[str, Any],
        intent: Optional[Dict[str, Any]] = None,
    ) -> "PolicyDecision":
        """Evaluate action against simple dict-based rules (self.rules list).

        Supported rule types: threshold, range, action_type, always.
        """
        for rule in self.rules:
            rule_type = rule.get("type", "")
            rule_id = rule.get("rule_id") or rule.get("id")

            # always rules
            if rule_type == "always":
                verdict = rule.get("verdict", "ALLOW").upper()
                return PolicyDecision(
                    verdict=verdict,
                    reason=rule.get("reason", f"Always rule: {verdict}"),
                    rule_id=rule_id,
                )

            # action_type rules
            if rule_type == "action_type":
                allowed = rule.get("allowed_actions", [])
                if action not in allowed:
                    verdict = rule.get("verdict", "BLOCK").upper()
                    return PolicyDecision(
                        verdict=verdict,
                        reason=rule.get("reason", f"Action '{action}' not in allowed list"),
                        rule_id=rule_id,
                    )

            # threshold rules
            if rule_type == "threshold":
                field_path = rule.get("field", "")
                threshold = rule.get("threshold")
                operator = rule.get("operator", "greater_than")
                value = self._get_field_value(field_path, {"action": action, "context": context, "intent": intent or {}})
                if value is not None and threshold is not None:
                    try:
                        numeric_value = float(value)
                        numeric_threshold = float(threshold)
                        triggered = False
                        if operator == "greater_than" and numeric_value > numeric_threshold:
                            triggered = True
                        elif operator == "less_than" and numeric_value < numeric_threshold:
                            triggered = True
                        elif operator == "greater_equal" and numeric_value >= numeric_threshold:
                            triggered = True
                        elif operator == "less_equal" and numeric_value <= numeric_threshold:
                            triggered = True
                        if triggered:
                            verdict = rule.get("verdict", "BLOCK").upper()
                            return PolicyDecision(
                                verdict=verdict,
                                reason=rule.get("reason", f"Threshold exceeded: {field_path}={value}"),
                                rule_id=rule_id,
                            )
                    except (ValueError, TypeError):
                        pass

            # range rules
            if rule_type == "range":
                field_path = rule.get("field", "")
                range_min = rule.get("range_min")
                range_max = rule.get("range_max")
                value = self._get_field_value(field_path, {"action": action, "context": context, "intent": intent or {}})
                if value is not None:
                    try:
                        numeric_value = float(value)
                        outside = False
                        if range_min is not None and numeric_value < float(range_min):
                            outside = True
                        if range_max is not None and numeric_value > float(range_max):
                            outside = True
                        if outside:
                            verdict = rule.get("verdict", "BLOCK").upper()
                            return PolicyDecision(
                                verdict=verdict,
                                reason=rule.get("reason", f"Value out of range: {field_path}={value}"),
                                rule_id=rule_id,
                            )
                    except (ValueError, TypeError):
                        pass

        return PolicyDecision(verdict="ALLOW", reason="No policy rules matched")

    def _evaluate_rule(
        self,
        rule: PolicyRule,
        context: Dict[str, Any]
    ) -> tuple[bool, str]:
        """Evaluate a single rule against context.

        Args:
            rule: PolicyRule to evaluate
            context: Evaluation context

        Returns:
            Tuple of (matches: bool, reason: str)
        """
        # Get field value using dot notation
        field_value = self._get_field_value(rule.field, context)

        if field_value is None:
            return False, f"Field '{rule.field}' not found"

        # Evaluate based on rule type
        if rule.rule_type == RuleType.THRESHOLD:
            return self._evaluate_threshold(rule, field_value)
        elif rule.rule_type == RuleType.RANGE:
            return self._evaluate_range(rule, field_value)
        elif rule.rule_type == RuleType.EQUALS:
            return self._evaluate_equals(rule, field_value)
        elif rule.rule_type == RuleType.CONTAINS:
            return self._evaluate_contains(rule, field_value)
        else:
            logger.warning(f"Unknown rule type: {rule.rule_type}")
            return False, f"Unknown rule type: {rule.rule_type}"

    def _evaluate_threshold(self, rule: PolicyRule, value: Any) -> tuple[bool, str]:
        """Evaluate a threshold rule."""
        try:
            numeric_value = float(value)
            threshold = float(rule.threshold)

            if rule.threshold_operator == "greater_than":
                matches = numeric_value > threshold
                reason = f"{rule.field} ({numeric_value}) > {threshold}"
            elif rule.threshold_operator == "less_than":
                matches = numeric_value < threshold
                reason = f"{rule.field} ({numeric_value}) < {threshold}"
            elif rule.threshold_operator == "greater_equal":
                matches = numeric_value >= threshold
                reason = f"{rule.field} ({numeric_value}) >= {threshold}"
            elif rule.threshold_operator == "less_equal":
                matches = numeric_value <= threshold
                reason = f"{rule.field} ({numeric_value}) <= {threshold}"
            else:
                return False, f"Unknown threshold operator: {rule.threshold_operator}"

            return matches, reason
        except (ValueError, TypeError) as e:
            return False, f"Invalid numeric value for threshold: {e}"

    def _evaluate_range(self, rule: PolicyRule, value: Any) -> tuple[bool, str]:
        """Evaluate a range rule."""
        try:
            numeric_value = float(value)
            min_val = float(rule.range_min)
            max_val = float(rule.range_max)

            # Rule matches if value is OUTSIDE the range
            matches = numeric_value < min_val or numeric_value > max_val
            reason = f"{rule.field} ({numeric_value}) outside range [{min_val}, {max_val}]"

            return matches, reason
        except (ValueError, TypeError) as e:
            return False, f"Invalid numeric value for range: {e}"

    def _evaluate_equals(self, rule: PolicyRule, value: Any) -> tuple[bool, str]:
        """Evaluate an equals rule."""
        matches = value == rule.value
        reason = f"{rule.field} ({value}) == {rule.value}"
        return matches, reason

    def _evaluate_contains(self, rule: PolicyRule, value: Any) -> tuple[bool, str]:
        """Evaluate a contains rule."""
        if isinstance(value, list):
            matches = rule.value in value
            reason = f"{rule.field} contains {rule.value}"
        elif isinstance(value, str):
            matches = str(rule.value) in value
            reason = f"{rule.field} contains '{rule.value}'"
        else:
            matches = False
            reason = f"{rule.field} is not a list or string"

        return matches, reason

    def _get_field_value(self, field_path: str, context: Dict[str, Any]) -> Any:
        """Get field value using dot notation.

        Examples:
            "action" -> context["action"]
            "context.risk_score" -> context["context"]["risk_score"]
            "intent.parameters.cost" -> context["intent"]["parameters"]["cost"]
        """
        parts = field_path.split(".")
        value = context

        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return None

        return value

    def _generate_constraint(
        self,
        rule: PolicyRule,
        context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Generate a constraint for a DEGRADE decision.

        When a rule action is DEGRADE, we generate a constraint that describes
        how the action should be modified.
        """
        if rule.rule_type == RuleType.THRESHOLD:
            return {
                "type": "limit",
                "field": rule.field,
                "max_value": rule.threshold,
                "reason": rule.name,
            }
        elif rule.rule_type == RuleType.RANGE:
            return {
                "type": "range",
                "field": rule.field,
                "min_value": rule.range_min,
                "max_value": rule.range_max,
                "reason": rule.name,
            }
        else:
            return {
                "type": "generic",
                "reason": rule.name,
            }

    def _handle_error(self, action: str, error: Exception) -> "PolicyDecision":
        """Handle policy engine errors with fail-safe behavior.

        Args:
            action: The action being evaluated
            error: The exception that occurred

        Returns:
            PolicyDecision based on fail-safe mode
        """
        error_msg = f"Policy engine error: {str(error)[:200]}"

        if FAIL_SAFE_MODE in ("allow", "allow_with_log"):
            logger.error(f"FAIL-SAFE ALLOW: {error_msg}")
            return PolicyDecision(
                verdict="ALLOW_WITH_LOG",
                reason=f"Fail-safe: {error_msg}",
            )
        else:
            logger.error(f"FAIL-SAFE BLOCK: {error_msg}")
            return PolicyDecision(
                verdict="BLOCK",
                reason=f"Fail-safe: {error_msg}",
            )

    def get_statistics(self) -> Dict[str, Any]:
        """Get engine statistics for monitoring.

        Returns:
            Dictionary with engine statistics
        """
        total_rules = len(self.rules_cache)
        enabled_rules = sum(1 for r in self.rules_cache.values() if r.enabled)

        # Count rules by action
        action_counts = {}
        for rule in self.rules_cache.values():
            action = rule.action.value
            action_counts[action] = action_counts.get(action, 0) + 1

        # Count rules by type
        type_counts = {}
        for rule in self.rules_cache.values():
            rule_type = rule.rule_type.value
            type_counts[rule_type] = type_counts.get(rule_type, 0) + 1

        return {
            "total_rules": total_rules,
            "enabled_rules": enabled_rules,
            "disabled_rules": total_rules - enabled_rules,
            "policy_sets": len(self.policy_sets),
            "rules_by_action": action_counts,
            "rules_by_type": type_counts,
            "fail_safe_mode": FAIL_SAFE_MODE,
        }

    def clear_cache(self):
        """Clear the rules cache."""
        self.rules_cache.clear()
        logger.info("Policy rules cache cleared")

    def reload_from_storage(self, storage):
        """Reload all policy rules from storage.

        Args:
            storage: PolicyStorage instance
        """
        self.clear_cache()
        policy_sets = storage.get_all_policy_sets()
        for policy_set in policy_sets:
            self.add_policy_set(policy_set)
        logger.info(f"Reloaded {len(self.rules_cache)} rules from storage")
