"""EDON Proof — Level 1: Logical Proof.

Generates a deterministic, step-by-step exploit chain from a failure state.

No AI required. Same failure state always produces the same proof.
This is what closes deals — a concrete, readable chain from weakness to damage.

Each step contains:
  - actor:          who takes this step (agent, attacker, system)
  - action:         what they do
  - target:         what system or component is affected
  - rule_violated:  the specific governance constraint that is absent
  - consequence:    what becomes possible because of this missing rule

The chain is built deterministically from:
  1. The vulnerability class (defines the attack pattern template)
  2. The failure state path (provides the real nodes/edges)
  3. The constraint violation (names the missing rule)
  4. The data classes (determines severity of each consequence)
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from typing import Optional

from ..logging_config import get_logger

logger = get_logger(__name__)


# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class ProofStep:
    step_number: int
    actor: str            # "agent:billing_agent" | "attacker" | "system"
    action: str           # human-readable action description
    target: str           # what system or tool is targeted
    rule_violated: str    # the missing governance constraint
    consequence: str      # what this step makes possible
    is_critical: bool = False   # the step where the exploit actually succeeds


@dataclass
class LogicalProof:
    failure_state_id: str
    vulnerability_class: str
    proof_level: str = "logical"
    steps: list[ProofStep] = field(default_factory=list)
    rules_violated: list[str] = field(default_factory=list)   # deduplicated across all steps
    entry_point: str = ""          # where the attacker enters
    final_outcome: str = ""        # what the attacker achieves
    data_classes_exposed: list[str] = field(default_factory=list)
    confidence: float = 0.90       # logical proofs are high confidence — deterministic
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    def to_narrative(self) -> str:
        """Render the proof as a human-readable numbered list."""
        lines = [f"Exploit Chain: {self.vulnerability_class.replace('_', ' ').title()}"]
        lines.append(f"Entry: {self.entry_point}")
        lines.append("")
        for step in self.steps:
            lines.append(f"Step {step.step_number}: {step.action}")
            lines.append(f"  Target:    {step.target}")
            lines.append(f"  No rule:   {step.rule_violated}")
            lines.append(f"  Enables:   {step.consequence}")
            if step.is_critical:
                lines.append("  *** EXPLOIT SUCCEEDS HERE ***")
        lines.append("")
        lines.append(f"Outcome: {self.final_outcome}")
        return "\n".join(lines)


# ── Path node parsing ──────────────────────────────────────────────────────────

def _parse_path(path: list[str]) -> dict:
    """Extract named components from a failure state path."""
    result = {
        "agents": [], "tools": [], "ops": [],
        "reads": [], "writes": [], "sink": None, "source": None,
    }
    for node in path:
        if node.startswith("agent:"):
            result["agents"].append(node[6:])
        elif node.startswith("tool:"):
            result["tools"].append(node[5:])
        elif node.startswith("op:"):
            result["ops"].append(node[3:])
        elif node.startswith("read:"):
            result["reads"].append(node[5:])
        elif node.startswith("write:"):
            result["writes"].append(node[6:])
        elif node.startswith("sink:"):
            result["sink"] = node[5:]
        elif node == "user_input":
            result["source"] = "user_input"
        elif node == "subagent:spawned":
            result["tools"].append("spawned_subagent")
    return result


def _agent_label(nodes: dict) -> str:
    return nodes["agents"][0] if nodes["agents"] else "unknown_agent"


def _tool_label(nodes: dict) -> str:
    return nodes["tools"][0] if nodes["tools"] else "unknown_tool"


def _op_label(nodes: dict) -> str:
    return nodes["ops"][0] if nodes["ops"] else "unknown_op"


def _data_label(data_classes: list[str]) -> str:
    priority = ["PHI", "PCI", "PII", "AUTH", "INTERNAL"]
    for dc in priority:
        if dc in data_classes:
            return dc
    return data_classes[0] if data_classes else "sensitive"


# ── Rule violation labels ──────────────────────────────────────────────────────

_RULE_LABELS: dict[str, str] = {
    "no_deidentification_gate":              "No deidentification step before external transmission",
    "no_policy_evaluation_on_privileged_op": "No policy rule evaluates this privileged operation",
    "allow_with_no_policy_constraint":       "Action allowed with no governance rule applied",
    "no_input_sanitization_node":            "No input sanitization between user input and tool call",
    "multi_step_path_bypasses_single_step_block": "Multi-step path achieves what a single block would prevent",
    "no_per_branch_policy_evaluation":       "Spawned sub-agents inherit no independent governance",
    "cross_tenant_context_reuse":            "Context scoped to one principal reused for another",
}

def _rule_label(constraint_violation: str) -> str:
    return _RULE_LABELS.get(constraint_violation, constraint_violation.replace("_", " "))


# ── Proof templates per vulnerability class ────────────────────────────────────

def _proof_data_exfiltration(fs: dict, nodes: dict) -> list[ProofStep]:
    agent   = _agent_label(nodes)
    tool    = _tool_label(nodes)
    op      = _op_label(nodes)
    dc      = _data_label(fs.get("data_classes", ["INTERNAL"]))
    cv      = _rule_label(fs.get("constraint_violation", ""))

    return [
        ProofStep(1, f"agent:{agent}", f"Agent calls {tool}.{op} with {dc} data in payload",
            tool, "No payload inspection rule on this agent+tool path",
            f"{dc} data is passed directly to {tool} without classification or masking"),
        ProofStep(2, f"agent:{agent}", f"{tool} operation executes without governance gate",
            tool, cv,
            f"No approval or constraint checked — {tool}.{op} runs freely with {dc} payload"),
        ProofStep(3, "system", f"Data transmission exits system boundary via {tool}",
            "external_sink", "No deidentification or boundary enforcement",
            f"{dc} data is now outside the system — irreversible. No audit record written.",
            is_critical=True),
    ]


def _proof_privilege_escalation(fs: dict, nodes: dict) -> list[ProofStep]:
    agent = _agent_label(nodes)
    tool  = _tool_label(nodes)
    op    = _op_label(nodes)
    cv    = _rule_label(fs.get("constraint_violation", ""))

    return [
        ProofStep(1, "attacker", f"Attacker controls or compromises {agent}",
            f"agent:{agent}", "No agent identity verification or scope lock",
            f"Attacker can direct {agent} to perform any operation in its capability set"),
        ProofStep(2, f"agent:{agent}", f"Agent calls {tool}.{op} — a privileged operation",
            tool, cv,
            f"Privileged operation {tool}.{op} is evaluated with no policy constraint"),
        ProofStep(3, "system", f"System executes {tool}.{op} without scope validation",
            tool, "No intent contract enforced on privileged operation path",
            f"{op} executes at full privilege — attacker achieves elevated access",
            is_critical=True),
    ]


def _proof_prompt_injection(fs: dict, nodes: dict) -> list[ProofStep]:
    agent = _agent_label(nodes)
    tool  = _tool_label(nodes)
    op    = _op_label(nodes)
    cv    = _rule_label(fs.get("constraint_violation", ""))

    return [
        ProofStep(1, "attacker", "Attacker crafts malicious payload in user-controlled input field",
            "user_input", "No input boundary between user content and agent context",
            "Malicious instruction is treated as legitimate agent directive"),
        ProofStep(2, f"agent:{agent}", f"Agent passes injected content unfiltered to {tool}.{op}",
            tool, cv,
            "Injected content reaches external tool call — attacker now controls the operation"),
        ProofStep(3, tool, f"{tool}.{op} executes with attacker-controlled payload",
            "external_sink", "No output validation before external transmission",
            f"Attacker-controlled data sent via {tool} — can exfiltrate data, trigger abuse, or pivot",
            is_critical=True),
    ]


def _proof_policy_bypass_chaining(fs: dict, nodes: dict) -> list[ProofStep]:
    agent  = _agent_label(nodes)
    reads  = nodes["reads"]
    writes = nodes["writes"]
    dc     = _data_label(fs.get("data_classes", ["INTERNAL"]))
    cv     = _rule_label(fs.get("constraint_violation", ""))

    read_label  = reads[0]  if reads  else "internal_source"
    write_label = writes[0] if writes else "external_sink"

    return [
        ProofStep(1, f"agent:{agent}", f"Agent reads {dc} data from {read_label} — individually allowed",
            read_label, "Single-step read has no constraint on downstream use",
            f"{dc} data is now in agent context — the intent of this read is not locked"),
        ProofStep(2, f"agent:{agent}", f"Agent writes to {write_label} using previously read {dc} data",
            write_label, "No cross-step policy linking the read intent to write scope",
            "Write is individually allowed — the policy sees two separate ALLOW decisions"),
        ProofStep(3, "system", f"{dc} data reaches {write_label} via two-step chain",
            "external_sink", cv,
            f"A single BLOCK on the write would have prevented this. The chain bypasses it.",
            is_critical=True),
    ]


def _proof_unconstrained_fanout(fs: dict, nodes: dict) -> list[ProofStep]:
    agent = _agent_label(nodes)
    cv    = _rule_label(fs.get("constraint_violation", ""))

    return [
        ProofStep(1, f"agent:{agent}", "Agent spawns sub-agent via tool:agent call",
            "agent_spawning", "No governance evaluation before sub-agent is created",
            "Sub-agent exists with inherited capabilities but no independent governance scope"),
        ProofStep(2, "spawned_subagent", "Sub-agent takes actions without governance evaluation",
            "any_tool", cv,
            "Every action the sub-agent takes escapes the governance loop entirely"),
        ProofStep(3, "spawned_subagent", "Sub-agent performs high-risk operation",
            "any_tool", "No per-branch policy evaluation for spawned agents",
            "Effectively unlimited capability within the sub-agent's runtime — no audit trail",
            is_critical=True),
    ]


def _proof_audit_gap(fs: dict, nodes: dict) -> list[ProofStep]:
    agent = _agent_label(nodes)
    tool  = _tool_label(nodes)
    op    = _op_label(nodes)
    cv    = _rule_label(fs.get("constraint_violation", ""))

    return [
        ProofStep(1, f"agent:{agent}", f"Agent calls {tool}.{op} — action is allowed",
            tool, cv,
            "No governance rule evaluates this path — the action proceeds unchecked"),
        ProofStep(2, "system", "No audit record written for this action",
            "audit_log", "No audit checkpoint on ungoverned ALLOW path",
            "Action is invisible to any monitoring, alerting, or forensics system"),
        ProofStep(3, "attacker", "Attacker exploits ungoverned path repeatedly",
            tool, "No detection capability on this action type",
            "Repeated abuse goes undetected — no alert, no log, no incident created",
            is_critical=True),
    ]


def _proof_confused_deputy(fs: dict, nodes: dict) -> list[ProofStep]:
    agent = _agent_label(nodes)
    tool  = _tool_label(nodes)
    cv    = _rule_label(fs.get("constraint_violation", ""))

    return [
        ProofStep(1, "attacker", f"Attacker crafts request that causes {agent} to act on their behalf",
            f"agent:{agent}", "No principal isolation between tenants or users",
            f"{agent} uses credentials or context scoped to another principal"),
        ProofStep(2, f"agent:{agent}", f"Agent calls {tool} using the victim's credentials/context",
            tool, cv,
            "The tool sees a legitimate agent call — it cannot distinguish the actual principal"),
        ProofStep(3, tool, "Operation executes with victim's access scope",
            "protected_resource", "No cross-tenant context validation at execution",
            "Attacker achieves access to resources they were never authorized for",
            is_critical=True),
    ]


# ── Outcome labels ─────────────────────────────────────────────────────────────

_OUTCOMES: dict[str, str] = {
    "data_exfiltration":             "Sensitive data exits the system boundary — irreversible, undetected",
    "privilege_escalation":          "Attacker gains capabilities beyond their authorized scope",
    "prompt_injection_propagation":  "Attacker controls an external tool call via injected instructions",
    "policy_bypass_via_chaining":    "Policy block circumvented via multi-step path — achieves the blocked outcome",
    "unconstrained_tool_fanout":     "Spawned agents operate outside governance — effectively unlimited capability",
    "audit_gap":                     "Repeated abuse with zero detection, zero alert, zero forensic record",
    "confused_deputy":               "Cross-principal access achieved — attacker accesses another user's data",
    "_default":                      "System security property violated — attacker achieves unauthorized outcome",
}

_ENTRY_POINTS: dict[str, str] = {
    "data_exfiltration":             "Agent with access to sensitive data + external tool capability",
    "privilege_escalation":          "Any agent capable of invoking a privileged operation",
    "prompt_injection_propagation":  "Any user-controlled input field that reaches an agent",
    "policy_bypass_via_chaining":    "Any agent with both read-internal + write-external capability",
    "unconstrained_tool_fanout":     "Any agent capable of spawning sub-agents",
    "audit_gap":                     "Any agent path that reaches an ungoverned ALLOW verdict",
    "confused_deputy":               "Any multi-tenant or multi-user system with shared agent context",
    "_default":                      "Identified weak point in execution graph",
}


# ── Step generators map ────────────────────────────────────────────────────────

_STEP_GENERATORS = {
    "data_exfiltration":             _proof_data_exfiltration,
    "privilege_escalation":          _proof_privilege_escalation,
    "prompt_injection_propagation":  _proof_prompt_injection,
    "policy_bypass_via_chaining":    _proof_policy_bypass_chaining,
    "unconstrained_tool_fanout":     _proof_unconstrained_fanout,
    "audit_gap":                     _proof_audit_gap,
    "confused_deputy":               _proof_confused_deputy,
}


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_logical_proof(failure_state: dict) -> LogicalProof:
    """Generate a Level 1 Logical Proof from a failure state dict.

    Deterministic — same failure state always produces the same proof.
    No AI, no network calls. Returns in microseconds.

    Args:
        failure_state: dict from FailureState.to_dict() or ImpactStore.get_failure_states()

    Returns:
        LogicalProof with step-by-step exploit chain.
    """
    vuln  = failure_state.get("vulnerability_class", "_default")
    path  = failure_state.get("path", [])
    dc    = failure_state.get("data_classes", ["INTERNAL"])
    cv    = failure_state.get("constraint_violation", "")
    fsid  = failure_state.get("failure_state_id", "unknown")

    nodes = _parse_path(path)
    generator = _STEP_GENERATORS.get(vuln)

    if generator:
        steps = generator(failure_state, nodes)
    else:
        # Generic fallback for unknown vuln classes
        agent = _agent_label(nodes)
        tool  = _tool_label(nodes)
        steps = [
            ProofStep(1, f"agent:{agent}", f"Agent calls {tool} without governance constraint",
                tool, _rule_label(cv),
                "Operation executes without policy evaluation"),
            ProofStep(2, "system", "No constraint enforced — exploit path is open",
                "governance_layer", "Missing governance rule on this path",
                "Attacker can traverse this path repeatedly without detection",
                is_critical=True),
        ]

    # Collect unique rules violated across all steps
    rules_violated = list(dict.fromkeys(
        s.rule_violated for s in steps
    ))

    proof = LogicalProof(
        failure_state_id=fsid,
        vulnerability_class=vuln,
        steps=steps,
        rules_violated=rules_violated,
        entry_point=_ENTRY_POINTS.get(vuln, _ENTRY_POINTS["_default"]),
        final_outcome=_OUTCOMES.get(vuln, _OUTCOMES["_default"]),
        data_classes_exposed=dc,
    )

    logger.debug(
        "[proof/logical] generated: fs=%s vuln=%s steps=%d",
        fsid[:8], vuln, len(steps),
    )
    return proof
