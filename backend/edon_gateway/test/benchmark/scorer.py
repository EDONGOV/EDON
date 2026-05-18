"""Benchmark scoring harness.

Runs ALL_CASES (or a subset) against any GovernanceProtocol implementation
and produces a structured score report with:
  - overall pass rate
  - false-negative rate (dangerous actions incorrectly permitted)
  - false-positive rate (safe actions incorrectly blocked)
  - latency percentiles (p50, p95, p99)
  - per-category breakdown
  - per-severity breakdown
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .protocol import BenchmarkCase, GovernanceInput, GovernanceOutput, GovernanceProtocol


@dataclass
class CaseResult:
    case: BenchmarkCase
    output: GovernanceOutput
    passed: bool
    failure_reason: Optional[str] = None


@dataclass
class BenchmarkReport:
    total: int
    passed: int
    failed: int

    # Safety-critical: dangerous action incorrectly permitted (verdict=ALLOW when must_not_be ALLOW)
    false_negatives: int
    # Precision: safe action incorrectly blocked
    false_positives: int

    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    latency_mean_ms: float

    by_category: Dict[str, Dict[str, Any]]  # category -> {total, passed, failed}
    by_severity: Dict[str, Dict[str, Any]]  # severity -> {total, passed, failed}

    failures: List[CaseResult]
    results: List[CaseResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def false_negative_rate(self) -> float:
        """Fraction of must-not-ALLOW cases that incorrectly returned ALLOW."""
        must_not_allow = [r for r in self.results
                         if r.case.must_not_be and "ALLOW" in r.case.must_not_be]
        if not must_not_allow:
            return 0.0
        fn = sum(1 for r in must_not_allow if not r.passed)
        return fn / len(must_not_allow)

    @property
    def false_positive_rate(self) -> float:
        """Fraction of is_safe_action cases that were incorrectly blocked."""
        safe = [r for r in self.results if r.case.is_safe_action]
        if not safe:
            return 0.0
        fp = sum(1 for r in safe if not r.passed)
        return fp / len(safe)

    def summary(self) -> str:
        lines = [
            "══════════════════════════════════════════",
            "  EDON Governance Benchmark Report",
            "══════════════════════════════════════════",
            f"  Pass rate          : {self.pass_rate:.1%}  ({self.passed}/{self.total})",
            f"  False-negative rate: {self.false_negative_rate:.1%}  (dangerous actions allowed)",
            f"  False-positive rate: {self.false_positive_rate:.1%}  (safe actions blocked)",
            f"  Latency p50/p95/p99: {self.latency_p50_ms:.1f} / {self.latency_p95_ms:.1f} / {self.latency_p99_ms:.1f} ms",
            "",
            "  By category:",
        ]
        for cat, stats in sorted(self.by_category.items()):
            rate = stats["passed"] / stats["total"] if stats["total"] else 0
            lines.append(f"    {cat:<20} {rate:.0%}  ({stats['passed']}/{stats['total']})")
        lines.append("")
        lines.append("  By severity:")
        for sev in ("critical", "high", "medium"):
            if sev not in self.by_severity:
                continue
            stats = self.by_severity[sev]
            rate = stats["passed"] / stats["total"] if stats["total"] else 0
            lines.append(f"    {sev:<20} {rate:.0%}  ({stats['passed']}/{stats['total']})")
        if self.failures:
            lines += ["", "  Failures:"]
            for r in self.failures:
                lines.append(f"    [{r.case.id}] {r.case.description}")
                lines.append(f"           got={r.output.verdict}  {r.failure_reason}")
        lines.append("══════════════════════════════════════════")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pass_rate": round(self.pass_rate, 4),
            "false_negative_rate": round(self.false_negative_rate, 4),
            "false_positive_rate": round(self.false_positive_rate, 4),
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "false_negatives": self.false_negatives,
            "false_positives": self.false_positives,
            "latency": {
                "p50_ms": round(self.latency_p50_ms, 2),
                "p95_ms": round(self.latency_p95_ms, 2),
                "p99_ms": round(self.latency_p99_ms, 2),
                "mean_ms": round(self.latency_mean_ms, 2),
            },
            "by_category": self.by_category,
            "by_severity": self.by_severity,
            "failures": [
                {
                    "id": r.case.id,
                    "description": r.case.description,
                    "severity": r.case.severity,
                    "verdict": r.output.verdict,
                    "reason": r.failure_reason,
                    "latency_ms": round(r.output.latency_ms, 2),
                }
                for r in self.failures
            ],
        }


def _percentile(data: List[float], p: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = (p / 100) * (len(sorted_data) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(sorted_data) - 1)
    return sorted_data[lo] + (sorted_data[hi] - sorted_data[lo]) * (idx - lo)


def run_benchmark(
    system: GovernanceProtocol,
    cases: List[BenchmarkCase],
    warm_up: int = 3,
) -> BenchmarkReport:
    """Run all cases against *system* and return a scored BenchmarkReport.

    Args:
        system: Any GovernanceProtocol implementation.
        cases:  List of BenchmarkCase to run.
        warm_up: Number of warm-up calls before timing starts.
    """
    # Warm-up: prime caches without recording latency
    if cases and warm_up:
        for c in cases[:warm_up]:
            try:
                system.evaluate(c.input)
            except Exception:
                pass

    results: List[CaseResult] = []
    latencies: List[float] = []

    for case in cases:
        try:
            t0 = time.perf_counter()
            output = system.evaluate(case.input)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            output.latency_ms = elapsed_ms
        except Exception as exc:
            output = GovernanceOutput(
                verdict="ERROR",
                reason=str(exc),
                latency_ms=0.0,
            )

        passed = case.check(output)
        failure_reason = None
        if not passed:
            if case.must_be:
                failure_reason = f"expected={case.must_be}"
            elif case.must_be_one_of:
                failure_reason = f"expected one of {case.must_be_one_of}"
            elif case.must_not_be:
                failure_reason = f"must not be {case.must_not_be}"

        results.append(CaseResult(case=case, output=output, passed=passed,
                                  failure_reason=failure_reason))
        latencies.append(output.latency_ms)

    passed_count = sum(1 for r in results if r.passed)
    failures = [r for r in results if not r.passed]

    # False negatives: dangerous action got ALLOW when it must not be ALLOW
    false_negatives = sum(
        1 for r in results
        if not r.passed
        and r.case.must_not_be
        and "ALLOW" in r.case.must_not_be
        and r.output.verdict == "ALLOW"
    )
    # False positives: safe action got blocked when it must be ALLOW
    false_positives = sum(
        1 for r in results
        if not r.passed and r.case.is_safe_action
    )

    # Per-category breakdown
    by_category: Dict[str, Dict[str, Any]] = {}
    for r in results:
        cat = r.case.category
        if cat not in by_category:
            by_category[cat] = {"total": 0, "passed": 0, "failed": 0}
        by_category[cat]["total"] += 1
        if r.passed:
            by_category[cat]["passed"] += 1
        else:
            by_category[cat]["failed"] += 1

    # Per-severity breakdown
    by_severity: Dict[str, Dict[str, Any]] = {}
    for r in results:
        sev = r.case.severity
        if sev not in by_severity:
            by_severity[sev] = {"total": 0, "passed": 0, "failed": 0}
        by_severity[sev]["total"] += 1
        if r.passed:
            by_severity[sev]["passed"] += 1
        else:
            by_severity[sev]["failed"] += 1

    return BenchmarkReport(
        total=len(results),
        passed=passed_count,
        failed=len(failures),
        false_negatives=false_negatives,
        false_positives=false_positives,
        latency_p50_ms=_percentile(latencies, 50),
        latency_p95_ms=_percentile(latencies, 95),
        latency_p99_ms=_percentile(latencies, 99),
        latency_mean_ms=statistics.mean(latencies) if latencies else 0.0,
        by_category=by_category,
        by_severity=by_severity,
        failures=failures,
        results=results,
    )
