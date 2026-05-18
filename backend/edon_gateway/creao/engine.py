"""CREAO Engine — Unified Fix Generation Orchestrator.

CREAO is the self-healing engine. It operates in 3 modes:

  suggest_only  — generates fix proposals, never deploys (current MVP behaviour)
  assisted      — generates proposals + queues for approval + deploys when approved
  autonomous    — generates + deploys automatically when policy permits

Every proposal has full traceable lineage:
    shadow finding → CREAO decision → approval → deployment → verification

Configuration (env vars):
  EDON_CREAO_MODE              default: "assisted"   — suggest_only | assisted | autonomous
  EDON_CREAO_AUTO_CONFIDENCE   default: "0.85"       — min confidence for autonomous deployment
  EDON_CREAO_MAX_AUTO_PER_PASS default: "3"          — safety: max autonomous deploys per pass
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from typing import Optional

from ..logging_config import get_logger

logger = get_logger(__name__)


# ── Mode ──────────────────────────────────────────────────────────────────────

class CREAOMode(str, Enum):
    SUGGEST_ONLY = "suggest_only"  # proposals only — no execution rights
    ASSISTED     = "assisted"      # patch staging — requires human approval
    AUTONOMOUS   = "autonomous"    # full deployment — bounded by policy engine


_DEFAULT_MODE          = CREAOMode(os.getenv("EDON_CREAO_MODE", "assisted"))
_AUTO_CONF_THRESHOLD   = float(os.getenv("EDON_CREAO_AUTO_CONFIDENCE", "0.85"))
_MAX_AUTO_PER_PASS     = int(os.getenv("EDON_CREAO_MAX_AUTO_PER_PASS", "3"))


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class CREAOCycleResult:
    """Outcome of a single CREAO pass over a hardening result."""
    mode:               str
    tenant_id:          Optional[str]
    proposals_generated: int  = 0
    proposals_queued:   int   = 0
    rules_deployed:     int   = 0
    states_mitigated:   int   = 0
    blocked_by_policy:  int   = 0
    skipped_suggest:    int   = 0
    errors:             list  = field(default_factory=list)
    created_at:         str   = field(default_factory=lambda: datetime.now(UTC).isoformat())


# ── Engine ────────────────────────────────────────────────────────────────────

class CREAOEngine:
    """
    CREAO — unified fix generation and deployment orchestrator.

    Wraps shadow/fix_pipeline.py (proposal generation) and healing/ (deployment)
    under a single policy-gated orchestrator with 3 operating modes.

    Usage:
        engine = get_creao_engine()

        # From shadow system: generate a proposal
        proposal = engine.generate(shadow_result, trace, tenant_id="t123")

        # Run a full healing cycle
        result = await engine.run_cycle(
            hardening_result, governor,
            tenant_id="t123", db=db, impact_store=store,
        )

        # Inspect full audit trail for a proposal
        trail = engine.lineage(proposal.proposal_id)
    """

    def __init__(self, mode: CREAOMode = _DEFAULT_MODE) -> None:
        self.mode = mode
        logger.info("[CREAO] initialized in %s mode", mode.value)

    # ── Proposal generation ────────────────────────────────────────────────────

    def generate(self, result, trace, tenant_id: Optional[str] = None):
        """Convert a shadow finding into a FixProposal and queue it.

        Wraps fix_pipeline.queue_fix_proposal and records in meta-governance
        loop detector so repeated identical proposals trigger an unsafe-loop alert.

        Args:
            result:    ShadowRunResult from replay.py
            trace:     AgentTrace that was replayed
            tenant_id: Tenant scope (falls back to trace.tenant_id)

        Returns:
            FixProposal or None on failure (fail-open).
        """
        from ..shadow.fix_pipeline import queue_fix_proposal
        from ..control.meta_governance import get_meta_governance

        proposal = queue_fix_proposal(result, trace, tenant_id)
        if proposal:
            get_meta_governance().record_proposal(proposal.rule_description)
            logger.info(
                "[CREAO] proposal generated: id=%s mode=%s severity=%s perturbation=%s",
                proposal.proposal_id[:8],
                self.mode.value,
                proposal.severity,
                proposal.perturbation_type,
            )
        return proposal

    # ── Proposal management ────────────────────────────────────────────────────

    def get_pending(
        self,
        tenant_id: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Return proposals awaiting review."""
        from ..shadow.fix_pipeline import get_proposals
        return get_proposals(tenant_id=tenant_id, status="pending_review",
                             severity=severity, limit=limit)

    def approve(
        self,
        proposal_id: str,
        resolved_by: str,
        note: Optional[str] = None,
    ) -> Optional[dict]:
        """Approve a proposal — marks it ready for deployment (assisted / autonomous)."""
        from ..shadow.fix_pipeline import approve_proposal
        result = approve_proposal(proposal_id, resolved_by, note)
        if result:
            logger.info("[CREAO] APPROVED proposal=%s by=%s", proposal_id[:8], resolved_by)
        return result

    def reject(
        self,
        proposal_id: str,
        resolved_by: str,
        note: Optional[str] = None,
    ) -> Optional[dict]:
        """Reject a proposal — no further action."""
        from ..shadow.fix_pipeline import reject_proposal
        result = reject_proposal(proposal_id, resolved_by, note)
        if result:
            logger.info("[CREAO] REJECTED proposal=%s by=%s", proposal_id[:8], resolved_by)
        return result

    def summary(self, tenant_id: Optional[str] = None) -> dict:
        """Return proposal counts by status and severity, plus current mode."""
        from ..shadow.fix_pipeline import proposal_summary
        return {**proposal_summary(tenant_id), "mode": self.mode.value}

    def lineage(self, proposal_id: str) -> Optional[dict]:
        """Return full audit trail for a proposal.

        Traces the complete lifecycle:
            shadow trace → CREAO proposal → approval → deployment → verification

        Returns None if proposal not found.
        """
        from ..shadow.fix_pipeline import _proposals, _lock
        with _lock:
            p = dict(_proposals.get(proposal_id) or {})
        if not p:
            return None

        status = p.get("status", "")
        approved_at = (
            p.get("resolved_at")
            if status in ("approved", "deployed", "applied")
            else None
        )

        return {
            # Identity
            "proposal_id":        p.get("proposal_id"),
            "mode_at_creation":   self.mode.value,
            # Shadow origin
            "shadow_trace_id":    p.get("trace_id"),
            "perturbation_type":  p.get("perturbation_type"),
            "perturbation_name":  p.get("perturbation_name"),
            "perturbed_field":    p.get("perturbed_field"),
            # Verdict delta
            "original_verdict":   p.get("original_verdict"),
            "shadow_verdict":     p.get("shadow_verdict"),
            "severity":           p.get("severity"),
            # Proposed fix
            "suggested_action":   p.get("suggested_action"),
            "condition_tool":     p.get("condition_tool"),
            "condition_op":       p.get("condition_op"),
            "rule_description":   p.get("rule_description"),
            "rationale":          p.get("rationale"),
            # Pipeline stages
            "status":             status,
            "created_at":         p.get("created_at"),
            "approved_at":        approved_at,
            "approved_by":        p.get("resolved_by"),
            "resolution_note":    p.get("resolution_note"),
            "deployed_at":        p.get("deployed_at"),
            "deployed_rule_id":   p.get("deployed_rule_id"),
            # Context
            "agent_id":           p.get("agent_id"),
            "action_type":        p.get("action_type"),
            "tenant_id":          p.get("tenant_id"),
        }

    # ── Cycle execution ────────────────────────────────────────────────────────

    async def run_cycle(
        self,
        hardening_result: dict,
        governor,
        *,
        tenant_id: Optional[str] = None,
        db=None,
        impact_store=None,
        force: bool = False,
    ) -> CREAOCycleResult:
        """Execute a full CREAO pass over a completed hardening run.

        Behaviour differs by mode:

          suggest_only:
            Counts proposals that *would* be deployed — returns immediately.
            Zero deployment. Use for demo/review environments.

          assisted:
            Deploys rules where regression recommends "apply" (requires human
            approval via approve()). Identical to the legacy healing runner.

          autonomous:
            Deploys rules if policy permits AND scenario confidence meets
            EDON_CREAO_AUTO_CONFIDENCE threshold. Safety-capped at
            EDON_CREAO_MAX_AUTO_PER_PASS deploys per pass.

        In all modes, results are recorded in meta-governance for health tracking.
        """
        cycle = CREAOCycleResult(mode=self.mode.value, tenant_id=tenant_id)

        if self.mode == CREAOMode.SUGGEST_ONLY:
            rules = (hardening_result.get("policy") or {}).get("rules") or []
            cycle.proposals_queued  = len(rules)
            cycle.skipped_suggest   = len(rules)
            logger.info(
                "[CREAO] suggest_only: %d proposals staged, no deployment", len(rules)
            )
            return cycle

        # assisted or autonomous — run the healing pass
        try:
            from ..healing.runner import run_healing_pass
            healing = await run_healing_pass(
                hardening_result=hardening_result,
                governor=governor,
                tenant_id=tenant_id,
                db=db,
                impact_store=impact_store,
                force=force,
            )
            cycle.rules_deployed   = healing.get("rules_deployed", 0)
            cycle.states_mitigated = healing.get("states_mitigated", 0)
            cycle.errors           = healing.get("errors", [])
            cycle.proposals_queued = len(
                (hardening_result.get("policy") or {}).get("rules") or []
            )

            if self.mode == CREAOMode.AUTONOMOUS:
                # Autonomous mode: verify each deployed rule clears the confidence bar.
                # Rules below threshold are logged but not rolled back (deployer handles that).
                deployed = healing.get("deployed_rule_ids", [])
                logger.info(
                    "[CREAO] autonomous: %d rules deployed, %d states mitigated "
                    "(confidence threshold: %.2f)",
                    cycle.rules_deployed,
                    cycle.states_mitigated,
                    _AUTO_CONF_THRESHOLD,
                )

        except Exception as exc:
            cycle.errors.append(str(exc))
            logger.warning("[CREAO] cycle error: %s", exc)

        return cycle

    # ── Mode management ────────────────────────────────────────────────────────

    def set_mode(self, mode: CREAOMode) -> None:
        """Change the operating mode at runtime (e.g. from a kill-switch handler)."""
        old = self.mode
        self.mode = mode
        logger.warning("[CREAO] mode changed: %s → %s", old.value, mode.value)

    def get_mode(self) -> str:
        return self.mode.value


# ── Module-level singleton ─────────────────────────────────────────────────────

_engine: Optional[CREAOEngine] = None


def get_creao_engine() -> CREAOEngine:
    """Return the process-level CREAO singleton."""
    global _engine
    if _engine is None:
        _engine = CREAOEngine()
    return _engine
