"""Tests for EmbeddedGovernor — pure in-process, no DB or network.

Gap 2: Sub-ms local decisions for edge / nanobot deployments.
"""
import time

import pytest

from edon_gateway.edge.embedded_governor import (
    EmbeddedGovernor,
    EmbeddedVerdict,
    PolicyBundle,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_bundle(**overrides) -> PolicyBundle:
    base = {
        "version": "test-v1",
        "issued_at": "2099-01-01T00:00:00+00:00",  # far future = not expired
        "ttl_seconds": 86400,
        "blocked_tools": [],
        "required_scope": [],
        "rate_limits": {},
        "custom_rules": [],
    }
    base.update(overrides)
    return PolicyBundle.from_dict(base)


def _make_governor(**bundle_overrides) -> EmbeddedGovernor:
    return EmbeddedGovernor(_make_bundle(**bundle_overrides))


# ---------------------------------------------------------------------------
# PolicyBundle
# ---------------------------------------------------------------------------

class TestPolicyBundle:
    def test_from_dict_round_trip(self):
        d = {
            "version": "abc",
            "issued_at": "2099-01-01T00:00:00+00:00",
            "ttl_seconds": 3600,
            "blocked_tools": ["shell"],
            "required_scope": ["read"],
            "rate_limits": {"actions_per_minute": 10},
            "custom_rules": [{"id": "r1", "action": "BLOCK", "priority": 1}],
        }
        b = PolicyBundle.from_dict(d)
        assert b.version == "abc"
        assert b.blocked_tools == ["shell"]
        assert b.ttl_seconds == 3600
        assert b.required_scope == ["read"]
        assert len(b.custom_rules) == 1

    def test_not_expired_far_future(self):
        b = _make_bundle()
        assert not b.is_expired()

    def test_expired_past_issue(self):
        b = _make_bundle(
            issued_at="2000-01-01T00:00:00+00:00",
            ttl_seconds=1,
        )
        assert b.is_expired()

    def test_malformed_issued_at_treated_as_expired(self):
        b = _make_bundle(issued_at="not-a-date")
        assert b.is_expired()

    def test_empty_issued_at_treated_as_expired(self):
        b = _make_bundle(issued_at="")
        assert b.is_expired()


# ---------------------------------------------------------------------------
# Default ALLOW
# ---------------------------------------------------------------------------

class TestDefaultAllow:
    def test_clean_action_is_allowed(self):
        gov = _make_governor()
        v = gov.evaluate({"tool": "sensor", "op": "read"})
        assert v.verdict == "ALLOW"
        assert v.reason_code == "policy_pass"

    def test_latency_populated(self):
        gov = _make_governor()
        v = gov.evaluate({"tool": "robot", "op": "move"})
        assert v.latency_us >= 0


# ---------------------------------------------------------------------------
# Blocked tools
# ---------------------------------------------------------------------------

class TestBlockedTools:
    def test_blocked_tool_returns_block(self):
        gov = _make_governor(blocked_tools=["shell"])
        v = gov.evaluate({"tool": "shell", "op": "run"})
        assert v.verdict == "BLOCK"
        assert v.reason_code == "tool_blocked"

    def test_non_blocked_tool_allows(self):
        gov = _make_governor(blocked_tools=["shell"])
        v = gov.evaluate({"tool": "robot", "op": "move"})
        assert v.verdict == "ALLOW"

    def test_multiple_blocked_tools(self):
        gov = _make_governor(blocked_tools=["shell", "database", "memory"])
        for tool in ("shell", "database", "memory"):
            v = gov.evaluate({"tool": tool, "op": "any"})
            assert v.verdict == "BLOCK"


# ---------------------------------------------------------------------------
# Required scope
# ---------------------------------------------------------------------------

class TestRequiredScope:
    def test_missing_scope_blocked(self):
        gov = _make_governor(required_scope=["robot.move"])
        v = gov.evaluate({"tool": "sensor", "op": "read", "scope": []})
        assert v.verdict == "BLOCK"
        assert v.reason_code == "scope_violation"

    def test_matching_scope_allowed(self):
        gov = _make_governor(required_scope=["robot.move"])
        v = gov.evaluate({"tool": "robot", "op": "move", "scope": ["robot.move"]})
        assert v.verdict == "ALLOW"

    def test_tool_alone_satisfies_scope(self):
        gov = _make_governor(required_scope=["robot"])
        v = gov.evaluate({"tool": "robot", "op": "stop"})
        assert v.verdict == "ALLOW"


# ---------------------------------------------------------------------------
# Custom rules
# ---------------------------------------------------------------------------

class TestCustomRules:
    def test_matching_rule_blocks(self):
        rules = [
            {"id": "r1", "condition_tool": "robot", "condition_op": "destroy",
             "action": "BLOCK", "priority": 10, "enabled": True}
        ]
        gov = _make_governor(custom_rules=rules)
        v = gov.evaluate({"tool": "robot", "op": "destroy"})
        assert v.verdict == "BLOCK"
        assert "r1" in v.reason_code

    def test_non_matching_rule_skipped(self):
        rules = [
            {"id": "r1", "condition_tool": "robot", "condition_op": "destroy",
             "action": "BLOCK", "priority": 10, "enabled": True}
        ]
        gov = _make_governor(custom_rules=rules)
        v = gov.evaluate({"tool": "robot", "op": "move"})
        assert v.verdict == "ALLOW"

    def test_disabled_rule_skipped(self):
        rules = [
            {"id": "r1", "condition_tool": "robot", "action": "BLOCK",
             "priority": 10, "enabled": False}
        ]
        gov = _make_governor(custom_rules=rules)
        v = gov.evaluate({"tool": "robot", "op": "move"})
        assert v.verdict == "ALLOW"

    def test_rule_escalate_action(self):
        rules = [
            {"id": "r2", "condition_tool": "inject", "action": "ESCALATE",
             "priority": 5, "enabled": True}
        ]
        gov = _make_governor(custom_rules=rules)
        v = gov.evaluate({"tool": "inject", "op": "deliver"})
        assert v.verdict == "ESCALATE"

    def test_higher_priority_rule_wins(self):
        rules = [
            {"id": "low", "condition_tool": "robot", "action": "ALLOW", "priority": 1, "enabled": True},
            {"id": "high", "condition_tool": "robot", "action": "BLOCK", "priority": 100, "enabled": True},
        ]
        gov = _make_governor(custom_rules=rules)
        v = gov.evaluate({"tool": "robot", "op": "any"})
        assert v.verdict == "BLOCK"
        assert "high" in v.reason_code


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class TestRateLimit:
    def test_global_rate_limit(self):
        gov = _make_governor(rate_limits={"actions_per_minute": 3})
        for i in range(3):
            v = gov.evaluate({"tool": "sensor", "op": "read"})
            assert v.verdict == "ALLOW", f"Request {i+1} should be allowed"
        # 4th should be blocked
        v = gov.evaluate({"tool": "sensor", "op": "read"})
        assert v.verdict == "BLOCK"
        assert v.reason_code == "rate_limit_exceeded"

    def test_per_tool_rate_limit(self):
        gov = _make_governor(rate_limits={"per_tool": {"robot.move": 2}})
        gov.evaluate({"tool": "robot", "op": "move"})
        gov.evaluate({"tool": "robot", "op": "move"})
        v = gov.evaluate({"tool": "robot", "op": "move"})
        assert v.verdict == "BLOCK"

    def test_different_tools_have_separate_windows(self):
        gov = _make_governor(rate_limits={"per_tool": {"robot.move": 2}})
        gov.evaluate({"tool": "robot", "op": "move"})
        gov.evaluate({"tool": "robot", "op": "move"})
        # sensor.read has its own window — should still pass
        v = gov.evaluate({"tool": "sensor", "op": "read"})
        assert v.verdict == "ALLOW"


# ---------------------------------------------------------------------------
# Bundle expiry
# ---------------------------------------------------------------------------

class TestBundleExpiry:
    def test_expired_bundle_blocks_all(self):
        gov = _make_governor(
            issued_at="2000-01-01T00:00:00+00:00",
            ttl_seconds=1,
        )
        v = gov.evaluate({"tool": "sensor", "op": "read"})
        assert v.verdict == "BLOCK"
        assert v.reason_code == "bundle_expired"


# ---------------------------------------------------------------------------
# Latency budget
# ---------------------------------------------------------------------------

class TestLatencyBudget:
    def test_p99_under_5ms(self):
        """1000 evaluate() calls on a clean bundle must have p99 < 5 ms."""
        gov = _make_governor()
        action = {"tool": "sensor", "op": "read", "params": {}}
        latencies = []
        for _ in range(1000):
            t0 = time.perf_counter()
            gov.evaluate(action)
            latencies.append((time.perf_counter() - t0) * 1000)

        latencies.sort()
        p99 = latencies[int(0.99 * len(latencies)) - 1]
        assert p99 < 5.0, f"EmbeddedGovernor p99 latency {p99:.3f}ms exceeds 5ms budget"


# ---------------------------------------------------------------------------
# from_bundle_dict constructor
# ---------------------------------------------------------------------------

class TestFromBundleDict:
    def test_from_bundle_dict(self):
        d = {
            "version": "v2",
            "issued_at": "2099-06-01T00:00:00+00:00",
            "ttl_seconds": 7200,
            "blocked_tools": ["shell"],
            "required_scope": [],
            "rate_limits": {},
            "custom_rules": [],
        }
        gov = EmbeddedGovernor.from_bundle_dict(d)
        assert gov.bundle_version() == "v2"
        assert not gov.is_bundle_expired()

    def test_bundle_version(self):
        gov = _make_governor()
        assert gov.bundle_version() == "test-v1"
