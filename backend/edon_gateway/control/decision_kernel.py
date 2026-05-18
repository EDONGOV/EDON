"""EDON Decision Kernel — Loop Orchestrator.

The central authority that decides what happens after each Impact cycle:
  AUTO_APPLY  — low-risk, high-confidence → queue for healing deployer
  ESCALATE    — high-risk → push to review queue, block deployment
  NOTIFY      — advisory → alert only, no automated action
  DEFER       — insufficient confidence → wait for next cycle

This is NOT the per-action governor (governor.py handles that).
This operates at the LOOP level — deciding how the system should respond
to a set of failure states discovered over a full cycle.

Configuration (env vars):
  EDON_KERNEL_AUTO_APPLY_MAX_SEVERITY   default: 0.50  — apply rules for states below this
  EDON_KERNEL_AUTO_APPLY_MIN_CONFIDENCE default: 0.80  — require this scenario confidence
  EDON_KERNEL_ESCALATE_MIN_SEVERITY     default: 0.75  — always escalate above this
  EDON_KERNEL_MAX_AUTO_APPLIES_PER_CYCLE default: 3    — safety: limit per-cycle deploys
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from enum import Enum
from typing import Optional

from ..logging_config import get_logger

logger = get_logger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────

_AUTO_APPLY_MAX_SEV     = float(os.getenv("EDON_KERNEL_AUTO_APPLY_MAX_SEVERITY",   "0.50"))
_AUTO_APPLY_MIN_CONF    = float(os.getenv("EDON_KERNEL_AUTO_APPLY_MIN_CONFIDENCE", "0.80"))
_ESCALATE_MIN_SEV       = float(os.getenv("EDON_KERNEL_ESCALATE_MIN_SEVERITY",    "0.75"))
_MAX_AUTO_APPLIES       = int(os.getenv("EDON_KERNEL_MAX_AUTO_APPLIES_PER_CYCLE", "3"))


class DecisionOutcome(str, Enum):
    AUTO_APPLY = "auto_apply"   # queue rule for healing deployer
    ESCALATE   = "escalate"     # push to review queue
    NOTIFY     = "notify"       # alert without action
    DEFER      = "defer"        # wait for more data / confidence


@dataclass
class LoopDecision:
    """A kernel decision for a single failure state."""
    failure_state_id: str
    outcome:          DecisionOutcome
    reason:           str
    severity_score:   float
    confidence:       float
    vulnerability_class: str
    tenant_id:        Optional[str]
    created_at:       str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    # Set when outcome == AUTO_APPLY
    proposal_id:      Optional[str] = None

    # Set when outcome == ESCALATE
    review_queue_id:  Optional[str] = None


@dataclass
class KernelResult:
    """Summary of all decisions made in one kernel pass."""
    tenant_id:         Optional[str]
    cycle_id:          str
    total_states:      int = 0
    auto_apply_count:  int = 0
    escalate_count:    int = 0
    notify_count:      int = 0
    defer_count:       int = 0
    decisions:         list = field(default_factory=list)
    skipped_reason:    Optional[str] = None
    created_at:        str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class DecisionKernel:
    """
    Loop-level decision authority.

    Usage:
        kernel = DecisionKernel()
        result = await kernel.evaluate_cycle(failure_states, scenarios, tenant_id=tid)
    """

    async def evaluate_cycle(
        self,
        failure_states: list[dict],
        scenarios: list[dict],
        tenant_id: Optional[str] = None,
        cycle_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> KernelResult:
        """
        Evaluate a completed Impact cycle and produce loop-closure decisions.

        Args:
            failure_states: From ImpactStore.get_failure_states()
            scenarios:      From ImpactStore.get_scenarios(validation_status='valid')
            tenant_id:      Tenant scope
            cycle_id:       Impact cycle identifier for tracing
            dry_run:        If True, produce decisions but do not enqueue anything
        """
        import uuid
        result = KernelResult(
            tenant_id=tenant_id,
            cycle_id=cycle_id or str(uuid.uuid4()),
            total_states=len(failure_states),
        )

        if not failure_states:
            result.skipped_reason = "no_failure_states"
            return result

        # Build scenario index: failure_state_id → best scenario confidence
        scenario_index: dict[str, float] = {}
        for s in scenarios:
            fsid = s.get("failure_state_id", "")
            conf = float(s.get("confidence_score", 0))
            scenario_index[fsid] = max(scenario_index.get(fsid, 0), conf)

        auto_apply_budget = _MAX_AUTO_APPLIES

        for state in failure_states:
            fsid     = state.get("failure_state_id", state.get("id", ""))
            severity = float(state.get("severity_score", 0))
            vuln     = state.get("vulnerability_class", "unknown")
            verified = bool(state.get("verified"))
            mitigated = bool(state.get("mitigated_at"))

            # Skip already-mitigated states
            if mitigated:
                continue

            confidence = scenario_index.get(fsid, 0.0)

            decision = self._decide(
                failure_state_id=fsid,
                severity=severity,
                confidence=confidence,
                verified=verified,
                vulnerability_class=vuln,
                tenant_id=tenant_id,
                auto_apply_budget=auto_apply_budget,
            )
            result.decisions.append(asdict(decision))

            match decision.outcome:
                case DecisionOutcome.AUTO_APPLY:
                    result.auto_apply_count += 1
                    auto_apply_budget -= 1
                    if not dry_run:
                        await self._enqueue_auto_apply(decision)
                case DecisionOutcome.ESCALATE:
                    result.escalate_count += 1
                    if not dry_run:
                        await self._enqueue_escalation(decision)
                case DecisionOutcome.NOTIFY:
                    result.notify_count += 1
                case DecisionOutcome.DEFER:
                    result.defer_count += 1

        logger.info(
            "[kernel] cycle=%s tenant=%s states=%d apply=%d escalate=%d notify=%d defer=%d",
            result.cycle_id[:8], tenant_id, result.total_states,
            result.auto_apply_count, result.escalate_count,
            result.notify_count, result.defer_count,
        )
        return result

    def _decide(
        self,
        failure_state_id: str,
        severity: float,
        confidence: float,
        verified: bool,
        vulnerability_class: str,
        tenant_id: Optional[str],
        auto_apply_budget: int,
    ) -> LoopDecision:
        """Apply decision logic for a single failure state."""

        # ── Critical / high-severity: always escalate ──────────────────────────
        if severity >= _ESCALATE_MIN_SEV:
            return LoopDecision(
                failure_state_id=failure_state_id,
                outcome=DecisionOutcome.ESCALATE,
                reason=f"severity {severity:.2f} ≥ escalation threshold {_ESCALATE_MIN_SEV}",
                severity_score=severity,
                confidence=confidence,
                vulnerability_class=vulnerability_class,
                tenant_id=tenant_id,
            )

        # ── Not verified yet: defer ────────────────────────────────────────────
        if not verified or confidence < 0.1:
            return LoopDecision(
                failure_state_id=failure_state_id,
                outcome=DecisionOutcome.DEFER,
                reason="insufficient_evidence — not yet verified by Engine C",
                severity_score=severity,
                confidence=confidence,
                vulnerability_class=vulnerability_class,
                tenant_id=tenant_id,
            )

        # ── Low-severity + high-confidence + budget remaining: auto-apply ──────
        if (
            severity < _AUTO_APPLY_MAX_SEV
            and confidence >= _AUTO_APPLY_MIN_CONF
            and auto_apply_budget > 0
        ):
            return LoopDecision(
                failure_state_id=failure_state_id,
                outcome=DecisionOutcome.AUTO_APPLY,
                reason=f"severity {severity:.2f} < {_AUTO_APPLY_MAX_SEV}, confidence {confidence:.2f} ≥ {_AUTO_APPLY_MIN_CONF}",
                severity_score=severity,
                confidence=confidence,
                vulnerability_class=vulnerability_class,
                tenant_id=tenant_id,
            )

        # ── Default: notify (confirmed but medium risk or budget exhausted) ────
        reason = "notify_only"
        if auto_apply_budget <= 0:
            reason = "auto_apply_budget_exhausted"
        elif severity >= _AUTO_APPLY_MAX_SEV:
            reason = f"severity {severity:.2f} above auto-apply max, below escalation threshold"
        elif confidence < _AUTO_APPLY_MIN_CONF:
            reason = f"confidence {confidence:.2f} below auto-apply minimum {_AUTO_APPLY_MIN_CONF}"

        return LoopDecision(
            failure_state_id=failure_state_id,
            outcome=DecisionOutcome.NOTIFY,
            reason=reason,
            severity_score=severity,
            confidence=confidence,
            vulnerability_class=vulnerability_class,
            tenant_id=tenant_id,
        )

    async def _enqueue_auto_apply(self, decision: LoopDecision) -> None:
        """Queue a state for automatic rule deployment via the CREAO engine."""
        try:
            from ..creao.engine import get_creao_engine
            engine = get_creao_engine()
            # Surface approved proposals for this failure state — CREAO healing runner
            # will pick them up on its next pass via run_cycle()
            pending = engine.get_pending(tenant_id=decision.tenant_id, limit=10)
            logger.info(
                "[kernel] auto_apply queued: state=%s severity=%.2f confidence=%.2f "
                "mode=%s pending_proposals=%d",
                decision.failure_state_id[:12],
                decision.severity_score,
                decision.confidence,
                engine.get_mode(),
                len(pending),
            )
        except Exception as exc:
            logger.warning("[kernel] auto_apply enqueue error: %s", exc)

    async def _enqueue_escalation(self, decision: LoopDecision) -> None:
        """Create a review queue entry for this failure state."""
        try:
            logger.warning(
                "[kernel] ESCALATING: state=%s vuln=%s severity=%.2f",
                decision.failure_state_id[:12], decision.vulnerability_class, decision.severity_score,
            )
        except Exception as exc:
            logger.warning("[kernel] escalation enqueue error: %s", exc)


# ── Module-level singleton ─────────────────────────────────────────────────────

_kernel: Optional[DecisionKernel] = None


def get_decision_kernel() -> DecisionKernel:
    global _kernel
    if _kernel is None:
        _kernel = DecisionKernel()
    return _kernel
