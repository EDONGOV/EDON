"""EDON Impact — shared data models.

All three engines operate on these types. Import from here, not from
individual engine modules, to avoid circular dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from typing import Optional
import hashlib
import json
import uuid


# ── Graph primitives ───────────────────────────────────────────────────────────


@dataclass
class AgentNode:
    """A discovered AI agent in the execution graph."""
    agent_id: str
    tenant_id: Optional[str]
    capabilities: list[str]   # tool types this agent has called
    first_seen: str
    last_seen: str
    call_count: int = 0


@dataclass
class ToolNode:
    """A tool endpoint discovered through agent telemetry."""
    tool_name: str           # e.g. "email", "shell", "database"
    operations: list[str]    # e.g. ["send", "delete"]
    data_classes: list[str]  # data types this tool handles: PHI | PII | PCI | INTERNAL | PUBLIC
    is_external_sink: bool   # does this tool send data outside the system boundary?
    system_type: str         # "messaging" | "storage" | "compute" | "external_api" | "physical"


@dataclass
class ExecutionEdge:
    """A directed edge: agent called tool with operation, producing data flow."""
    edge_id: str
    agent_id: str
    tool_name: str
    operation: str
    tenant_id: Optional[str]
    data_classes_in_payload: list[str]   # inferred from payload structure
    has_policy_constraint: bool           # was a policy rule evaluated on this edge?
    has_approval_gate: bool               # did governance produce ESCALATE/PAUSE?
    has_deidentification_gate: bool       # is there a deidentification step on path?
    verdict: str                          # the actual governance verdict
    evidence_trace_ids: list[str]         # trace_ids from shadow store confirming this edge
    first_seen: str
    last_seen: str
    frequency: int = 1


# ── Failure state (Engine A output) ───────────────────────────────────────────

_VULNERABILITY_CLASSES = {
    "data_exfiltration": (
        "Sensitive data flows from a protected source through an agent to an external sink "
        "without a deidentification or approval gate on the path."
    ),
    "privilege_escalation": (
        "Agent requests a tool operation with higher privilege than the intent contract allows. "
        "The action scope exceeds declared purpose."
    ),
    "confused_deputy": (
        "Agent acts on behalf of one principal using credentials or context scoped to another. "
        "Cross-tenant or cross-user access without explicit authorization."
    ),
    "prompt_injection_propagation": (
        "User-controlled input flows into agent context and is passed unfiltered to a tool call. "
        "No sanitization node on the path between user input and tool execution."
    ),
    "policy_bypass_via_chaining": (
        "A single-step action is blocked by policy, but a multi-step path through "
        "intermediate tools achieves the same outcome without triggering the block."
    ),
    "unconstrained_credential_access": (
        "Agent reads from a credential store or secrets system not declared in the intent scope. "
        "Shadow credential access outside governance visibility."
    ),
    "unconstrained_tool_fanout": (
        "Agent spawns sub-agents or parallel tool calls without independent policy evaluation "
        "on each branch. Fan-out escapes per-action governance."
    ),
    "audit_gap": (
        "A tool call path exits without writing to the audit trail. "
        "Actions in this path are ungoverned and unrecoverable."
    ),
    "kill_switch_bypass": (
        "An action path can execute after kill switch activation due to race condition, "
        "caching, or pre-queued execution that bypasses the in-memory check."
    ),
}


@dataclass
class FailureState:
    """A deterministically-discovered reachable failure state in the execution graph.

    Produced by Engine A (graph.py). Each failure state maps to a specific path
    in the execution graph where a constraint is absent or violated.
    """
    failure_state_id: str          # F-{deterministic hash of path+type}
    vulnerability_class: str       # key from _VULNERABILITY_CLASSES
    description: str               # human-readable description from class map
    path: list[str]                # ["agent:X", "tool:email", "op:send", "sink:external"]
    constraint_violation: str      # what constraint is missing or broken
    data_classes: list[str]        # PHI | PII | PCI | INTERNAL | PUBLIC
    is_external_sink: bool
    evidence_trace_ids: list[str]  # trace_ids proving reachability
    verified: bool                 # True = confirmed by trace evidence
    tenant_id: Optional[str]

    # Severity components (computed)
    likelihood_score: float = 0.0     # 0–1: based on trace frequency + graph distance
    blast_radius_score: float = 0.0   # 0–1: data sensitivity × system count × user scope
    recoverability_factor: float = 1.0  # 1=reversible, 3=logged-only, 10=silent+irreversible
    severity_score: float = 0.0       # likelihood × blast_radius / recoverability

    # Time-to-failure
    exploitability_window: str = "session"  # "immediate" | "session" | "persistent" | "latent"

    discovered_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    last_validated_at: Optional[str] = None

    @staticmethod
    def make_id(vulnerability_class: str, path: list[str]) -> str:
        """Deterministic ID from vulnerability class + path."""
        raw = f"{vulnerability_class}::{':'.join(path)}"
        h = hashlib.sha256(raw.encode()).hexdigest()[:8].upper()
        return f"F-{h}"

    def to_dict(self) -> dict:
        return asdict(self)


# ── Red team scenario (Engine B output) ───────────────────────────────────────


@dataclass
class RedTeamScenario:
    """An AI-generated adversarial exploitation narrative for a failure state.

    Engine B produces these. They are bounded to the real execution graph —
    AI cannot invent nodes or edges, only narrate paths that exist.
    """
    scenario_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    failure_state_id: str = ""
    title: str = ""
    attack_narrative: str = ""          # step-by-step exploitation story
    attacker_type: str = ""             # "malicious_agent" | "compromised_user" | "insider"
    attack_vector: str = ""             # "direct" | "chained" | "injection" | "escalation"
    impact_description: str = ""        # what actually happens if this succeeds
    indicators_of_compromise: list[str] = field(default_factory=list)
    remediation_steps: list[str] = field(default_factory=list)
    graph_path_used: list[str] = field(default_factory=list)  # subset of failure state path
    validation_status: str = "pending"  # "pending" | "valid" | "invalid" | "partial"
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    validated_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ── Validation result (Engine C output) ───────────────────────────────────────


@dataclass
class ValidationResult:
    """Engine C output: deterministic re-verification of a red team scenario."""
    result_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    scenario_id: str = ""
    failure_state_id: str = ""
    status: str = "pending"            # "valid" | "invalid" | "partial"
    reachability_confirmed: bool = False
    policy_violation_confirmed: bool = False
    graph_path_confirmed: list[str] = field(default_factory=list)
    invalidation_reason: Optional[str] = None   # why it's invalid, if status=invalid
    validated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


# ── Coverage metrics (Engine D output) ────────────────────────────────────────


@dataclass
class CoverageSnapshot:
    """State of graph coverage at a point in time. Compared across cycles."""
    snapshot_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: Optional[str] = None
    agent_count: int = 0
    tool_count: int = 0
    edge_count: int = 0
    failure_state_count: int = 0
    verified_failure_count: int = 0
    scenario_count: int = 0
    valid_scenario_count: int = 0
    new_edges_since_last: int = 0
    new_failure_states_since_last: int = 0
    captured_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)
