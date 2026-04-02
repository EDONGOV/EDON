"""Swarm coordination API.

A swarm is a named group of agents / nanobots governed collectively.
Swarm policies define collective constraints that individual governance
alone cannot enforce:

  - **Action budgets**: max N actions of type X per minute across the whole swarm
  - **Quorum rules**: M of N members must agree before an action executes
  - **Dosage caps**: total payload delivered by the swarm must not exceed a limit

Endpoints:
  POST /swarms                        — create a new swarm
  GET  /swarms                        — list swarms for the tenant
  POST /swarms/{id}/members           — add an agent to a swarm
  DELETE /swarms/{id}/members/{agent} — remove an agent from a swarm
  POST /swarms/{id}/evaluate          — evaluate an action against swarm policy
  GET  /swarms/{id}/state             — real-time swarm state and metrics
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..logging_config import get_logger
from ..persistence import get_db
from ..swarm.coordinator import SwarmCoordinator, SwarmEvalContext
from ..tenancy import get_request_tenant_id

logger = get_logger(__name__)

router = APIRouter(prefix="/swarms", tags=["swarms"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class SwarmCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    policy: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SwarmCreateResponse(BaseModel):
    swarm_id: str
    name: str
    status: str
    created_at: str


class SwarmMemberRequest(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=200)


class SwarmEvaluateRequest(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=200)
    action_type: str = Field(..., min_length=1, max_length=200)
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[str] = None


class SwarmEvaluateResponse(BaseModel):
    swarm_id: str
    agent_id: str
    verdict: str
    reason: str
    quorum_votes: int
    quorum_required: int
    budget_remaining: Optional[int]
    dosage_remaining: Optional[float]


# ---------------------------------------------------------------------------
# Schema bootstrap (idempotent)
# ---------------------------------------------------------------------------

def _ensure_swarm_tables(db) -> None:
    """Create swarm tables if they don't exist."""
    with db._get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS swarms (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                name TEXT NOT NULL,
                policy_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_swarms_tenant ON swarms(tenant_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_swarms_status ON swarms(status)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS swarm_members (
                swarm_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                joined_at TEXT NOT NULL,
                PRIMARY KEY (swarm_id, agent_id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_swarm_members_swarm ON swarm_members(swarm_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_swarm_members_agent ON swarm_members(agent_id)
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS swarm_action_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                swarm_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                verdict TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                amount REAL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_swarm_log_swarm_ts
            ON swarm_action_log(swarm_id, timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_swarm_log_action_type
            ON swarm_action_log(swarm_id, action_type, timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_swarm_log_agent ON swarm_action_log(agent_id)
        """)
        conn.commit()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("", response_model=SwarmCreateResponse, status_code=201)
async def create_swarm(request: Request, req: SwarmCreateRequest):
    """Create a new swarm with the given collective policy."""
    tenant_id = get_request_tenant_id(request) or "default"
    db = get_db()
    _ensure_swarm_tables(db)

    swarm_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    with db._get_connection() as conn:
        conn.execute(
            """
            INSERT INTO swarms (id, tenant_id, name, policy_json, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'active', ?, ?)
            """,
            (swarm_id, tenant_id, req.name, json.dumps(req.policy), now, now),
        )
        conn.commit()

    logger.info(f"Swarm created: {swarm_id} name={req.name!r} tenant={tenant_id}")
    return SwarmCreateResponse(
        swarm_id=swarm_id, name=req.name, status="active", created_at=now
    )


@router.get("")
async def list_swarms(request: Request):
    """List all swarms for the current tenant."""
    tenant_id = get_request_tenant_id(request) or "default"
    db = get_db()
    _ensure_swarm_tables(db)

    with db._get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, status, created_at, updated_at FROM swarms WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchall()

    return {
        "swarms": [
            {"swarm_id": r[0], "name": r[1], "status": r[2],
             "created_at": r[3], "updated_at": r[4]}
            for r in rows
        ]
    }


@router.post("/{swarm_id}/members", status_code=201)
async def add_swarm_member(swarm_id: str, request: Request, req: SwarmMemberRequest):
    """Add an agent to a swarm."""
    tenant_id = get_request_tenant_id(request) or "default"
    db = get_db()
    _ensure_swarm_tables(db)
    _assert_swarm_access(swarm_id, tenant_id, db)

    now = datetime.now(UTC).isoformat()
    with db._get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO swarm_members (swarm_id, agent_id, tenant_id, joined_at)
            VALUES (?, ?, ?, ?)
            """,
            (swarm_id, req.agent_id, tenant_id, now),
        )
        conn.commit()

    return {"swarm_id": swarm_id, "agent_id": req.agent_id, "joined_at": now}


@router.delete("/{swarm_id}/members/{agent_id}", status_code=200)
async def remove_swarm_member(swarm_id: str, agent_id: str, request: Request):
    """Remove an agent from a swarm."""
    tenant_id = get_request_tenant_id(request) or "default"
    db = get_db()
    _ensure_swarm_tables(db)
    _assert_swarm_access(swarm_id, tenant_id, db)

    with db._get_connection() as conn:
        conn.execute(
            "DELETE FROM swarm_members WHERE swarm_id = ? AND agent_id = ?",
            (swarm_id, agent_id),
        )
        conn.commit()

    return {"swarm_id": swarm_id, "agent_id": agent_id, "status": "removed"}


@router.post("/{swarm_id}/evaluate", response_model=SwarmEvaluateResponse)
async def evaluate_swarm_action(
    swarm_id: str, request: Request, req: SwarmEvaluateRequest
):
    """Evaluate an agent action against swarm-level collective policies."""
    tenant_id = get_request_tenant_id(request) or "default"
    db = get_db()
    _ensure_swarm_tables(db)
    _assert_swarm_access(swarm_id, tenant_id, db)

    ctx = SwarmEvalContext(
        swarm_id=swarm_id,
        agent_id=req.agent_id,
        action_type=req.action_type,
        payload=req.payload,
        timestamp=req.timestamp or datetime.now(UTC).isoformat(),
    )
    coordinator = SwarmCoordinator(db)
    verdict = coordinator.evaluate(ctx)

    return SwarmEvaluateResponse(
        swarm_id=swarm_id,
        agent_id=req.agent_id,
        verdict=verdict.verdict,
        reason=verdict.reason,
        quorum_votes=verdict.quorum_votes,
        quorum_required=verdict.quorum_required,
        budget_remaining=verdict.budget_remaining,
        dosage_remaining=verdict.dosage_remaining,
    )


@router.get("/{swarm_id}/state")
async def get_swarm_state(swarm_id: str, request: Request):
    """Return real-time swarm state: members, action counts, dosage consumed."""
    tenant_id = get_request_tenant_id(request) or "default"
    db = get_db()
    _ensure_swarm_tables(db)
    _assert_swarm_access(swarm_id, tenant_id, db)

    coordinator = SwarmCoordinator(db)
    return coordinator.get_swarm_state(swarm_id, tenant_id)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _assert_swarm_access(swarm_id: str, tenant_id: str, db) -> None:
    """Raise 404 if swarm not found, 403 if owned by a different tenant."""
    with db._get_connection() as conn:
        row = conn.execute(
            "SELECT tenant_id FROM swarms WHERE id = ?", (swarm_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Swarm '{swarm_id}' not found")
    if row[0] != tenant_id:
        raise HTTPException(status_code=403, detail="Not authorised for this swarm")
