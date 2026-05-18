"""Engine A — Deterministic Execution Graph Kernel.

Builds and maintains the execution graph from live agent telemetry.
Every captured trace is an edge. Every new tool is a node.
The graph is the source of truth for all failure state discovery.

Graph construction rules (deterministic — no AI):
  1. Each trace produces one ExecutionEdge: agent → tool.operation
  2. Tool nodes are classified by known profiles (external sinks, data classes)
  3. Edges are annotated with governance signals from the original verdict
  4. Failure states are enumerated by graph traversal (not heuristics)

The graph is never built from assumptions. If there is no trace evidence,
there is no edge, and there is no failure state.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, UTC
from typing import Optional

from .schemas import (
    AgentNode, ToolNode, ExecutionEdge, FailureState,
    _VULNERABILITY_CLASSES,
)
from .store import ImpactStore
from ..logging_config import get_logger

logger = get_logger(__name__)


# ── Tool classification profiles ───────────────────────────────────────────────
# What we know about each tool type from its name.
# This is the ONLY place assumptions are made. Everything else is trace-derived.

_TOOL_PROFILES: dict[str, dict] = {
    "email":        {"data_classes": ["PII"], "is_external_sink": True,  "system_type": "messaging"},
    "shell":        {"data_classes": ["INTERNAL"], "is_external_sink": False, "system_type": "compute"},
    "file":         {"data_classes": ["INTERNAL"], "is_external_sink": False, "system_type": "storage"},
    "database":     {"data_classes": ["PHI", "PII", "PCI", "INTERNAL"], "is_external_sink": False, "system_type": "storage"},
    "browser":      {"data_classes": ["PII"], "is_external_sink": True,  "system_type": "external_api"},
    "http":         {"data_classes": ["INTERNAL"], "is_external_sink": True,  "system_type": "external_api"},
    "slack":        {"data_classes": ["INTERNAL", "PII"], "is_external_sink": True, "system_type": "messaging"},
    "discord":      {"data_classes": ["INTERNAL", "PII"], "is_external_sink": True, "system_type": "messaging"},
    "calendar":     {"data_classes": ["PII"], "is_external_sink": True,  "system_type": "messaging"},
    "github":       {"data_classes": ["INTERNAL"], "is_external_sink": True,  "system_type": "external_api"},
    "memory":       {"data_classes": ["PII", "INTERNAL"], "is_external_sink": False, "system_type": "storage"},
    "agent":        {"data_classes": ["INTERNAL"], "is_external_sink": False, "system_type": "compute"},
    "notion":       {"data_classes": ["INTERNAL", "PII"], "is_external_sink": True,  "system_type": "storage"},
    "twitter":      {"data_classes": ["PUBLIC", "PII"], "is_external_sink": True,  "system_type": "messaging"},
    "gmail":        {"data_classes": ["PII"], "is_external_sink": True,  "system_type": "messaging"},
    "clawdbot":     {"data_classes": ["INTERNAL"], "is_external_sink": False, "system_type": "compute"},
    "robot":        {"data_classes": ["INTERNAL"], "is_external_sink": False, "system_type": "physical"},
    "vehicle":      {"data_classes": ["INTERNAL"], "is_external_sink": False, "system_type": "physical"},
    "drone":        {"data_classes": ["INTERNAL"], "is_external_sink": False, "system_type": "physical"},
    # default for unknown tools
    "_default":     {"data_classes": ["INTERNAL"], "is_external_sink": False, "system_type": "unknown"},
}

# Operations that indicate privilege elevation
_ESCALATION_OPS = frozenset({
    "delete", "remove", "drop", "exec", "execute", "run", "deploy",
    "admin", "sudo", "grant", "revoke", "escalate", "override",
    "bulk_delete", "truncate", "migrate", "publish",
})

# Payload keys that suggest sensitive data presence
_PHI_KEYS = frozenset({"patient_id", "mrn", "dob", "diagnosis", "medication", "ssn", "npi"})
_PII_KEYS = frozenset({"email", "name", "phone", "address", "user_id", "user_email"})
_PCI_KEYS = frozenset({"card_number", "cvv", "pan", "account_number", "routing_number"})


def _classify_payload_data(payload: dict) -> list[str]:
    """Infer data classes present in a payload from its key names."""
    if not payload:
        return []
    keys = {k.lower() for k in payload.keys()}
    classes = []
    if keys & _PHI_KEYS:
        classes.append("PHI")
    if keys & _PII_KEYS:
        classes.append("PII")
    if keys & _PCI_KEYS:
        classes.append("PCI")
    if not classes:
        classes.append("INTERNAL")
    return classes


def _tool_profile(tool_name: str) -> dict:
    return _TOOL_PROFILES.get(tool_name.lower(), _TOOL_PROFILES["_default"])


def _edge_id(agent_id: str, tool_name: str, operation: str, tenant_id: Optional[str]) -> str:
    """Deterministic edge ID: same agent+tool+op+tenant always produces same ID."""
    raw = f"{tenant_id or ''}::{agent_id}::{tool_name}::{operation}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── Graph construction ─────────────────────────────────────────────────────────


def ingest_trace(trace, store: ImpactStore) -> ExecutionEdge:
    """Ingest one AgentTrace into the execution graph.

    Updates AgentNode, ToolNode, and ExecutionEdge in the store.
    Returns the upserted edge.
    """
    now = datetime.now(UTC).isoformat()
    tool_name = trace.action_type.split(".", 1)[0].lower()
    operation = trace.action_type.split(".", 1)[1].lower() if "." in trace.action_type else "unknown"
    profile = _tool_profile(tool_name)

    # Upsert agent node
    agent = AgentNode(
        agent_id=trace.agent_id,
        tenant_id=trace.tenant_id,
        capabilities=[tool_name],
        first_seen=trace.captured_at,
        last_seen=now,
        call_count=1,
    )
    store.upsert_agent(agent)

    # Upsert tool node — merge operations from existing if present
    existing_tools = {t["tool_name"]: t for t in store.get_tools()}
    existing_tool = existing_tools.get(tool_name)
    ops = list(set((existing_tool["operations"] if existing_tool else []) + [operation]))
    tool_node = ToolNode(
        tool_name=tool_name,
        operations=ops,
        data_classes=profile["data_classes"],
        is_external_sink=profile["is_external_sink"],
        system_type=profile["system_type"],
    )
    store.upsert_tool(tool_node)

    # Build edge
    edge_id = _edge_id(trace.agent_id, tool_name, operation, trace.tenant_id)
    verdict = trace.original_verdict
    has_approval = verdict in ("ESCALATE", "PAUSE")
    has_constraint = verdict != "ALLOW"  # any non-ALLOW means policy evaluated and reacted

    edge = ExecutionEdge(
        edge_id=edge_id,
        agent_id=trace.agent_id,
        tool_name=tool_name,
        operation=operation,
        tenant_id=trace.tenant_id,
        data_classes_in_payload=_classify_payload_data(trace.action_payload),
        has_policy_constraint=has_constraint,
        has_approval_gate=has_approval,
        has_deidentification_gate=False,   # no deidentification pipeline in current system
        verdict=verdict,
        evidence_trace_ids=[trace.trace_id],
        first_seen=trace.captured_at,
        last_seen=now,
        frequency=1,
    )
    store.upsert_edge(edge)
    return edge


def build_graph_from_store(
    shadow_store,
    impact_store: ImpactStore,
    tenant_id: Optional[str] = None,
    limit: int = 1000,
) -> int:
    """Batch-ingest recent shadow traces into the impact graph.

    Returns count of edges processed.
    """
    traces = shadow_store.get_recent_traces(tenant_id=tenant_id, limit=limit)
    count = 0
    for trace in traces:
        try:
            ingest_trace(trace, impact_store)
            count += 1
        except Exception as exc:
            logger.debug("[impact/graph] ingest error trace=%s: %s", trace.trace_id[:8], exc)
    logger.info("[impact/graph] ingested %d traces into execution graph", count)
    return count


# ── Failure state enumeration ──────────────────────────────────────────────────


def _severity_scores(
    edge: dict,
    data_classes: list[str],
    is_external_sink: bool,
) -> tuple[float, float, float, float]:
    """Compute (likelihood, blast_radius, recoverability, severity) for an edge-based failure state."""

    # Likelihood: based on edge frequency (normalized) and how close to external sink
    freq = min(edge.get("frequency", 1), 100)
    likelihood = min(0.3 + (freq / 100.0) * 0.7, 1.0)

    # Blast radius: data sensitivity + external sink flag
    data_score = 0.2
    if "PHI" in data_classes:
        data_score = 1.0
    elif "PCI" in data_classes:
        data_score = 0.9
    elif "PII" in data_classes:
        data_score = 0.7
    elif "INTERNAL" in data_classes:
        data_score = 0.4
    sink_multiplier = 1.5 if is_external_sink else 1.0
    blast_radius = min(data_score * sink_multiplier, 1.0)

    # Recoverability: external sinks are hard to recover
    if is_external_sink and "PHI" in data_classes:
        recoverability = 10.0  # silent + irreversible
    elif is_external_sink:
        recoverability = 3.0   # logged but irreversible
    else:
        recoverability = 1.0   # reversible

    severity = round((likelihood * blast_radius) / recoverability, 4)
    return likelihood, blast_radius, recoverability, severity


def _exploitability_window(edge: dict, vulnerability_class: str) -> str:
    """Estimate time-to-failure from edge + class signals."""
    freq = edge.get("frequency", 1)
    op = edge.get("operation", "")
    if vulnerability_class in ("data_exfiltration", "prompt_injection_propagation"):
        return "immediate" if freq >= 5 else "session"
    if vulnerability_class in ("privilege_escalation", "confused_deputy"):
        return "session"
    if vulnerability_class == "policy_bypass_via_chaining":
        return "persistent"
    if vulnerability_class == "audit_gap":
        return "latent"
    return "session"


def enumerate_failure_states(
    impact_store: ImpactStore,
    tenant_id: Optional[str] = None,
) -> list[FailureState]:
    """Engine A core: traverse graph to find failure states.

    Rules (all deterministic):
      1. data_exfiltration      — edge with sensitive data class flows to external sink
                                  AND has_deidentification_gate=False
      2. privilege_escalation   — edge operation is in escalation ops set
                                  AND has_policy_constraint=False (never evaluated)
      3. audit_gap              — edge exists with verdict not in audit trail pattern
                                  (approximated: ALLOW verdict with no constraint)
      4. prompt_injection_prop  — agent edges where operation suggests user input passthrough
      5. unconstrained_fanout   — agent tool edges (tool_name=agent) with no constraint
      6. policy_bypass_via_chaining — edges where two consecutive ALLOW verdicts achieve
                                      what a single BLOCK would prevent (cross-edge analysis)
    """
    edges = impact_store.get_edges(tenant_id=tenant_id)
    tools = {t["tool_name"]: t for t in impact_store.get_tools()}
    failure_states: list[FailureState] = []
    seen_ids: set[str] = set()

    def _add(fs: FailureState) -> None:
        if fs.failure_state_id not in seen_ids:
            seen_ids.add(fs.failure_state_id)
            failure_states.append(fs)
            impact_store.save_failure_state(fs)

    for edge in edges:
        tool_name = edge["tool_name"]
        operation = edge["operation"]
        tool = tools.get(tool_name, {})
        is_external = bool(tool.get("is_external_sink", False))
        data_classes = edge.get("data_classes_in_payload") or tool.get("data_classes", ["INTERNAL"])
        has_constraint = edge.get("has_policy_constraint", False)
        has_deident = edge.get("has_deidentification_gate", False)
        verdict = edge.get("verdict", "ALLOW")
        evidence = edge.get("evidence_trace_ids", [])

        # ── 1. Data exfiltration ───────────────────────────────────────────────
        if is_external and any(d in ("PHI", "PII", "PCI") for d in data_classes) and not has_deident:
            path = [f"agent:{edge['agent_id']}", f"tool:{tool_name}", f"op:{operation}", "sink:external"]
            fs_id = FailureState.make_id("data_exfiltration", path)
            lk, br, rc, sv = _severity_scores(edge, data_classes, is_external)
            _add(FailureState(
                failure_state_id=fs_id,
                vulnerability_class="data_exfiltration",
                description=_VULNERABILITY_CLASSES["data_exfiltration"],
                path=path,
                constraint_violation="no_deidentification_gate",
                data_classes=data_classes,
                is_external_sink=True,
                evidence_trace_ids=evidence,
                verified=len(evidence) > 0,
                tenant_id=tenant_id or edge.get("tenant_id"),
                likelihood_score=lk,
                blast_radius_score=br,
                recoverability_factor=rc,
                severity_score=sv,
                exploitability_window=_exploitability_window(edge, "data_exfiltration"),
            ))

        # ── 2. Privilege escalation ────────────────────────────────────────────
        if operation in _ESCALATION_OPS and not has_constraint:
            path = [f"agent:{edge['agent_id']}", f"tool:{tool_name}", f"op:{operation}"]
            fs_id = FailureState.make_id("privilege_escalation", path)
            lk, br, rc, sv = _severity_scores(edge, data_classes, is_external)
            _add(FailureState(
                failure_state_id=fs_id,
                vulnerability_class="privilege_escalation",
                description=_VULNERABILITY_CLASSES["privilege_escalation"],
                path=path,
                constraint_violation="no_policy_evaluation_on_privileged_op",
                data_classes=data_classes,
                is_external_sink=is_external,
                evidence_trace_ids=evidence,
                verified=len(evidence) > 0,
                tenant_id=tenant_id or edge.get("tenant_id"),
                likelihood_score=lk,
                blast_radius_score=br,
                recoverability_factor=rc,
                severity_score=sv,
                exploitability_window="session",
            ))

        # ── 3. Audit gap ───────────────────────────────────────────────────────
        if verdict == "ALLOW" and not has_constraint and not is_external:
            path = [f"agent:{edge['agent_id']}", f"tool:{tool_name}", f"op:{operation}", "sink:internal"]
            fs_id = FailureState.make_id("audit_gap", path)
            lk, br, rc, sv = _severity_scores(edge, data_classes, False)
            sv = round(sv * 0.5, 4)   # audit gaps are medium priority by default
            _add(FailureState(
                failure_state_id=fs_id,
                vulnerability_class="audit_gap",
                description=_VULNERABILITY_CLASSES["audit_gap"],
                path=path,
                constraint_violation="allow_with_no_policy_constraint",
                data_classes=data_classes,
                is_external_sink=False,
                evidence_trace_ids=evidence,
                verified=len(evidence) > 0,
                tenant_id=tenant_id or edge.get("tenant_id"),
                likelihood_score=lk,
                blast_radius_score=br,
                recoverability_factor=rc,
                severity_score=sv,
                exploitability_window="latent",
            ))

        # ── 4. Prompt injection propagation ────────────────────────────────────
        # Heuristic: operation name suggests passthrough of context to external
        _injection_ops = frozenset({"send", "post", "submit", "write", "publish", "call", "invoke"})
        if operation in _injection_ops and is_external and tool_name in ("email", "slack", "http", "browser", "discord", "twitter", "gmail"):
            path = [f"user_input", f"agent:{edge['agent_id']}", f"tool:{tool_name}", f"op:{operation}", "sink:external"]
            fs_id = FailureState.make_id("prompt_injection_propagation", path)
            lk, br, rc, sv = _severity_scores(edge, data_classes, True)
            _add(FailureState(
                failure_state_id=fs_id,
                vulnerability_class="prompt_injection_propagation",
                description=_VULNERABILITY_CLASSES["prompt_injection_propagation"],
                path=path,
                constraint_violation="no_input_sanitization_node",
                data_classes=data_classes,
                is_external_sink=True,
                evidence_trace_ids=evidence,
                verified=len(evidence) > 0,
                tenant_id=tenant_id or edge.get("tenant_id"),
                likelihood_score=lk,
                blast_radius_score=br,
                recoverability_factor=rc,
                severity_score=sv,
                exploitability_window="immediate",
            ))

        # ── 5. Unconstrained tool fan-out ──────────────────────────────────────
        if tool_name == "agent" and not has_constraint:
            path = [f"agent:{edge['agent_id']}", "tool:agent", f"op:{operation}", "subagent:spawned"]
            fs_id = FailureState.make_id("unconstrained_tool_fanout", path)
            lk, br, rc, sv = _severity_scores(edge, data_classes, False)
            _add(FailureState(
                failure_state_id=fs_id,
                vulnerability_class="unconstrained_tool_fanout",
                description=_VULNERABILITY_CLASSES["unconstrained_tool_fanout"],
                path=path,
                constraint_violation="no_per_branch_policy_evaluation",
                data_classes=["INTERNAL"],
                is_external_sink=False,
                evidence_trace_ids=evidence,
                verified=len(evidence) > 0,
                tenant_id=tenant_id or edge.get("tenant_id"),
                likelihood_score=lk,
                blast_radius_score=br,
                recoverability_factor=rc,
                severity_score=sv,
                exploitability_window="session",
            ))

    # ── 6. Policy bypass via chaining (cross-edge) ────────────────────────────
    # Find: any two edges where individually ALLOW, but together they form
    # a path from internal data to external sink that a single action can't achieve.
    tool_map: dict[str, list[dict]] = {}
    for edge in edges:
        tool_map.setdefault(edge["tool_name"], []).append(edge)

    # Look for internal-read → external-write chains by the same agent
    agent_edges: dict[str, list[dict]] = {}
    for edge in edges:
        agent_edges.setdefault(edge["agent_id"], []).append(edge)

    for agent_id, agent_edge_list in agent_edges.items():
        reads = [e for e in agent_edge_list if e["verdict"] == "ALLOW" and
                 not tools.get(e["tool_name"], {}).get("is_external_sink")]
        writes = [e for e in agent_edge_list if e["verdict"] == "ALLOW" and
                  tools.get(e["tool_name"], {}).get("is_external_sink")]

        for r in reads:
            for w in writes:
                if r["edge_id"] == w["edge_id"]:
                    continue
                r_data = set(r.get("data_classes_in_payload", []))
                sensitive = r_data & {"PHI", "PII", "PCI"}
                if sensitive:
                    path = [
                        f"agent:{agent_id}",
                        f"read:{r['tool_name']}.{r['operation']}",
                        f"write:{w['tool_name']}.{w['operation']}",
                        "sink:external",
                    ]
                    fs_id = FailureState.make_id("policy_bypass_via_chaining", path)
                    combined_evidence = list(set(
                        r.get("evidence_trace_ids", []) + w.get("evidence_trace_ids", [])
                    ))
                    lk, br, rc, sv = _severity_scores(
                        {"frequency": max(r.get("frequency", 1), w.get("frequency", 1))},
                        list(sensitive), True,
                    )
                    chain_tenant = tenant_id or r.get("tenant_id")
                    _add(FailureState(
                        failure_state_id=fs_id,
                        vulnerability_class="policy_bypass_via_chaining",
                        description=_VULNERABILITY_CLASSES["policy_bypass_via_chaining"],
                        path=path,
                        constraint_violation="multi_step_path_bypasses_single_step_block",
                        data_classes=list(sensitive),
                        is_external_sink=True,
                        evidence_trace_ids=combined_evidence,
                        verified=len(combined_evidence) >= 2,
                        tenant_id=chain_tenant,
                        likelihood_score=lk,
                        blast_radius_score=br,
                        recoverability_factor=rc,
                        severity_score=sv,
                        exploitability_window="persistent",
                    ))

    logger.info(
        "[impact/graph] enumerated %d failure states for tenant=%s",
        len(failure_states), tenant_id,
    )
    return failure_states
