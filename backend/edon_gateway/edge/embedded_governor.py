"""Embedded (edge) policy governor — pure Python, zero I/O.

Designed to run on resource-constrained edge devices (Raspberry Pi, NVIDIA
Jetson, microcontroller with MicroPython) that control nanobot / CAV swarms.
The device receives a PolicyBundle from the gateway's
GET /edge/{id}/policy-bundle endpoint, stores it locally, and uses
EmbeddedGovernor to evaluate every action before the swarm acts.

Design constraints:
  - No database access.
  - No network calls.
  - No disk I/O during evaluate().
  - Target: p99 < 5 ms on a Raspberry Pi 4 (1.5 GHz Cortex-A72).

Thread-safety: EmbeddedGovernor is NOT thread-safe due to the in-memory
rate-limit counters (_rate_windows).  Create one instance per thread/coroutine,
or protect the shared instance with a threading.Lock.
"""
from __future__ import annotations

import time
import json
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class PolicyBundle:
    """Immutable, pre-compiled policy snapshot for edge evaluation.

    Produced by the gateway's /edge/{id}/policy-bundle endpoint and
    consumed by EmbeddedGovernor.from_bundle_dict().
    """
    version: str
    issued_at: str          # ISO-8601 UTC
    ttl_seconds: int
    blocked_tools: List[str]
    required_scope: List[str]
    rate_limits: Dict[str, Any]   # {"actions_per_minute": N, "per_tool": {...}}
    custom_rules: List[Dict[str, Any]]

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PolicyBundle":
        return cls(
            version=d.get("version", "unknown"),
            issued_at=d.get("issued_at", ""),
            ttl_seconds=int(d.get("ttl_seconds", 3600)),
            blocked_tools=[str(t) for t in d.get("blocked_tools", [])],
            required_scope=[str(s) for s in d.get("required_scope", [])],
            rate_limits=d.get("rate_limits", {}),
            custom_rules=d.get("custom_rules", []),
        )

    def is_expired(self) -> bool:
        """True if wall-clock time has passed issued_at + ttl_seconds."""
        if not self.issued_at:
            return True
        try:
            issued = datetime.fromisoformat(
                self.issued_at.replace("Z", "+00:00")
            )
            now = datetime.now(timezone.utc)
            age = (now - issued).total_seconds()
            return age > self.ttl_seconds
        except (ValueError, TypeError):
            return True  # malformed timestamp → treat as expired (fail-closed)


@dataclass
class EmbeddedVerdict:
    """Result of a single EmbeddedGovernor.evaluate() call."""
    verdict: str           # ALLOW | BLOCK | ESCALATE
    reason_code: str
    explanation: str
    latency_us: float = 0.0   # microseconds; populated post-evaluate


# ---------------------------------------------------------------------------
# Governor
# ---------------------------------------------------------------------------

class EmbeddedGovernor:
    """Pure-Python, I/O-free policy evaluator for edge / nanobot deployment.

    Usage::

        bundle = PolicyBundle.from_dict(bundle_dict)  # from gateway HTTP response
        gov = EmbeddedGovernor(bundle)

        verdict = gov.evaluate({
            "tool": "robot",
            "op": "move",
            "params": {"direction": "forward", "distance_mm": 50},
            "scope": ["robot.move"],
            "estimated_risk": "medium",
        })
        # verdict.verdict → "ALLOW" | "BLOCK" | "ESCALATE"
        # verdict.latency_us → e.g. 180.3
    """

    def __init__(self, bundle: PolicyBundle) -> None:
        self._bundle = bundle
        # Sliding-window rate counters: (tool, op) → deque of monotonic_ns timestamps
        self._rate_windows: Dict[Tuple[str, str], Deque[int]] = {}
        # Global action count deque (for actions_per_minute global cap)
        self._global_window: Deque[int] = deque()

    @classmethod
    def from_bundle_dict(cls, bundle_dict: Dict[str, Any]) -> "EmbeddedGovernor":
        """Construct from the dict returned by GET /edge/{id}/policy-bundle."""
        return cls(PolicyBundle.from_dict(bundle_dict))

    def evaluate(self, action_dict: Dict[str, Any]) -> EmbeddedVerdict:
        """Evaluate *action_dict* against the loaded bundle.

        No I/O.  Returns EmbeddedVerdict in < 5 ms on typical hardware.
        """
        t0 = time.monotonic_ns()
        verdict = self._evaluate_impl(action_dict)
        verdict.latency_us = (time.monotonic_ns() - t0) / 1_000
        return verdict

    def bundle_version(self) -> str:
        return self._bundle.version

    def is_bundle_expired(self) -> bool:
        return self._bundle.is_expired()

    # ------------------------------------------------------------------
    # Internal evaluation pipeline
    # ------------------------------------------------------------------

    def _evaluate_impl(self, action_dict: Dict[str, Any]) -> EmbeddedVerdict:
        """Evaluation order mirrors EDONGovernor for verdict consistency.

        Steps:
          1. Bundle expiry check → BLOCK (fail-closed if stale bundle)
          2. Blocked-tools check
          3. Required-scope check
          4. Custom rules (priority-ordered)
          5. Global rate limit
          6. Per-tool rate limit
          7. Default → ALLOW
        """
        tool = str(action_dict.get("tool", ""))
        op   = str(action_dict.get("op", ""))
        scope: List[str] = action_dict.get("scope") or []
        estimated_risk = str(action_dict.get("estimated_risk", "low"))

        # 1. Bundle expiry
        if self._bundle.is_expired():
            return EmbeddedVerdict(
                verdict="BLOCK",
                reason_code="bundle_expired",
                explanation=(
                    f"Policy bundle version {self._bundle.version!r} has expired. "
                    "Fetch a fresh bundle from the gateway."
                ),
            )

        # 2. Blocked tools
        if tool in self._bundle.blocked_tools:
            return EmbeddedVerdict(
                verdict="BLOCK",
                reason_code="tool_blocked",
                explanation=f"Tool '{tool}' is blocked by edge policy bundle.",
            )

        # 3. Required scope
        if self._bundle.required_scope:
            action_scope = set(scope) | {f"{tool}.{op}", tool, op}
            if not action_scope.intersection(self._bundle.required_scope):
                return EmbeddedVerdict(
                    verdict="BLOCK",
                    reason_code="scope_violation",
                    explanation=(
                        f"Action '{tool}.{op}' is not in required scope "
                        f"{self._bundle.required_scope}."
                    ),
                )

        # 4. Custom rules (higher priority value = evaluated first)
        for rule in sorted(
            self._bundle.custom_rules,
            key=lambda r: int(r.get("priority", 0)),
            reverse=True,
        ):
            if self._rule_matches(rule, tool, op, estimated_risk):
                action = str(rule.get("action", "BLOCK")).upper()
                rule_id = rule.get("id", "custom")
                if action in ("BLOCK", "ESCALATE", "ALLOW"):
                    return EmbeddedVerdict(
                        verdict=action,
                        reason_code=f"custom_rule:{rule_id}",
                        explanation=f"Custom rule '{rule_id}' matched — action={action}.",
                    )

        # 5. Global rate limit (actions_per_minute)
        global_cap = self._bundle.rate_limits.get("actions_per_minute")
        if global_cap is not None:
            within, used = self._check_global_rate(int(global_cap))
            if not within:
                return EmbeddedVerdict(
                    verdict="BLOCK",
                    reason_code="rate_limit_exceeded",
                    explanation=(
                        f"Global rate limit of {global_cap} actions/min exceeded "
                        f"({used} actions in last 60s)."
                    ),
                )

        # 6. Per-tool rate limit
        per_tool_caps: Dict[str, int] = self._bundle.rate_limits.get("per_tool", {})
        tool_key = f"{tool}.{op}"
        cap = per_tool_caps.get(tool_key) or per_tool_caps.get(tool)
        if cap is not None:
            within, used = self._check_tool_rate(tool, op, int(cap))
            if not within:
                return EmbeddedVerdict(
                    verdict="BLOCK",
                    reason_code="rate_limit_exceeded",
                    explanation=(
                        f"Rate limit of {cap} actions/min for '{tool_key}' exceeded "
                        f"({used} in last 60s)."
                    ),
                )

        # 7. Default allow
        return EmbeddedVerdict(
            verdict="ALLOW",
            reason_code="policy_pass",
            explanation="Action passes all edge policy checks.",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _rule_matches(
        rule: Dict[str, Any], tool: str, op: str, estimated_risk: str
    ) -> bool:
        """True if all non-None rule conditions match the action."""
        if not rule.get("enabled", True):
            return False
        if rule.get("condition_tool") and rule["condition_tool"] != tool:
            return False
        if rule.get("condition_op") and rule["condition_op"] != op:
            return False
        if rule.get("condition_risk_level") and rule["condition_risk_level"] != estimated_risk:
            return False
        return True

    def _check_global_rate(self, cap: int) -> Tuple[bool, int]:
        """Sliding 60-second global window.  Returns (within_limit, current_count)."""
        now_ns = time.monotonic_ns()
        cutoff_ns = now_ns - 60 * 1_000_000_000
        while self._global_window and self._global_window[0] < cutoff_ns:
            self._global_window.popleft()
        count = len(self._global_window)
        if count >= cap:
            return False, count
        self._global_window.append(now_ns)
        return True, count + 1

    def _check_tool_rate(self, tool: str, op: str, cap: int) -> Tuple[bool, int]:
        """Sliding 60-second per-(tool, op) window."""
        key = (tool, op)
        now_ns = time.monotonic_ns()
        cutoff_ns = now_ns - 60 * 1_000_000_000
        if key not in self._rate_windows:
            self._rate_windows[key] = deque()
        window = self._rate_windows[key]
        while window and window[0] < cutoff_ns:
            window.popleft()
        count = len(window)
        if count >= cap:
            return False, count
        window.append(now_ns)
        return True, count + 1
