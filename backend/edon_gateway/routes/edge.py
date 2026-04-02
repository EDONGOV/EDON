"""Edge node management API.

Edge nodes are swarm controllers that operate offline (no live connection to
the gateway) and sync back when reconnected.  This router provides:

  POST /edge/register           — register an edge node and get initial policy bundle
  GET  /edge/{node_id}/policy-bundle — fetch latest compiled policy bundle
  POST /edge/{node_id}/sync     — upload offline-queued actions for audit
  GET  /edge                    — list edge nodes for the tenant
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, UTC, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..logging_config import get_logger
from ..persistence import get_db
from ..tenancy import get_request_tenant_id

logger = get_logger(__name__)

router = APIRouter(prefix="/edge", tags=["edge"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class EdgeNodeRegisterRequest(BaseModel):
    node_id: str = Field(..., min_length=1, max_length=200)
    name: str = Field(..., min_length=1, max_length=200)
    capabilities: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EdgeNodeRegisterResponse(BaseModel):
    node_id: str
    status: str
    policy_version: str
    registered_at: str


class EdgeSyncRequest(BaseModel):
    actions: List[Dict[str, Any]]
    last_synced_at: Optional[str] = None


class EdgeSyncResponse(BaseModel):
    accepted: int
    rejected: int
    new_policy_version: Optional[str]
    synced_at: str


# ---------------------------------------------------------------------------
# Schema bootstrap (idempotent)
# ---------------------------------------------------------------------------

def _ensure_edge_tables(db) -> None:
    """Create edge_nodes and edge_sync_queue tables if they don't exist."""
    with db._get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS edge_nodes (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                name TEXT NOT NULL,
                capabilities TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'active',
                last_seen TEXT,
                policy_version TEXT NOT NULL DEFAULT '0',
                metadata TEXT DEFAULT '{}',
                registered_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_edge_nodes_tenant ON edge_nodes(tenant_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_edge_nodes_status ON edge_nodes(status)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS edge_sync_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                edge_node_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                action_json TEXT NOT NULL,
                verdict TEXT,
                synced_at TEXT NOT NULL,
                processed_at TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_edge_sync_node ON edge_sync_queue(edge_node_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_edge_sync_tenant ON edge_sync_queue(tenant_id)
        """)
        conn.commit()


# ---------------------------------------------------------------------------
# Bundle compilation
# ---------------------------------------------------------------------------

def _compile_bundle(tenant_id: str, db) -> Dict[str, Any]:
    """Compile a PolicyBundle dict from the tenant's active policy rules."""
    with db._get_connection() as conn:
        rows = conn.execute(
            """
            SELECT condition_tool, condition_op, condition_risk_level,
                   action, priority, id, enabled
            FROM policy_rules
            WHERE tenant_id = ? AND enabled = 1
            ORDER BY priority DESC
            """,
            (tenant_id,),
        ).fetchall()

    blocked_tools: List[str] = []
    custom_rules: List[Dict[str, Any]] = []

    for row in rows:
        rule_action = str(row[3]).upper()
        if rule_action == "BLOCK" and row[0] and not row[1]:
            # Whole-tool block rule → goes into blocked_tools for fast O(1) lookup
            blocked_tools.append(str(row[0]))
        else:
            custom_rules.append({
                "id": str(row[5]),
                "condition_tool": row[0],
                "condition_op": row[1],
                "condition_risk_level": row[2],
                "action": rule_action,
                "priority": int(row[4] or 0),
                "enabled": bool(row[6]),
            })

    bundle: Dict[str, Any] = {
        "issued_at": datetime.now(UTC).isoformat(),
        "ttl_seconds": 3600,
        "blocked_tools": list(set(blocked_tools)),
        "required_scope": [],
        "rate_limits": {"actions_per_minute": 100},
        "custom_rules": custom_rules,
    }
    # Version is the SHA-256 of the canonical bundle content
    bundle_bytes = json.dumps(bundle, sort_keys=True).encode("utf-8")
    bundle["version"] = hashlib.sha256(bundle_bytes).hexdigest()[:16]
    return bundle


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/register", response_model=EdgeNodeRegisterResponse)
async def register_edge_node(request: Request, req: EdgeNodeRegisterRequest):
    """Register an edge node for a tenant and return initial policy bundle."""
    tenant_id = get_request_tenant_id(request) or "default"
    db = get_db()
    _ensure_edge_tables(db)

    now = datetime.now(UTC).isoformat()
    bundle = _compile_bundle(tenant_id, db)
    policy_version = bundle["version"]

    with db._get_connection() as conn:
        conn.execute(
            """
            INSERT INTO edge_nodes (id, tenant_id, name, capabilities, status,
                                    last_seen, policy_version, metadata, registered_at)
            VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                capabilities=excluded.capabilities,
                last_seen=excluded.last_seen,
                policy_version=excluded.policy_version,
                metadata=excluded.metadata
            """,
            (
                req.node_id,
                tenant_id,
                req.name,
                json.dumps(req.capabilities),
                now,
                policy_version,
                json.dumps(req.metadata),
                now,
            ),
        )
        conn.commit()

    logger.info(f"Edge node registered: {req.node_id} tenant={tenant_id}")
    return EdgeNodeRegisterResponse(
        node_id=req.node_id,
        status="active",
        policy_version=policy_version,
        registered_at=now,
    )


@router.get("/{node_id}/policy-bundle")
async def get_policy_bundle(node_id: str, request: Request):
    """Return a compiled PolicyBundle for the edge node."""
    tenant_id = get_request_tenant_id(request) or "default"
    db = get_db()
    _ensure_edge_tables(db)

    with db._get_connection() as conn:
        row = conn.execute(
            "SELECT tenant_id FROM edge_nodes WHERE id = ?", (node_id,)
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Edge node '{node_id}' not found")
    if row[0] != tenant_id:
        raise HTTPException(status_code=403, detail="Not authorised for this edge node")

    bundle = _compile_bundle(tenant_id, db)

    # Update policy_version in DB
    with db._get_connection() as conn:
        conn.execute(
            "UPDATE edge_nodes SET policy_version = ?, last_seen = ? WHERE id = ?",
            (bundle["version"], datetime.now(UTC).isoformat(), node_id),
        )
        conn.commit()

    issued_dt = datetime.fromisoformat(bundle["issued_at"].replace("Z", "+00:00"))
    expires_dt = issued_dt + timedelta(seconds=bundle["ttl_seconds"])

    return {
        "node_id": node_id,
        "policy_version": bundle["version"],
        "bundle": bundle,
        "issued_at": bundle["issued_at"],
        "expires_at": expires_dt.isoformat(),
    }


@router.post("/{node_id}/sync", response_model=EdgeSyncResponse)
async def sync_edge_actions(node_id: str, request: Request, req: EdgeSyncRequest):
    """Accept offline-queued actions from an edge node and add to audit trail."""
    tenant_id = get_request_tenant_id(request) or "default"
    db = get_db()
    _ensure_edge_tables(db)

    with db._get_connection() as conn:
        row = conn.execute(
            "SELECT tenant_id FROM edge_nodes WHERE id = ?", (node_id,)
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Edge node '{node_id}' not found")
    if row[0] != tenant_id:
        raise HTTPException(status_code=403, detail="Not authorised for this edge node")

    now = datetime.now(UTC).isoformat()
    accepted = 0
    rejected = 0

    for action in req.actions:
        try:
            agent_id = str(action.get("agent_id", node_id))
            action_type = str(action.get("action_type", action.get("tool", "unknown")))
            verdict = str(action.get("verdict", "ALLOW")).upper()
            timestamp = str(action.get("timestamp", now))

            # Write to edge_sync_queue for traceability
            with db._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO edge_sync_queue
                        (edge_node_id, tenant_id, action_json, verdict, synced_at, processed_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (node_id, tenant_id, json.dumps(action), verdict, timestamp, now),
                )
                conn.commit()

            # Also write to audit_events with edge_node_id set
            db.save_audit_event(
                action={"type": action_type, "payload": action.get("params", {})},
                decision={"verdict": verdict, "reason": action.get("reason", "edge_sync")},
                intent_id=None,
                agent_id=agent_id,
                context={"synced_from": node_id, "offline": True},
                customer_id=tenant_id,
                edge_node_id=node_id,
            )
            accepted += 1
        except Exception as exc:
            logger.warning(f"Edge sync: rejected action from {node_id}: {exc}")
            rejected += 1

    # Update last_seen
    with db._get_connection() as conn:
        conn.execute(
            "UPDATE edge_nodes SET last_seen = ? WHERE id = ?", (now, node_id)
        )
        conn.commit()

    # Return fresh policy version so edge node can detect staleness
    bundle = _compile_bundle(tenant_id, db)

    return EdgeSyncResponse(
        accepted=accepted,
        rejected=rejected,
        new_policy_version=bundle["version"],
        synced_at=now,
    )


@router.get("")
async def list_edge_nodes(request: Request):
    """List all edge nodes for the current tenant."""
    tenant_id = get_request_tenant_id(request) or "default"
    db = get_db()
    _ensure_edge_tables(db)

    with db._get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, capabilities, status, last_seen, policy_version,
                   metadata, registered_at
            FROM edge_nodes WHERE tenant_id = ?
            ORDER BY registered_at DESC
            """,
            (tenant_id,),
        ).fetchall()

    nodes = []
    for row in rows:
        nodes.append({
            "node_id": row[0],
            "name": row[1],
            "capabilities": json.loads(row[2] or "[]"),
            "status": row[3],
            "last_seen": row[4],
            "policy_version": row[5],
            "metadata": json.loads(row[6] or "{}"),
            "registered_at": row[7],
        })

    return {"nodes": nodes, "total": len(nodes)}
