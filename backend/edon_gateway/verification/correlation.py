"""Verifier pair correlation matrix for EDON.

Tracks the historical agreement rate between every pair of parallel
verifiers for each (tenant_id, action_type). High agreement between
verifiers that declared themselves independent is evidence of shared
infrastructure — they don't provide independent evidence.

Threshold: correlation > 0.90 over ≥ 50 observations → reduce the
effective weight of the correlated pair in aggregation.

Weight reduction formula:
    For each pair (vi, vj) with correlation > _CORR_THRESHOLD:
        Both verifiers receive multiplier = 1 - (corr - _CORR_THRESHOLD) * 2
        Floored at 0.40 (never fully zero out a verifier, just reduce it)

Called from:
    registry.py → after running verification, record pair agreements
    aggregator.py → apply weight multipliers before computing vc
"""
from __future__ import annotations

import os
import sqlite3
import threading
from typing import Optional

_DB_PATH         = os.getenv("EDON_CORR_DB", "verifier_correlation.db")
_CORR_THRESHOLD  = float(os.getenv("EDON_CORR_THRESHOLD", "0.90"))
_MIN_OBSERVATIONS = int(os.getenv("EDON_CORR_MIN_OBS", "50"))
_MIN_WEIGHT      = 0.40   # floor on correlated verifier weight


class VerifierCorrelationMatrix:

    def __init__(self, db_path: str = _DB_PATH) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._mem_conn: Optional[sqlite3.Connection] = None
        if db_path == ":memory:":
            self._mem_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._mem_conn.row_factory = sqlite3.Row
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        if self._mem_conn is not None:
            return self._mem_conn
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS verifier_correlations (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id    TEXT NOT NULL,
                    action_type  TEXT NOT NULL,
                    v1_id        TEXT NOT NULL,
                    v2_id        TEXT NOT NULL,
                    agreements   INTEGER NOT NULL DEFAULT 0,
                    total        INTEGER NOT NULL DEFAULT 0,
                    last_updated REAL NOT NULL DEFAULT 0
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_corr_pair
                    ON verifier_correlations (tenant_id, action_type, v1_id, v2_id);
            """)

    def _canonical_pair(self, a: str, b: str) -> tuple[str, str]:
        """Always store pairs in alphabetical order to avoid (A,B) vs (B,A) duplicates."""
        return (a, b) if a <= b else (b, a)

    def record_outcomes(
        self,
        tenant_id:   str,
        action_type: str,
        source_results: list,   # list[SourceResult]
    ) -> None:
        """Record pairwise agreement/disagreement for all verifier pairs.

        Two verifiers 'agree' when both report verified=True or both report False.
        """
        if len(source_results) < 2:
            return

        _tid  = tenant_id or ""
        import time
        now   = time.time()

        with self._lock, self._conn() as conn:
            for i in range(len(source_results)):
                for j in range(i + 1, len(source_results)):
                    vi = source_results[i]
                    vj = source_results[j]
                    v1_id, v2_id = self._canonical_pair(vi.verifier_id, vj.verifier_id)
                    # Agreement: both verified or both not verified
                    agreed = int(vi.verified == vj.verified)
                    conn.execute(
                        "INSERT INTO verifier_correlations "
                        "(tenant_id, action_type, v1_id, v2_id, agreements, total, last_updated) "
                        "VALUES (?,?,?,?,?,1,?) "
                        "ON CONFLICT(tenant_id, action_type, v1_id, v2_id) DO UPDATE SET "
                        "agreements = agreements + ?, total = total + 1, last_updated = ?",
                        (_tid, action_type, v1_id, v2_id, agreed, now, agreed, now),
                    )

    def get_correlation(
        self,
        tenant_id:   str,
        action_type: str,
        v1_id:       str,
        v2_id:       str,
    ) -> Optional[float]:
        """Return agreement rate for a pair, or None if insufficient data."""
        _tid = tenant_id or ""
        v1, v2 = self._canonical_pair(v1_id, v2_id)
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT agreements, total FROM verifier_correlations "
                "WHERE tenant_id=? AND action_type=? AND v1_id=? AND v2_id=?",
                (_tid, action_type, v1, v2),
            ).fetchone()
        if not row or int(row["total"]) < _MIN_OBSERVATIONS:
            return None
        return round(int(row["agreements"]) / int(row["total"]), 4)

    def get_weight_multipliers(
        self,
        tenant_id:   str,
        action_type: str,
        verifier_ids: list[str],
    ) -> dict[str, float]:
        """Return per-verifier weight multipliers accounting for correlation.

        Uncorrelated verifiers get 1.0.
        Correlated pairs (> _CORR_THRESHOLD over _MIN_OBSERVATIONS) get reduced
        weight so their combined influence doesn't over-inflate confidence.
        """
        multipliers = {vid: 1.0 for vid in verifier_ids}

        for i in range(len(verifier_ids)):
            for j in range(i + 1, len(verifier_ids)):
                corr = self.get_correlation(tenant_id, action_type,
                                            verifier_ids[i], verifier_ids[j])
                if corr is not None and corr > _CORR_THRESHOLD:
                    # Both get reduced; the one with the lower default index gets the smaller cut
                    reduction = min(0.60, (corr - _CORR_THRESHOLD) * 2)
                    for vid in (verifier_ids[i], verifier_ids[j]):
                        current = multipliers[vid]
                        multipliers[vid] = round(max(_MIN_WEIGHT, current - reduction / 2), 4)

        return multipliers

    def flagged_pairs(
        self,
        tenant_id:   str,
        action_type: Optional[str] = None,
    ) -> list[dict]:
        """Return all correlated pairs above threshold with sufficient data."""
        _tid = tenant_id or ""
        with self._lock, self._conn() as conn:
            if action_type:
                rows = conn.execute(
                    "SELECT * FROM verifier_correlations "
                    "WHERE tenant_id=? AND action_type=? AND total >= ? "
                    "ORDER BY CAST(agreements AS REAL)/total DESC",
                    (_tid, action_type, _MIN_OBSERVATIONS),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM verifier_correlations "
                    "WHERE tenant_id=? AND total >= ? "
                    "ORDER BY CAST(agreements AS REAL)/total DESC",
                    (_tid, _MIN_OBSERVATIONS),
                ).fetchall()

        result = []
        for r in rows:
            corr = int(r["agreements"]) / int(r["total"])
            if corr > _CORR_THRESHOLD:
                result.append({
                    "tenant_id":   r["tenant_id"],
                    "action_type": r["action_type"],
                    "v1_id":       r["v1_id"],
                    "v2_id":       r["v2_id"],
                    "correlation": round(corr, 4),
                    "total":       int(r["total"]),
                    "flagged":     True,
                })
        return result


# ── Singleton ──────────────────────────────────────────────────────────────────

_matrix: Optional[VerifierCorrelationMatrix] = None
_matrix_lock = threading.Lock()


def get_correlation_matrix() -> VerifierCorrelationMatrix:
    global _matrix
    if _matrix is None:
        with _matrix_lock:
            if _matrix is None:
                _matrix = VerifierCorrelationMatrix()
    return _matrix
