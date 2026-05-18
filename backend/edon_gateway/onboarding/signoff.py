"""Go-live signoff gate.

The client explicitly approves the governance scope before enforcement activates.
After signoff:
  - hard safety policies become immutable (cannot be changed via API)
  - shadow mode is replaced by active enforcement
  - the signoff record is append-only (no updates, only new signoffs)

This is the "moment of truth" in the onboarding flow. Nothing goes live
without an explicit named human approval.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, UTC
from typing import Optional

from ..logging_config import get_logger

logger = get_logger(__name__)

_DB_PATH = os.getenv("EDON_ONBOARDING_DB", "onboarding.db")


@dataclass
class SignoffRequest:
    signoff_id: str
    profile_id: str
    tenant_id: str
    requested_at: str
    requested_by: str

    # What the client is explicitly approving
    enforcement_scope: list[str]    # agent system names in scope
    escalation_rules_accepted: bool
    kill_switch_authority: str      # who can trigger kill switch
    data_classes_governed: list[str]
    policy_count_hard_safety: int
    policy_count_operational: int
    policy_count_intent_contracts: int

    # Resolution
    status: str = "pending"         # "pending" | "approved" | "rejected"
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None
    rejection_reason: Optional[str] = None

    def as_dict(self) -> dict:
        return asdict(self)


class SignoffStore:
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
                CREATE TABLE IF NOT EXISTS signoffs (
                    signoff_id   TEXT PRIMARY KEY,
                    profile_id   TEXT NOT NULL,
                    tenant_id    TEXT NOT NULL,
                    data         TEXT NOT NULL,
                    status       TEXT NOT NULL DEFAULT 'pending',
                    created_at   TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_signoffs_profile
                    ON signoffs (profile_id);
                CREATE INDEX IF NOT EXISTS idx_signoffs_tenant
                    ON signoffs (tenant_id);
            """)

    def create(
        self,
        profile_id: str,
        tenant_id: str,
        requested_by: str,
        enforcement_scope: list[str],
        escalation_rules_accepted: bool,
        kill_switch_authority: str,
        data_classes_governed: list[str],
        policy_count_hard_safety: int = 0,
        policy_count_operational: int = 0,
        policy_count_intent_contracts: int = 0,
    ) -> SignoffRequest:
        signoff_id = f"so-{uuid.uuid4().hex[:10]}"
        now = datetime.now(UTC).isoformat()
        sr = SignoffRequest(
            signoff_id=signoff_id,
            profile_id=profile_id,
            tenant_id=tenant_id,
            requested_at=now,
            requested_by=requested_by,
            enforcement_scope=enforcement_scope,
            escalation_rules_accepted=escalation_rules_accepted,
            kill_switch_authority=kill_switch_authority,
            data_classes_governed=data_classes_governed,
            policy_count_hard_safety=policy_count_hard_safety,
            policy_count_operational=policy_count_operational,
            policy_count_intent_contracts=policy_count_intent_contracts,
        )
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO signoffs (signoff_id, profile_id, tenant_id, data, status, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (signoff_id, profile_id, tenant_id, json.dumps(sr.as_dict()), "pending", now),
            )
        logger.info(f"[signoff] created: {signoff_id} profile={profile_id} by={requested_by}")
        return sr

    def approve(self, signoff_id: str, approved_by: str) -> Optional[SignoffRequest]:
        now = datetime.now(UTC).isoformat()
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT data FROM signoffs WHERE signoff_id=?", (signoff_id,)).fetchone()
            if row is None:
                return None
            d = json.loads(row["data"])
            d["status"] = "approved"
            d["resolved_at"] = now
            d["resolved_by"] = approved_by
            conn.execute(
                "UPDATE signoffs SET data=?, status=? WHERE signoff_id=?",
                (json.dumps(d), "approved", signoff_id),
            )
        logger.info(f"[signoff] approved: {signoff_id} by={approved_by}")
        return SignoffRequest(**d)

    def reject(self, signoff_id: str, rejected_by: str, reason: str) -> Optional[SignoffRequest]:
        now = datetime.now(UTC).isoformat()
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT data FROM signoffs WHERE signoff_id=?", (signoff_id,)).fetchone()
            if row is None:
                return None
            d = json.loads(row["data"])
            d["status"] = "rejected"
            d["resolved_at"] = now
            d["resolved_by"] = rejected_by
            d["rejection_reason"] = reason
            conn.execute(
                "UPDATE signoffs SET data=?, status=? WHERE signoff_id=?",
                (json.dumps(d), "rejected", signoff_id),
            )
        logger.info(f"[signoff] rejected: {signoff_id} by={rejected_by} reason={reason}")
        return SignoffRequest(**d)

    def get(self, signoff_id: str) -> Optional[SignoffRequest]:
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT data FROM signoffs WHERE signoff_id=?", (signoff_id,)).fetchone()
        if row is None:
            return None
        return SignoffRequest(**json.loads(row["data"]))

    def list_for_profile(self, profile_id: str) -> list[dict]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT data FROM signoffs WHERE profile_id=? ORDER BY created_at DESC",
                (profile_id,),
            ).fetchall()
        return [json.loads(r["data"]) for r in rows]

    def latest_approved(self, tenant_id: str) -> Optional[dict]:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT data FROM signoffs WHERE tenant_id=? AND status='approved' "
                "ORDER BY created_at DESC LIMIT 1",
                (tenant_id,),
            ).fetchone()
        return json.loads(row["data"]) if row else None


# ── Singleton ──────────────────────────────────────────────────────────────────

_store: Optional[SignoffStore] = None
_store_lock = threading.Lock()


def get_signoff_store() -> SignoffStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = SignoffStore()
    return _store
