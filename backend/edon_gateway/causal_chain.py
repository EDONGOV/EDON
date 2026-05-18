"""Persistent cross-session causal chain for EDON.

The coordination graph is session-scoped and in-memory. This module is
persistent and agent-scoped — it tracks what an agent has done across ALL
sessions over the past N days.

Adversarial pattern it closes:
    Session 1: agent reads credential (low-risk, passes governance)
    [4 hour gap]
    Session 2: agent sends to external endpoint (evaluated in isolation, looks clean)

The causal chain sees both. Session boundaries are the adversary's friend —
this module removes them from the threat model.

Risk formula (time-weighted):
    For each prior action by this agent in the lookback window:
        age_sec = now - action.ts
        weight  = e^(-λ × age_sec)   [half-life = 24h]
        risk   += weight × type_weight[output_type]

    type_weights: credential=0.30, data=0.10
    cap at 1.0

Wire-in:
    - v1_action.py: evaluate_causal_risk() before governor
    - action_result.py: record_causal_action() after successful execution
"""
from __future__ import annotations

import hashlib
import math
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Optional

_DB_PATH    = os.getenv("EDON_CAUSAL_DB", "causal.db")
_MAX_AGE_DAYS  = int(os.getenv("EDON_CAUSAL_MAX_AGE_DAYS", "7"))
_HALF_LIFE_SEC = float(os.getenv("EDON_CAUSAL_HALF_LIFE_HOURS", "24")) * 3600
_DECAY_LAMBDA  = math.log(2) / _HALF_LIFE_SEC

_PRUNE_INTERVAL_SEC = 3600   # prune old rows once per hour at most

# Risk contribution per output_type (pre-decay weight)
_TYPE_WEIGHTS: dict[str, float] = {
    "credential": 0.30,
    "data":       0.10,
}

# Infer from action_type (mirrors coordination.py logic — credential wins over data)
_CREDENTIAL_PARTS = {"credential", "auth", "token", "secret", "key", "password", "login"}
_DATA_PARTS       = {"read", "get", "query", "list", "fetch", "search"}


def _infer_output_type(action_type: str) -> Optional[str]:
    parts = set(action_type.lower().split("."))
    if parts & _CREDENTIAL_PARTS:
        return "credential"
    if parts & _DATA_PARTS:
        return "data"
    return None


@dataclass
class CausalContribution:
    """Blame attribution for a single prior action that contributes to current risk."""
    action_id:           str
    action_type:         str
    output_type:         str
    age_h:               float   # hours ago
    contribution_weight: float   # normalized share of total causal_score [0, 1]
    reason:              str     # human-readable e.g. "credential.read 4h ago → email.send now"


@dataclass
class CausalRisk:
    causal_score:        float   # time-weighted risk sum, capped at 1.0
    credential_actions:  int     # count of credential-producing actions in window
    data_actions:        int     # count of data-producing actions in window
    oldest_action_age_h: float   # age of oldest relevant action in hours
    reason:              str
    contributions:       "list[CausalContribution]" = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.contributions is None:
            self.contributions = []

    def top_cause(self) -> "CausalContribution | None":
        """Return the single highest-weight contributing action, or None."""
        if not self.contributions:
            return None
        return max(self.contributions, key=lambda c: c.contribution_weight)


class CausalChainStore:
    """SQLite-backed persistent causal chain tracker."""

    def __init__(self, db_path: str = _DB_PATH) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._mem_conn: Optional[sqlite3.Connection] = None
        self._last_prune = 0.0
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
                CREATE TABLE IF NOT EXISTS causal_actions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id   TEXT NOT NULL,
                    agent_id    TEXT NOT NULL,
                    action_id   TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    output_type TEXT,          -- "credential" | "data" | NULL
                    ts          REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_causal_agent
                    ON causal_actions (tenant_id, agent_id, ts DESC);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_causal_action_id
                    ON causal_actions (action_id);
            """)

    def record(
        self,
        tenant_id:   str,
        agent_id:    str,
        action_id:   str,
        action_type: str,
        ts:          Optional[float] = None,
    ) -> None:
        """Record an executed action in the causal chain."""
        output_type = _infer_output_type(action_type)
        _ts = ts or time.time()
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO causal_actions "
                "(tenant_id, agent_id, action_id, action_type, output_type, ts) "
                "VALUES (?,?,?,?,?,?)",
                (tenant_id or "", agent_id, action_id, action_type, output_type, _ts),
            )
            self._maybe_prune(conn)

    def evaluate(
        self,
        tenant_id:   str,
        agent_id:    str,
        action_type: str,
        lookback_days: Optional[int] = None,
    ) -> CausalRisk:
        """Compute time-weighted causal risk for a proposed action.

        Looks at everything this agent has done in the lookback window
        (default: _MAX_AGE_DAYS) regardless of session. Scores the
        accumulated causal context for the proposed action_type.
        """
        _tid      = tenant_id or ""
        _days     = lookback_days or _MAX_AGE_DAYS
        _cutoff   = time.time() - _days * 86400
        _now      = time.time()

        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT action_id, action_type, output_type, ts FROM causal_actions "
                "WHERE tenant_id=? AND agent_id=? AND ts >= ? "
                "ORDER BY ts DESC",
                (_tid, agent_id, _cutoff),
            ).fetchall()

        if not rows:
            return CausalRisk(
                causal_score=0.0, credential_actions=0, data_actions=0,
                oldest_action_age_h=0.0, reason="no_causal_history",
            )

        score       = 0.0
        cred_count  = 0
        data_count  = 0
        oldest_age  = 0.0

        # First pass: compute raw weights per row for later normalization
        _row_weights: list[tuple] = []   # (action_id, action_type, otype, age_sec, raw_weight)
        for r in rows:
            otype = r["output_type"]
            if otype not in _TYPE_WEIGHTS:
                continue
            age_sec  = _now - float(r["ts"])
            weight   = math.exp(-_DECAY_LAMBDA * age_sec)
            raw      = weight * _TYPE_WEIGHTS[otype]
            score   += raw
            if otype == "credential":
                cred_count += 1
            elif otype == "data":
                data_count += 1
            oldest_age = max(oldest_age, age_sec / 3600)
            _row_weights.append((r["action_id"], r["action_type"], otype, age_sec, raw))

        score = round(min(score, 1.0), 4)

        # Build attribution: normalize each row's contribution relative to total
        contributions: list[CausalContribution] = []
        if score > 0 and _row_weights:
            # Use capped score for normalization so weights sum to ≤ 1.0
            _norm_base = max(score, sum(w[4] for w in _row_weights))
            for aid, atype, otype, age_sec, raw in sorted(_row_weights, key=lambda x: -x[4]):
                contrib = round(raw / _norm_base, 4)
                if contrib < 0.01:
                    continue  # omit negligible contributors
                age_h = round(age_sec / 3600, 2)
                contributions.append(CausalContribution(
                    action_id=aid,
                    action_type=atype,
                    output_type=otype,
                    age_h=age_h,
                    contribution_weight=contrib,
                    reason=f"{atype} ({age_h}h ago) → {action_type} now",
                ))

        if score == 0.0:
            reason = "no_relevant_outputs_in_history"
        elif cred_count > 0 and score > 0.40:
            reason = f"credential_producing_history(n={cred_count},score={score})"
        elif cred_count > 0:
            reason = f"aged_credential_history(n={cred_count},score={score})"
        else:
            reason = f"data_producing_history(n={data_count},score={score})"

        return CausalRisk(
            causal_score=score,
            credential_actions=cred_count,
            data_actions=data_count,
            oldest_action_age_h=round(oldest_age, 2),
            reason=reason,
            contributions=contributions,
        )

    def lookup_actions(self, action_ids: list[str]) -> list[dict]:
        """Look up stored causal chain records by action_id list.

        Used when the agent declares explicit lineage via caused_by=[...].
        Returns the stored records for those action_ids so we can compute
        precise attribution weights rather than inferring from timing.
        """
        if not action_ids:
            return []
        placeholders = ",".join("?" * len(action_ids))
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                f"SELECT action_id, action_type, output_type, ts "
                f"FROM causal_actions WHERE action_id IN ({placeholders})",
                action_ids,
            ).fetchall()
        return [dict(r) for r in rows]

    def build_declared_contributions(
        self,
        action_ids: list[str],
        current_action_type: str,
    ) -> list[CausalContribution]:
        """Build CausalContribution objects from explicitly declared lineage.

        Unlike heuristic inference, declared lineage has equal initial weight
        (1/N each), adjusted by output_type severity. The agent is saying
        "these specific prior actions caused this one."
        """
        records = self.lookup_actions(action_ids)
        if not records:
            return []

        now = time.time()
        _type_weights_for_contrib = {"credential": 0.30, "data": 0.10}
        raw_weights = []
        for r in records:
            otype = r.get("output_type") or ""
            tw    = _type_weights_for_contrib.get(otype, 0.05)
            age_s = now - float(r.get("ts", now))
            decay = math.exp(-_DECAY_LAMBDA * age_s)
            raw_weights.append((r, otype, age_s, tw * decay))

        total = sum(w[3] for w in raw_weights) or 1.0
        contributions = []
        for r, otype, age_s, raw in sorted(raw_weights, key=lambda x: -x[3]):
            contrib = round(raw / total, 4)
            age_h   = round(age_s / 3600, 2)
            contributions.append(CausalContribution(
                action_id=r["action_id"],
                action_type=r["action_type"],
                output_type=otype,
                age_h=age_h,
                contribution_weight=contrib,
                reason=f"[declared] {r['action_type']} {age_h}h ago → {current_action_type}",
            ))
        return contributions

    def _maybe_prune(self, conn: sqlite3.Connection) -> None:
        now = time.time()
        if now - self._last_prune < _PRUNE_INTERVAL_SEC:
            return
        cutoff = now - _MAX_AGE_DAYS * 86400
        conn.execute("DELETE FROM causal_actions WHERE ts < ?", (cutoff,))
        self._last_prune = now


# ── Singleton ──────────────────────────────────────────────────────────────────

_store: Optional[CausalChainStore] = None
_store_lock = threading.Lock()


def get_causal_chain() -> CausalChainStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = CausalChainStore()
    return _store
