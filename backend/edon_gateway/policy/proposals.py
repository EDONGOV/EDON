"""Policy proposal queue — decouples ADAPT from direct policy mutation.

Structural invariant: the system being governed cannot directly modify
the policy that governs it. ADAPT submits proposals. A separate authority
(human reviewer or external read-only verifier) applies them.

Flow:
    ADAPT → submit_proposal()         → status="pending"
    Human / route → apply_proposal()  → calls db.create_policy_rule()
                  → reject_proposal() → status="rejected", reason logged

This creates a durable audit trail of every auto-generated policy change,
with explicit approval provenance on each applied rule.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Optional

_DB_PATH = os.getenv("EDON_PROPOSALS_DB", "proposals.db")


@dataclass
class PolicyProposal:
    proposal_id:      str
    tenant_id:        str
    source:           str          # "adapt_threshold" | "adapt_ai_suggestion" | "adapt_drift"
    action:           str          # "ALLOW" | "BLOCK" | "ESCALATE"
    name:             str
    description:      str
    condition_tool:   Optional[str]
    condition_op:     Optional[str]
    priority:         int
    rationale:        str          # why ADAPT proposed this
    evidence:         str          # supporting data (precision%, sample count, etc.)
    confidence_tier:  str          # "low" | "medium" | "high"
    status:           str          # "pending" | "applied" | "rejected" | "expired"
    created_at:       float
    reviewed_at:      Optional[float]
    reviewed_by:      Optional[str]
    reject_reason:    Optional[str]
    sla_deadline:     Optional[float]   # unix ts by which review is expected


def _compute_confidence_tier(evidence: str, source: str) -> str:
    """Derive tier from evidence string heuristics.

    high:   circuit_breaker in source, or evidence contains sample count ≥ 200
    medium: sample count 50–199, or source is adapt_threshold
    low:    everything else
    """
    if "circuit_breaker" in source:
        return "high"
    import re
    nums = [int(n) for n in re.findall(r"\d+", evidence)]
    sample = max(nums) if nums else 0
    if sample >= 200:
        return "high"
    if sample >= 50 or source == "adapt_threshold":
        return "medium"
    return "low"


# SLA windows by tier (seconds)
_SLA_SECONDS: dict[str, int] = {
    "high":   int(os.getenv("EDON_PROPOSAL_SLA_HIGH_H",   "24")) * 3600,
    "medium": int(os.getenv("EDON_PROPOSAL_SLA_MED_H",    "72")) * 3600,
    "low":    int(os.getenv("EDON_PROPOSAL_SLA_LOW_H",   "168")) * 3600,  # 7 days
}


class ProposalStore:
    """SQLite-backed store for ADAPT-generated policy proposals.

    Intentionally separate from the main trust.db and the tenant policy DB —
    proposals live in their own store so they can be reviewed independently.
    """

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
                CREATE TABLE IF NOT EXISTS policy_proposals (
                    proposal_id     TEXT PRIMARY KEY,
                    tenant_id       TEXT NOT NULL,
                    source          TEXT NOT NULL,
                    action          TEXT NOT NULL,
                    name            TEXT NOT NULL,
                    description     TEXT NOT NULL,
                    condition_tool  TEXT,
                    condition_op    TEXT,
                    priority        INTEGER NOT NULL DEFAULT 500,
                    rationale       TEXT NOT NULL,
                    evidence        TEXT NOT NULL DEFAULT '',
                    confidence_tier TEXT NOT NULL DEFAULT 'low',
                    status          TEXT NOT NULL DEFAULT 'pending',
                    created_at      REAL NOT NULL,
                    reviewed_at     REAL,
                    reviewed_by     TEXT,
                    reject_reason   TEXT,
                    sla_deadline    REAL
                );
                CREATE INDEX IF NOT EXISTS idx_proposals_tenant_status
                    ON policy_proposals (tenant_id, status, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_proposals_sla
                    ON policy_proposals (status, sla_deadline);
            """)

    def submit(
        self,
        tenant_id:      str,
        source:         str,
        action:         str,
        name:           str,
        description:    str,
        rationale:      str,
        condition_tool: Optional[str] = None,
        condition_op:   Optional[str] = None,
        priority:       int = 500,
        evidence:       str = "",
    ) -> str:
        """Submit a proposal. Returns proposal_id."""
        pid   = str(uuid.uuid4())
        now   = time.time()
        tier  = _compute_confidence_tier(evidence, source)
        sla   = now + _SLA_SECONDS[tier]
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO policy_proposals "
                "(proposal_id,tenant_id,source,action,name,description,"
                "condition_tool,condition_op,priority,rationale,evidence,"
                "confidence_tier,status,created_at,sla_deadline) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid, tenant_id or "", source, action, name, description,
                 condition_tool, condition_op, priority, rationale, evidence,
                 tier, "pending", now, sla),
            )
        return pid

    def list_pending(self, tenant_id: Optional[str] = None, limit: int = 50) -> list[dict]:
        # Auto-expire stale proposals on every list call (cheap — uses index)
        self.expire_old()
        with self._lock, self._conn() as conn:
            if tenant_id:
                rows = conn.execute(
                    "SELECT * FROM policy_proposals WHERE status='pending' AND tenant_id=? "
                    "ORDER BY confidence_tier DESC, sla_deadline ASC LIMIT ?",
                    (tenant_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM policy_proposals WHERE status='pending' "
                    "ORDER BY confidence_tier DESC, sla_deadline ASC LIMIT ?",
                    (limit,),
                ).fetchall()
        now = time.time()
        result = []
        for r in rows:
            d = dict(r)
            sla = d.get("sla_deadline")
            d["sla_breached"] = bool(sla and sla < now)
            d["sla_remaining_h"] = round((sla - now) / 3600, 1) if sla else None
            result.append(d)
        return result

    def sla_breached(self, tenant_id: Optional[str] = None) -> list[dict]:
        """Return all pending proposals that have exceeded their SLA deadline."""
        now = time.time()
        with self._lock, self._conn() as conn:
            if tenant_id:
                rows = conn.execute(
                    "SELECT * FROM policy_proposals "
                    "WHERE status='pending' AND sla_deadline < ? AND tenant_id=? "
                    "ORDER BY sla_deadline ASC",
                    (now, tenant_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM policy_proposals "
                    "WHERE status='pending' AND sla_deadline < ? "
                    "ORDER BY sla_deadline ASC",
                    (now,),
                ).fetchall()
        return [dict(r) for r in rows]

    def batch_apply(self, proposal_ids: list[str], reviewed_by: str, db) -> dict[str, bool]:
        """Apply multiple proposals in one call. Returns {proposal_id: success}."""
        results = {}
        for pid in proposal_ids:
            results[pid] = self.apply(pid, reviewed_by, db)
        return results

    def batch_reject(self, proposal_ids: list[str], reviewed_by: str, reason: str) -> dict[str, bool]:
        """Reject multiple proposals in one call. Returns {proposal_id: success}."""
        results = {}
        for pid in proposal_ids:
            results[pid] = self.reject(pid, reviewed_by, reason)
        return results

    def list_all(self, tenant_id: str, limit: int = 100) -> list[dict]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM policy_proposals WHERE tenant_id=? "
                "ORDER BY created_at DESC LIMIT ?",
                (tenant_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get(self, proposal_id: str) -> Optional[dict]:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM policy_proposals WHERE proposal_id=?",
                (proposal_id,),
            ).fetchone()
        return dict(row) if row else None

    def apply(self, proposal_id: str, reviewed_by: str, db) -> bool:
        """Apply a pending proposal by calling db.create_policy_rule().

        This is the ONLY path that converts a proposal into a live policy rule.
        The `db` arg is the tenant database — passed in so this module has no
        import dependency on the persistence layer.

        Returns True if applied, False if already applied/rejected/not found.
        """
        proposal = self.get(proposal_id)
        if not proposal or proposal["status"] != "pending":
            return False
        if not proposal["tenant_id"]:
            return False

        db.create_policy_rule(
            tenant_id=proposal["tenant_id"],
            name=proposal["name"],
            description=f"{proposal['description']} [proposal:{proposal_id}]",
            action=proposal["action"],
            condition_tool=proposal["condition_tool"],
            condition_op=proposal["condition_op"],
            priority=proposal["priority"],
            enabled=True,
        )

        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE policy_proposals SET status='applied', reviewed_at=?, reviewed_by=? "
                "WHERE proposal_id=?",
                (time.time(), reviewed_by, proposal_id),
            )
        return True

    def reject(self, proposal_id: str, reviewed_by: str, reason: str) -> bool:
        proposal = self.get(proposal_id)
        if not proposal or proposal["status"] != "pending":
            return False
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE policy_proposals SET status='rejected', reviewed_at=?, "
                "reviewed_by=?, reject_reason=? WHERE proposal_id=?",
                (time.time(), reviewed_by, reason, proposal_id),
            )
        return True

    def expire_old(self, max_age_days: int = 7) -> int:
        """Expire proposals older than max_age_days that are still pending."""
        cutoff = time.time() - max_age_days * 86400
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                "UPDATE policy_proposals SET status='expired' "
                "WHERE status='pending' AND created_at < ?",
                (cutoff,),
            )
            return cur.rowcount


# ── Singleton ──────────────────────────────────────────────────────────────────

_store: Optional[ProposalStore] = None
_store_lock = threading.Lock()


def get_proposal_store() -> ProposalStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = ProposalStore()
    return _store
