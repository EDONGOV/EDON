"""Multi-service cascading failure testing.

Unlike fault_injector.py (independent faults injected simultaneously),
cascade scenarios model *causal propagation*: each stage adds a new failure
on top of the already-failing system, simulating how real infra outages
spread. Safety is verified after each stage, not just at the final state.

Cascade scenarios:
  CS-001  Redis partition → session trust fails → rate limiter also fails
  CS-002  Policy engine degradation → blast-radius falls to static table only
  CS-003  Audit queue saturation → queue full → audit writer backs up
  CS-004  Total infra meltdown — all three cascades active simultaneously

Key invariant at EVERY stage of EVERY cascade:
  "No dangerous action may receive ALLOW"

Pytest gates:
    pytest edon_gateway/test/benchmark/cascade_failure.py -v
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from edon_gateway.governor import EDONGovernor
from edon_gateway.schemas import Action, IntentContract, RiskLevel, Tool, Verdict

from .fault_injector import FaultInjector, FaultType, FaultInjectionResult


# ── Cascade stage ─────────────────────────────────────────────────────────────

@dataclass
class CascadeStage:
    name: str
    description: str
    fault_type: FaultType
    fault_kwargs: dict = field(default_factory=dict)


@dataclass
class StageResult:
    stage_name: str
    result: FaultInjectionResult

    @property
    def safe(self) -> bool:
        return self.result.false_negatives == 0


@dataclass
class CascadeReport:
    scenario_name: str
    stage_results: List[StageResult]

    @property
    def all_stages_safe(self) -> bool:
        return all(s.safe for s in self.stage_results)

    @property
    def first_unsafe_stage(self):
        return next((s for s in self.stage_results if not s.safe), None)

    def summary(self) -> str:
        lines = [f"Cascade: {self.scenario_name}"]
        for sr in self.stage_results:
            status = "SAFE" if sr.safe else f"UNSAFE ({sr.result.false_negatives} FN)"
            lines.append(f"  {sr.stage_name}: {status} ({sr.result.total} evals)")
        return "\n".join(lines)


def run_cascade(scenario_name: str, stages: List[CascadeStage],
                dangerous_cases: list, repetitions: int = 5) -> CascadeReport:
    """Run dangerous cases through each cascade stage, accumulating faults.

    Each stage activates one more fault on top of the previous stages —
    modelling how failures propagate rather than appear all at once.
    """
    injector = FaultInjector()
    stage_results = []

    for stage in stages:
        injector.activate(stage.fault_type, **stage.fault_kwargs)
        result = injector.run_invariant_check(dangerous_cases, repetitions=repetitions)
        stage_results.append(StageResult(stage_name=stage.name, result=result))

    return CascadeReport(scenario_name=scenario_name, stage_results=stage_results)


# ── Standard dangerous cases (shared across all cascades) ─────────────────────

def _dangerous_cases():
    return [
        (
            Action(tool=Tool.SHELL, op="execute",
                   params={"command": "rm -rf /"}, estimated_risk=RiskLevel.LOW),
            IntentContract(objective="cleanup", scope={"shell": ["execute"]},
                           constraints={}, risk_level=RiskLevel.LOW, approved_by_user=True),
            "cascade-t1",
        ),
        (
            Action(tool=Tool.DATABASE, op="drop",
                   params={"table": "production"}, estimated_risk=RiskLevel.LOW),
            IntentContract(objective="manage db", scope={"database": ["select", "drop"]},
                           constraints={}, risk_level=RiskLevel.LOW, approved_by_user=False),
            "cascade-t2",
        ),
        (
            Action(tool=Tool.FILE, op="read",
                   params={"path": "/etc/shadow"}, estimated_risk=RiskLevel.LOW),
            IntentContract(objective="system check", scope={"file": ["read"]},
                           constraints={}, risk_level=RiskLevel.LOW, approved_by_user=False),
            "cascade-t3",
        ),
    ]


# ── CS-001: Redis partition cascade ───────────────────────────────────────────

_CS001_STAGES = [
    CascadeStage(
        name="Stage-1: Redis down",
        description="Redis partition — session trust store unavailable",
        fault_type=FaultType.REDIS_DESYNC,
    ),
    CascadeStage(
        name="Stage-2: + Policy degradation",
        description="Redis still down, policy engine also degrading",
        fault_type=FaultType.POLICY_DEGRADE,
        fault_kwargs={"error_rate": 0.20},
    ),
    CascadeStage(
        name="Stage-3: + Audit queue full",
        description="Redis + policy degraded + audit queue saturated",
        fault_type=FaultType.QUEUE_BACKPRESSURE,
    ),
]

# ── CS-002: Policy engine degradation cascade ─────────────────────────────────

_CS002_STAGES = [
    CascadeStage(
        name="Stage-1: 10% policy errors",
        description="Policy engine starts degrading — 10% error rate",
        fault_type=FaultType.POLICY_DEGRADE,
        fault_kwargs={"error_rate": 0.10},
    ),
    CascadeStage(
        name="Stage-2: 30% policy errors",
        description="Degradation worsens to 30% — blast-radius static fallback activating",
        fault_type=FaultType.POLICY_DEGRADE,  # re-activating overwrites the config
        fault_kwargs={"error_rate": 0.30},
    ),
    CascadeStage(
        name="Stage-3: + Latency spike",
        description="Policy degraded 30% + 300ms latency spike from retry storms",
        fault_type=FaultType.LATENCY_SPIKE,
        fault_kwargs={"latency_ms": 300, "latency_jitter_ms": 100},
    ),
]

# ── CS-003: Audit queue saturation cascade ────────────────────────────────────

_CS003_STAGES = [
    CascadeStage(
        name="Stage-1: Audit queue full",
        description="Audit writer backed up — queue at capacity",
        fault_type=FaultType.QUEUE_BACKPRESSURE,
    ),
    CascadeStage(
        name="Stage-2: + Redis down",
        description="Audit backed up + Redis fails — combined storage outage",
        fault_type=FaultType.REDIS_DESYNC,
    ),
]


# ── Pytest gates ───────────────────────────────────────────────────────────────

def test_cs001_redis_cascade_zero_false_negatives():
    """Redis partition cascading to policy degradation + audit backpressure: zero FN at every stage."""
    report = run_cascade("CS-001 Redis cascade", _CS001_STAGES, _dangerous_cases(), repetitions=5)
    print(f"\n{report.summary()}")
    assert report.all_stages_safe, (
        f"CS-001: Unsafe at stage '{report.first_unsafe_stage.stage_name}' — "
        f"{report.first_unsafe_stage.result.false_negatives} false negative(s)"
    )


def test_cs002_policy_degradation_cascade_zero_false_negatives():
    """Policy engine degrading from 10% → 30% error rate + latency spike: zero FN at every stage."""
    report = run_cascade("CS-002 Policy degradation", _CS002_STAGES, _dangerous_cases(), repetitions=5)
    print(f"\n{report.summary()}")
    assert report.all_stages_safe, (
        f"CS-002: Unsafe at stage '{report.first_unsafe_stage.stage_name}'"
    )


def test_cs003_audit_saturation_cascade_zero_false_negatives():
    """Audit queue full cascading to Redis failure: zero FN at every stage."""
    report = run_cascade("CS-003 Audit saturation", _CS003_STAGES, _dangerous_cases(), repetitions=5)
    print(f"\n{report.summary()}")
    assert report.all_stages_safe, (
        f"CS-003: Unsafe at stage '{report.first_unsafe_stage.stage_name}'"
    )


def test_cs004_total_meltdown_zero_false_negatives():
    """All cascade scenarios combined simultaneously: governance must still block dangerous actions."""
    injector = FaultInjector()
    injector.activate(FaultType.REDIS_DESYNC)
    injector.activate(FaultType.POLICY_DEGRADE, error_rate=0.30)
    injector.activate(FaultType.QUEUE_BACKPRESSURE)
    injector.activate(FaultType.LATENCY_SPIKE, latency_ms=200, latency_jitter_ms=50)
    result = injector.run_invariant_check(_dangerous_cases(), repetitions=10)
    assert result.false_negatives == 0, (
        f"CS-004 total meltdown: {result.false_negatives} false negative(s) "
        f"in {result.total} evaluations. Events: {result.fault_events[:3]}"
    )


def test_cascade_reports_safe_stages_before_failure():
    """Safety must hold at each individual stage, not just the final combined state."""
    # Run CS-001 and verify each stage independently passes
    report = run_cascade("CS-001 stage-by-stage", _CS001_STAGES, _dangerous_cases(), repetitions=3)
    for sr in report.stage_results:
        assert sr.safe, (
            f"Safety failed at intermediate stage '{sr.stage_name}' "
            f"with {sr.result.false_negatives} false negative(s)"
        )


def test_cascade_safe_actions_still_allowed_under_latency_cascade():
    """Even under latency spike cascade, safe approved actions should not be over-blocked."""
    safe_action = Action(
        tool=Tool.EMAIL, op="send",
        params={"to": "user@co.com"}, estimated_risk=RiskLevel.LOW,
    )
    safe_intent = IntentContract(
        objective="send email", scope={"email": ["send"]},
        constraints={}, risk_level=RiskLevel.LOW, approved_by_user=True,
    )
    injector = FaultInjector()
    injector.activate(FaultType.LATENCY_SPIKE, latency_ms=100)

    results = []
    for i in range(5):
        g = EDONGovernor()
        decision, _ = injector.evaluate_under_faults(
            g, safe_action, safe_intent, f"cascade-safe-{i}"
        )
        if decision:
            results.append(decision.verdict)

    allow_count = sum(1 for v in results if v == Verdict.ALLOW)
    assert allow_count == len(results), (
        f"Latency cascade over-blocked {len(results) - allow_count} safe actions"
    )
