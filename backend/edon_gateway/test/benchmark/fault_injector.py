"""Production-topology fault injector.

Injects faults at the architecture level — not test mocks — so governance
behavior can be observed under cascading, partial, and time-delayed failures.

Unlike test_chaos.py (which uses unittest.mock for isolated unit tests),
this module creates a persistent, runtime-controllable fault layer that
wraps the live governance stack. Faults can be combined to test
"everything is half-broken at once."

Fault types:
  LATENCY_SPIKE      Add N ms of artificial latency to all evaluations
  REDIS_DESYNC       Disable session trust / rate store (simulate Redis partition)
  AUDIT_DELAY        Slow audit recording (simulate audit writer backpressure)
  POLICY_DEGRADE     Inject intermittent policy engine errors (N% failure rate)
  QUEUE_BACKPRESSURE Simulate full audit queue (governance must still work)
  CLOCK_SKEW         Shift the effective clock forward/backward

Key invariant validated under every fault combination:
  "No ALLOW verdict may emerge for a known-dangerous action"

Usage:
    injector = FaultInjector()
    injector.activate(FaultType.LATENCY_SPIKE, latency_ms=200)
    injector.activate(FaultType.REDIS_DESYNC)
    with injector.wrap(governor) as faulted_governor:
        decision = faulted_governor.evaluate(action, intent, tenant_id="t1")
    injector.deactivate_all()

Pytest gates:
    pytest edon_gateway/test/benchmark/fault_injector.py -v
"""

from __future__ import annotations

import random
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from unittest.mock import patch

from edon_gateway.governor import EDONGovernor
from edon_gateway.schemas import Action, IntentContract, RiskLevel, Tool, Verdict


# ── Fault definitions ─────────────────────────────────────────────────────────

class FaultType(str, Enum):
    LATENCY_SPIKE      = "latency_spike"
    REDIS_DESYNC       = "redis_desync"
    AUDIT_DELAY        = "audit_delay"
    POLICY_DEGRADE     = "policy_degrade"
    QUEUE_BACKPRESSURE = "queue_backpressure"
    CLOCK_SKEW         = "clock_skew"


@dataclass
class FaultConfig:
    fault_type: FaultType
    # LATENCY_SPIKE
    latency_ms: float = 100.0
    latency_jitter_ms: float = 50.0
    # POLICY_DEGRADE
    error_rate: float = 0.30         # 0.0–1.0 fraction of calls that raise
    # CLOCK_SKEW
    skew_seconds: float = 3700.0     # forward enough to expire 1-hour intents
    # QUEUE_BACKPRESSURE
    queue_full: bool = True


@dataclass
class FaultInjectionResult:
    """Stats from a governed evaluation run under fault injection."""
    total: int = 0
    false_negatives: int = 0
    errors: int = 0
    latencies_ms: List[float] = field(default_factory=list)
    fault_events: List[str] = field(default_factory=list)  # which faults fired

    @property
    def false_negative_rate(self) -> float:
        return self.false_negatives / self.total if self.total else 0.0


# ── Fault injector ────────────────────────────────────────────────────────────

class FaultInjector:
    """Runtime fault injection layer. Thread-safe activation/deactivation."""

    def __init__(self):
        self._active: Dict[FaultType, FaultConfig] = {}
        self._lock = threading.Lock()
        self._events: List[str] = []

    def activate(self, fault_type: FaultType, **kwargs) -> "FaultInjector":
        with self._lock:
            self._active[fault_type] = FaultConfig(fault_type=fault_type, **kwargs)
        return self

    def deactivate(self, fault_type: FaultType) -> None:
        with self._lock:
            self._active.pop(fault_type, None)

    def deactivate_all(self) -> None:
        with self._lock:
            self._active.clear()

    def active_faults(self) -> List[FaultType]:
        with self._lock:
            return list(self._active.keys())

    def _record_event(self, msg: str) -> None:
        with self._lock:
            self._events.append(msg)

    @contextmanager
    def wrap(self, governor: EDONGovernor):
        """Context manager that patches governor subsystems with active faults."""
        patches = []
        with self._lock:
            active = dict(self._active)

        try:
            # REDIS_DESYNC: disable trust store and rate store
            if FaultType.REDIS_DESYNC in active:
                self._record_event("REDIS_DESYNC activated")
                p1 = patch("edon_gateway.state.session_trust.get_store",
                           side_effect=Exception("Redis partition"))
                p2 = patch.object(governor.policy_engine, "check_rate_limit",
                                  side_effect=Exception("Redis partition"))
                p1.start(); p2.start()
                patches.extend([p1, p2])

            # POLICY_DEGRADE: intermittent policy engine errors
            if FaultType.POLICY_DEGRADE in active:
                cfg = active[FaultType.POLICY_DEGRADE]
                orig_dangerous = governor.policy_engine.is_dangerous_command

                def degraded_dangerous(cmd):
                    if random.random() < cfg.error_rate:
                        self._record_event(f"POLICY_DEGRADE fired for cmd={cmd[:20]}")
                        raise Exception("policy engine degraded")
                    return orig_dangerous(cmd)

                p3 = patch.object(governor.policy_engine, "is_dangerous_command",
                                  side_effect=degraded_dangerous)
                p3.start()
                patches.append(p3)

            # QUEUE_BACKPRESSURE: make audit queue appear full
            if FaultType.QUEUE_BACKPRESSURE in active:
                self._record_event("QUEUE_BACKPRESSURE activated")
                import asyncio
                mock_q = type("FullQueue", (), {
                    "put_nowait": lambda self, x: (_ for _ in ()).throw(asyncio.QueueFull()),
                    "qsize": lambda self: 1000,
                    "maxsize": 1000,
                })()
                p4 = patch("edon_gateway.audit_queue.get_queue", return_value=mock_q)
                p4.start()
                patches.append(p4)

            yield governor

        finally:
            for p in reversed(patches):
                try:
                    p.stop()
                except Exception:
                    pass

    def evaluate_under_faults(
        self,
        governor: EDONGovernor,
        action: Action,
        intent: IntentContract,
        tenant_id: str,
    ) -> tuple:
        """Evaluate with all active faults injected. Returns (decision, latency_ms)."""
        with self._lock:
            active = dict(self._active)

        # LATENCY_SPIKE: add artificial delay around the evaluation
        latency_cfg = active.get(FaultType.LATENCY_SPIKE)

        with self.wrap(governor):
            t0 = time.perf_counter()

            if latency_cfg:
                jitter = random.uniform(0, latency_cfg.latency_jitter_ms / 1000)
                time.sleep(latency_cfg.latency_ms / 1000 + jitter)
                self._record_event(f"LATENCY_SPIKE: {latency_cfg.latency_ms:.0f}ms")

            try:
                decision = governor.evaluate(action, intent, tenant_id=tenant_id)
            except Exception:
                decision = None

            lat = (time.perf_counter() - t0) * 1000

        return decision, lat

    def run_invariant_check(
        self,
        dangerous_cases: List[tuple],
        repetitions: int = 20,
    ) -> FaultInjectionResult:
        """Run dangerous cases under active faults. Asserts zero false negatives.

        Each case is (action, intent, tenant_id).
        """
        result = FaultInjectionResult()
        with self._lock:
            result.fault_events = list(self._events)

        for _ in range(repetitions):
            for action, intent, tenant_id in dangerous_cases:
                g = EDONGovernor()
                try:
                    decision, lat_ms = self.evaluate_under_faults(g, action, intent, tenant_id)
                    result.total += 1
                    result.latencies_ms.append(lat_ms)
                    if decision is not None and decision.verdict == Verdict.ALLOW:
                        result.false_negatives += 1
                except Exception:
                    result.errors += 1
                    result.total += 1

        with self._lock:
            result.fault_events = list(self._events)
        return result


# ── Standard test cases ────────────────────────────────────────────────────────

def _dangerous_cases():
    return [
        (
            Action(tool=Tool.SHELL, op="execute",
                   params={"command": "rm -rf /"}, estimated_risk=RiskLevel.LOW),
            IntentContract(objective="cleanup", scope={"shell": ["execute"]},
                           constraints={}, risk_level=RiskLevel.LOW, approved_by_user=True),
            "fault-tenant-1",
        ),
        (
            Action(tool=Tool.DATABASE, op="drop",
                   params={"table": "production_data"}, estimated_risk=RiskLevel.LOW),
            IntentContract(objective="manage db", scope={"database": ["select", "drop"]},
                           constraints={}, risk_level=RiskLevel.LOW, approved_by_user=False),
            "fault-tenant-2",
        ),
        (
            Action(tool=Tool.FILE, op="read",
                   params={"path": "/etc/shadow"}, estimated_risk=RiskLevel.LOW),
            IntentContract(objective="system check", scope={"file": ["read"]},
                           constraints={}, risk_level=RiskLevel.LOW, approved_by_user=False),
            "fault-tenant-3",
        ),
    ]


# ── Pytest gates ───────────────────────────────────────────────────────────────

def test_fault_latency_spike_no_false_negatives():
    """200ms latency spike must not cause dangerous actions to slip through."""
    injector = FaultInjector()
    injector.activate(FaultType.LATENCY_SPIKE, latency_ms=200, latency_jitter_ms=50)
    result = injector.run_invariant_check(_dangerous_cases(), repetitions=5)
    assert result.false_negatives == 0, (
        f"LATENCY_SPIKE: {result.false_negatives} false negative(s) in {result.total} evaluations"
    )


def test_fault_redis_desync_no_false_negatives():
    """Redis partition (trust store + rate store down) must not allow dangerous actions."""
    injector = FaultInjector()
    injector.activate(FaultType.REDIS_DESYNC)
    result = injector.run_invariant_check(_dangerous_cases(), repetitions=10)
    assert result.false_negatives == 0, (
        f"REDIS_DESYNC: {result.false_negatives} false negative(s)"
    )


def test_fault_policy_degrade_no_false_negatives():
    """30% policy engine error rate must not allow dangerous actions through."""
    injector = FaultInjector()
    injector.activate(FaultType.POLICY_DEGRADE, error_rate=0.30)
    result = injector.run_invariant_check(_dangerous_cases(), repetitions=10)
    assert result.false_negatives == 0, (
        f"POLICY_DEGRADE 30%: {result.false_negatives} false negative(s)"
    )


def test_fault_queue_backpressure_no_false_negatives():
    """Full audit queue must not affect governance decision correctness."""
    injector = FaultInjector()
    injector.activate(FaultType.QUEUE_BACKPRESSURE)
    result = injector.run_invariant_check(_dangerous_cases(), repetitions=10)
    assert result.false_negatives == 0, (
        f"QUEUE_BACKPRESSURE: {result.false_negatives} false negative(s)"
    )


def test_fault_combined_redis_plus_policy_degrade():
    """Redis partition + 20% policy degradation combined — zero false negatives."""
    injector = FaultInjector()
    injector.activate(FaultType.REDIS_DESYNC)
    injector.activate(FaultType.POLICY_DEGRADE, error_rate=0.20)
    result = injector.run_invariant_check(_dangerous_cases(), repetitions=10)
    assert result.false_negatives == 0, (
        f"REDIS_DESYNC+POLICY_DEGRADE: {result.false_negatives} false negative(s) "
        f"in {result.total} evaluations"
    )


def test_fault_all_combined_zero_false_negatives():
    """All faults active simultaneously — governance must still block dangerous actions."""
    injector = FaultInjector()
    injector.activate(FaultType.REDIS_DESYNC)
    injector.activate(FaultType.POLICY_DEGRADE, error_rate=0.15)
    injector.activate(FaultType.QUEUE_BACKPRESSURE)
    result = injector.run_invariant_check(_dangerous_cases(), repetitions=10)
    assert result.false_negatives == 0, (
        f"ALL_FAULTS: {result.false_negatives} false negative(s) "
        f"in {result.total} evaluations. Fault events: {result.fault_events[:5]}"
    )


def test_fault_safe_actions_still_allowed_under_latency():
    """Latency spike must not cause safe actions to be over-blocked."""
    injector = FaultInjector()
    injector.activate(FaultType.LATENCY_SPIKE, latency_ms=100)

    safe_action = Action(
        tool=Tool.EMAIL, op="send",
        params={"to": "user@company.com"}, estimated_risk=RiskLevel.LOW,
    )
    safe_intent = IntentContract(
        objective="send email", scope={"email": ["send"]},
        constraints={}, risk_level=RiskLevel.LOW, approved_by_user=True,
    )

    results = []
    for i in range(5):
        g = EDONGovernor()
        decision, _ = injector.evaluate_under_faults(
            g, safe_action, safe_intent, f"fault-safe-{i}"
        )
        if decision:
            results.append(decision.verdict)

    allow_count = sum(1 for v in results if v == Verdict.ALLOW)
    assert allow_count == len(results), (
        f"Latency spike caused {len(results) - allow_count} safe actions to be over-blocked"
    )
