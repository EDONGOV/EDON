"""EDON Proof — Sandbox Executor (Level 2.5).

Executes each exploit step in an isolated mock environment.
No real tools are called. Every step runs against synthetic handlers
that return realistic responses.

This answers a different question from Level 2 (simulated):
  Level 2 asks:  "Would the governor ALLOW this?"
  Sandbox asks:  "If it were allowed — what would ACTUALLY HAPPEN?"

The sandbox proves the full kill chain end-to-end:
  Step 1: Agent reads patient records → handler returns realistic PHI payload
  Step 2: Agent sends to email → handler confirms data transmitted to external
  Step 3: System records no audit entry → handler confirms no trace written

Each step records:
  - data_accessed:     what sensitive data was read
  - data_transmitted:  what left the system boundary
  - operation_result:  what the tool returned
  - side_effect:       what changed (even in mock)
  - reversible:        can this be undone?

The execution trace is the demo artifact. It shows exactly what an attacker
would get — not a prediction, but a structured proof of what executes.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from typing import Optional, Callable

from ..logging_config import get_logger

logger = get_logger(__name__)


# ── Execution record ───────────────────────────────────────────────────────────

@dataclass
class SandboxStep:
    step_number: int
    action_type: str
    actor: str

    # What the tool handler returned
    operation_result: dict
    data_accessed: list[str]       # data class labels touched ("PHI", "PCI", etc.)
    data_transmitted: list[str]    # data class labels that left system boundary
    side_effect: str               # human-readable what changed
    reversible: bool               # can this be undone?

    # Governance overlay
    would_be_blocked: bool         # True = an existing rule would stop this
    blocking_rule: Optional[str]   # which rule would block it (if any)

    latency_ms: float
    is_critical: bool = False      # the step where the exploit succeeds


@dataclass
class SandboxExecution:
    """Complete sandbox execution result for one exploit chain."""
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    failure_state_id: str = ""
    vulnerability_class: str = ""
    proof_level: str = "sandbox"

    steps: list[SandboxStep] = field(default_factory=list)
    exploit_completed: bool = False       # did the attack reach its objective?
    data_exfiltrated: list[str] = field(default_factory=list)  # data classes that "left"
    first_blocked_at: Optional[int] = None
    total_data_accessed: list[str] = field(default_factory=list)

    # Demo-ready summary
    execution_narrative: str = ""     # "Here is exactly what happened"
    blast_radius_summary: str = ""    # "What the attacker obtained"

    confidence: float = 0.95          # sandbox is high confidence — deterministic execution
    elapsed_ms: float = 0.0
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


# ── Mock tool handlers ─────────────────────────────────────────────────────────
# Each handler returns a realistic response as if the tool really ran.
# Data is synthetic — no real systems touched.

def _handle_email_send(payload: dict, data_classes: list[str]) -> dict:
    transmitted = [dc for dc in data_classes if dc in ("PHI", "PCI", "PII", "AUTH")]
    return {
        "status": "sent",
        "message_id": f"SYNTHETIC-{uuid.uuid4().hex[:8]}",
        "recipient": payload.get("email", "target@external.com"),
        "data_in_body": transmitted,
        "delivery_confirmed": True,
        "retrievable": False,   # once sent, cannot be recalled
    }


def _handle_database_read(payload: dict, data_classes: list[str]) -> dict:
    records = []
    if "PHI" in data_classes:
        records.append({"patient_id": "SYNTHETIC-001", "diagnosis": "SYNTHETIC-PHI",
                        "medication": "SYNTHETIC", "ssn": "000-00-0000"})
    if "PCI" in data_classes:
        records.append({"card_number": "4111XXXXXXXXXXXX", "cvv": "XXX",
                        "account_id": "SYNTHETIC-PCI"})
    if "PII" in data_classes and not records:
        records.append({"user_id": "SYNTHETIC-001", "email": "user@synthetic.internal",
                        "name": "Synthetic User"})
    return {
        "status": "ok",
        "records_returned": len(records) or 1,
        "data": records or [{"id": "SYNTHETIC-001", "data": "INTERNAL"}],
        "data_classes_present": data_classes,
    }


def _handle_database_delete(payload: dict, data_classes: list[str]) -> dict:
    return {
        "status": "deleted",
        "rows_affected": 1,
        "target_id": payload.get("id") or payload.get("user_id") or "SYNTHETIC-001",
        "reversible": False,
        "audit_written": False,   # key: delete without audit
    }


def _handle_database_write(payload: dict, data_classes: list[str]) -> dict:
    return {
        "status": "written",
        "rows_affected": 1,
        "record_id": f"SYNTHETIC-{uuid.uuid4().hex[:8]}",
        "reversible": True,
    }


def _handle_http_post(payload: dict, data_classes: list[str]) -> dict:
    transmitted = [dc for dc in data_classes if dc in ("PHI", "PCI", "PII")]
    return {
        "status": 200,
        "response": "ok",
        "data_transmitted": transmitted,
        "endpoint": "https://external.synthetic.target/api",
        "tls": True,
        "logged_by_target": "unknown",
    }


def _handle_shell_execute(payload: dict, data_classes: list[str]) -> dict:
    return {
        "status": "executed",
        "exit_code": 0,
        "stdout": "SYNTHETIC EXECUTION OUTPUT",
        "privilege_level": "elevated",
        "audit_trail": False,
    }


def _handle_agent_spawn(payload: dict, data_classes: list[str]) -> dict:
    return {
        "status": "spawned",
        "subagent_id": f"subagent-{uuid.uuid4().hex[:6]}",
        "capabilities_inherited": True,
        "governance_scope_set": False,    # key: no governance on spawn
        "parent_context_copied": True,
    }


def _handle_billing_refund(payload: dict, data_classes: list[str]) -> dict:
    return {
        "status": "processed",
        "refund_id": f"REF-{uuid.uuid4().hex[:8]}",
        "amount": payload.get("amount", 9999.99),
        "approved": True,
        "secondary_validation": False,    # key: no secondary check
        "fraud_check": "skipped",
    }


def _handle_default(payload: dict, data_classes: list[str]) -> dict:
    return {
        "status": "executed",
        "action": "synthetic_execution",
        "data_involved": data_classes,
    }


_TOOL_HANDLERS: dict[str, Callable] = {
    "email":    _handle_email_send,
    "database": _handle_database_read,
    "http":     _handle_http_post,
    "shell":    _handle_shell_execute,
    "agent":    _handle_agent_spawn,
    "billing":  _handle_billing_refund,
    "github":   _handle_http_post,
    "slack":    _handle_email_send,
}

_EXTERNAL_TOOLS = frozenset({"email", "http", "slack", "browser", "github", "discord"})
_DESTRUCTIVE_OPS = frozenset({"delete", "drop", "truncate", "remove", "destroy"})


def _get_handler(tool: str, op: str) -> Callable:
    if tool == "database" and op in _DESTRUCTIVE_OPS:
        return _handle_database_delete
    if tool == "database" and op in ("write", "create", "update", "insert"):
        return _handle_database_write
    return _TOOL_HANDLERS.get(tool, _handle_default)


# ── Step executor ──────────────────────────────────────────────────────────────

def _execute_step(
    step_number: int,
    action_type: str,
    actor: str,
    data_classes: list[str],
    is_critical: bool,
    governor=None,
    tenant_id: Optional[str] = None,
) -> SandboxStep:
    t0 = time.perf_counter()

    tool, _, op = action_type.partition(".")
    handler = _get_handler(tool, op)

    # Build synthetic payload matching data classes
    payload: dict = {"_sandbox": True, "_proof": True}
    if "PHI" in data_classes:
        payload.update({"patient_id": "SYN-001", "diagnosis": "SYNTHETIC"})
    elif "PCI" in data_classes:
        payload.update({"card_number": "4111XXXXXXXXXXXX", "amount": 0.01})
    elif "PII" in data_classes:
        payload.update({"email": "synthetic@edon-sandbox.internal", "user_id": "SYN-001"})

    result = handler(payload, data_classes)

    # Determine what was accessed vs transmitted
    is_external = tool in _EXTERNAL_TOOLS
    data_accessed    = data_classes if not is_external else []
    data_transmitted = data_classes if is_external else []

    # Determine side effect description
    if tool == "email" or (tool == "http" and op == "post"):
        side_effect = f"{', '.join(data_classes)} data transmitted to external system (unrecoverable)"
        reversible  = False
    elif op in _DESTRUCTIVE_OPS:
        side_effect = f"Record permanently deleted — no audit trail written"
        reversible  = False
    elif tool == "agent" and op in ("spawn", "execute", "call"):
        side_effect = "Sub-agent spawned with inherited capabilities, no governance scope"
        reversible  = True
    elif tool == "billing":
        side_effect = f"Refund processed: ${result.get('amount', 0):.2f} — no secondary validation"
        reversible  = False
    else:
        side_effect = f"{action_type} executed against {tool} system"
        reversible  = True

    # Check if an existing policy would block this (governance overlay)
    would_block = False
    blocking_rule = None
    if governor is not None:
        try:
            from ..schemas import Action, Tool, IntentContract, RiskLevel, ActionSource
            try:
                tool_enum = Tool(tool)
            except ValueError:
                tool_enum = Tool.CUSTOM
            action_obj = Action(
                tool=tool_enum, op=op, params={**payload, "_shadow": True},
                requested_at=datetime.now(UTC), source=ActionSource.AGENT,
                tags=["sandbox_check"],
            )
            intent = IntentContract(
                objective="sandbox_proof_check", scope={}, constraints={},
                risk_level=RiskLevel.HIGH, approved_by_user=False,
            )
            decision = governor.evaluate(
                action=action_obj, intent=intent,
                context={"agent_id": actor, "_shadow": True},
                tenant_rules=[],
            )
            verdict = decision.verdict.value if hasattr(decision.verdict, "value") else str(decision.verdict)
            would_block = verdict in ("BLOCK", "ESCALATE", "HUMAN_REQUIRED")
            if would_block:
                blocking_rule = getattr(decision, "reason", "existing_policy")
        except Exception:
            pass

    latency = round((time.perf_counter() - t0) * 1000, 2)

    return SandboxStep(
        step_number=step_number,
        action_type=action_type,
        actor=actor,
        operation_result=result,
        data_accessed=data_accessed,
        data_transmitted=data_transmitted,
        side_effect=side_effect,
        reversible=reversible,
        would_be_blocked=would_block,
        blocking_rule=str(blocking_rule)[:200] if blocking_rule else None,
        latency_ms=latency,
        is_critical=is_critical,
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def execute_sandbox(
    logical_proof,        # LogicalProof from proof/logical.py
    failure_state: dict,
    governor=None,
    tenant_id: Optional[str] = None,
) -> SandboxExecution:
    """Execute an exploit chain in the sandbox and return a full execution record.

    This is a synchronous operation — all handlers are deterministic mocks.
    Runs in <10ms per step regardless of system state.

    Args:
        logical_proof: LogicalProof containing the exploit steps
        failure_state: Original failure state dict (provides data classes, agent ID)
        governor:      Optional — used only for governance overlay check per step
        tenant_id:     Tenant scope

    Returns:
        SandboxExecution with step-by-step execution trace + blast radius summary.
    """
    from .logical import LogicalProof as LP

    t0 = time.perf_counter()
    data_classes = failure_state.get("data_classes", ["INTERNAL"])
    path = failure_state.get("path", [])

    # Extract actor from path
    actor = "synthetic_agent"
    for node in path:
        if node.startswith("agent:"):
            actor = node[6:]
            break

    exec_steps: list[SandboxStep] = []
    all_data_accessed: list[str] = []
    all_data_transmitted: list[str] = []
    exploit_completed = False
    first_blocked: Optional[int] = None

    for proof_step in logical_proof.steps:
        try:
            from .simulated import _step_to_action_type
            action_type = _step_to_action_type(proof_step)
        except Exception:
            action_type = "http.post"

        step = _execute_step(
            step_number=proof_step.step_number,
            action_type=action_type,
            actor=actor,
            data_classes=data_classes,
            is_critical=proof_step.is_critical,
            governor=governor,
            tenant_id=tenant_id,
        )
        exec_steps.append(step)

        all_data_accessed.extend(step.data_accessed)
        all_data_transmitted.extend(step.data_transmitted)

        if step.would_be_blocked and first_blocked is None:
            first_blocked = step.step_number

        if step.is_critical and not step.would_be_blocked:
            exploit_completed = True

    # Deduplicate
    all_data_accessed    = list(dict.fromkeys(all_data_accessed))
    all_data_transmitted = list(dict.fromkeys(all_data_transmitted))

    elapsed = round((time.perf_counter() - t0) * 1000, 2)

    # Build narrative
    vuln = failure_state.get("vulnerability_class", "unknown")
    if exploit_completed:
        narrative = (
            f"Sandbox execution COMPLETED. The {vuln.replace('_', ' ')} exploit ran "
            f"all {len(exec_steps)} steps without being blocked. "
            f"Data accessed: {', '.join(all_data_accessed) or 'none'}. "
            f"Data transmitted externally: {', '.join(all_data_transmitted) or 'none'}."
        )
    elif first_blocked:
        narrative = (
            f"Sandbox execution STOPPED at Step {first_blocked}. "
            f"An existing policy rule would block this step. "
            f"Steps 1–{first_blocked - 1} completed before the block."
        )
    else:
        narrative = (
            f"Sandbox execution ran {len(exec_steps)} steps. "
            f"No blocks detected at current policy configuration."
        )

    # Blast radius summary
    if all_data_transmitted:
        blast = (
            f"Attacker would obtain: {', '.join(set(all_data_transmitted))} data. "
            f"{'Cannot be recalled once transmitted.' if not all(s.reversible for s in exec_steps) else 'Potentially reversible.'}"
        )
    elif all_data_accessed:
        blast = f"Attacker would access: {', '.join(set(all_data_accessed))} data within system."
    else:
        blast = "Attacker gains elevated system access or control."

    logger.info(
        "[proof/sandbox] executed: vuln=%s steps=%d completed=%s elapsed=%.0fms",
        vuln, len(exec_steps), exploit_completed, elapsed,
    )

    return SandboxExecution(
        failure_state_id=failure_state.get("failure_state_id", "unknown"),
        vulnerability_class=vuln,
        steps=exec_steps,
        exploit_completed=exploit_completed,
        data_exfiltrated=all_data_transmitted,
        first_blocked_at=first_blocked,
        total_data_accessed=all_data_accessed,
        execution_narrative=narrative,
        blast_radius_summary=blast,
        elapsed_ms=elapsed,
    )
