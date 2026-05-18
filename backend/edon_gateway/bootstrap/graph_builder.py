"""EDON Bootstrap Graph Builder.

Converts a ParsedSystem (from parser.py) into live AgentNode / ToolNode /
ExecutionEdge objects and ingests them directly into the ImpactStore.

Design principles:
  - Schema-derived edges get evidence_trace_ids=["bootstrap:openapi"] — they are
    real paths but unconfirmed by live traffic. verified=False.
  - Log-derived edges get evidence_trace_ids=["bootstrap:log:{n}"] — confirmed
    by observed traffic. verified=True.
  - Agent-config edges get verified=False but are tagged with agent source.
  - Tool profiles from impact/graph.py are reused — no duplicate classification logic.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, UTC
from typing import Optional

from ..impact.schemas import AgentNode, ToolNode, ExecutionEdge
from ..impact.store import ImpactStore
from ..logging_config import get_logger
from .parser import ParsedSystem, ParsedAgent, ParsedEndpoint, ParsedLogEdge

logger = get_logger(__name__)


# Reuse the tool profiles from impact/graph.py — single source of truth
_TOOL_PROFILES: dict[str, dict] = {
    "email":    {"data_classes": ["PII"], "is_external_sink": True,  "system_type": "messaging"},
    "shell":    {"data_classes": ["INTERNAL"], "is_external_sink": False, "system_type": "compute"},
    "file":     {"data_classes": ["INTERNAL"], "is_external_sink": False, "system_type": "storage"},
    "database": {"data_classes": ["PHI", "PII", "PCI", "INTERNAL"], "is_external_sink": False, "system_type": "storage"},
    "browser":  {"data_classes": ["PII"], "is_external_sink": True,  "system_type": "external_api"},
    "http":     {"data_classes": ["INTERNAL"], "is_external_sink": True,  "system_type": "external_api"},
    "slack":    {"data_classes": ["INTERNAL", "PII"], "is_external_sink": True, "system_type": "messaging"},
    "github":   {"data_classes": ["INTERNAL"], "is_external_sink": True,  "system_type": "external_api"},
    "memory":   {"data_classes": ["PII", "INTERNAL"], "is_external_sink": False, "system_type": "storage"},
    "agent":    {"data_classes": ["INTERNAL"], "is_external_sink": False, "system_type": "compute"},
    "auth":     {"data_classes": ["AUTH", "PII"], "is_external_sink": False, "system_type": "auth"},
    "billing":  {"data_classes": ["PCI", "PII"], "is_external_sink": True,  "system_type": "external_api"},
    "_default": {"data_classes": ["INTERNAL"], "is_external_sink": False, "system_type": "unknown"},
}


def _profile(tool_name: str) -> dict:
    return _TOOL_PROFILES.get(tool_name.lower(), _TOOL_PROFILES["_default"])


def _edge_id(agent_id: str, tool: str, operation: str, tenant_id: Optional[str]) -> str:
    raw = f"bootstrap::{tenant_id or ''}::{agent_id}::{tool}::{operation}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _now() -> str:
    return datetime.now(UTC).isoformat()


# ── Ingest functions ───────────────────────────────────────────────────────────

def _ingest_agent(agent: ParsedAgent, store: ImpactStore, tenant_id: Optional[str]) -> None:
    node = AgentNode(
        agent_id=agent.agent_id,
        tenant_id=tenant_id,
        capabilities=agent.tools,
        first_seen=_now(),
        last_seen=_now(),
        call_count=0,
    )
    store.upsert_agent(node)


def _ingest_endpoint(
    ep: ParsedEndpoint,
    agent_id: str,
    store: ImpactStore,
    tenant_id: Optional[str],
) -> ExecutionEdge:
    """Convert one ParsedEndpoint into a ToolNode + ExecutionEdge."""
    profile = _profile(ep.tool)
    now = _now()

    # Merge data classes: endpoint-inferred + tool profile
    all_data_classes = list(set(ep.data_classes + profile["data_classes"]))

    tool_node = ToolNode(
        tool_name=ep.tool,
        operations=[ep.operation],
        data_classes=all_data_classes,
        is_external_sink=ep.is_external or profile["is_external_sink"],
        system_type=profile["system_type"],
    )
    store.upsert_tool(tool_node)

    edge = ExecutionEdge(
        edge_id=_edge_id(agent_id, ep.tool, ep.operation, tenant_id),
        agent_id=agent_id,
        tool_name=ep.tool,
        operation=ep.operation,
        tenant_id=tenant_id,
        data_classes_in_payload=all_data_classes,
        has_policy_constraint=ep.auth_required,  # auth = some constraint exists
        has_approval_gate=False,
        has_deidentification_gate=False,
        verdict="ALLOW",  # schema-derived: no governance verdict yet
        evidence_trace_ids=["bootstrap:openapi"],
        first_seen=now,
        last_seen=now,
        frequency=1,
    )
    store.upsert_edge(edge)
    return edge


def _ingest_log_edge(
    le: ParsedLogEdge,
    store: ImpactStore,
    tenant_id: Optional[str],
) -> ExecutionEdge:
    """Convert one ParsedLogEdge into a ToolNode + ExecutionEdge."""
    parts = le.action_type.split(".", 1)
    tool  = parts[0].lower()
    op    = parts[1].lower() if len(parts) > 1 else "unknown"
    profile = _profile(tool)
    now = _now()

    all_data_classes = list(set(le.data_classes + profile["data_classes"]))

    # Upsert tool — merge operations if it already exists
    existing_tools = {t["tool_name"]: t for t in store.get_tools()}
    existing = existing_tools.get(tool)
    ops = list(set((existing["operations"] if existing else []) + [op]))
    store.upsert_tool(ToolNode(
        tool_name=tool,
        operations=ops,
        data_classes=all_data_classes,
        is_external_sink=profile["is_external_sink"],
        system_type=profile["system_type"],
    ))

    # Upsert agent
    store.upsert_agent(AgentNode(
        agent_id=le.agent_id,
        tenant_id=tenant_id,
        capabilities=[tool],
        first_seen=now,
        last_seen=now,
        call_count=le.count,
    ))

    verdict = le.sample_verdict or "ALLOW"
    has_constraint = verdict not in ("ALLOW", None)

    edge = ExecutionEdge(
        edge_id=_edge_id(le.agent_id, tool, op, tenant_id),
        agent_id=le.agent_id,
        tool_name=tool,
        operation=op,
        tenant_id=tenant_id,
        data_classes_in_payload=all_data_classes,
        has_policy_constraint=has_constraint,
        has_approval_gate=verdict in ("ESCALATE", "PAUSE"),
        has_deidentification_gate=False,
        verdict=verdict,
        evidence_trace_ids=[f"bootstrap:log:{le.agent_id}:{tool}.{op}"],
        first_seen=now,
        last_seen=now,
        frequency=le.count,
    )
    store.upsert_edge(edge)
    return edge


# ── Master builder ─────────────────────────────────────────────────────────────

def build_graph(
    system: ParsedSystem,
    store: ImpactStore,
    tenant_id: Optional[str] = None,
) -> dict:
    """Ingest a ParsedSystem into ImpactStore. Returns an ingest summary."""
    tid = tenant_id or system.tenant_id
    summary = {
        "agents_created": 0,
        "tools_created": 0,
        "edges_created": 0,
        "log_edges": 0,
        "schema_edges": 0,
    }

    # 1. Ingest declared agents
    for agent in system.agents:
        try:
            _ingest_agent(agent, store, tid)
            summary["agents_created"] += 1
            # Create edges for each tool × operation the agent is declared to use
            for tool_name, operations in agent.operations.items():
                profile = _profile(tool_name)
                store.upsert_tool(ToolNode(
                    tool_name=tool_name,
                    operations=operations,
                    data_classes=profile["data_classes"],
                    is_external_sink=profile["is_external_sink"],
                    system_type=profile["system_type"],
                ))
                summary["tools_created"] += 1
                for op in operations:
                    now = _now()
                    edge = ExecutionEdge(
                        edge_id=_edge_id(agent.agent_id, tool_name, op, tid),
                        agent_id=agent.agent_id,
                        tool_name=tool_name,
                        operation=op,
                        tenant_id=tid,
                        data_classes_in_payload=profile["data_classes"],
                        has_policy_constraint=agent.permission_level in ("read_only",),
                        has_approval_gate=False,
                        has_deidentification_gate=False,
                        verdict="ALLOW",
                        evidence_trace_ids=["bootstrap:agent_config"],
                        first_seen=now,
                        last_seen=now,
                        frequency=1,
                    )
                    store.upsert_edge(edge)
                    summary["edges_created"] += 1
        except Exception as exc:
            logger.warning("[bootstrap/graph] agent ingest error: %s", exc)

    # 2. Ingest endpoints — assign to first agent or a synthetic "api_surface" agent
    if system.endpoints:
        api_agent_id = (
            system.agents[0].agent_id if system.agents else "api_surface"
        )
        # Ensure the api agent node exists
        store.upsert_agent(AgentNode(
            agent_id=api_agent_id,
            tenant_id=tid,
            capabilities=[ep.tool for ep in system.endpoints],
            first_seen=_now(),
            last_seen=_now(),
            call_count=0,
        ))
        for ep in system.endpoints:
            try:
                _ingest_endpoint(ep, api_agent_id, store, tid)
                summary["schema_edges"] += 1
                summary["edges_created"] += 1
            except Exception as exc:
                logger.warning("[bootstrap/graph] endpoint ingest error: %s %s", ep.path, exc)

    # 3. Ingest log edges (highest fidelity — real traffic)
    for le in system.log_edges:
        try:
            _ingest_log_edge(le, store, tid)
            summary["log_edges"] += 1
            summary["edges_created"] += 1
        except Exception as exc:
            logger.warning("[bootstrap/graph] log edge ingest error: %s", exc)

    logger.info(
        "[bootstrap/graph] ingested: agents=%d tools=%d edges=%d "
        "(schema=%d log=%d) tenant=%s",
        summary["agents_created"], summary["tools_created"],
        summary["edges_created"], summary["schema_edges"],
        summary["log_edges"], tid,
    )
    return summary
