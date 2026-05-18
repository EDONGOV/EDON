"""Aggregation logic for multi-source verification results.

Two outputs — epistemically separate:
  confidence        → weighted mean by verifier_trust; feeds trust engine
  disagreement_score → variance across sources; feeds system health / observability

POISONED detection:
  When confidence > 0.7 but disagreement_score > 0.15, at least one source
  strongly contradicts the majority. Flag as POISONED for investigation.
"""
from __future__ import annotations

import math
from typing import Optional

from .base import SourceResult, VerificationResult, VerifierStatus, ResolutionType


def aggregate(
    source_results: list[SourceResult],
    verifier_trusts: dict[str, float],       # {verifier_id: trust_score}
    resolution_type: ResolutionType = ResolutionType.IMMEDIATE,
    deferred: bool = False,
    deferred_window: str = "1h",
    max_wait_hours: int = 24,
) -> VerificationResult:
    """Aggregate multiple SourceResults into a single VerificationResult.

    Confidence formula:
        vc = sum(source.confidence × verifier_trust[source.verifier_id])
             / sum(verifier_trust[source.verifier_id])

    Disagreement formula:
        disagreement_score = stddev(source_confidences)  [equal-weighted, for system health]

    POISONED detection:
        vc > 0.7 AND disagreement_score > 0.15 → at least one source strongly
        contradicts the majority. Cannot trust the aggregate — flag POISONED.
    """
    if not source_results:
        return VerificationResult.no_verifier()

    # Separate OK-ish from hard-failed sources
    usable = [s for s in source_results if s.status != VerifierStatus.FAILED]
    failed = [s for s in source_results if s.status == VerifierStatus.FAILED]

    if not usable:
        return VerificationResult(
            confidence=0.0,
            disagreement_score=0.0,
            verified=False,
            status=VerifierStatus.FAILED,
            resolution_type=resolution_type,
            deferred=deferred,
            deferred_window=deferred_window,
            max_wait_hours=max_wait_hours,
            source_type="observation",
            sources=[],
            disagreements=[s.verifier_id for s in failed],
            source_results=source_results,
        )

    # Weighted confidence
    total_weight = sum(
        verifier_trusts.get(s.verifier_id, 0.50)
        for s in usable
    )
    if total_weight <= 0:
        total_weight = len(usable)   # equal weights fallback

    vc = sum(
        s.confidence * verifier_trusts.get(s.verifier_id, 0.50)
        for s in usable
    ) / total_weight

    # Disagreement score — equal-weighted stddev (system health signal)
    confs = [s.confidence for s in usable]
    mean  = sum(confs) / len(confs)
    variance = sum((c - mean) ** 2 for c in confs) / len(confs)
    disagreement = round(math.sqrt(variance), 6)

    # Identify disagreeing sources (confidence < 0.5 when majority says verified)
    majority_verified = vc >= 0.5
    disagreements = [
        s.verifier_id for s in usable
        if (s.confidence < 0.5 and majority_verified)
        or (s.confidence >= 0.5 and not majority_verified)
    ]

    # POISONED detection: strong cross-source disagreement regardless of vc direction.
    # High disagreement means at least one source strongly contradicts the others —
    # the system cannot determine which source is correct.
    if disagreement > 0.25 and len(usable) >= 2:
        status = VerifierStatus.POISONED
    elif any(s.status == VerifierStatus.STALE for s in usable):
        status = VerifierStatus.STALE
    elif any(s.status == VerifierStatus.DEGRADED for s in usable):
        status = VerifierStatus.DEGRADED
    else:
        status = VerifierStatus.OK

    verified = vc >= 0.70 and status not in (VerifierStatus.POISONED, VerifierStatus.FAILED)

    return VerificationResult(
        confidence=round(vc, 4),
        disagreement_score=round(disagreement, 4),
        verified=verified,
        status=status,
        resolution_type=resolution_type,
        deferred=deferred,
        deferred_window=deferred_window,
        max_wait_hours=max_wait_hours,
        source_type="observation",
        sources=[s.verifier_id for s in usable],
        disagreements=disagreements,
        source_results=source_results,
    )
