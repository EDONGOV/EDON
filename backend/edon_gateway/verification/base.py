"""Core types for the Independent Observation Layer.

Epistemic separation:
  - Agent claims   → source_type="agent_claim" → shapes risk estimation only
  - Observations   → source_type="observation" → updates verification_confidence + trust

VerificationResult is the single system boundary. Nothing downstream
(trust, learning, adaptation) receives agent-controlled input directly.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class VerifierStatus(str, Enum):
    OK        = "ok"
    DEGRADED  = "degraded"   # returned result, but with reduced confidence
    STALE     = "stale"      # result may be from cache / eventual consistency lag
    FAILED    = "failed"     # no result returned; treat as absence-of-confirmation
    POISONED  = "poisoned"   # results internally consistent but likely systematically wrong
                             # (detectable only via cross-source disagreement)


class ResolutionType(str, Enum):
    IMMEDIATE = "immediate"   # truth available now (API receipt, synchronous check)
    EVENTUAL  = "eventual"    # truth arrives later (inbox delivery, DB propagation)
    MANUAL    = "manual"      # human confirmation required


@dataclass
class SourceResult:
    """Result from a single verification source."""
    verifier_id: str
    verified: bool
    confidence: float          # 0.0–1.0 as reported by this source
    status: VerifierStatus
    latency_ms: int = 0
    raw: Optional[dict] = None


@dataclass
class VerificationResult:
    """Aggregated output of the Observation Layer.

    This is the only value that crosses the system boundary into the trust engine.
    Agent-provided data NEVER appears here as verification_confidence.
    """
    # Aggregated confidence: weighted mean of source confidences by verifier_trust
    confidence: float

    # Variance across source confidences — separate from vc, used for system health
    disagreement_score: float

    # Overall verdict
    verified: bool
    status: VerifierStatus

    # Resolution pathway
    resolution_type: ResolutionType
    deferred: bool              # True → schedule T+1h/T+24h/T+7d check; no immediate trust update
    deferred_window: str        # "1h" | "24h" | "7d" — first checkpoint
    max_wait_hours: int         # TTL: after this, treat unresolved as STALE → negative signal

    # Provenance
    source_type: str            # "observation" | "agent_claim"
    sources: list[str]          # verifier IDs that ran successfully
    disagreements: list[str]    # verifier IDs whose confidence < 0.5 when majority said verified

    # For cross-source POISONED detection
    source_results: list[SourceResult] = field(default_factory=list)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @classmethod
    def agent_claim(cls, outcome: str) -> "VerificationResult":
        """Produce a result that marks agent self-report correctly.

        source_type="agent_claim" → trust engine treats this as prior-shaping only,
        never as evidence. confidence=0.0 to prevent any trust gain.
        """
        return cls(
            confidence=0.0,
            disagreement_score=0.0,
            verified=False,
            status=VerifierStatus.FAILED,
            resolution_type=ResolutionType.MANUAL,
            deferred=False,
            deferred_window="",
            max_wait_hours=0,
            source_type="agent_claim",
            sources=[],
            disagreements=[],
        )

    @classmethod
    def no_verifier(cls) -> "VerificationResult":
        """No verifier registered for this action type.

        Returns low confidence (not zero — the action may still be legitimate).
        Trust engine will treat this as weak partial evidence.
        """
        return cls(
            confidence=0.20,
            disagreement_score=0.0,
            verified=False,
            status=VerifierStatus.DEGRADED,
            resolution_type=ResolutionType.MANUAL,
            deferred=False,
            deferred_window="",
            max_wait_hours=0,
            source_type="observation",
            sources=[],
            disagreements=[],
        )

    @property
    def is_observation(self) -> bool:
        return self.source_type == "observation"

    @property
    def should_penalize(self) -> bool:
        """True when result warrants a trust reduction rather than neutral."""
        return self.status in (VerifierStatus.FAILED, VerifierStatus.POISONED)

    def to_dict(self) -> dict:
        return {
            "confidence":         self.confidence,
            "disagreement_score": self.disagreement_score,
            "verified":           self.verified,
            "status":             self.status.value,
            "resolution_type":    self.resolution_type.value,
            "deferred":           self.deferred,
            "deferred_window":    self.deferred_window,
            "max_wait_hours":     self.max_wait_hours,
            "source_type":        self.source_type,
            "sources":            self.sources,
            "disagreements":      self.disagreements,
        }


# ── Verifier ABC ───────────────────────────────────────────────────────────────

class Verifier(ABC):
    """Base class for all independent verification sources.

    Implementations must be:
    - Agent-independent: cannot receive or rely on agent-provided data as proof
    - Fault-tolerant: must return a VerifierStatus even on error
    - Tenant-aware: must scope to tenant_id

    Fix 3 — verifier diversity:
    upstream_source must be unique per (tenant_id, action_type) when registering
    in PARALLEL. Two verifiers sharing the same upstream_source do not provide
    independent evidence — the registry rejects duplicate sources at registration.

    Set upstream_source to the domain/service your verify() method queries,
    e.g. "sendgrid_api", "postgres_db", "stripe_api".
    """

    verifier_id:     str   = "base"
    default_trust:   float = 0.70   # prior trust for this verifier type
    upstream_source: str   = "default"  # unique source identifier for diversity check

    @abstractmethod
    def verify(
        self,
        tenant_id: str,
        action_type: str,
        result_payload: Optional[dict],
    ) -> SourceResult:
        """Run verification. Must never raise — return FAILED status on error."""
        ...


class NullVerifier(Verifier):
    """Sentinel: no verifier registered for this action type.

    Does NOT return a SourceResult — it signals the registry to route
    this outcome to pending_outcomes only (no trust update).

    Core invariant: trust must only move on externally grounded evidence.
    An absent verifier = absent evidence = trust freeze, not DEGRADED update.
    """
    verifier_id = "null"
    default_trust = 0.10
    is_null = True   # registry checks this flag

    def verify(
        self, tenant_id: str, action_type: str, result_payload: Optional[dict]
    ) -> SourceResult:
        # This path should not be reached if registry checks is_null first.
        return SourceResult(
            verifier_id=self.verifier_id,
            verified=False,
            confidence=0.0,
            status=VerifierStatus.FAILED,
        )

    @classmethod
    def result(cls) -> "VerificationResult":
        """Return the correct VerificationResult for an unregistered action type.

        source_type="unknown" → trust engine treats this as no-op.
        deferred=True + window="24h" → routes to pending_outcomes for manual review.
        """
        return VerificationResult(
            confidence=0.0,
            disagreement_score=0.0,
            verified=False,
            status=VerifierStatus.DEGRADED,
            resolution_type=ResolutionType.MANUAL,
            deferred=True,
            deferred_window="24h",
            max_wait_hours=72,
            source_type="unknown",
            sources=[],
            disagreements=[],
        )
