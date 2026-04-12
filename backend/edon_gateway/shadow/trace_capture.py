"""Component 1 — Trace capture instrumentation.

Captures agent action evaluation traces from the /v1/action pipeline.
Stores inputs (action_payload, context, action_type) and outputs
(verdict, reason, latency) so they can be replayed under perturbation.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Optional

from ..logging_config import get_logger

logger = get_logger(__name__)

# ── Data model ─────────────────────────────────────────────────────────────────


@dataclass
class AgentTrace:
    """Snapshot of a single agent action evaluation — inputs + governance outputs."""

    trace_id: str
    captured_at: str            # ISO-8601
    agent_id: str
    tenant_id: Optional[str]
    action_type: str            # e.g. "email.send"
    action_payload: dict
    context: dict               # full request context (sans sensitive keys)
    timestamp: str              # original ISO request timestamp
    intent_id: Optional[str]
    # Original evaluation outputs
    original_verdict: str
    original_reason: str
    original_latency_ms: int
    original_meta: dict = field(default_factory=dict)

    @classmethod
    def from_action_request(
        cls,
        *,
        agent_id: str,
        tenant_id: Optional[str],
        action_type: str,
        action_payload: dict,
        context: dict,
        timestamp: str,
        intent_id: Optional[str],
        verdict: str,
        reason: str,
        latency_ms: int,
        meta: dict | None = None,
    ) -> "AgentTrace":
        # Strip keys that would make replay non-deterministic or leak secrets
        safe_context = {
            k: v for k, v in context.items()
            if k not in ("api_key", "token", "secret", "password", "credential")
        }
        return cls(
            trace_id=str(uuid.uuid4()),
            captured_at=datetime.now(UTC).isoformat(),
            agent_id=agent_id,
            tenant_id=tenant_id,
            action_type=action_type,
            action_payload=dict(action_payload or {}),
            context=safe_context,
            timestamp=timestamp,
            intent_id=intent_id,
            original_verdict=verdict,
            original_reason=reason,
            original_latency_ms=latency_ms,
            original_meta=dict(meta or {}),
        )


# ── Action result model ────────────────────────────────────────────────────────


@dataclass
class ActionResult:
    """Outcome reported by an agent after executing a tool action.

    Correlates with AgentTrace via action_id (the decision_id returned by
    /v1/action). This closes the loop: EDON knows what it decided AND what
    actually happened when the tool ran.
    """

    result_id: str
    action_id: str          # decision_id from the /v1/action response
    agent_id: str
    tenant_id: Optional[str]
    action_type: str
    outcome: str            # "success" | "failure" | "partial" | "timeout"
    latency_ms: int         # tool execution time (not governance latency)
    error: Optional[str]    # error message if outcome != success
    result_summary: Optional[str]   # sanitized one-liner (max 500 chars)
    executed_at: str        # ISO-8601 — when tool ran
    reported_at: str        # ISO-8601 — when EDON received this

    @classmethod
    def build(
        cls,
        *,
        action_id: str,
        agent_id: str,
        tenant_id: Optional[str],
        action_type: str,
        outcome: str,
        latency_ms: int,
        error: Optional[str] = None,
        result_summary: Optional[str] = None,
        executed_at: str,
    ) -> "ActionResult":
        # Hard-cap summary to prevent exfil via result field
        safe_summary = (result_summary or "")[:500] or None
        return cls(
            result_id=str(uuid.uuid4()),
            action_id=action_id,
            agent_id=agent_id,
            tenant_id=tenant_id,
            action_type=action_type,
            outcome=outcome,
            latency_ms=latency_ms,
            error=(error or "")[:1000] or None,
            result_summary=safe_summary,
            executed_at=executed_at,
            reported_at=datetime.now(UTC).isoformat(),
        )


# ── Storage ────────────────────────────────────────────────────────────────────


class TraceStore:
    """SQLite-backed store for captured traces and shadow run results."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.getenv("EDON_SHADOW_DB_PATH", "edon_shadow.db")
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ── Internal ───────────────────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS action_results (
                    result_id       TEXT PRIMARY KEY,
                    action_id       TEXT NOT NULL,
                    agent_id        TEXT NOT NULL,
                    tenant_id       TEXT,
                    action_type     TEXT NOT NULL,
                    outcome         TEXT NOT NULL,
                    latency_ms      INTEGER NOT NULL,
                    error           TEXT,
                    result_summary  TEXT,
                    executed_at     TEXT NOT NULL,
                    reported_at     TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_action_results_action_id
                    ON action_results(action_id);

                CREATE INDEX IF NOT EXISTS idx_action_results_tenant
                    ON action_results(tenant_id, reported_at);

                CREATE INDEX IF NOT EXISTS idx_action_results_outcome
                    ON action_results(outcome, reported_at);

                CREATE TABLE IF NOT EXISTS shadow_traces (
                    trace_id           TEXT PRIMARY KEY,
                    captured_at        TEXT NOT NULL,
                    agent_id           TEXT NOT NULL,
                    tenant_id          TEXT,
                    action_type        TEXT NOT NULL,
                    action_payload     TEXT NOT NULL,   -- JSON
                    context            TEXT NOT NULL,   -- JSON
                    timestamp          TEXT NOT NULL,
                    intent_id          TEXT,
                    original_verdict   TEXT NOT NULL,
                    original_reason    TEXT NOT NULL,
                    original_latency_ms INTEGER NOT NULL,
                    original_meta      TEXT NOT NULL    -- JSON
                );

                CREATE TABLE IF NOT EXISTS shadow_results (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id            TEXT NOT NULL,
                    perturbation_name   TEXT NOT NULL,
                    perturbation_type   TEXT NOT NULL,
                    perturbed_field     TEXT,
                    shadow_verdict      TEXT NOT NULL,
                    shadow_reason       TEXT NOT NULL,
                    shadow_latency_ms   INTEGER NOT NULL,
                    verdict_changed     INTEGER NOT NULL,
                    severity            TEXT NOT NULL,
                    findings            TEXT NOT NULL,  -- JSON list
                    created_at          TEXT NOT NULL,
                    FOREIGN KEY (trace_id) REFERENCES shadow_traces(trace_id)
                );

                CREATE INDEX IF NOT EXISTS idx_shadow_results_trace
                    ON shadow_results(trace_id);

                CREATE INDEX IF NOT EXISTS idx_shadow_results_severity
                    ON shadow_results(severity, created_at);

                CREATE INDEX IF NOT EXISTS idx_shadow_traces_tenant
                    ON shadow_traces(tenant_id, captured_at);

                CREATE TABLE IF NOT EXISTS confirmed_bypasses (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_id           TEXT NOT NULL,
                    trace_id            TEXT NOT NULL,
                    agent_id            TEXT NOT NULL,
                    tenant_id           TEXT,
                    action_type         TEXT NOT NULL,
                    perturbation_name   TEXT NOT NULL,
                    perturbation_type   TEXT NOT NULL,
                    original_verdict    TEXT NOT NULL,
                    shadow_verdict      TEXT NOT NULL,
                    real_outcome        TEXT NOT NULL,
                    confirmed_at        TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_confirmed_bypasses_tenant
                    ON confirmed_bypasses(tenant_id, confirmed_at);

                CREATE TABLE IF NOT EXISTS shadow_baselines (
                    trace_id              TEXT PRIMARY KEY,
                    baseline_verdict      TEXT NOT NULL,
                    baseline_reason       TEXT NOT NULL,
                    baseline_latency_ms   INTEGER NOT NULL,
                    matches_original      INTEGER NOT NULL,
                    non_determinism_flag  INTEGER NOT NULL,
                    created_at            TEXT NOT NULL
                );
            """)

    # ── Write ──────────────────────────────────────────────────────────────────

    def save_action_result(self, result: ActionResult) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO action_results
                (result_id, action_id, agent_id, tenant_id, action_type,
                 outcome, latency_ms, error, result_summary,
                 executed_at, reported_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.result_id,
                    result.action_id,
                    result.agent_id,
                    result.tenant_id,
                    result.action_type,
                    result.outcome,
                    result.latency_ms,
                    result.error,
                    result.result_summary,
                    result.executed_at,
                    result.reported_at,
                ),
            )

    def get_action_result(self, action_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM action_results WHERE action_id = ? LIMIT 1",
                (action_id,),
            ).fetchone()
        return dict(row) if row else None

    def outcome_stats(self, tenant_id: Optional[str] = None) -> dict:
        """Return outcome counts — useful for policy tuning dashboard."""
        with self._conn() as conn:
            if tenant_id:
                rows = conn.execute(
                    "SELECT outcome, COUNT(*) as cnt FROM action_results "
                    "WHERE tenant_id = ? GROUP BY outcome",
                    (tenant_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT outcome, COUNT(*) as cnt FROM action_results GROUP BY outcome"
                ).fetchall()
        totals: dict = {"success": 0, "failure": 0, "partial": 0, "timeout": 0}
        for row in rows:
            totals[row["outcome"]] = row["cnt"]
        return totals

    def save_baseline(self, baseline: Any) -> None:
        """Persist a BaselineResult (imported lazily to avoid circular deps)."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO shadow_baselines
                (trace_id, baseline_verdict, baseline_reason, baseline_latency_ms,
                 matches_original, non_determinism_flag, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    baseline.trace_id,
                    baseline.baseline_verdict,
                    baseline.baseline_reason,
                    baseline.baseline_latency_ms,
                    int(baseline.matches_original),
                    int(baseline.non_determinism_flag),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def get_baseline(self, trace_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM shadow_baselines WHERE trace_id = ? LIMIT 1",
                (trace_id,),
            ).fetchone()
        return dict(row) if row else None

    def save_confirmed_bypass(
        self,
        *,
        action_id: str,
        trace_id: str,
        agent_id: str,
        tenant_id: Optional[str],
        action_type: str,
        perturbation_name: str,
        perturbation_type: str,
        original_verdict: str,
        shadow_verdict: str,
        real_outcome: str,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO confirmed_bypasses
                (action_id, trace_id, agent_id, tenant_id, action_type,
                 perturbation_name, perturbation_type, original_verdict,
                 shadow_verdict, real_outcome, confirmed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action_id, trace_id, agent_id, tenant_id, action_type,
                    perturbation_name, perturbation_type, original_verdict,
                    shadow_verdict, real_outcome, datetime.now(UTC).isoformat(),
                ),
            )

    def get_confirmed_bypasses(
        self,
        tenant_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        with self._conn() as conn:
            if tenant_id:
                rows = conn.execute(
                    "SELECT * FROM confirmed_bypasses WHERE tenant_id = ? "
                    "ORDER BY confirmed_at DESC LIMIT ?",
                    (tenant_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM confirmed_bypasses ORDER BY confirmed_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    def non_determinism_count(self, tenant_id: Optional[str] = None) -> int:
        """How many traces have produced a different verdict on re-evaluation."""
        with self._conn() as conn:
            if tenant_id:
                row = conn.execute(
                    """
                    SELECT COUNT(*) FROM shadow_baselines b
                    JOIN shadow_traces t ON b.trace_id = t.trace_id
                    WHERE b.non_determinism_flag = 1 AND t.tenant_id = ?
                    """,
                    (tenant_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM shadow_baselines WHERE non_determinism_flag = 1"
                ).fetchone()
        return row[0] if row else 0

    def save_trace(self, trace: AgentTrace) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO shadow_traces
                (trace_id, captured_at, agent_id, tenant_id, action_type,
                 action_payload, context, timestamp, intent_id,
                 original_verdict, original_reason, original_latency_ms, original_meta)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace.trace_id,
                    trace.captured_at,
                    trace.agent_id,
                    trace.tenant_id,
                    trace.action_type,
                    json.dumps(trace.action_payload),
                    json.dumps(trace.context),
                    trace.timestamp,
                    trace.intent_id,
                    trace.original_verdict,
                    trace.original_reason,
                    trace.original_latency_ms,
                    json.dumps(trace.original_meta),
                ),
            )

    def save_result(self, result: Any) -> None:
        """Persist a ShadowRunResult (imported lazily to avoid circular deps)."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO shadow_results
                (trace_id, perturbation_name, perturbation_type, perturbed_field,
                 shadow_verdict, shadow_reason, shadow_latency_ms,
                 verdict_changed, severity, findings, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.trace_id,
                    result.perturbation_name,
                    result.perturbation_type,
                    result.perturbed_field,
                    result.shadow_verdict,
                    result.shadow_reason,
                    result.shadow_latency_ms,
                    int(result.verdict_changed),
                    result.severity,
                    json.dumps(result.findings),
                    datetime.now(UTC).isoformat(),
                ),
            )

    # ── Read ───────────────────────────────────────────────────────────────────

    def get_recent_traces(
        self,
        tenant_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[AgentTrace]:
        with self._conn() as conn:
            if tenant_id:
                rows = conn.execute(
                    "SELECT * FROM shadow_traces WHERE tenant_id = ? "
                    "ORDER BY captured_at DESC LIMIT ?",
                    (tenant_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM shadow_traces ORDER BY captured_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()

        return [
            AgentTrace(
                trace_id=r["trace_id"],
                captured_at=r["captured_at"],
                agent_id=r["agent_id"],
                tenant_id=r["tenant_id"],
                action_type=r["action_type"],
                action_payload=json.loads(r["action_payload"]),
                context=json.loads(r["context"]),
                timestamp=r["timestamp"],
                intent_id=r["intent_id"],
                original_verdict=r["original_verdict"],
                original_reason=r["original_reason"],
                original_latency_ms=r["original_latency_ms"],
                original_meta=json.loads(r["original_meta"]),
            )
            for r in rows
        ]

    def recent_findings(
        self,
        tenant_id: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        with self._conn() as conn:
            clauses = ["1=1"]
            params: list[Any] = []

            if tenant_id:
                clauses.append("t.tenant_id = ?")
                params.append(tenant_id)
            if severity:
                clauses.append("r.severity = ?")
                params.append(severity)

            where = " AND ".join(clauses)
            params.append(limit)

            rows = conn.execute(
                f"""
                SELECT r.*, t.agent_id, t.tenant_id, t.action_type,
                       t.original_verdict AS trace_original_verdict
                FROM shadow_results r
                JOIN shadow_traces t ON r.trace_id = t.trace_id
                WHERE {where}
                ORDER BY r.created_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()

        results = []
        for row in rows:
            d = dict(row)
            d["findings"] = json.loads(d.get("findings") or "[]")
            results.append(d)
        return results

    def get_session_traces(
        self,
        session_id: str,
        tenant_id: Optional[str] = None,
    ) -> list[AgentTrace]:
        """Return all traces for a session, ordered by capture time (oldest first)."""
        with self._conn() as conn:
            if tenant_id:
                rows = conn.execute(
                    """
                    SELECT * FROM shadow_traces
                    WHERE json_extract(context, '$.session_id') = ?
                      AND tenant_id = ?
                    ORDER BY captured_at ASC
                    """,
                    (session_id, tenant_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM shadow_traces
                    WHERE json_extract(context, '$.session_id') = ?
                    ORDER BY captured_at ASC
                    """,
                    (session_id,),
                ).fetchall()

        return [
            AgentTrace(
                trace_id=r["trace_id"],
                captured_at=r["captured_at"],
                agent_id=r["agent_id"],
                tenant_id=r["tenant_id"],
                action_type=r["action_type"],
                action_payload=json.loads(r["action_payload"]),
                context=json.loads(r["context"]),
                timestamp=r["timestamp"],
                intent_id=r["intent_id"],
                original_verdict=r["original_verdict"],
                original_reason=r["original_reason"],
                original_latency_ms=r["original_latency_ms"],
                original_meta=json.loads(r["original_meta"]),
            )
            for r in rows
        ]

    def finding_summary(self, tenant_id: Optional[str] = None) -> dict:
        """Return count breakdown by severity for dashboard display."""
        with self._conn() as conn:
            if tenant_id:
                rows = conn.execute(
                    """
                    SELECT r.severity, COUNT(*) as cnt
                    FROM shadow_results r
                    JOIN shadow_traces t ON r.trace_id = t.trace_id
                    WHERE t.tenant_id = ?
                    GROUP BY r.severity
                    """,
                    (tenant_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT severity, COUNT(*) as cnt FROM shadow_results GROUP BY severity"
                ).fetchall()

        totals = {"stable": 0, "advisory": 0, "critical": 0}
        for row in rows:
            totals[row["severity"]] = row["cnt"]
        return totals


# ── Module-level singleton ─────────────────────────────────────────────────────

_store: Optional[TraceStore] = None


def get_trace_store() -> TraceStore:
    global _store
    if _store is None:
        _store = TraceStore()
    return _store


def capture_trace(
    *,
    agent_id: str,
    tenant_id: Optional[str],
    action_type: str,
    action_payload: dict,
    context: dict,
    timestamp: str,
    intent_id: Optional[str],
    verdict: str,
    reason: str,
    latency_ms: int,
    meta: dict | None = None,
) -> AgentTrace:
    """Build and persist an AgentTrace from /v1/action evaluation data.

    Returns the saved trace so the caller can pass it directly to shadow_run_trace.
    """
    trace = AgentTrace.from_action_request(
        agent_id=agent_id,
        tenant_id=tenant_id,
        action_type=action_type,
        action_payload=action_payload,
        context=context,
        timestamp=timestamp,
        intent_id=intent_id,
        verdict=verdict,
        reason=reason,
        latency_ms=latency_ms,
        meta=meta,
    )
    try:
        get_trace_store().save_trace(trace)
    except Exception as exc:
        logger.warning("[shadow] trace save failed (non-blocking): %s", exc)
    return trace
