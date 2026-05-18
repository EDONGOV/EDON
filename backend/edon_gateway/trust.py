"""Closed-loop trust engine for EDON.

Thirteen guarantees:

Original eight:
  1. Velocity bound        — per-update delta clamped; window budget enforced
  2. Uncertainty separation — "no data" and "bad data" produce different scores
  3. Action granularity    — key includes risk_bucket; trust isolated per context
  4. Short-term memory     — recent burst of failures triggers immediate penalty
  5. Adaptive thresholds   — per-agent ALLOW/BLOCK thresholds calibrate from escalation history
  6. Circuit breaker       — global failure spike hardens all borderline decisions
  7. Explainability        — every TrustScore carries a structured audit reason
  8. Verification tiers    — trust gain scales with evidence strength

New five:
  9.  Verification confidence — float [0,1] replaces integer tiers;
                                 trust_update *= confidence; near-zero → negative signal
  10. Delayed outcomes        — pending_outcomes table; T+1h/T+24h/T+7d checkpoints;
                                 retroactive_correct() re-scores past actions
  11. Tool trust layer        — tool_trust table; combined = 0.5*action + 0.3*agent + 0.2*tool
  12. Trust volatility        — stddev of last-N deltas; high volatility caps effective_trust
  13. Retroactive correction  — explicit API to re-score; bypasses velocity window
"""
from __future__ import annotations

import fnmatch
import hashlib
import hmac
import json
import math
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, UTC, timedelta
from typing import Optional

# ── Storage ────────────────────────────────────────────────────────────────────
_DB_PATH = os.getenv("EDON_TRUST_DB", "trust.db")

# ── Velocity jitter (adversarial resistance) ───────────────────────────────────
# Per-tenant jitter rotates daily using HMAC so an adversary cannot probe and
# memorize the exact velocity cap. Stable within a calendar day per tenant.
# Jitter range: [0.80, 1.20] of the base velocity constants.
def _get_velocity_jitter(tenant_id: str) -> float:
    today  = datetime.now(UTC).strftime("%Y%m%d").encode()
    key    = (tenant_id or "global").encode()
    digest = hmac.new(key, today, hashlib.sha256).digest()
    return round(0.80 + (digest[0] / 255) * 0.40, 4)  # [0.80, 1.20]

# ── Update coefficients ────────────────────────────────────────────────────────
_ALPHA_BASE    = 0.05
_ALPHA_PARTIAL = 0.0125
_BETA_FAILURE  = 0.15
_BETA_RETROACTIVE = 0.10   # penalty per retroactive failure (lighter than live — already happened)

# ── Velocity clamping (guarantee 1) ───────────────────────────────────────────
_MAX_GAIN_PER_UPDATE  = +0.05
_MAX_LOSS_PER_UPDATE  = -0.10
_VELOCITY_WINDOW_SEC  = 60
_MAX_DELTA_PER_WINDOW = 0.10

# ── Prior + confidence (guarantee 2) ──────────────────────────────────────────
_PRIOR              = 0.50
_CONFIDENCE_K       = 10
_UNCERTAINTY_PENALTY = 0.10

# ── Verification confidence (guarantee 9) ─────────────────────────────────────
# trust_update *= verification_confidence
# Below _VC_NEGATIVE_THRESHOLD on a claimed success → soft negative signal
_VC_NEGATIVE_THRESHOLD = 0.10
_VC_NEGATIVE_BETA      = 0.05   # soft penalty coefficient when confidence ≈ 0

# ── Time decay ─────────────────────────────────────────────────────────────────
_DECAY_HALF_LIFE_DAYS = float(os.getenv("EDON_TRUST_DECAY_DAYS", "30"))
_DECAY_LAMBDA = math.log(2) / (_DECAY_HALF_LIFE_DAYS * 86400)

# ── Short-term memory (guarantee 4) ───────────────────────────────────────────
_RECENT_WINDOW      = 5
_BURST_FAIL_TRIGGER = 2
_BURST_PENALTY      = 0.70

# ── Tool trust (guarantee 11) ─────────────────────────────────────────────────
_TOOL_CONFIDENCE_K = 20   # tools need more data before confidence builds
# Combined = 0.5*action + 0.3*agent + 0.2*tool
_W_ACTION = 0.50
_W_AGENT  = 0.30
_W_TOOL   = 0.20

# ── Trust volatility (guarantee 12) ───────────────────────────────────────────
_VOLATILITY_WINDOW    = 10    # stddev over last N delta values
_VOLATILITY_HIGH      = 0.04  # stddev above this → cap effective_trust
_VOLATILITY_CAP_BASE  = 0.80  # max effective_trust when volatility is high

# ── Delayed outcomes (guarantee 10) ───────────────────────────────────────────
_DELAYED_WINDOWS_HOURS = (1, 24, 168)   # T+1h, T+24h, T+7d

# ── Default decision thresholds ───────────────────────────────────────────────
THRESHOLD_ALLOW    = 0.75
THRESHOLD_ESCALATE = 0.50
THRESHOLD_BLOCK    = 0.30

# ── Adaptive threshold limits (guarantee 5) ───────────────────────────────────
_ALLOW_LOWER_LIMIT       = 0.55
_BLOCK_UPPER_LIMIT       = 0.45
_THRESHOLD_STEP          = 0.05
_MIN_ESCALATION_SAMPLE   = 5

# ── Circuit breaker (guarantee 6) ─────────────────────────────────────────────
_CB_SPIKE_FACTOR  = 2.0
_CB_MIN_SAMPLE    = 20
_CB_BASELINE_HOURS = 24

# ── Cold start ─────────────────────────────────────────────────────────────────
_COLD_START_MIN = int(os.getenv("EDON_TRUST_COLD_START_MIN", "10"))

# ── Hard block patterns ───────────────────────────────────────────────────────
_DEFAULT_HARD_BLOCK = (
    "credential.*,auth.delete,auth.revoke_all,*.drop_table,"
    "*.delete_all,*.truncate,system.shutdown,system.reset,admin.impersonate"
)
_HARD_BLOCK_PATTERNS: frozenset[str] = frozenset(
    p.strip()
    for p in os.getenv("EDON_HARD_BLOCK_PATTERNS", _DEFAULT_HARD_BLOCK).split(",")
    if p.strip()
)


# ── Result type ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TrustScore:
    # Stored / decayed / effective per layer
    agent_raw: float
    action_raw: float
    tool_raw: float

    agent_decayed: float
    action_decayed: float
    tool_decayed: float

    agent_effective: float
    action_effective: float
    tool_effective: float

    agent_confidence: float
    action_confidence: float
    tool_confidence: float
    uncertainty: float

    # Combined scores
    combined_raw: float     # 0.5*action + 0.3*agent + 0.2*tool (confidence-weighted)
    adjusted_trust: float   # combined from decayed scores - uncertainty penalty
    effective_trust: float  # after burst penalty + volatility cap

    # Diagnostics
    recent_failures: int
    burst_multiplier: float
    volatility: float
    volatility_cap: float

    agent_outcomes: int
    action_outcomes: int
    tool_outcomes: int

    # Thresholds
    effective_allow_threshold: float
    effective_block_threshold: float

    # Flags
    circuit_breaker_active: bool
    cold_start: bool
    hard_blocked: bool

    reason: str

    # Adversarial resistance signals
    behavioral_entropy: float = 1.0   # 0=concentrated (suspicious), 1=diverse (normal)

    # Fix 1 — modifier trace: each entry is {"name", "impact", "active"}
    # Shows exactly which mechanism fired and how much it moved the score.
    modifiers: tuple = ()

    def to_dict(self) -> dict:
        return {
            "agent_trust":             self.agent_effective,
            "action_trust":            self.action_effective,
            "tool_trust":              self.tool_effective,
            "combined_trust":          self.combined_raw,
            "adjusted_trust":          self.adjusted_trust,
            "effective_trust":         self.effective_trust,
            "confidence":              self.action_confidence,
            "uncertainty":             self.uncertainty,
            "volatility":              self.volatility,
            "volatility_cap":          self.volatility_cap,
            "recent_failures":         self.recent_failures,
            "burst_multiplier":        self.burst_multiplier,
            "cold_start":              self.cold_start,
            "hard_blocked":            self.hard_blocked,
            "circuit_breaker_active":  self.circuit_breaker_active,
            "allow_threshold":         self.effective_allow_threshold,
            "block_threshold":         self.effective_block_threshold,
            "reason":                  self.reason,
            "behavioral_entropy":      self.behavioral_entropy,
            "modifiers":               list(self.modifiers),
        }


# ── Engine ─────────────────────────────────────────────────────────────────────

class TrustEngine:

    def __init__(self, db_path: str = _DB_PATH) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._mem_conn: Optional[sqlite3.Connection] = None
        if db_path == ":memory:":
            self._mem_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._mem_conn.row_factory = sqlite3.Row
        self._init_db()

    # ── DB helpers ─────────────────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        if self._mem_conn is not None:
            return self._mem_conn
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS agent_trust (
                    tenant_id             TEXT NOT NULL,
                    agent_id              TEXT NOT NULL,
                    score                 REAL    NOT NULL DEFAULT 0.50,
                    outcomes              INTEGER NOT NULL DEFAULT 0,
                    successes             INTEGER NOT NULL DEFAULT 0,
                    last_updated          REAL    NOT NULL DEFAULT 0,
                    window_delta          REAL    NOT NULL DEFAULT 0,
                    window_start_ts       REAL    NOT NULL DEFAULT 0,
                    escalation_approvals  INTEGER NOT NULL DEFAULT 0,
                    escalation_denials    INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (tenant_id, agent_id)
                );

                CREATE TABLE IF NOT EXISTS action_trust (
                    tenant_id       TEXT NOT NULL,
                    agent_id        TEXT NOT NULL,
                    action_key      TEXT NOT NULL,
                    score           REAL    NOT NULL DEFAULT 0.50,
                    outcomes        INTEGER NOT NULL DEFAULT 0,
                    successes       INTEGER NOT NULL DEFAULT 0,
                    last_updated    REAL    NOT NULL DEFAULT 0,
                    window_delta    REAL    NOT NULL DEFAULT 0,
                    window_start_ts REAL    NOT NULL DEFAULT 0,
                    PRIMARY KEY (tenant_id, agent_id, action_key)
                );

                -- Guarantee 11: tool-level shared trust layer
                CREATE TABLE IF NOT EXISTS tool_trust (
                    tenant_id    TEXT NOT NULL,
                    tool         TEXT NOT NULL,
                    op           TEXT NOT NULL,
                    score        REAL    NOT NULL DEFAULT 0.50,
                    outcomes     INTEGER NOT NULL DEFAULT 0,
                    incidents    INTEGER NOT NULL DEFAULT 0,
                    last_updated REAL    NOT NULL DEFAULT 0,
                    PRIMARY KEY (tenant_id, tool, op)
                );

                -- Guarantee 4: last-N outcome memory for burst detection
                CREATE TABLE IF NOT EXISTS recent_outcomes (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id   TEXT NOT NULL,
                    agent_id    TEXT NOT NULL,
                    action_key  TEXT NOT NULL,
                    outcome     TEXT NOT NULL,
                    ts          REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_recent_outcomes
                    ON recent_outcomes (tenant_id, agent_id, action_key, ts DESC);

                -- Guarantee 12: trust delta history for volatility calculation
                CREATE TABLE IF NOT EXISTS trust_changes (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id  TEXT NOT NULL,
                    agent_id   TEXT NOT NULL,
                    action_key TEXT NOT NULL,
                    delta      REAL NOT NULL,
                    ts         REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_trust_changes
                    ON trust_changes (tenant_id, agent_id, action_key, ts DESC);

                -- Guarantee 10: pending delayed outcome checkpoints
                CREATE TABLE IF NOT EXISTS pending_outcomes (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id            TEXT NOT NULL,
                    agent_id             TEXT NOT NULL,
                    action_id            TEXT NOT NULL,
                    action_type          TEXT NOT NULL,
                    risk_bucket          TEXT NOT NULL DEFAULT 'default',
                    initial_outcome      TEXT NOT NULL,
                    trust_at_record      REAL,
                    check_at_1h          REAL,
                    check_at_24h         REAL,
                    check_at_7d          REAL,
                    checked_1h           INTEGER NOT NULL DEFAULT 0,
                    checked_24h          INTEGER NOT NULL DEFAULT 0,
                    checked_7d           INTEGER NOT NULL DEFAULT 0,
                    created_at           REAL NOT NULL,
                    resolved             INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_pending_outcomes_due
                    ON pending_outcomes (resolved, check_at_1h);

                -- Guarantee 6: hourly stats for circuit breaker
                CREATE TABLE IF NOT EXISTS outcome_stats (
                    tenant_id   TEXT NOT NULL,
                    hour_bucket TEXT NOT NULL,
                    total       INTEGER NOT NULL DEFAULT 0,
                    failures    INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (tenant_id, hour_bucket)
                );

                -- Meta-trust over verifiers (guarantee 9 extension)
                -- Verifiers themselves can be trusted or untrustworthy.
                -- Used by the aggregator to weight source confidences.
                CREATE TABLE IF NOT EXISTS verifier_trust (
                    tenant_id    TEXT NOT NULL,
                    verifier_id  TEXT NOT NULL,
                    score        REAL    NOT NULL DEFAULT 0.70,
                    outcomes     INTEGER NOT NULL DEFAULT 0,
                    last_updated REAL    NOT NULL DEFAULT 0,
                    PRIMARY KEY (tenant_id, verifier_id)
                );
            """)
            # Migrate agent_trust columns added after initial schema creation
            for col, defn in [
                ("window_delta",         "REAL    NOT NULL DEFAULT 0"),
                ("window_start_ts",      "REAL    NOT NULL DEFAULT 0"),
                ("escalation_approvals", "INTEGER NOT NULL DEFAULT 0"),
                ("escalation_denials",   "INTEGER NOT NULL DEFAULT 0"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE agent_trust ADD COLUMN {col} {defn}")
                    conn.commit()
                except Exception:
                    pass  # column already exists

            # Migrate action_trust — action_key is a PRIMARY KEY component; if the
            # table predates it we must drop and recreate (trust scores are rebuildable)
            try:
                conn.execute("SELECT action_key FROM action_trust LIMIT 1")
            except Exception:
                conn.execute("DROP TABLE IF EXISTS action_trust")
                conn.execute("""
                    CREATE TABLE action_trust (
                        tenant_id       TEXT NOT NULL,
                        agent_id        TEXT NOT NULL,
                        action_key      TEXT NOT NULL,
                        score           REAL    NOT NULL DEFAULT 0.50,
                        outcomes        INTEGER NOT NULL DEFAULT 0,
                        successes       INTEGER NOT NULL DEFAULT 0,
                        last_updated    REAL    NOT NULL DEFAULT 0,
                        window_delta    REAL    NOT NULL DEFAULT 0,
                        window_start_ts REAL    NOT NULL DEFAULT 0,
                        PRIMARY KEY (tenant_id, agent_id, action_key)
                    )
                """)
                conn.commit()

    # ── Math helpers ───────────────────────────────────────────────────────────

    def _apply_decay(self, score: float, ts: float) -> float:
        if ts <= 0:
            return score
        age = max(0.0, time.time() - ts)
        return _PRIOR + (score - _PRIOR) * math.exp(-_DECAY_LAMBDA * age)

    def _apply_confidence(self, score: float, outcomes: int, k: int = _CONFIDENCE_K) -> tuple[float, float]:
        c = outcomes / (outcomes + k)
        return _PRIOR * (1.0 - c) + score * c, round(c, 4)

    def _clamp_delta(
        self, old_score: float, raw_new: float,
        window_delta: float, window_start_ts: float,
        tenant_id: str = "",
    ) -> tuple[float, float, float]:
        now = time.time()
        if now - window_start_ts > _VELOCITY_WINDOW_SEC:
            window_delta = 0.0
            window_start_ts = now

        # Adversarial resistance: daily-rotating per-tenant jitter so the exact
        # velocity cap cannot be probed and memorized by a patient adversary.
        _jitter     = _get_velocity_jitter(tenant_id)
        _max_gain   = _MAX_GAIN_PER_UPDATE  * _jitter
        _max_loss   = _MAX_LOSS_PER_UPDATE  * _jitter
        _max_window = _MAX_DELTA_PER_WINDOW * _jitter

        raw_delta = raw_new - old_score
        clamped   = max(_max_loss, min(_max_gain, raw_delta))

        if clamped > 0:
            remaining = max(0.0, _max_window - window_delta)
            clamped   = min(clamped, remaining)
        else:
            remaining = max(0.0, _max_window + window_delta)
            clamped   = max(clamped, -remaining)

        new_score = max(0.01, min(0.99, old_score + clamped))
        return round(new_score, 6), round(window_delta + clamped, 6), window_start_ts

    def _compute_volatility(
        self, conn: sqlite3.Connection,
        tenant_id: str, agent_id: str, action_key: str,
    ) -> float:
        """Stddev of last _VOLATILITY_WINDOW trust deltas (guarantee 12)."""
        rows = conn.execute(
            "SELECT delta FROM trust_changes "
            "WHERE tenant_id=? AND agent_id=? AND action_key=? "
            "ORDER BY ts DESC LIMIT ?",
            (tenant_id, agent_id, action_key, _VOLATILITY_WINDOW),
        ).fetchall()
        if len(rows) < 3:
            return 0.0
        deltas = [float(r["delta"]) for r in rows]
        mean = sum(deltas) / len(deltas)
        variance = sum((d - mean) ** 2 for d in deltas) / len(deltas)
        return round(math.sqrt(variance), 6)

    def _compute_behavioral_entropy(
        self, conn: sqlite3.Connection,
        tenant_id: str, agent_id: str, lookback: int = 50,
    ) -> float:
        """Shannon entropy of action_key distribution over last `lookback` outcomes.

        Returns 0.0 = perfectly concentrated (always same action)
                1.0 = maximally diverse (uniform across all distinct actions)

        Low entropy + high-risk action = adversarial probing signal.
        No history = 1.0 (unknown is treated as maximally uncertain, not suspicious).
        """
        rows = conn.execute(
            "SELECT action_key, COUNT(*) AS cnt FROM recent_outcomes "
            "WHERE tenant_id=? AND agent_id=? "
            "GROUP BY action_key",
            (tenant_id, agent_id),
        ).fetchall()

        if not rows:
            return 1.0

        total = sum(int(r["cnt"]) for r in rows)
        if total == 0:
            return 1.0

        n_distinct = len(rows)
        if n_distinct == 1:
            return 0.0

        entropy = -sum(
            (int(r["cnt"]) / total) * math.log2(int(r["cnt"]) / total)
            for r in rows if int(r["cnt"]) > 0
        )
        max_entropy = math.log2(n_distinct)
        return round(entropy / max_entropy, 4) if max_entropy > 0 else 1.0

    def _recent_failures(
        self, conn: sqlite3.Connection,
        tenant_id: str, agent_id: str, action_key: str,
    ) -> int:
        rows = conn.execute(
            "SELECT outcome FROM recent_outcomes "
            "WHERE tenant_id=? AND agent_id=? AND action_key=? "
            "ORDER BY ts DESC LIMIT ?",
            (tenant_id, agent_id, action_key, _RECENT_WINDOW),
        ).fetchall()
        return sum(1 for r in rows if r["outcome"] in ("failure", "timeout"))

    def _prune_recent(
        self, conn: sqlite3.Connection,
        tenant_id: str, agent_id: str, action_key: str,
    ) -> None:
        conn.execute(
            "DELETE FROM recent_outcomes WHERE id IN ("
            "  SELECT id FROM recent_outcomes "
            "  WHERE tenant_id=? AND agent_id=? AND action_key=? "
            "  ORDER BY ts DESC LIMIT -1 OFFSET ?"
            ")",
            (tenant_id, agent_id, action_key, _RECENT_WINDOW * 2),
        )

    # ── Adaptive risk elevation thresholds (non-linear, data-driven) ─────────────
    # Fixed: critical < 0.35, high < 0.50, medium < 0.65
    # Adaptive: thresholds move with the per-tenant trust distribution.
    #   - If this tenant's agents are generally trusted (median=0.75), then 0.50
    #     is the bottom quartile — that agent IS high risk relative to fleet.
    #   - If agents are generally low-trust (median=0.45), the bar for critical
    #     must shift or everything becomes critical.
    # Cache: 15min TTL per tenant; falls back to fixed values if < 50 samples.
    _adaptive_threshold_cache: dict = {}  # {tenant_id: (critical, high, medium, expires_at)}
    _ADAPTIVE_TTL      = 900     # 15 minutes
    _ADAPTIVE_MIN_N    = 50      # minimum agent scores before calibrating
    _ADAPTIVE_CRIT_PCT = 10      # p10 → critical threshold
    _ADAPTIVE_HIGH_PCT = 25      # p25 → high threshold
    _ADAPTIVE_MED_PCT  = 50      # p50 → medium threshold
    # Absolute limits so thresholds never become perverse
    _ADAPTIVE_CRIT_LO, _ADAPTIVE_CRIT_HI = 0.25, 0.55
    _ADAPTIVE_HIGH_LO,  _ADAPTIVE_HIGH_HI  = 0.35, 0.65
    _ADAPTIVE_MED_LO,   _ADAPTIVE_MED_HI   = 0.45, 0.75

    def compute_adaptive_risk_thresholds(self, tenant_id: str) -> dict[str, float]:
        """Return non-linear risk elevation thresholds calibrated from this tenant's
        actual trust distribution.

        Returns dict with keys: critical, high, medium — the combined_trust values
        below which risk_estimate is elevated to that level.

        Falls back to fixed defaults (0.35/0.50/0.65) if insufficient data.
        """
        _tid = tenant_id or ""
        now  = time.time()
        cached = self._adaptive_threshold_cache.get(_tid)
        if cached and cached[3] > now:
            return {"critical": cached[0], "high": cached[1], "medium": cached[2]}

        # Query all current agent scores for this tenant as a distribution proxy
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT score FROM agent_trust WHERE tenant_id=? ORDER BY score ASC",
                (_tid,),
            ).fetchall()

        scores = [float(r["score"]) for r in rows if r["score"] is not None]

        if len(scores) < self._ADAPTIVE_MIN_N:
            # Not enough data — return fixed defaults
            return {"critical": 0.35, "high": 0.50, "medium": 0.65}

        def _pct(data: list[float], p: int) -> float:
            k  = (len(data) - 1) * p / 100
            lo = int(k)
            hi = min(lo + 1, len(data) - 1)
            return data[lo] + (data[hi] - data[lo]) * (k - lo)

        crit_raw = _pct(scores, self._ADAPTIVE_CRIT_PCT)
        high_raw = _pct(scores, self._ADAPTIVE_HIGH_PCT)
        med_raw  = _pct(scores, self._ADAPTIVE_MED_PCT)

        crit  = round(max(self._ADAPTIVE_CRIT_LO, min(self._ADAPTIVE_CRIT_HI, crit_raw)), 4)
        high  = round(max(self._ADAPTIVE_HIGH_LO,  min(self._ADAPTIVE_HIGH_HI,  high_raw)), 4)
        med   = round(max(self._ADAPTIVE_MED_LO,   min(self._ADAPTIVE_MED_HI,   med_raw)), 4)

        # Ensure ordering: critical < high < medium
        high = max(high, crit + 0.05)
        med  = max(med,  high + 0.05)

        self._adaptive_threshold_cache[_tid] = (crit, high, med, now + self._ADAPTIVE_TTL)
        return {"critical": crit, "high": high, "medium": med}

    def _adaptive_thresholds(self, approvals: int, denials: int) -> tuple[float, float]:
        total = approvals + denials
        if total < _MIN_ESCALATION_SAMPLE:
            return THRESHOLD_ALLOW, THRESHOLD_BLOCK
        approval_rate = approvals / total
        denial_rate   = denials   / total
        allow_t = THRESHOLD_ALLOW
        block_t = THRESHOLD_BLOCK
        if approval_rate > 0.85:
            allow_t = max(_ALLOW_LOWER_LIMIT, allow_t - _THRESHOLD_STEP)
        if denial_rate > 0.50:
            block_t = min(_BLOCK_UPPER_LIMIT, block_t + _THRESHOLD_STEP)
        return allow_t, block_t

    def _circuit_breaker_active(self, conn: sqlite3.Connection, tenant_id: str) -> bool:
        now_str = datetime.now(UTC).strftime("%Y-%m-%dT%H")
        cur = conn.execute(
            "SELECT total, failures FROM outcome_stats WHERE tenant_id=? AND hour_bucket=?",
            (tenant_id, now_str),
        ).fetchone()
        if not cur or int(cur["total"]) < _CB_MIN_SAMPLE:
            return False
        current_rate = int(cur["failures"]) / int(cur["total"])
        baseline = conn.execute(
            "SELECT SUM(total) AS t, SUM(failures) AS f FROM outcome_stats "
            "WHERE tenant_id=? AND hour_bucket < ? ORDER BY hour_bucket DESC LIMIT ?",
            (tenant_id, now_str, _CB_BASELINE_HOURS),
        ).fetchone()
        if not baseline or not baseline["t"] or int(baseline["t"]) < _CB_MIN_SAMPLE:
            return False
        baseline_rate = int(baseline["f"]) / int(baseline["t"])
        return baseline_rate > 0 and current_rate > _CB_SPIKE_FACTOR * baseline_rate

    def _record_outcome_stats(self, conn: sqlite3.Connection, tenant_id: str, is_failure: bool) -> None:
        bucket = datetime.now(UTC).strftime("%Y-%m-%dT%H")
        conn.execute(
            "INSERT INTO outcome_stats (tenant_id, hour_bucket, total, failures) VALUES (?,?,1,?) "
            "ON CONFLICT(tenant_id, hour_bucket) DO UPDATE SET "
            "total=total+1, failures=failures+excluded.failures",
            (tenant_id, bucket, 1 if is_failure else 0),
        )

    def _read_tool_trust(
        self, conn: sqlite3.Connection, tenant_id: str, tool: str, op: str,
    ) -> tuple[float, int, float]:
        """Returns (decayed_effective, outcomes, confidence)."""
        row = conn.execute(
            "SELECT score, outcomes, last_updated FROM tool_trust "
            "WHERE tenant_id=? AND tool=? AND op=?",
            (tenant_id, tool, op),
        ).fetchone()
        if not row:
            return _PRIOR, 0, 0.0
        raw      = float(row["score"])
        outcomes = int(row["outcomes"])
        ts       = float(row["last_updated"])
        decayed  = self._apply_decay(raw, ts)
        eff, conf = self._apply_confidence(decayed, outcomes, k=_TOOL_CONFIDENCE_K)
        return eff, outcomes, conf

    def _update_tool_trust(
        self, conn: sqlite3.Connection, tenant_id: str, tool: str, op: str,
        is_failure: bool,
    ) -> None:
        now = time.time()
        row = conn.execute(
            "SELECT score, outcomes, incidents FROM tool_trust "
            "WHERE tenant_id=? AND tool=? AND op=?",
            (tenant_id, tool, op),
        ).fetchone()
        cur   = float(row["score"])    if row else _PRIOR
        outs  = int(row["outcomes"])   + 1 if row else 1
        incs  = int(row["incidents"])  + (1 if is_failure else 0) if row else (1 if is_failure else 0)
        # Tool trust updates are slower (×0.5) — shared state, be conservative
        if is_failure:
            new_score = max(0.01, cur - _BETA_FAILURE * 0.5 * cur)
        else:
            new_score = min(0.99, cur + _ALPHA_BASE * 0.5 * (1.0 - cur))
        conn.execute(
            "INSERT INTO tool_trust (tenant_id, tool, op, score, outcomes, incidents, last_updated) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(tenant_id, tool, op) DO UPDATE SET "
            "score=excluded.score, outcomes=excluded.outcomes, "
            "incidents=excluded.incidents, last_updated=excluded.last_updated",
            (tenant_id, tool, op, round(new_score, 6), outs, incs, now),
        )

    def _build_reason(
        self, *, hard_blocked: bool, cold_start: bool, circuit_breaker: bool,
        combined_raw: float, adjusted_trust: float, effective_trust: float,
        uncertainty: float, recent_failures: int, action_confidence: float,
        volatility: float, allow_t: float, block_t: float,
    ) -> str:
        if hard_blocked:
            return "hard_policy_block"
        parts: list[str] = []
        if circuit_breaker:
            parts.append("circuit_breaker_active")
        if cold_start:
            parts.append(f"cold_start(outcomes<{_COLD_START_MIN})")
        if uncertainty > 0.6:
            parts.append(f"low_confidence({action_confidence:.0%})")
        elif uncertainty > 0.3:
            parts.append(f"medium_confidence({action_confidence:.0%})")
        if recent_failures >= _BURST_FAIL_TRIGGER:
            parts.append(f"burst_failures({recent_failures}/{_RECENT_WINDOW})")
        if volatility >= _VOLATILITY_HIGH:
            parts.append(f"high_volatility({volatility:.3f})")
        if effective_trust > allow_t:
            parts.append("sufficient_trust")
        elif effective_trust > block_t:
            parts.append(f"low_trust(combined={combined_raw:.2f})")
        else:
            parts.append(f"insufficient_trust(combined={combined_raw:.2f})")
        if adjusted_trust < combined_raw - 0.02:
            parts.append(f"uncertainty_penalty(-{_UNCERTAINTY_PENALTY * uncertainty:.2f})")
        return " + ".join(parts) or "sufficient_trust"

    # ── Public API ─────────────────────────────────────────────────────────────

    @staticmethod
    def make_action_key(action_type: str, risk_bucket: str = "default") -> str:
        if risk_bucket and risk_bucket != "default":
            return f"{action_type}.{risk_bucket}"
        return action_type

    @staticmethod
    def parse_tool_op(action_type: str) -> tuple[str, str]:
        """Extract (tool, op) from action_type string, ignoring risk_bucket suffix."""
        parts = action_type.split(".")
        tool = parts[0] if parts else "unknown"
        op   = parts[1] if len(parts) > 1 else ""
        return tool, op

    def is_hard_blocked(self, action_type: str) -> bool:
        lower = action_type.lower()
        return any(fnmatch.fnmatch(lower, p.lower()) for p in _HARD_BLOCK_PATTERNS)

    def get_trust(
        self,
        tenant_id: str,
        agent_id: str,
        action_type: str,
        risk_bucket: str = "default",
    ) -> TrustScore:
        """Return fully computed trust across all 13 guarantees."""
        _tid = tenant_id or ""
        action_key = self.make_action_key(action_type, risk_bucket)
        tool, op   = self.parse_tool_op(action_type)

        with self._lock, self._conn() as conn:
            row_a = conn.execute(
                "SELECT score, outcomes, successes, last_updated, "
                "escalation_approvals, escalation_denials "
                "FROM agent_trust WHERE tenant_id=? AND agent_id=?",
                (_tid, agent_id),
            ).fetchone()
            row_t = conn.execute(
                "SELECT score, outcomes, successes, last_updated "
                "FROM action_trust WHERE tenant_id=? AND agent_id=? AND action_key=?",
                (_tid, agent_id, action_key),
            ).fetchone()
            tool_eff, tool_outcomes, tool_conf = self._read_tool_trust(conn, _tid, tool, op)
            recent_fail        = self._recent_failures(conn, _tid, agent_id, action_key)
            volatility         = self._compute_volatility(conn, _tid, agent_id, action_key)
            cb_active          = self._circuit_breaker_active(conn, _tid)
            behavioral_entropy = self._compute_behavioral_entropy(conn, _tid, agent_id)

        # Agent
        a_raw      = float(row_a["score"])        if row_a else _PRIOR
        a_outcomes = int(row_a["outcomes"])        if row_a else 0
        a_ts       = float(row_a["last_updated"]) if row_a else 0.0
        a_decayed  = self._apply_decay(a_raw, a_ts)
        a_eff, a_conf = self._apply_confidence(a_decayed, a_outcomes)
        a_approvals = int(row_a["escalation_approvals"]) if row_a else 0
        a_denials   = int(row_a["escalation_denials"])   if row_a else 0

        # Action
        t_raw      = float(row_t["score"])        if row_t else _PRIOR
        t_outcomes = int(row_t["outcomes"])        if row_t else 0
        t_ts       = float(row_t["last_updated"]) if row_t else 0.0
        t_decayed  = self._apply_decay(t_raw, t_ts)
        t_eff, t_conf = self._apply_confidence(t_decayed, t_outcomes)

        # Tool (raw value for display)
        tool_row = None
        with self._lock, self._conn() as conn2:
            tool_row = conn2.execute(
                "SELECT score, last_updated FROM tool_trust WHERE tenant_id=? AND tool=? AND op=?",
                (_tid, tool, op),
            ).fetchone()
        tool_raw     = float(tool_row["score"]) if tool_row else _PRIOR
        tool_decayed = self._apply_decay(tool_raw, float(tool_row["last_updated"]) if tool_row else 0.0)

        # Combined — confidence-weighted (for display/reporting)
        combined_raw = round(_W_ACTION * t_eff + _W_AGENT * a_eff + _W_TOOL * tool_eff, 4)

        # Adjusted trust — decayed only, no confidence rescue (guarantee 2)
        raw_combined   = round(_W_ACTION * t_decayed + _W_AGENT * a_decayed + _W_TOOL * tool_decayed, 4)
        uncertainty    = round(1.0 - t_conf, 4)
        adjusted_trust = round(raw_combined - _UNCERTAINTY_PENALTY * uncertainty, 4)
        adjusted_trust = max(0.01, min(0.99, adjusted_trust))

        # ── Fix 1: build named modifier trace ─────────────────────────────────
        # Each entry: {"name": str, "impact": float, "active": bool}
        # impact = how many trust points this mechanism added or removed.
        _modifiers: list[dict] = []

        # Anchor: what raw_combined says before any modifier
        _modifiers.append({
            "name": "prior_history",
            "impact": round(raw_combined - _PRIOR, 4),
            "active": True,
            "value": round(raw_combined, 4),
        })

        # Uncertainty penalty
        _unc_impact = round(-(adjusted_trust - raw_combined), 4)
        _modifiers.append({
            "name": "uncertainty_penalty",
            "impact": _unc_impact,
            "active": uncertainty > 0.05,
            "value": round(uncertainty, 4),
        })

        # Burst penalty (guarantee 4)
        burst_mult      = _BURST_PENALTY if recent_fail >= _BURST_FAIL_TRIGGER else 1.0
        _pre_burst      = adjusted_trust
        effective_trust = round(adjusted_trust * burst_mult, 4)
        _modifiers.append({
            "name": "burst_penalty",
            "impact": round(effective_trust - _pre_burst, 4),
            "active": burst_mult < 1.0,
            "value": recent_fail,
        })

        # Circuit breaker (guarantee 6)
        _pre_cb = effective_trust
        if cb_active and THRESHOLD_BLOCK < effective_trust < THRESHOLD_ALLOW:
            effective_trust = round(effective_trust * 0.85, 4)
        _modifiers.append({
            "name": "circuit_breaker",
            "impact": round(effective_trust - _pre_cb, 4),
            "active": cb_active,
            "value": cb_active,
        })

        # Volatility cap (guarantee 12)
        vol_cap  = 1.0
        _pre_vol = effective_trust
        if volatility >= _VOLATILITY_HIGH:
            vol_cap = max(0.50, _VOLATILITY_CAP_BASE - volatility * 5)
            effective_trust = round(min(effective_trust, vol_cap), 4)
        _modifiers.append({
            "name": "volatility_cap",
            "impact": round(effective_trust - _pre_vol, 4),
            "active": volatility >= _VOLATILITY_HIGH,
            "value": round(volatility, 6),
        })

        # Behavioral entropy signal (advisory — doesn't move effective_trust directly;
        # v1_action.py reads it and may elevate risk_estimate for concentrated agents)
        _modifiers.append({
            "name": "behavioral_entropy",
            "impact": 0.0,          # read-path advisory, not a score deduction
            "active": behavioral_entropy < 0.30,
            "value": behavioral_entropy,
        })

        # Adaptive thresholds (guarantee 5)
        allow_t, block_t = self._adaptive_thresholds(a_approvals, a_denials)

        cold_start   = t_outcomes < _COLD_START_MIN
        hard_blocked = self.is_hard_blocked(action_type)

        reason = self._build_reason(
            hard_blocked=hard_blocked, cold_start=cold_start,
            circuit_breaker=cb_active, combined_raw=combined_raw,
            adjusted_trust=adjusted_trust, effective_trust=effective_trust,
            uncertainty=uncertainty, recent_failures=recent_fail,
            action_confidence=t_conf, volatility=volatility,
            allow_t=allow_t, block_t=block_t,
        )

        return TrustScore(
            agent_raw=round(a_raw, 4),          action_raw=round(t_raw, 4),          tool_raw=round(tool_raw, 4),
            agent_decayed=round(a_decayed, 4),  action_decayed=round(t_decayed, 4),  tool_decayed=round(tool_decayed, 4),
            agent_effective=round(a_eff, 4),    action_effective=round(t_eff, 4),    tool_effective=round(tool_eff, 4),
            agent_confidence=a_conf,            action_confidence=t_conf,            tool_confidence=tool_conf,
            uncertainty=uncertainty,
            combined_raw=combined_raw,
            adjusted_trust=adjusted_trust,
            effective_trust=effective_trust,
            recent_failures=recent_fail,
            burst_multiplier=burst_mult,
            volatility=round(volatility, 6),
            volatility_cap=round(vol_cap, 4),
            agent_outcomes=a_outcomes,          action_outcomes=t_outcomes,          tool_outcomes=tool_outcomes,
            effective_allow_threshold=allow_t,
            effective_block_threshold=block_t,
            circuit_breaker_active=cb_active,
            cold_start=cold_start,
            hard_blocked=hard_blocked,
            reason=reason,
            behavioral_entropy=behavioral_entropy,
            modifiers=tuple(_modifiers),
        )

    def record_outcome(
        self,
        tenant_id: str,
        agent_id: str,
        action_type: str,
        outcome: str,
        verification_confidence: float = 1.0,
        human_decision: Optional[str] = None,
        risk_bucket: str = "default",
        action_id: Optional[str] = None,
        schedule_delayed: bool = False,
    ) -> None:
        """Update trust from a real outcome.

        Guarantee 9 — verification confidence:
          trust_update *= verification_confidence
          confidence < 0.10 on claimed success → soft negative signal

        Guarantee 10 — delayed outcomes:
          If schedule_delayed=True and action_id provided, creates pending
          outcome checkpoints at T+1h, T+24h, T+7d for retroactive scoring.
        """
        now = time.time()
        _tid = tenant_id or ""
        action_key = self.make_action_key(action_type, risk_bucket)
        tool, op   = self.parse_tool_op(action_type)

        vc = max(0.0, min(1.0, float(verification_confidence)))
        is_failure = outcome in ("failure", "timeout")

        if human_decision == "allow":
            is_success = True
            raw_gain = lambda s: s + _ALPHA_BASE * (1.0 - s)
        elif human_decision == "deny":
            is_success = False
            raw_gain = lambda s: s - _BETA_FAILURE * s
        elif is_failure:
            is_success = False
            raw_gain = lambda s: s - _BETA_FAILURE * s
        elif outcome == "success" and vc >= _VC_NEGATIVE_THRESHOLD:
            # Guarantee 9: scale gain by verification confidence
            alpha_vc = _ALPHA_BASE * vc
            is_success = vc >= 0.8
            raw_gain = lambda s: s + alpha_vc * (1.0 - s)
        elif outcome == "success" and vc < _VC_NEGATIVE_THRESHOLD:
            # Near-zero confidence on claimed success = soft negative (guarantee 9)
            is_success = False
            raw_gain = lambda s: s - _VC_NEGATIVE_BETA * (1.0 - vc) * s
        else:  # partial
            is_success = False
            raw_gain = lambda s: s + _ALPHA_PARTIAL * vc * (1.0 - s)

        with self._lock, self._conn() as conn:
            # ── Agent trust ────────────────────────────────────────────────────
            row_a = conn.execute(
                "SELECT score, outcomes, successes, window_delta, window_start_ts, "
                "escalation_approvals, escalation_denials FROM agent_trust "
                "WHERE tenant_id=? AND agent_id=?",
                (_tid, agent_id),
            ).fetchone()
            a_score  = float(row_a["score"])           if row_a else _PRIOR
            a_outs   = int(row_a["outcomes"])           + 1 if row_a else 1
            a_succ   = int(row_a["successes"])          + (1 if is_success else 0) if row_a else (1 if is_success else 0)
            a_wd     = float(row_a["window_delta"])     if row_a else 0.0
            a_wts    = float(row_a["window_start_ts"])  if row_a else 0.0
            a_appr   = int(row_a["escalation_approvals"]) + (1 if human_decision == "allow" else 0) if row_a else (1 if human_decision == "allow" else 0)
            a_deny   = int(row_a["escalation_denials"])   + (1 if human_decision == "deny"  else 0) if row_a else (1 if human_decision == "deny"  else 0)
            a_new, a_wd, a_wts = self._clamp_delta(a_score, raw_gain(a_score), a_wd, a_wts, _tid)
            conn.execute(
                "INSERT INTO agent_trust (tenant_id,agent_id,score,outcomes,successes,last_updated,"
                "window_delta,window_start_ts,escalation_approvals,escalation_denials) VALUES (?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(tenant_id,agent_id) DO UPDATE SET score=excluded.score,outcomes=excluded.outcomes,"
                "successes=excluded.successes,last_updated=excluded.last_updated,"
                "window_delta=excluded.window_delta,window_start_ts=excluded.window_start_ts,"
                "escalation_approvals=excluded.escalation_approvals,escalation_denials=excluded.escalation_denials",
                (_tid,agent_id,a_new,a_outs,a_succ,now,a_wd,a_wts,a_appr,a_deny),
            )

            # ── Action trust ───────────────────────────────────────────────────
            row_t = conn.execute(
                "SELECT score, outcomes, successes, window_delta, window_start_ts "
                "FROM action_trust WHERE tenant_id=? AND agent_id=? AND action_key=?",
                (_tid, agent_id, action_key),
            ).fetchone()
            t_score  = float(row_t["score"])           if row_t else _PRIOR
            t_outs   = int(row_t["outcomes"])           + 1 if row_t else 1
            t_succ   = int(row_t["successes"])          + (1 if is_success else 0) if row_t else (1 if is_success else 0)
            t_wd     = float(row_t["window_delta"])     if row_t else 0.0
            t_wts    = float(row_t["window_start_ts"])  if row_t else 0.0
            t_new, t_wd, t_wts = self._clamp_delta(t_score, raw_gain(t_score), t_wd, t_wts, _tid)
            conn.execute(
                "INSERT INTO action_trust (tenant_id,agent_id,action_key,score,outcomes,successes,"
                "last_updated,window_delta,window_start_ts) VALUES (?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(tenant_id,agent_id,action_key) DO UPDATE SET score=excluded.score,"
                "outcomes=excluded.outcomes,successes=excluded.successes,last_updated=excluded.last_updated,"
                "window_delta=excluded.window_delta,window_start_ts=excluded.window_start_ts",
                (_tid,agent_id,action_key,t_new,t_outs,t_succ,now,t_wd,t_wts),
            )

            # ── Tool trust (guarantee 11) ──────────────────────────────────────
            self._update_tool_trust(conn, _tid, tool, op, is_failure=is_failure)

            # ── Volatility tracking (guarantee 12) ────────────────────────────
            delta = t_new - t_score
            conn.execute(
                "INSERT INTO trust_changes (tenant_id,agent_id,action_key,delta,ts) VALUES (?,?,?,?,?)",
                (_tid, agent_id, action_key, round(delta, 6), now),
            )
            conn.execute(
                "DELETE FROM trust_changes WHERE id IN ("
                "  SELECT id FROM trust_changes WHERE tenant_id=? AND agent_id=? AND action_key=? "
                "  ORDER BY ts DESC LIMIT -1 OFFSET ?)",
                (_tid, agent_id, action_key, _VOLATILITY_WINDOW * 2),
            )

            # ── Short-term memory (guarantee 4) ───────────────────────────────
            conn.execute(
                "INSERT INTO recent_outcomes (tenant_id,agent_id,action_key,outcome,ts) VALUES (?,?,?,?,?)",
                (_tid, agent_id, action_key, outcome, now),
            )
            self._prune_recent(conn, _tid, agent_id, action_key)

            # ── Circuit breaker stats (guarantee 6) ───────────────────────────
            self._record_outcome_stats(conn, _tid, is_failure=is_failure)

            # ── Schedule delayed outcome checkpoints (guarantee 10) ───────────
            if schedule_delayed and action_id:
                ts_score = t_new
                conn.execute(
                    "INSERT INTO pending_outcomes "
                    "(tenant_id,agent_id,action_id,action_type,risk_bucket,initial_outcome,"
                    "trust_at_record,check_at_1h,check_at_24h,check_at_7d,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        _tid, agent_id, action_id, action_type, risk_bucket, outcome,
                        ts_score,
                        now + 3600,
                        now + 86400,
                        now + 604800,
                        now,
                    ),
                )

    def retroactive_correct(
        self,
        tenant_id: str,
        agent_id: str,
        action_type: str,
        outcome: str,
        risk_bucket: str = "default",
        action_id: Optional[str] = None,
        window: str = "unknown",
    ) -> None:
        """Re-score trust based on a delayed outcome (guarantee 13).

        Applies _BETA_RETROACTIVE penalty, bypassing velocity window since
        this is a correction of past state, not a new event.
        """
        now = time.time()
        _tid = tenant_id or ""
        action_key = self.make_action_key(action_type, risk_bucket)
        tool, op   = self.parse_tool_op(action_type)
        is_failure = outcome in ("failure", "timeout")

        if is_failure:
            correct_fn = lambda s: s - _BETA_RETROACTIVE * s
        else:
            correct_fn = lambda s: s + (_ALPHA_PARTIAL) * (1.0 - s)

        with self._lock, self._conn() as conn:
            for table, keys, vals in (
                ("agent_trust",  ("tenant_id","agent_id"),                    (_tid,agent_id)),
                ("action_trust", ("tenant_id","agent_id","action_key"), (_tid,agent_id,action_key)),
            ):
                where = " AND ".join(f"{c}=?" for c in keys)
                row = conn.execute(f"SELECT score,outcomes FROM {table} WHERE {where}", vals).fetchone()
                cur   = float(row["score"])   if row else _PRIOR
                outs  = int(row["outcomes"])  if row else 0
                new_s = round(max(0.01, min(0.99, correct_fn(cur))), 6)
                col_list     = ",".join(keys)
                placeholders = ",".join("?" for _ in keys)
                conn.execute(
                    f"INSERT INTO {table} ({col_list},score,outcomes,successes,last_updated,"
                    f"window_delta,window_start_ts) VALUES ({placeholders},?,?,0,?,0,0) "
                    f"ON CONFLICT({col_list}) DO UPDATE SET score=excluded.score,last_updated=excluded.last_updated",
                    (*vals, new_s, outs, now),
                )
            if is_failure:
                self._update_tool_trust(conn, _tid, tool, op, is_failure=True)
            # Mark pending outcome as resolved
            if action_id:
                conn.execute(
                    "UPDATE pending_outcomes SET resolved=1 WHERE tenant_id=? AND action_id=? AND action_type=?",
                    (_tid, action_id, action_type),
                )

    def get_due_delayed_checks(self, tenant_id: Optional[str] = None, limit: int = 50) -> list[dict]:
        """Return pending outcome rows whose next check time has passed."""
        now = time.time()
        _tid = tenant_id or ""
        with self._lock, self._conn() as conn:
            if tenant_id:
                rows = conn.execute(
                    "SELECT * FROM pending_outcomes WHERE resolved=0 AND tenant_id=? AND ("
                    "  (checked_1h=0 AND check_at_1h <= ?) OR "
                    "  (checked_24h=0 AND check_at_24h <= ?) OR "
                    "  (checked_7d=0  AND check_at_7d  <= ?)"
                    ") ORDER BY check_at_1h ASC LIMIT ?",
                    (_tid, now, now, now, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM pending_outcomes WHERE resolved=0 AND ("
                    "  (checked_1h=0 AND check_at_1h <= ?) OR "
                    "  (checked_24h=0 AND check_at_24h <= ?) OR "
                    "  (checked_7d=0  AND check_at_7d  <= ?)"
                    ") ORDER BY check_at_1h ASC LIMIT ?",
                    (now, now, now, limit),
                ).fetchall()
        return [dict(r) for r in rows]

    def mark_delayed_check_done(self, row_id: int, window: str) -> None:
        col = {"1h": "checked_1h", "24h": "checked_24h", "7d": "checked_7d"}.get(window)
        if not col:
            return
        with self._lock, self._conn() as conn:
            conn.execute(f"UPDATE pending_outcomes SET {col}=1 WHERE id=?", (row_id,))

    def is_circuit_breaker_active(self, tenant_id: str = "") -> bool:
        """Public check for ADAPT meta-policy gate (Patch D)."""
        with self._lock, self._conn() as conn:
            return self._circuit_breaker_active(conn, tenant_id or "")

    def detect_exploitation_pattern(
        self,
        tenant_id: str,
        agent_id: str,
        action_type: str,
        risk_bucket: str = "default",
        lookback: int = 10,
    ) -> dict:
        """Patch E: detect strategic trust-building followed by high-risk action.

        Pattern: agent accumulates a run of safe, positive-delta actions to build
        trust, then attempts an action in a "critical" or "high" risk bucket.

        Returns:
            {
                "exploitation_suspected": bool,
                "trust_trend": float,          # mean delta over lookback window
                "positive_run": int,           # consecutive positive-delta updates
                "risk_bucket": str,
                "reason": str,
            }

        Callers (v1_action.py) can use exploitation_suspected=True to:
          - Force escalation regardless of trust score
          - Set risk_estimate to "critical"
          - Add to the audit trail
        """
        _tid = tenant_id or ""
        HIGH_RISK = {"critical", "high"}

        result = {
            "exploitation_suspected": False,
            "trust_trend": 0.0,
            "positive_run": 0,
            "risk_bucket": risk_bucket,
            "reason": "ok",
        }

        if risk_bucket not in HIGH_RISK:
            return result

        with self._lock, self._conn() as conn:
            # Use recent_outcomes for run detection — trust_changes deltas saturate to 0
            # via velocity clamping when many calls happen within the same 60s window,
            # making delta-based consecutive run detection unreliable.
            rows = conn.execute(
                "SELECT outcome FROM recent_outcomes "
                "WHERE tenant_id=? AND agent_id=? "
                "ORDER BY ts DESC LIMIT ?",
                (_tid, agent_id, lookback),
            ).fetchall()

            if len(rows) < 3:
                result["reason"] = "insufficient_history"
                return result

            outcomes = [r["outcome"] for r in rows]
            success_count = sum(1 for o in outcomes if o == "success")
            success_rate = success_count / len(outcomes)
            result["trust_trend"] = round(success_rate - 0.5, 4)

            # Count consecutive successes from the most recent backward
            run = 0
            for o in outcomes:
                if o == "success":
                    run += 1
                else:
                    break
            result["positive_run"] = run

            # Exploitation signal: high success rate AND consecutive run into high-risk action.
            if success_rate >= 0.80 and run >= 4:
                result["exploitation_suspected"] = True
                result["reason"] = (
                    f"positive_trust_run({run})_into_{risk_bucket}_action"
                )

        return result

    def get_verifier_trusts(self, tenant_id: str) -> dict[str, float]:
        """Return {verifier_id: trust_score} for use by the aggregator."""
        _tid = tenant_id or ""
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT verifier_id, score FROM verifier_trust WHERE tenant_id=?",
                (_tid,),
            ).fetchall()
        return {r["verifier_id"]: float(r["score"]) for r in rows}

    def update_verifier_trust(
        self,
        tenant_id: str,
        verifier_id: str,
        was_correct: bool,
    ) -> None:
        """Update meta-trust for a verifier based on whether its result was accurate.

        Called when a retroactive correction or human review contradicts a
        verifier's original output. Correct verifiers build trust slowly;
        incorrect ones lose it faster (same asymmetry as agent trust).
        """
        now = time.time()
        _tid = tenant_id or ""
        alpha = 0.03  # slower than agent trust — verifiers are shared infrastructure
        beta  = 0.12
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT score, outcomes FROM verifier_trust WHERE tenant_id=? AND verifier_id=?",
                (_tid, verifier_id),
            ).fetchone()
            cur  = float(row["score"])   if row else 0.70
            outs = int(row["outcomes"])  + 1 if row else 1
            new_score = cur + alpha * (1.0 - cur) if was_correct else cur - beta * cur
            new_score = round(max(0.10, min(0.99, new_score)), 6)
            conn.execute(
                "INSERT INTO verifier_trust (tenant_id,verifier_id,score,outcomes,last_updated) "
                "VALUES (?,?,?,?,?) ON CONFLICT(tenant_id,verifier_id) DO UPDATE SET "
                "score=excluded.score,outcomes=excluded.outcomes,last_updated=excluded.last_updated",
                (_tid, verifier_id, new_score, outs, now),
            )

    def record_outcome_from_verification(
        self,
        tenant_id: str,
        agent_id: str,
        action_type: str,
        outcome: str,
        verification: object,  # VerificationResult — avoid circular import
        human_decision: Optional[str] = None,
        risk_bucket: str = "default",
        action_id: Optional[str] = None,
        schedule_delayed: bool = False,
    ) -> None:
        """Primary entry point: update trust from a VerificationResult.

        Enforces the epistemic boundary:
          - source_type="agent_claim" → risk estimation only, no trust update
          - source_type="observation" → full trust update using verification.confidence
          - verification.deferred=True → schedules pending_outcome, no immediate vc update
          - verification.status=POISONED → penalise verifier_trust, treat as FAILED
        """
        _source_type = getattr(verification, "source_type", "observation")

        # Agent claims never touch trust — they are prior-shaping only
        if _source_type == "agent_claim":
            return

        # Unknown = no verifier registered; freeze trust (no update), route to pending.
        # Cannot apply vc=0.0 here — that triggers a negative signal which is incorrect:
        # absence of a verifier is not evidence of failure.
        if _source_type == "unknown":
            if action_id:
                _tid = tenant_id or ""
                _now = time.time()
                with self._lock, self._conn() as conn:
                    conn.execute(
                        "INSERT OR IGNORE INTO pending_outcomes "
                        "(tenant_id,agent_id,action_id,action_type,risk_bucket,initial_outcome,"
                        "trust_at_record,check_at_1h,check_at_24h,check_at_7d,created_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            _tid, agent_id, action_id, action_type,
                            risk_bucket, outcome, 0.50,
                            _now + 3600, _now + 86400, _now + 604800, _now,
                        ),
                    )
            return

        # Unpack via getattr to avoid circular import on the type
        _v_status      = getattr(getattr(verification, "status",       None), "value", "") or ""
        _v_deferred    = getattr(verification, "deferred",    False)
        _v_confidence  = float(getattr(verification, "confidence", 0.0))
        _v_disagreements: list[str] = list(getattr(verification, "disagreements", []))
        _v_disagreement_score = float(getattr(verification, "disagreement_score", 0.0))

        if _v_status == "poisoned":
            for vid in _v_disagreements:
                self.update_verifier_trust(tenant_id, vid, was_correct=False)
            vc = 0.0
        elif _v_status == "failed":
            vc = 0.0
        elif _v_deferred:
            self.record_outcome(
                tenant_id=tenant_id, agent_id=agent_id,
                action_type=action_type, outcome=outcome,
                verification_confidence=0.0,
                human_decision=human_decision,
                risk_bucket=risk_bucket,
                action_id=action_id,
                schedule_delayed=True,
            )
            return
        else:
            # Patch C: disagreement_score attenuates trust update.
            # High cross-source disagreement means the aggregate confidence cannot be trusted —
            # cap the damage at 50% reduction so a single noisy source can't zero out vc.
            vc = _v_confidence * (1.0 - min(0.50, _v_disagreement_score))

        self.record_outcome(
            tenant_id=tenant_id, agent_id=agent_id,
            action_type=action_type, outcome=outcome,
            verification_confidence=vc,
            human_decision=human_decision,
            risk_bucket=risk_bucket,
            action_id=action_id,
            schedule_delayed=schedule_delayed,
        )

    def record_escalation_decision(
        self, tenant_id: str, agent_id: str, decision: str,
    ) -> None:
        self.record_outcome(
            tenant_id=tenant_id, agent_id=agent_id,
            action_type="__escalation__",
            outcome="success" if decision == "allow" else "failure",
            verification_confidence=1.0,
            human_decision=decision,
        )

    def verdict_from_trust(self, trust: TrustScore) -> str:
        if trust.hard_blocked:
            return "BLOCK"
        if trust.cold_start:
            return "COLD_START"
        if trust.effective_trust > trust.effective_allow_threshold:
            return "ALLOW"
        if trust.effective_trust > trust.effective_block_threshold:
            return "ESCALATE"
        return "BLOCK"

    def summary(self, tenant_id: str) -> dict:
        _tid = tenant_id or ""
        now  = time.time()
        with self._lock, self._conn() as conn:
            agents = conn.execute(
                "SELECT agent_id, score, outcomes, successes, last_updated, "
                "escalation_approvals, escalation_denials "
                "FROM agent_trust WHERE tenant_id=? ORDER BY score DESC",
                (_tid,),
            ).fetchall()
            tools = conn.execute(
                "SELECT tool, op, score, outcomes, incidents, last_updated "
                "FROM tool_trust WHERE tenant_id=? ORDER BY score ASC LIMIT 20",
                (_tid,),
            ).fetchall()
            cb = self._circuit_breaker_active(conn, _tid)
        result_agents = []
        for r in agents:
            raw = float(r["score"])
            ts  = float(r["last_updated"])
            dec = self._apply_decay(raw, ts)
            eff, conf = self._apply_confidence(dec, int(r["outcomes"]))
            at, bt = self._adaptive_thresholds(
                int(r["escalation_approvals"]), int(r["escalation_denials"])
            )
            result_agents.append({
                "agent_id":        r["agent_id"],
                "score_raw":       round(raw, 4),
                "score_effective": round(eff, 4),
                "confidence":      round(conf, 4),
                "outcomes":        int(r["outcomes"]),
                "allow_threshold": at,
                "block_threshold": bt,
                "days_stale":      round((now - ts) / 86400, 1) if ts > 0 else None,
            })
        return {
            "tenant_id": tenant_id,
            "circuit_breaker_active": cb,
            "agents": result_agents,
            "tools":  [dict(r) for r in tools],
        }


# ── Singleton ──────────────────────────────────────────────────────────────────

_engine: Optional[TrustEngine] = None
_engine_lock = threading.Lock()


def get_trust_engine() -> TrustEngine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = TrustEngine()
    return _engine
