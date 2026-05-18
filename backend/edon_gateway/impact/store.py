"""EDON Impact — persistence layer.

SQLite-backed store for the execution graph, failure states, red team scenarios,
and validation results. Separate from the shadow trace store to keep concerns clean.

All reads/writes are synchronous and thread-safe. Async callers use asyncio.to_thread.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import asdict
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional, Any

from .schemas import (
    AgentNode, ToolNode, ExecutionEdge, FailureState,
    RedTeamScenario, ValidationResult, CoverageSnapshot,
)
from ..logging_config import get_logger

logger = get_logger(__name__)

_store_singleton: Optional["ImpactStore"] = None
_store_lock = threading.Lock()


def _db_path() -> Path:
    env = os.getenv("EDON_IMPACT_DB_PATH", "").strip()
    if env:
        p = Path(env)
    else:
        base_url = os.getenv("EDON_DB_URL", "").strip()
        if base_url.startswith("sqlite:///"):
            p = Path(base_url.replace("sqlite:///", "", 1)).parent / "impact.db"
        else:
            p = Path("/tmp/edon_data/impact.db")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


class ImpactStore:
    """Thread-safe SQLite store for all Impact engine data."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._path = Path(db_path) if db_path else _db_path()
        self._local = threading.local()
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(str(self._path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return self._local.conn

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS impact_agents (
                    agent_id        TEXT NOT NULL,
                    tenant_id       TEXT,
                    capabilities    TEXT DEFAULT '[]',
                    first_seen      TEXT NOT NULL,
                    last_seen       TEXT NOT NULL,
                    call_count      INTEGER DEFAULT 0,
                    PRIMARY KEY (agent_id, tenant_id)
                );

                CREATE TABLE IF NOT EXISTS impact_tools (
                    tool_name       TEXT PRIMARY KEY,
                    operations      TEXT DEFAULT '[]',
                    data_classes    TEXT DEFAULT '[]',
                    is_external_sink INTEGER DEFAULT 0,
                    system_type     TEXT DEFAULT 'unknown'
                );

                CREATE TABLE IF NOT EXISTS impact_edges (
                    edge_id                     TEXT PRIMARY KEY,
                    agent_id                    TEXT NOT NULL,
                    tool_name                   TEXT NOT NULL,
                    operation                   TEXT NOT NULL,
                    tenant_id                   TEXT,
                    data_classes_in_payload     TEXT DEFAULT '[]',
                    has_policy_constraint       INTEGER DEFAULT 0,
                    has_approval_gate           INTEGER DEFAULT 0,
                    has_deidentification_gate   INTEGER DEFAULT 0,
                    verdict                     TEXT NOT NULL,
                    evidence_trace_ids          TEXT DEFAULT '[]',
                    first_seen                  TEXT NOT NULL,
                    last_seen                   TEXT NOT NULL,
                    frequency                   INTEGER DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_edges_tenant ON impact_edges(tenant_id);
                CREATE INDEX IF NOT EXISTS idx_edges_tool ON impact_edges(tool_name);

                CREATE TABLE IF NOT EXISTS impact_failure_states (
                    failure_state_id        TEXT PRIMARY KEY,
                    vulnerability_class     TEXT NOT NULL,
                    description             TEXT NOT NULL,
                    path                    TEXT DEFAULT '[]',
                    constraint_violation    TEXT NOT NULL,
                    data_classes            TEXT DEFAULT '[]',
                    is_external_sink        INTEGER DEFAULT 0,
                    evidence_trace_ids      TEXT DEFAULT '[]',
                    verified                INTEGER DEFAULT 0,
                    tenant_id               TEXT,
                    likelihood_score        REAL DEFAULT 0.0,
                    blast_radius_score      REAL DEFAULT 0.0,
                    recoverability_factor   REAL DEFAULT 1.0,
                    severity_score          REAL DEFAULT 0.0,
                    exploitability_window   TEXT DEFAULT 'session',
                    discovered_at           TEXT NOT NULL,
                    last_validated_at       TEXT,
                    mitigated_at            TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_fs_tenant ON impact_failure_states(tenant_id);
                CREATE INDEX IF NOT EXISTS idx_fs_class ON impact_failure_states(vulnerability_class);
                CREATE INDEX IF NOT EXISTS idx_fs_severity ON impact_failure_states(severity_score DESC);

                CREATE TABLE IF NOT EXISTS impact_scenarios (
                    scenario_id             TEXT PRIMARY KEY,
                    failure_state_id        TEXT NOT NULL,
                    title                   TEXT NOT NULL,
                    attack_narrative        TEXT NOT NULL,
                    attacker_type           TEXT NOT NULL,
                    attack_vector           TEXT NOT NULL,
                    impact_description      TEXT NOT NULL,
                    indicators_of_compromise TEXT DEFAULT '[]',
                    remediation_steps       TEXT DEFAULT '[]',
                    graph_path_used         TEXT DEFAULT '[]',
                    validation_status       TEXT DEFAULT 'pending',
                    generated_at            TEXT NOT NULL,
                    validated_at            TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_scenarios_fs ON impact_scenarios(failure_state_id);

                CREATE TABLE IF NOT EXISTS impact_validations (
                    result_id                   TEXT PRIMARY KEY,
                    scenario_id                 TEXT NOT NULL,
                    failure_state_id            TEXT NOT NULL,
                    status                      TEXT NOT NULL,
                    reachability_confirmed      INTEGER DEFAULT 0,
                    policy_violation_confirmed  INTEGER DEFAULT 0,
                    graph_path_confirmed        TEXT DEFAULT '[]',
                    invalidation_reason         TEXT,
                    validated_at                TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS impact_coverage (
                    snapshot_id                 TEXT PRIMARY KEY,
                    tenant_id                   TEXT,
                    agent_count                 INTEGER DEFAULT 0,
                    tool_count                  INTEGER DEFAULT 0,
                    edge_count                  INTEGER DEFAULT 0,
                    failure_state_count         INTEGER DEFAULT 0,
                    verified_failure_count      INTEGER DEFAULT 0,
                    scenario_count              INTEGER DEFAULT 0,
                    valid_scenario_count        INTEGER DEFAULT 0,
                    new_edges_since_last        INTEGER DEFAULT 0,
                    new_failure_states_since_last INTEGER DEFAULT 0,
                    captured_at                 TEXT NOT NULL
                );
            """)
            # Migrate existing DBs that predate mitigated_at column
            try:
                conn.execute("ALTER TABLE impact_failure_states ADD COLUMN mitigated_at TEXT")
                conn.commit()
            except Exception:
                pass  # column already exists

    # ── Agent nodes ────────────────────────────────────────────────────────────

    def upsert_agent(self, node: AgentNode) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO impact_agents
                    (agent_id, tenant_id, capabilities, first_seen, last_seen, call_count)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(agent_id, tenant_id) DO UPDATE SET
                    capabilities = excluded.capabilities,
                    last_seen    = excluded.last_seen,
                    call_count   = call_count + 1
                """,
                (
                    node.agent_id, node.tenant_id,
                    json.dumps(node.capabilities),
                    node.first_seen, node.last_seen, node.call_count,
                ),
            )

    def get_agents(self, tenant_id: Optional[str] = None) -> list[dict]:
        with self._conn() as conn:
            if tenant_id:
                rows = conn.execute(
                    "SELECT * FROM impact_agents WHERE tenant_id = ?", (tenant_id,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM impact_agents").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["capabilities"] = json.loads(d.get("capabilities") or "[]")
            result.append(d)
        return result

    # ── Tool nodes ─────────────────────────────────────────────────────────────

    def upsert_tool(self, node: ToolNode) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO impact_tools
                    (tool_name, operations, data_classes, is_external_sink, system_type)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(tool_name) DO UPDATE SET
                    operations      = excluded.operations,
                    data_classes    = excluded.data_classes,
                    is_external_sink = excluded.is_external_sink,
                    system_type     = excluded.system_type
                """,
                (
                    node.tool_name, json.dumps(node.operations),
                    json.dumps(node.data_classes),
                    int(node.is_external_sink), node.system_type,
                ),
            )

    def get_tools(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM impact_tools").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["operations"] = json.loads(d.get("operations") or "[]")
            d["data_classes"] = json.loads(d.get("data_classes") or "[]")
            result.append(d)
        return result

    # ── Execution edges ────────────────────────────────────────────────────────

    def upsert_edge(self, edge: ExecutionEdge) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO impact_edges
                    (edge_id, agent_id, tool_name, operation, tenant_id,
                     data_classes_in_payload, has_policy_constraint,
                     has_approval_gate, has_deidentification_gate, verdict,
                     evidence_trace_ids, first_seen, last_seen, frequency)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(edge_id) DO UPDATE SET
                    last_seen           = excluded.last_seen,
                    frequency           = frequency + 1,
                    verdict             = excluded.verdict,
                    has_approval_gate   = excluded.has_approval_gate,
                    evidence_trace_ids  = excluded.evidence_trace_ids
                """,
                (
                    edge.edge_id, edge.agent_id, edge.tool_name, edge.operation,
                    edge.tenant_id,
                    json.dumps(edge.data_classes_in_payload),
                    int(edge.has_policy_constraint), int(edge.has_approval_gate),
                    int(edge.has_deidentification_gate),
                    edge.verdict,
                    json.dumps(edge.evidence_trace_ids[-10:]),  # keep last 10 trace refs
                    edge.first_seen, edge.last_seen, edge.frequency,
                ),
            )

    def get_edges(self, tenant_id: Optional[str] = None) -> list[dict]:
        with self._conn() as conn:
            if tenant_id:
                rows = conn.execute(
                    "SELECT * FROM impact_edges WHERE tenant_id = ?", (tenant_id,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM impact_edges").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            for k in ("data_classes_in_payload", "evidence_trace_ids"):
                d[k] = json.loads(d.get(k) or "[]")
            for k in ("has_policy_constraint", "has_approval_gate", "has_deidentification_gate"):
                d[k] = bool(d[k])
            result.append(d)
        return result

    def edge_count(self, tenant_id: Optional[str] = None) -> int:
        with self._conn() as conn:
            if tenant_id:
                return conn.execute(
                    "SELECT COUNT(*) FROM impact_edges WHERE tenant_id = ?", (tenant_id,)
                ).fetchone()[0]
            return conn.execute("SELECT COUNT(*) FROM impact_edges").fetchone()[0]

    # ── Failure states ─────────────────────────────────────────────────────────

    def save_failure_state(self, fs: FailureState) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO impact_failure_states
                    (failure_state_id, vulnerability_class, description, path,
                     constraint_violation, data_classes, is_external_sink,
                     evidence_trace_ids, verified, tenant_id,
                     likelihood_score, blast_radius_score, recoverability_factor,
                     severity_score, exploitability_window, discovered_at, last_validated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fs.failure_state_id, fs.vulnerability_class, fs.description,
                    json.dumps(fs.path), fs.constraint_violation,
                    json.dumps(fs.data_classes), int(fs.is_external_sink),
                    json.dumps(fs.evidence_trace_ids), int(fs.verified),
                    fs.tenant_id, fs.likelihood_score, fs.blast_radius_score,
                    fs.recoverability_factor, fs.severity_score,
                    fs.exploitability_window, fs.discovered_at, fs.last_validated_at,
                ),
            )

    def get_failure_states(
        self,
        tenant_id: Optional[str] = None,
        vulnerability_class: Optional[str] = None,
        verified_only: bool = False,
        limit: int = 100,
    ) -> list[dict]:
        clauses = ["1=1"]
        params: list[Any] = []
        if tenant_id:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if vulnerability_class:
            clauses.append("vulnerability_class = ?")
            params.append(vulnerability_class)
        if verified_only:
            clauses.append("verified = 1")
        params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM impact_failure_states WHERE {' AND '.join(clauses)} "
                f"ORDER BY severity_score DESC LIMIT ?",
                params,
            ).fetchall()

        result = []
        for r in rows:
            d = dict(r)
            for k in ("path", "data_classes", "evidence_trace_ids"):
                d[k] = json.loads(d.get(k) or "[]")
            d["is_external_sink"] = bool(d["is_external_sink"])
            d["verified"] = bool(d["verified"])
            d["mitigated_at"] = d.get("mitigated_at")
            result.append(d)
        return result

    def get_failure_state(self, failure_state_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM impact_failure_states WHERE failure_state_id = ?",
                (failure_state_id,),
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        for k in ("path", "data_classes", "evidence_trace_ids"):
            d[k] = json.loads(d.get(k) or "[]")
        d["is_external_sink"] = bool(d["is_external_sink"])
        d["verified"] = bool(d["verified"])
        d["mitigated_at"] = d.get("mitigated_at")
        return d

    def mark_mitigated(self, failure_state_id: str) -> None:
        """Mark a failure state as mitigated (self-healing applied and verified)."""
        now = datetime.now(UTC).isoformat()
        with self._conn() as conn:
            conn.execute(
                "UPDATE impact_failure_states SET mitigated_at = ? WHERE failure_state_id = ?",
                (now, failure_state_id),
            )

    def failure_state_count(self, tenant_id: Optional[str] = None) -> int:
        with self._conn() as conn:
            if tenant_id:
                return conn.execute(
                    "SELECT COUNT(*) FROM impact_failure_states WHERE tenant_id = ?",
                    (tenant_id,),
                ).fetchone()[0]
            return conn.execute("SELECT COUNT(*) FROM impact_failure_states").fetchone()[0]

    # ── Scenarios ──────────────────────────────────────────────────────────────

    def save_scenario(self, scenario: RedTeamScenario) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO impact_scenarios
                    (scenario_id, failure_state_id, title, attack_narrative,
                     attacker_type, attack_vector, impact_description,
                     indicators_of_compromise, remediation_steps, graph_path_used,
                     validation_status, generated_at, validated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scenario.scenario_id, scenario.failure_state_id,
                    scenario.title, scenario.attack_narrative,
                    scenario.attacker_type, scenario.attack_vector,
                    scenario.impact_description,
                    json.dumps(scenario.indicators_of_compromise),
                    json.dumps(scenario.remediation_steps),
                    json.dumps(scenario.graph_path_used),
                    scenario.validation_status,
                    scenario.generated_at, scenario.validated_at,
                ),
            )

    def get_scenarios(
        self,
        failure_state_id: Optional[str] = None,
        validation_status: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        clauses = ["1=1"]
        params: list[Any] = []
        if failure_state_id:
            clauses.append("failure_state_id = ?")
            params.append(failure_state_id)
        if validation_status:
            clauses.append("validation_status = ?")
            params.append(validation_status)
        params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM impact_scenarios WHERE {' AND '.join(clauses)} "
                f"ORDER BY generated_at DESC LIMIT ?",
                params,
            ).fetchall()

        result = []
        for r in rows:
            d = dict(r)
            for k in ("indicators_of_compromise", "remediation_steps", "graph_path_used"):
                d[k] = json.loads(d.get(k) or "[]")
            result.append(d)
        return result

    # ── Validations ────────────────────────────────────────────────────────────

    def save_validation(self, vr: ValidationResult) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO impact_validations
                    (result_id, scenario_id, failure_state_id, status,
                     reachability_confirmed, policy_violation_confirmed,
                     graph_path_confirmed, invalidation_reason, validated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    vr.result_id, vr.scenario_id, vr.failure_state_id,
                    vr.status,
                    int(vr.reachability_confirmed), int(vr.policy_violation_confirmed),
                    json.dumps(vr.graph_path_confirmed),
                    vr.invalidation_reason, vr.validated_at,
                ),
            )
        # Back-propagate validation status to scenario
        with self._conn() as conn:
            conn.execute(
                "UPDATE impact_scenarios SET validation_status = ?, validated_at = ? "
                "WHERE scenario_id = ?",
                (vr.status, vr.validated_at, vr.scenario_id),
            )

    def get_validation(self, scenario_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM impact_validations WHERE scenario_id = ? "
                "ORDER BY validated_at DESC LIMIT 1",
                (scenario_id,),
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["graph_path_confirmed"] = json.loads(d.get("graph_path_confirmed") or "[]")
        d["reachability_confirmed"] = bool(d["reachability_confirmed"])
        d["policy_violation_confirmed"] = bool(d["policy_violation_confirmed"])
        return d

    # ── Coverage snapshots ─────────────────────────────────────────────────────

    def save_coverage(self, snap: CoverageSnapshot) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO impact_coverage
                    (snapshot_id, tenant_id, agent_count, tool_count, edge_count,
                     failure_state_count, verified_failure_count, scenario_count,
                     valid_scenario_count, new_edges_since_last,
                     new_failure_states_since_last, captured_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snap.snapshot_id, snap.tenant_id, snap.agent_count,
                    snap.tool_count, snap.edge_count, snap.failure_state_count,
                    snap.verified_failure_count, snap.scenario_count,
                    snap.valid_scenario_count, snap.new_edges_since_last,
                    snap.new_failure_states_since_last, snap.captured_at,
                ),
            )

    def latest_coverage(self, tenant_id: Optional[str] = None) -> Optional[dict]:
        with self._conn() as conn:
            if tenant_id:
                row = conn.execute(
                    "SELECT * FROM impact_coverage WHERE tenant_id = ? "
                    "ORDER BY captured_at DESC LIMIT 1",
                    (tenant_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM impact_coverage ORDER BY captured_at DESC LIMIT 1"
                ).fetchone()
        return dict(row) if row else None


# ── Singleton ──────────────────────────────────────────────────────────────────


def get_impact_store() -> ImpactStore:
    global _store_singleton
    if _store_singleton is None:
        with _store_lock:
            if _store_singleton is None:
                _store_singleton = ImpactStore()
    return _store_singleton
