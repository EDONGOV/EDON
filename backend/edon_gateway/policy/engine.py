"""Policy Engine - Core governance evaluation engine.

This module implements the PolicyEngine class, which evaluates actions against
policy rules and returns decisions. It's inspired by the MAG authority engine
but adapted for the Python gateway context.

PolicyConfig (formerly in policies.py) and all behavioural guards
(rate-limiting, loop detection, work-hours, dangerous-command, external-sharing)
now live here. policies.py is a thin backward-compat re-export.
"""

import os
import logging
import concurrent.futures
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
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


# ── PolicyConfig ──────────────────────────────────────────────────────────────

@dataclass
class PolicyConfig:
    """Behavioural-guard configuration (rate limiting, loop detection, work hours, etc.)."""

    max_actions_per_minute: int = 30
    loop_detection_window_seconds: int = 60
    loop_detection_threshold: int = 5

    # Work hours (24-hour, local server time by default)
    work_hours_start: int = 8
    work_hours_end: int = 18

    # Risk thresholds
    auto_allow_risk_levels: Optional[Set[str]] = None
    escalate_risk_levels: Optional[Set[str]] = None

    # Shell commands that are always dangerous (substring match as fast path)
    dangerous_shell_commands: Optional[Set[str]] = None

    # Op-name patterns that indicate external data sharing
    external_sharing_patterns: Optional[List[str]] = None

    def __post_init__(self):
        try:
            if os.getenv("EDON_MAX_ACTIONS_PER_MINUTE"):
                self.max_actions_per_minute = int(os.getenv("EDON_MAX_ACTIONS_PER_MINUTE") or 30)
            if os.getenv("EDON_LOOP_DETECTION_WINDOW_SECONDS"):
                self.loop_detection_window_seconds = int(os.getenv("EDON_LOOP_DETECTION_WINDOW_SECONDS") or 60)
            if os.getenv("EDON_LOOP_DETECTION_THRESHOLD"):
                self.loop_detection_threshold = int(os.getenv("EDON_LOOP_DETECTION_THRESHOLD") or 5)
        except ValueError:
            pass

        if self.auto_allow_risk_levels is None:
            self.auto_allow_risk_levels = {"low"}
        if self.escalate_risk_levels is None:
            self.escalate_risk_levels = {"high", "critical"}
        if self.dangerous_shell_commands is None:
            self.dangerous_shell_commands = {
                "rm -rf",
                "format",
                "del /f /s /q",
                "shutdown",
                "reboot",
                "mkfs",
                "dd if=",
                "chmod 777 /",
                ":(){:|:&};:",  # fork bomb
                "curl | bash",
                "wget | bash",
                "wget -O- | sh",
            }
        if self.external_sharing_patterns is None:
            self.external_sharing_patterns = [
                "export",
                "upload",
                "share",
                "send_to",
                "external",
            ]

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

    def __init__(
        self,
        policy_sets: Optional[List[PolicySet]] = None,
        rules: Optional[List[Dict[str, Any]]] = None,
        config: Optional["PolicyConfig"] = None,
        rate_store=None,
    ):
        """Initialize policy engine.

        Args:
            policy_sets: Optional list of PolicySet objects to load.
            rules: Optional list of plain-dict rules for simple evaluation.
            config: Behavioural-guard configuration (rate limiting, loop detection, etc.).
            rate_store: Optional RateStore for Redis-backed rate/loop state.
                        Falls back to in-memory list when None.
        """
        self.policy_sets: Dict[str, PolicySet] = {}
        self.rules_cache: OrderedDict[str, PolicyRule] = OrderedDict()
        self._cache_size = 1000

        # Behavioural guard state
        self.config: PolicyConfig = config or PolicyConfig()
        # Legacy in-memory history — used only when rate_store is not provided
        self._action_history: List[tuple] = []  # (timestamp_float, tool, op, params_hash)

        # Redis-backed state (injected; falls back to None → in-memory path)
        self._rate_store = rate_store  # RateStore | None

        # Migrate plain-dict rules into the unified PolicyRule cache so there is
        # only one evaluation path.  Callers that pass raw dicts still work.
        if rules:
            for idx, r in enumerate(rules):
                self._ingest_dict_rule(r, idx)

        if policy_sets:
            for policy_set in policy_sets:
                self.add_policy_set(policy_set)

        logger.info(f"PolicyEngine initialized with {len(self.rules_cache)} rules")

    def _ingest_dict_rule(self, r: Dict[str, Any], idx: int) -> None:
        """Convert a plain-dict rule into a PolicyRule and add it to the cache.

        Supports the same rule types as the old _evaluate_simple_rules path:
        always, action_type, threshold, range.
        """
        rule_id = str(r.get("rule_id") or r.get("id") or f"dict_rule_{idx}")
        name = str(r.get("name") or rule_id)
        verdict = str(r.get("verdict", "BLOCK")).upper()
        action_map = {
            "BLOCK": PolicyAction.BLOCK,
            "ALLOW": PolicyAction.ALLOW,
            "HUMAN_REQUIRED": PolicyAction.REQUIRE_APPROVAL,
            "DEGRADE": PolicyAction.DEGRADE,
        }
        policy_action = action_map.get(verdict, PolicyAction.BLOCK)
        rule_type_str = str(r.get("type", "threshold")).lower()
        type_map = {
            "threshold": RuleType.THRESHOLD,
            "range": RuleType.RANGE,
            "action_type": RuleType.EQUALS,
            "always": RuleType.EQUALS,
        }
        rule_type = type_map.get(rule_type_str, RuleType.THRESHOLD)

        rule = PolicyRule(
            rule_id=rule_id,
            name=name,
            rule_type=rule_type,
            field=str(r.get("field", "action")),
            threshold=r.get("threshold"),
            range_min=r.get("range_min"),
            range_max=r.get("range_max"),
            value=r.get("value") or r.get("allowed_actions"),
            action=policy_action,
            priority=int(r.get("priority", 50)),
            enabled=bool(r.get("enabled", True)),
        )
        # "always" type: we mark via a special field value so _evaluate_rule handles it
        if rule_type_str == "always":
            rule.field = "_always"
            rule.value = True
        elif rule_type_str == "action_type":
            rule.field = "action"
            rule.rule_type = RuleType.CONTAINS
        self._add_to_cache(rule)

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
        """Evaluate action against all rules in the unified PolicyRule cache."""
        if not self.rules_cache:
            return PolicyDecision(verdict="ALLOW", reason="No policy rules configured")

        eval_context = {
            "action": action,
            "context": context,
            "intent": intent or {},
        }

        matched_rules: List[str] = []

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

    # ── Behavioural guards (formerly in policies.py) ─────────────────────────

    def is_work_hours(self, timestamp: datetime) -> bool:
        """Return True if *timestamp* falls within configured work hours."""
        hour = timestamp.hour
        return self.config.work_hours_start <= hour < self.config.work_hours_end

    def is_dangerous_command(self, command: str) -> bool:
        """Return True if *command* matches a known-dangerous substring pattern."""
        command_lower = command.lower()
        return any(
            pattern in command_lower
            for pattern in (self.config.dangerous_shell_commands or set())
        )

    def is_external_sharing(self, op: str, params: dict) -> bool:
        """Return True if *op* or *params* suggest external data egress."""
        op_lower = op.lower()
        patterns = self.config.external_sharing_patterns or []
        if any(p in op_lower for p in patterns):
            return True
        params_str = str(params).lower()
        return any(p in params_str for p in patterns)

    def record_action(
        self,
        action,
        current_time: datetime,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> None:
        """Record an action for rate limiting and loop detection."""
        params_hash = str(sorted(action.params.items()))
        if self._rate_store is not None:
            from ..state.rate_store import RateStore
            rate_key = RateStore.rate_key(tenant_id, agent_id)
            loop_key = RateStore.loop_key(
                tenant_id, agent_id,
                action.tool.value if hasattr(action.tool, "value") else str(action.tool),
                action.op,
                params_hash,
            )
            self._rate_store.add_and_count(rate_key, 60.0)
            self._rate_store.add_and_count(loop_key, float(self.config.loop_detection_window_seconds))
        else:
            ts = current_time.timestamp()
            self._action_history.append((ts, action.tool, action.op, params_hash))
            cutoff = ts - 3600
            self._action_history = [e for e in self._action_history if e[0] >= cutoff]

    def check_rate_limit(
        self,
        current_time: datetime,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> bool:
        """Return True if the rate limit has been exceeded."""
        if self._rate_store is not None:
            from ..state.rate_store import RateStore
            key = RateStore.rate_key(tenant_id, agent_id)
            count = self._rate_store.count_in_window(key, 60.0)
            return count >= self.config.max_actions_per_minute
        cutoff = current_time.timestamp() - 60
        recent = [e for e in self._action_history if e[0] >= cutoff]
        return len(recent) >= self.config.max_actions_per_minute

    def detect_loop(
        self,
        tool,
        op: str,
        params_hash: str,
        current_time: datetime,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> bool:
        """Return True if the same (tool, op, params) has been seen too many times recently."""
        if self._rate_store is not None:
            from ..state.rate_store import RateStore
            key = RateStore.loop_key(
                tenant_id, agent_id,
                tool.value if hasattr(tool, "value") else str(tool),
                op,
                params_hash,
            )
            count = self._rate_store.count_in_window(key, float(self.config.loop_detection_window_seconds))
            return count >= self.config.loop_detection_threshold
        window_start = current_time.timestamp() - self.config.loop_detection_window_seconds
        tool_val = tool.value if hasattr(tool, "value") else str(tool)
        matching = [
            e for e in self._action_history
            if e[0] >= window_start
            and (e[1].value if hasattr(e[1], "value") else str(e[1])) == tool_val
            and e[2] == op
            and e[3] == params_hash
        ]
        return len(matching) >= self.config.loop_detection_threshold

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
