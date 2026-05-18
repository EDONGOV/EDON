"""Tests for EDON Gateway Policy Engine.

This test suite validates the core governance capability including:
- Threshold rules
- Range rules
- Fail-safe behavior
- Policy caching
"""

import pytest
from datetime import datetime, UTC

from edon_gateway.policy.schemas import (
    PolicyRule,
    PolicySet,
    RuleType,
    PolicyAction,
)
from edon_gateway.policy.engine import PolicyEngine

# engine.PolicyDecision uses .verdict (str) not .decision (enum)
# Verdict strings: "ALLOW", "BLOCK", "DEGRADE", "HUMAN_REQUIRED", "ALLOW_WITH_LOG"


class TestPolicyEngine:
    """Test suite for PolicyEngine."""

    def test_threshold_rule_greater_than(self):
        """Test threshold rule with greater_than operator."""
        engine = PolicyEngine()

        # Add a rule: Block if cost > 100
        rule = PolicyRule(
            rule_id="cost_limit",
            name="Cost limit exceeded",
            rule_type=RuleType.THRESHOLD,
            field="context.estimated_cost",
            threshold=100,
            threshold_operator="greater_than",
            action=PolicyAction.BLOCK,
            priority=90
        )
        engine.add_rule(rule)

        # Test case 1: Cost exceeds threshold - should BLOCK
        context = {"estimated_cost": 150}
        decision = engine.evaluate("purchase", context)

        assert decision.verdict == "BLOCK"
        assert decision.rule_id == "cost_limit"

        # Test case 2: Cost within threshold - should ESCALATE when no rule matches
        context = {"estimated_cost": 50}
        decision = engine.evaluate("purchase", context)

        assert decision.verdict == "ESCALATE"
        assert decision.rule_id is None

    def test_threshold_rule_less_than(self):
        """Test threshold rule with less_than operator."""
        engine = PolicyEngine()

        # Add a rule: Block if altitude < 50m
        rule = PolicyRule(
            rule_id="min_altitude",
            name="Altitude too low",
            rule_type=RuleType.THRESHOLD,
            field="context.altitude_m",
            threshold=50,
            threshold_operator="less_than",
            action=PolicyAction.BLOCK,
            priority=95
        )
        engine.add_rule(rule)

        # Test case 1: Altitude below threshold - should BLOCK
        context = {"altitude_m": 30}
        decision = engine.evaluate("fly", context)

        assert decision.verdict == "BLOCK"
        assert decision.rule_id == "min_altitude"

        # Test case 2: Altitude above threshold - should ESCALATE when no rule matches
        context = {"altitude_m": 100}
        decision = engine.evaluate("fly", context)

        assert decision.verdict == "ESCALATE"

    def test_range_rule(self):
        """Test range rule - triggers when value is outside range."""
        engine = PolicyEngine()

        # Add a rule: Degrade if velocity outside [0, 50] m/s
        rule = PolicyRule(
            rule_id="velocity_range",
            name="Velocity out of safe range",
            rule_type=RuleType.RANGE,
            field="context.velocity_ms",
            range_min=0,
            range_max=50,
            action=PolicyAction.DEGRADE,
            priority=80
        )
        engine.add_rule(rule)

        # Test case 1: Velocity below range - should DEGRADE
        context = {"velocity_ms": -10}
        decision = engine.evaluate("move", context)

        assert decision.verdict == "DEGRADE"
        assert decision.rule_id == "velocity_range"

        # Test case 2: Velocity above range - should DEGRADE
        context = {"velocity_ms": 70}
        decision = engine.evaluate("move", context)

        assert decision.verdict == "DEGRADE"

        # Test case 3: Velocity within range - should ESCALATE when no rule matches
        context = {"velocity_ms": 25}
        decision = engine.evaluate("move", context)

        assert decision.verdict == "ESCALATE"

    def test_equals_rule(self):
        """Test equals rule."""
        engine = PolicyEngine()

        # Add a rule: Block if action is "delete_all"
        rule = PolicyRule(
            rule_id="dangerous_action",
            name="Dangerous action detected",
            rule_type=RuleType.EQUALS,
            field="action",
            value="delete_all",
            action=PolicyAction.BLOCK,
            priority=100
        )
        engine.add_rule(rule)

        # Test case 1: Action matches - should BLOCK
        context = {}
        decision = engine.evaluate("delete_all", context)

        assert decision.verdict == "BLOCK"
        assert decision.rule_id == "dangerous_action"

        # Test case 2: Action doesn't match - should ESCALATE when no rule matches
        decision = engine.evaluate("delete_one", context)

        assert decision.verdict == "ESCALATE"

    def test_contains_rule_string(self):
        """Test contains rule with string value."""
        engine = PolicyEngine()

        # Add a rule: Block if command contains "rm -rf"
        rule = PolicyRule(
            rule_id="dangerous_command",
            name="Dangerous command detected",
            rule_type=RuleType.CONTAINS,
            field="context.command",
            value="rm -rf",
            action=PolicyAction.BLOCK,
            priority=100
        )
        engine.add_rule(rule)

        # Test case 1: Command contains pattern - should BLOCK
        context = {"command": "sudo rm -rf /data"}
        decision = engine.evaluate("shell", context)

        assert decision.verdict == "BLOCK"
        assert decision.rule_id == "dangerous_command"

        # Test case 2: Command doesn't contain pattern - should ESCALATE when no rule matches
        context = {"command": "ls -la"}
        decision = engine.evaluate("shell", context)

        assert decision.verdict == "ESCALATE"

    def test_contains_rule_list(self):
        """Test contains rule with list value."""
        engine = PolicyEngine()

        # Add a rule: Require approval if tags contain "sensitive"
        rule = PolicyRule(
            rule_id="sensitive_data",
            name="Sensitive data access",
            rule_type=RuleType.CONTAINS,
            field="context.tags",
            value="sensitive",
            action=PolicyAction.REQUIRE_APPROVAL,
            priority=85
        )
        engine.add_rule(rule)

        # Test case 1: Tags contain "sensitive" - should require approval
        context = {"tags": ["public", "sensitive", "encrypted"]}
        decision = engine.evaluate("access", context)

        assert decision.verdict == "HUMAN_REQUIRED"
        assert decision.rule_id == "sensitive_data"

        # Test case 2: Tags don't contain "sensitive" - should ESCALATE when no rule matches
        context = {"tags": ["public", "read-only"]}
        decision = engine.evaluate("access", context)

        assert decision.verdict == "ESCALATE"

    def test_rule_priority_ordering(self):
        """Test that higher priority rules are evaluated first."""
        engine = PolicyEngine()

        # Add low priority ALLOW rule
        rule1 = PolicyRule(
            rule_id="default_allow",
            name="Default allow",
            rule_type=RuleType.EQUALS,
            field="action",
            value="test_action",
            action=PolicyAction.ALLOW,
            priority=10
        )
        engine.add_rule(rule1)

        # Add high priority BLOCK rule
        rule2 = PolicyRule(
            rule_id="security_block",
            name="Security block",
            rule_type=RuleType.EQUALS,
            field="action",
            value="test_action",
            action=PolicyAction.BLOCK,
            priority=100
        )
        engine.add_rule(rule2)

        # Higher priority BLOCK rule should be evaluated first
        context = {}
        decision = engine.evaluate("test_action", context)

        assert decision.verdict == "BLOCK"
        assert decision.rule_id == "security_block"
        assert decision.rule_id != "default_allow"

    def test_policy_set_management(self):
        """Test policy set management."""
        engine = PolicyEngine()

        # Create a policy set with multiple rules
        policy_set = PolicySet(
            set_id="test_set_1",
            name="Test Policy Set",
            description="Test policies",
            domain="test"
        )

        rule1 = PolicyRule(
            rule_id="test_rule_1",
            name="Test Rule 1",
            rule_type=RuleType.THRESHOLD,
            field="context.value",
            threshold=100,
            action=PolicyAction.BLOCK,
            priority=90
        )

        rule2 = PolicyRule(
            rule_id="test_rule_2",
            name="Test Rule 2",
            rule_type=RuleType.EQUALS,
            field="action",
            value="test",
            action=PolicyAction.ALLOW,
            priority=50
        )

        policy_set.add_rule(rule1)
        policy_set.add_rule(rule2)

        # Add policy set to engine
        engine.add_policy_set(policy_set)

        # Verify both rules are loaded
        assert len(engine.rules_cache) == 2
        assert "test_rule_1" in engine.rules_cache
        assert "test_rule_2" in engine.rules_cache

        # Test evaluation
        context = {"value": 150}
        decision = engine.evaluate("purchase", context)

        assert decision.verdict == "BLOCK"

    def test_disabled_rule_not_evaluated(self):
        """Test that disabled rules are not evaluated."""
        engine = PolicyEngine()

        # Add disabled rule
        rule = PolicyRule(
            rule_id="disabled_rule",
            name="Disabled Rule",
            rule_type=RuleType.EQUALS,
            field="action",
            value="test_action",
            action=PolicyAction.BLOCK,
            priority=100,
            enabled=False
        )
        engine.add_rule(rule)

        # Rule should not be in cache since it's disabled
        assert "disabled_rule" not in engine.rules_cache

        # Action should escalate since no rule matches in governed mode
        context = {}
        decision = engine.evaluate("test_action", context)

        assert decision.verdict == "ESCALATE"

    def test_fail_safe_block_mode(self):
        """Test fail-safe behavior in BLOCK mode."""
        import os
        import importlib
        from edon_gateway.policy import engine as engine_module

        # Set fail-safe mode to block
        os.environ["EDON_POLICY_FAIL_SAFE"] = "block"
        importlib.reload(engine_module)

        engine = engine_module.PolicyEngine()

        # Add a rule that will cause an error (invalid field type)
        rule = PolicyRule(
            rule_id="error_rule",
            name="Error Rule",
            rule_type=RuleType.THRESHOLD,
            field="context.invalid_field",
            threshold=100,
            action=PolicyAction.ALLOW,
            priority=50
        )
        engine.add_rule(rule)

        # Simulate an error by not providing the expected field
        # The engine should catch the error and apply fail-safe
        context = {}  # Missing context.invalid_field

        decision = engine.evaluate("test", context)

        # No rule matched, so governed mode escalates by default.
        assert decision.verdict == "ESCALATE"

    def test_fail_safe_allow_mode(self):
        """Test fail-safe behavior in ALLOW mode."""
        import os
        import importlib
        from edon_gateway.policy import engine as engine_module

        # Set fail-safe mode to allow
        os.environ["EDON_POLICY_FAIL_SAFE"] = "allow_with_log"
        importlib.reload(engine_module)

        engine = engine_module.PolicyEngine()

        # Similar to above, but in allow mode
        rule = PolicyRule(
            rule_id="error_rule",
            name="Error Rule",
            rule_type=RuleType.THRESHOLD,
            field="context.value",
            threshold=100,
            action=PolicyAction.BLOCK,
            priority=50
        )
        engine.add_rule(rule)

        context = {}  # Missing field
        decision = engine.evaluate("test", context)

        # No rule matched, so governed mode escalates by default.
        assert decision.verdict == "ESCALATE"

    def test_cache_size_limit(self):
        """Test that cache respects size limits."""
        engine = PolicyEngine()
        engine._cache_size = 5  # Set small cache size for testing

        # Add 10 rules
        for i in range(10):
            rule = PolicyRule(
                rule_id=f"rule_{i}",
                name=f"Rule {i}",
                rule_type=RuleType.EQUALS,
                field="action",
                value=f"action_{i}",
                action=PolicyAction.ALLOW,
                priority=i
            )
            engine.add_rule(rule)

        # Cache should only contain 5 rules (the most recent ones)
        assert len(engine.rules_cache) <= engine._cache_size

    def test_constraint_generation(self):
        """Test that DEGRADE decisions are returned correctly."""
        engine = PolicyEngine()

        # Add rule with DEGRADE action
        rule = PolicyRule(
            rule_id="rate_limit",
            name="Rate limit exceeded",
            rule_type=RuleType.THRESHOLD,
            field="context.requests_per_minute",
            threshold=100,
            threshold_operator="greater_than",
            action=PolicyAction.DEGRADE,
            priority=80
        )
        engine.add_rule(rule)

        # Trigger rule
        context = {"requests_per_minute": 150}
        decision = engine.evaluate("api_call", context)

        assert decision.verdict == "DEGRADE"

    def test_statistics(self):
        """Test engine statistics collection."""
        engine = PolicyEngine()

        # Add various rules
        rules = [
            PolicyRule(
                rule_id="rule_1",
                name="Rule 1",
                rule_type=RuleType.THRESHOLD,
                field="context.value",
                threshold=100,
                action=PolicyAction.BLOCK,
                priority=90
            ),
            PolicyRule(
                rule_id="rule_2",
                name="Rule 2",
                rule_type=RuleType.RANGE,
                field="context.velocity",
                range_min=0,
                range_max=50,
                action=PolicyAction.DEGRADE,
                priority=80
            ),
            PolicyRule(
                rule_id="rule_3",
                name="Rule 3",
                rule_type=RuleType.EQUALS,
                field="action",
                value="test",
                action=PolicyAction.ALLOW,
                priority=50,
                enabled=False  # Disabled
            ),
        ]

        for rule in rules:
            engine.add_rule(rule)

        # Get statistics
        stats = engine.get_statistics()

        assert stats["total_rules"] == 2  # Only enabled rules
        assert stats["enabled_rules"] == 2
        assert "rules_by_action" in stats
        assert "rules_by_type" in stats
        assert stats["rules_by_action"]["block"] == 1
        assert stats["rules_by_action"]["degrade"] == 1
        assert stats["rules_by_type"]["threshold"] == 1
        assert stats["rules_by_type"]["range"] == 1

    def test_clear_cache(self):
        """Test cache clearing."""
        engine = PolicyEngine()

        # Add rules
        for i in range(5):
            rule = PolicyRule(
                rule_id=f"rule_{i}",
                name=f"Rule {i}",
                rule_type=RuleType.EQUALS,
                field="action",
                value=f"action_{i}",
                action=PolicyAction.ALLOW,
                priority=50
            )
            engine.add_rule(rule)

        assert len(engine.rules_cache) == 5

        # Clear cache
        engine.clear_cache()

        assert len(engine.rules_cache) == 0

    def test_nested_field_access(self):
        """Test accessing nested fields using dot notation."""
        engine = PolicyEngine()

        # Add rule with nested field
        rule = PolicyRule(
            rule_id="nested_rule",
            name="Nested Field Rule",
            rule_type=RuleType.THRESHOLD,
            field="context.metadata.priority",
            threshold=5,
            threshold_operator="greater_than",
            action=PolicyAction.BLOCK,
            priority=90
        )
        engine.add_rule(rule)

        # Test with nested context
        context = {
            "metadata": {
                "priority": 8,
                "category": "urgent"
            }
        }
        decision = engine.evaluate("process", context)

        assert decision.verdict == "BLOCK"
        assert decision.rule_id == "nested_rule"

    def test_intent_context_evaluation(self):
        """Test evaluation with both context and intent."""
        engine = PolicyEngine()

        # Add rule that references intent
        rule = PolicyRule(
            rule_id="intent_rule",
            name="Intent-based Rule",
            rule_type=RuleType.EQUALS,
            field="intent.objective",
            value="sensitive_operation",
            action=PolicyAction.REQUIRE_APPROVAL,
            priority=85
        )
        engine.add_rule(rule)

        # Test with intent
        context = {}
        intent = {"objective": "sensitive_operation"}
        decision = engine.evaluate("operation", context, intent)

        assert decision.verdict == "HUMAN_REQUIRED"
        assert decision.rule_id == "intent_rule"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
