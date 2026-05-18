"""Fleet-level cross-tenant attack campaign detector.

Attackers probe across tenants before exploiting locally. This module tracks
action fingerprints globally and surfaces coordinated campaigns:

  "10 tenants saw the same credential.read → email.send sequence this hour"

Fingerprint: rolling hash of the last _SEQ_LEN action_types for an agent.
  - Same fingerprint across N tenants in a window = campaign signal.
  - Fingerprint is tenant-isolated at record time but queried globally.

Campaign signal levels:
  none      → single-tenant, normal
  watch     → 2–3 tenants, same fingerprint, last 24h
  suspected → 4–9 tenants OR 3+ tenants in last 1h
  confirmed → 10+ tenants in any window

SQLite because fingerprint matching is simple set queries.
The global table is cross-tenant by design — that's the point.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

_DB_PATH          = os.getenv("EDON_FLEET_DB", "fleet.db")
_SEQ_LEN          = int(os.getenv("EDON_FLEET_SEQ_LEN", "5"))   # how many actions form a fingerprint
_WINDOW_HOURS     = float(os.getenv("EDON_FLEET_WINDOW_H", "24"))
_WATCH_THRESHOLD  = 2
_SUSPECT_THRESHOLD = 4
_CONFIRM_THRESHOLD = 10
_PRUNE_INTERVAL   = 3600   # prune once per hour


def _fingerprint(action_sequence: list[str]) -> str:
    """SHA-256 of JSON-encoded action sequence, hex-truncated to 16 chars."""
    raw = json.dumps(action_sequence, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class CampaignSignal:
    fingerprint:       str
    threat_level:      str                # "none" | "watch" | "suspected" | "confirmed"
    matched_tenants:   int
    matched_agents:    int
    sample_action_seq: list[str]          # the sequence that matched
    window_h:          float
    reason:            str
    top_tenants:       list[str] = field(default_factory=list)  # up to 3 example tenant_ids

    @property
    def is_threat(self) -> bool:
        return self.threat_level != "none"


class CampaignDetector:
    """Global cross-tenant fingerprint tracker."""

    def __init__(self, db_path: str = _DB_PATH) -> None:
        self._db_path = db_path
        self._lock    = threading.Lock()
        self._mem_conn: Optional[sqlite3.Connection] = None
        self._last_prune = 0.0
        # In-memory rolling sequence per (tenant_id, agent_id)
        self._sequences: dict[tuple[str, str], list[str]] = {}
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
                CREATE TABLE IF NOT EXISTS fleet_fingerprints (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id    TEXT NOT NULL,
                    agent_id     TEXT NOT NULL,
                    fingerprint  TEXT NOT NULL,
                    action_seq   TEXT NOT NULL,
                    ts           REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_fleet_fp
                    ON fleet_fingerprints (fingerprint, ts DESC);
                CREATE INDEX IF NOT EXISTS idx_fleet_tenant
                    ON fleet_fingerprints (tenant_id, ts DESC);
            """)

    def record(
        self,
        tenant_id:   str,
        agent_id:    str,
        action_type: str,
    ) -> None:
        """Record an action and update the rolling fingerprint for this agent."""
        key = (tenant_id or "", agent_id)
        with self._lock:
            seq = self._sequences.get(key, [])
            seq = (seq + [action_type])[-_SEQ_LEN:]
            self._sequences[key] = seq

            if len(seq) < _SEQ_LEN:
                return  # not enough history yet

            fp  = _fingerprint(seq)
            now = time.time()
            conn = self._conn()
            conn.execute(
                "INSERT INTO fleet_fingerprints (tenant_id, agent_id, fingerprint, action_seq, ts) "
                "VALUES (?,?,?,?,?)",
                (tenant_id or "", agent_id, fp, json.dumps(seq), now),
            )
            conn.commit()
            self._maybe_prune(conn, now)

    def detect(
        self,
        tenant_id:   str,
        agent_id:    str,
        action_type: str,
        window_h:    Optional[float] = None,
    ) -> CampaignSignal:
        """Check if the current agent's fingerprint matches a cross-tenant pattern.

        Computes the prospective fingerprint (what it would be IF this action
        is appended) and queries for matches across other tenants.
        """
        _win    = window_h or _WINDOW_HOURS
        _cutoff = time.time() - _win * 3600
        _tid    = tenant_id or ""

        key = (_tid, agent_id)
        with self._lock:
            seq = self._sequences.get(key, [])

        prospective = (seq + [action_type])[-_SEQ_LEN:]
        if len(prospective) < _SEQ_LEN:
            return CampaignSignal(
                fingerprint="", threat_level="none",
                matched_tenants=0, matched_agents=0,
                sample_action_seq=prospective, window_h=_win,
                reason="insufficient_sequence_history",
            )

        fp = _fingerprint(prospective)

        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT tenant_id, agent_id, action_seq FROM fleet_fingerprints "
                "WHERE fingerprint=? AND ts >= ? AND tenant_id != ? "
                "GROUP BY tenant_id, agent_id "
                "ORDER BY MAX(ts) DESC LIMIT 50",
                (fp, _cutoff, _tid),
            ).fetchall()

        if not rows:
            return CampaignSignal(
                fingerprint=fp, threat_level="none",
                matched_tenants=0, matched_agents=0,
                sample_action_seq=prospective, window_h=_win,
                reason="no_cross_tenant_matches",
            )

        matched_tenants = len(set(r["tenant_id"] for r in rows))
        matched_agents  = len(set(f"{r['tenant_id']}:{r['agent_id']}" for r in rows))
        top_tenants     = list(set(r["tenant_id"] for r in rows))[:3]

        # Also check short-window (1h) for urgency
        cutoff_1h = time.time() - 3600
        with self._lock, self._conn() as conn:
            recent_rows = conn.execute(
                "SELECT tenant_id FROM fleet_fingerprints "
                "WHERE fingerprint=? AND ts >= ? AND tenant_id != ? "
                "GROUP BY tenant_id",
                (fp, cutoff_1h, _tid),
            ).fetchall()
        recent_tenant_count = len(set(r["tenant_id"] for r in recent_rows))

        if matched_tenants >= _CONFIRM_THRESHOLD:
            level = "confirmed"
            reason = f"fingerprint matched {matched_tenants} tenants in {_win}h window"
        elif matched_tenants >= _SUSPECT_THRESHOLD or recent_tenant_count >= 3:
            level = "suspected"
            reason = (
                f"fingerprint matched {matched_tenants} tenants ({recent_tenant_count} in last 1h)"
            )
        elif matched_tenants >= _WATCH_THRESHOLD:
            level = "watch"
            reason = f"fingerprint matched {matched_tenants} tenants in {_win}h window"
        else:
            level = "none"
            reason = f"single cross-tenant match — insufficient for campaign signal"

        return CampaignSignal(
            fingerprint=fp,
            threat_level=level,
            matched_tenants=matched_tenants,
            matched_agents=matched_agents,
            sample_action_seq=prospective,
            window_h=_win,
            reason=reason,
            top_tenants=top_tenants,
        )

    def _maybe_prune(self, conn: sqlite3.Connection, now: float) -> None:
        if now - self._last_prune < _PRUNE_INTERVAL:
            return
        cutoff = now - (_WINDOW_HOURS * 2) * 3600
        conn.execute("DELETE FROM fleet_fingerprints WHERE ts < ?", (cutoff,))
        self._last_prune = now

    def fleet_stats(self, window_h: Optional[float] = None) -> dict:
        """Return top fingerprints by tenant spread — useful for monitoring."""
        _win    = window_h or _WINDOW_HOURS
        cutoff  = time.time() - _win * 3600
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT fingerprint, action_seq, COUNT(DISTINCT tenant_id) AS tenant_count, "
                "COUNT(DISTINCT agent_id) AS agent_count "
                "FROM fleet_fingerprints WHERE ts >= ? "
                "GROUP BY fingerprint ORDER BY tenant_count DESC LIMIT 20",
                (cutoff,),
            ).fetchall()
        return {
            "window_h": _win,
            "top_patterns": [
                {
                    "fingerprint":    r["fingerprint"],
                    "action_seq":     json.loads(r["action_seq"]),
                    "tenant_count":   r["tenant_count"],
                    "agent_count":    r["agent_count"],
                    "threat_level": (
                        "confirmed" if r["tenant_count"] >= _CONFIRM_THRESHOLD
                        else "suspected" if r["tenant_count"] >= _SUSPECT_THRESHOLD
                        else "watch" if r["tenant_count"] >= _WATCH_THRESHOLD
                        else "none"
                    ),
                }
                for r in rows
            ],
        }


# ── Singleton ──────────────────────────────────────────────────────────────────

_detector: Optional[CampaignDetector] = None
_detector_lock = threading.Lock()


def get_campaign_detector() -> CampaignDetector:
    global _detector
    if _detector is None:
        with _detector_lock:
            if _detector is None:
                _detector = CampaignDetector()
    return _detector
