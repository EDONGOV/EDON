"""Tenant-scoped Verifier Registry with composition strategies.

Registry key: (tenant_id, action_type) → [(Verifier, weight)]
Composition:
  PARALLEL   — all verifiers run simultaneously; aggregate all results
  SEQUENTIAL — run in order; stop at first OK result
  FALLBACK   — try primary; use secondary only if primary is DEGRADED/FAILED

Verifier trust is stored in the TrustEngine's verifier_trust table and fed
into the aggregator so that high-trust sources carry more weight than low-trust ones.
"""
from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Optional

from .base import (
    Verifier, NullVerifier, VerificationResult,
    VerifierStatus, ResolutionType, SourceResult,
)
from .aggregator import aggregate


class CompositionStrategy(str, Enum):
    PARALLEL   = "parallel"
    SEQUENTIAL = "sequential"
    FALLBACK   = "fallback"


class VerifierRegistry:
    """Single registry for all verifier registrations.

    Thread-safe. Tenant-isolated. Composition strategy is configurable
    per (tenant_id, action_type) at registration time.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # {(tenant_id, action_type): [(verifier, strategy)]}
        self._entries: dict[tuple[str, str], tuple[list[Verifier], CompositionStrategy]] = {}
        # {verifier_id: float} — read from TrustEngine at verify time
        self._default_trusts: dict[str, float] = {}

    # ── Registration ───────────────────────────────────────────────────────────

    def register(
        self,
        tenant_id: str,
        action_type: str,
        verifier: Verifier,
        strategy: CompositionStrategy = CompositionStrategy.PARALLEL,
    ) -> None:
        """Register a verifier for (tenant_id, action_type).

        Multiple calls with PARALLEL strategy accumulate verifiers.
        Sequential/fallback replace on re-registration.

        Fix 3 — diversity enforcement:
        PARALLEL registrations reject duplicate upstream_source values.
        Two verifiers querying the same upstream do not provide independent
        evidence and could both be wrong in the same way (correlated failure).
        """
        key = (tenant_id or "", action_type)
        with self._lock:
            existing = self._entries.get(key)
            if existing and existing[1] == CompositionStrategy.PARALLEL:
                # Reject if same upstream_source already registered
                new_source = getattr(verifier, "upstream_source", "default")
                for existing_v in existing[0]:
                    existing_source = getattr(existing_v, "upstream_source", "default")
                    if existing_source == new_source and new_source != "default":
                        import warnings
                        warnings.warn(
                            f"[VerifierRegistry] duplicate upstream_source='{new_source}' "
                            f"for ({tenant_id}, {action_type}) — verifier '{verifier.verifier_id}' "
                            f"rejected. Parallel verifiers must query independent sources.",
                            stacklevel=2,
                        )
                        return
                verifiers = existing[0] + [verifier]
            else:
                verifiers = [verifier]
            self._entries[key] = (verifiers, strategy)
            self._default_trusts[verifier.verifier_id] = verifier.default_trust

    def register_global(
        self,
        action_type: str,
        verifier: Verifier,
        strategy: CompositionStrategy = CompositionStrategy.PARALLEL,
    ) -> None:
        """Register a verifier for all tenants (action_type only, no tenant scope)."""
        self.register("__global__", action_type, verifier, strategy)

    # ── Verification ───────────────────────────────────────────────────────────

    def verify(
        self,
        tenant_id: str,
        action_type: str,
        result_payload: Optional[dict] = None,
        verifier_trusts: Optional[dict[str, float]] = None,
    ) -> VerificationResult:
        """Run verification for (tenant_id, action_type).

        Lookup order:
          1. Exact (tenant_id, action_type) match
          2. Global ("__global__", action_type) match
          3. NullVerifier fallback (returns DEGRADED, not FAILED)

        verifier_trusts: dict {verifier_id: score} from TrustEngine.
        Falls back to each verifier's default_trust if not provided.
        """
        _tid = tenant_id or ""
        verifiers, strategy = self._resolve(_tid, action_type)
        trusts = verifier_trusts or self._default_trusts

        # NullVerifier short-circuit: absent verifier = trust freeze, not DEGRADED update.
        # Trust engine treats source_type="unknown" as schedule-to-pending only.
        if len(verifiers) == 1 and getattr(verifiers[0], "is_null", False):
            return NullVerifier.result()

        if strategy == CompositionStrategy.PARALLEL:
            return self._run_parallel(verifiers, _tid, action_type, result_payload, trusts)
        elif strategy == CompositionStrategy.SEQUENTIAL:
            return self._run_sequential(verifiers, _tid, action_type, result_payload, trusts)
        else:  # FALLBACK
            return self._run_fallback(verifiers, _tid, action_type, result_payload, trusts)

    def _resolve(
        self, tenant_id: str, action_type: str,
    ) -> tuple[list[Verifier], CompositionStrategy]:
        with self._lock:
            tenant_key = (tenant_id, action_type)
            global_key = ("__global__", action_type)
            if tenant_key in self._entries:
                return self._entries[tenant_key]
            if global_key in self._entries:
                return self._entries[global_key]
            return [NullVerifier()], CompositionStrategy.PARALLEL

    # ── Composition strategies ─────────────────────────────────────────────────

    def _run_source(
        self, verifier: Verifier,
        tenant_id: str, action_type: str, result_payload: Optional[dict],
    ) -> SourceResult:
        start = time.monotonic()
        try:
            result = verifier.verify(tenant_id, action_type, result_payload)
            result.latency_ms = int((time.monotonic() - start) * 1000)
            return result
        except Exception:
            return SourceResult(
                verifier_id=verifier.verifier_id,
                verified=False,
                confidence=0.0,
                status=VerifierStatus.FAILED,
                latency_ms=int((time.monotonic() - start) * 1000),
            )

    def _run_parallel(
        self,
        verifiers: list[Verifier],
        tenant_id: str, action_type: str,
        result_payload: Optional[dict],
        trusts: dict[str, float],
    ) -> VerificationResult:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(verifiers), 4)) as pool:
            futures = {
                pool.submit(self._run_source, v, tenant_id, action_type, result_payload): v
                for v in verifiers
            }
            source_results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # Verifier correlation: record pair agreements, apply weight multipliers
        try:
            from .correlation import get_correlation_matrix
            _cm = get_correlation_matrix()
            _cm.record_outcomes(tenant_id, action_type, source_results)
            _ids = [s.verifier_id for s in source_results]
            _mults = _cm.get_weight_multipliers(tenant_id, action_type, _ids)
            # Merge multipliers into trusts (reduce correlated verifier weights)
            trusts = {vid: trusts.get(vid, 0.50) * _mults.get(vid, 1.0) for vid in set(list(trusts) + _ids)}
        except Exception:
            pass

        return aggregate(source_results, trusts)

    def _run_sequential(
        self,
        verifiers: list[Verifier],
        tenant_id: str, action_type: str,
        result_payload: Optional[dict],
        trusts: dict[str, float],
    ) -> VerificationResult:
        for verifier in verifiers:
            result = self._run_source(verifier, tenant_id, action_type, result_payload)
            if result.status == VerifierStatus.OK:
                return aggregate([result], trusts)
        # All returned non-OK; aggregate all
        all_results = [
            self._run_source(v, tenant_id, action_type, result_payload)
            for v in verifiers
        ]
        return aggregate(all_results, trusts)

    def _run_fallback(
        self,
        verifiers: list[Verifier],
        tenant_id: str, action_type: str,
        result_payload: Optional[dict],
        trusts: dict[str, float],
    ) -> VerificationResult:
        if not verifiers:
            return VerificationResult.no_verifier()
        primary = self._run_source(verifiers[0], tenant_id, action_type, result_payload)
        if primary.status in (VerifierStatus.OK, VerifierStatus.STALE):
            return aggregate([primary], trusts)
        # Primary degraded/failed — try backups
        all_results = [primary]
        for backup in verifiers[1:]:
            r = self._run_source(backup, tenant_id, action_type, result_payload)
            all_results.append(r)
            if r.status == VerifierStatus.OK:
                break
        return aggregate(all_results, trusts)

    # ── Introspection ──────────────────────────────────────────────────────────

    def list_registrations(self, tenant_id: Optional[str] = None) -> list[dict]:
        with self._lock:
            entries = []
            for (tid, at), (verifiers, strategy) in self._entries.items():
                if tenant_id and tid not in (tenant_id, "__global__"):
                    continue
                entries.append({
                    "tenant_id":  tid,
                    "action_type": at,
                    "strategy":   strategy.value,
                    "verifiers":  [v.verifier_id for v in verifiers],
                })
            return entries


# ── Singleton ──────────────────────────────────────────────────────────────────

_registry: Optional[VerifierRegistry] = None
_registry_lock = threading.Lock()


def get_verifier_registry() -> VerifierRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = VerifierRegistry()
    return _registry
