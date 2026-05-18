"""EDON Proof — Level 2: Simulated Execution.

Replays each step of a logical proof through the actual EDON governor in
sandbox (shadow) mode. No real system changes — the governor evaluates
synthetic action traces and returns real verdicts.

This proves the exploit against your actual policy engine, not just the graph.

What it answers:
  "If an attacker took these exact steps, what would the governor do?"

The governor has two possible responses per step:
  ALLOW / DEGRADE  → exploit step succeeds (gap confirmed)
  BLOCK / ESCALATE → step would be stopped (defence confirmed)

A simulated proof is "exploit_succeeded=True" only if ALL critical steps
receive ALLOW or DEGRADE verdicts from the real governor.

This is stronger evidence than Level 1:
  Level 1 proves the path EXISTS in the graph
  Level 2 proves the path PASSES the real policy engine
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from typing import Optional

from .logical import LogicalProof, ProofStep
from ..logging_config import get_logger

logger = get_logger(__name__)


# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class SimulatedStep:
    step_number: int
    action_type: str               # tool.operation sent to governor
    synthetic_payload: dict        # constructed payload matching data classes
    governor_verdict: str          # actual verdict from governor
    governor_reason: str           # governor's explanation
    latency_ms: float
    blocked: bool                  # True = BLOCK or ESCALATE
    exploit_succeeded_at_step: bool  # True = this is a critical step that was NOT blocked


@dataclass
class SimulatedProof:
    failure_state_id: str
    proof_level: str = "simulated"
    exploit_succeeded: bool = False      # True = all critical steps passed the governor
    blocked_at_step: Optional[int] = None  # first step that would be blocked
    steps: list[SimulatedStep] = field(default_factory=list)
    confidence: float = 0.0              # higher than logical, based on governor confirmation
    governor_coverage: float = 0.0       # % of steps that received a real verdict (not fallback)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    elapsed_ms: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ── Synthetic payload builder ──────────────────────────────────────────────────

# Per data class: minimal synthetic payload that signals the right sensitivity
_SYNTHETIC_PAYLOADS: dict[str, dict] = {
    "PHI":      {"patient_id": "SYNTHETIC_PHI_001", "diagnosis": "SYNTHETIC", "mrn": "SYN-001"},
    "PCI":      {"card_number": "4111111111111111", "cvv": "SYNTHETIC", "amount": 0.01},
    "PII":      {"email": "synthetic@edon-proof.internal", "user_id": "SYN-001", "name": "Synthetic User"},
    "AUTH":     {"token": "SYNTHETIC_TOKEN", "api_key": "edon-synthetic-key"},
    "INTERNAL": {"resource": "SYNTHETIC_INTERNAL", "operation": "simulated_proof"},
}


def _synthetic_payload(data_classes: list[str]) -> dict:
    """Build a synthetic payload that flags the relevant data classes."""
    payload: dict = {"_edon_proof": True, "_proof_level": "simulated"}
    priority = ["PHI", "PCI", "PII", "AUTH", "INTERNAL"]
    for dc in priority:
        if dc in data_classes:
            payload.update(_SYNTHETIC_PAYLOADS.get(dc, {}))
            break
    return payload


# ── Action type inference ──────────────────────────────────────────────────────

def _step_to_action_type(step: ProofStep) -> str:
    """Infer a tool.operation action_type from a proof step."""
    target = step.target.lower()

    # Direct tool targets
    if "." in target and not " " in target:
        return target  # already in tool.op format

    # Map common target labels
    mapping = {
        "email":            "email.send",
        "external_sink":    "http.post",
        "database":         "database.read",
        "audit_log":        "database.write",
        "any_tool":         "shell.execute",
        "agent_spawning":   "agent.spawn",
        "spawned_subagent": "agent.execute",
        "protected_resource": "database.read",
        "governance_layer": "http.post",
        "user_input":       "http.post",
    }
    for key, action in mapping.items():
        if key in target:
            return action

    # Parse from step action text
    action_lower = step.action.lower()
    if "delete" in action_lower:
        return f"{target.split()[0] if target.split() else 'database'}.delete"
    if "send" in action_lower or "transmit" in action_lower:
        return "email.send"
    if "read" in action_lower or "access" in action_lower:
        return "database.read"
    if "write" in action_lower or "update" in action_lower:
        return "database.write"
    if "execute" in action_lower or "run" in action_lower:
        return "shell.execute"

    return "http.post"  # safe default


# ── Governor sandbox evaluation ────────────────────────────────────────────────

async def _evaluate_step(
    step: ProofStep,
    data_classes: list[str],
    agent_id: str,
    tenant_id: Optional[str],
    governor,
) -> SimulatedStep:
    """Evaluate one proof step through the governor in shadow mode.

    Constructs a minimal synthetic action and evaluates it — no real execution.
    """
    action_type = _step_to_action_type(step)
    payload = _synthetic_payload(data_classes)
    t0 = time.perf_counter()

    try:
        from ..schemas import Action, Tool, IntentContract, RiskLevel, ActionSource

        tool_str, _, op_str = action_type.partition(".")
        try:
            tool_enum = Tool(tool_str.lower())
        except ValueError:
            tool_enum = Tool.CUSTOM
            payload["_custom_tool"] = tool_str.lower()

        action = Action(
            tool=tool_enum,
            op=op_str or "call",
            params=payload,
            requested_at=datetime.now(UTC),
            source=ActionSource.AGENT,
            tags=["edon_proof_simulation", f"level_2", f"step_{step.step_number}"],
        )
        intent = IntentContract(
            objective=step.action,
            scope={},
            constraints={},
            risk_level=RiskLevel.HIGH,
            approved_by_user=False,
        )
        context = {
            "agent_id": agent_id,
            "_shadow": True,
            "_shadow_mode": "proof_simulation",
            "_proof_step": step.step_number,
            "_synthetic": True,
        }

        decision = governor.evaluate(
            action=action,
            intent=intent,
            context=context,
            tenant_rules=[],   # evaluate against baseline — no tenant-specific rules
        )

        verdict = decision.verdict.value if hasattr(decision.verdict, "value") else str(decision.verdict)
        reason  = getattr(decision, "reason", "") or getattr(decision, "decision_reason", "")
        # DEGRADE counts as blocked: the governor intercepted the original action and
        # substituted a safe alternative — the attacker cannot complete the critical step.
        blocked = verdict in ("BLOCK", "ESCALATE", "PAUSE", "HUMAN_REQUIRED", "DEGRADE")
        latency = round((time.perf_counter() - t0) * 1000, 1)

        return SimulatedStep(
            step_number=step.step_number,
            action_type=action_type,
            synthetic_payload=payload,
            governor_verdict=verdict,
            governor_reason=str(reason)[:200],
            latency_ms=latency,
            blocked=blocked,
            exploit_succeeded_at_step=step.is_critical and not blocked,
        )

    except Exception as exc:
        latency = round((time.perf_counter() - t0) * 1000, 1)
        logger.debug("[proof/simulated] step %d eval error: %s", step.step_number, exc)
        return SimulatedStep(
            step_number=step.step_number,
            action_type=action_type,
            synthetic_payload=payload,
            governor_verdict="UNKNOWN",
            governor_reason=f"evaluation_error: {exc}",
            latency_ms=latency,
            blocked=False,  # fail-open — don't falsely claim protection
            exploit_succeeded_at_step=False,
        )


# ── Public API ─────────────────────────────────────────────────────────────────

async def generate_simulated_proof(
    logical_proof: LogicalProof,
    failure_state: dict,
    governor,
    tenant_id: Optional[str] = None,
) -> SimulatedProof:
    """Generate a Level 2 Simulated Proof by replaying exploit steps through the governor.

    Args:
        logical_proof:  Level 1 proof (provides the step chain)
        failure_state:  Original failure state dict (provides data classes, agent ID)
        governor:       Live EDON governor instance
        tenant_id:      Tenant scope

    Returns:
        SimulatedProof with real governor verdicts per step.
    """
    if governor is None:
        return SimulatedProof(
            failure_state_id=logical_proof.failure_state_id,
            error="governor_not_available",
        )

    t0 = time.perf_counter()
    data_classes = failure_state.get("data_classes", ["INTERNAL"])
    path         = failure_state.get("path", [])

    # Extract agent_id from path or use a synthetic one
    agent_id = "proof_simulation_agent"
    for node in path:
        if node.startswith("agent:"):
            agent_id = node[6:]
            break

    # Evaluate each step concurrently (they're independent — no state between steps)
    tasks = [
        _evaluate_step(step, data_classes, agent_id, tenant_id, governor)
        for step in logical_proof.steps
    ]
    sim_steps = await asyncio.gather(*tasks, return_exceptions=False)

    # Determine overall outcome
    real_verdicts  = [s for s in sim_steps if s.governor_verdict != "UNKNOWN"]
    governor_coverage = round(len(real_verdicts) / max(len(sim_steps), 1), 2)

    critical_steps    = [s for s in sim_steps if logical_proof.steps[s.step_number - 1].is_critical]
    exploit_succeeded = any(s.exploit_succeeded_at_step for s in critical_steps)

    blocked_at = None
    for s in sim_steps:
        if s.blocked:
            blocked_at = s.step_number
            break

    # Confidence: based on governor coverage + whether we got real verdicts on critical steps
    critical_covered = sum(1 for s in critical_steps if s.governor_verdict != "UNKNOWN")
    confidence = round(
        0.5 * governor_coverage
        + 0.5 * (critical_covered / max(len(critical_steps), 1)),
        2
    )
    # If exploit succeeded (critical steps passed) — higher confidence in the finding
    if exploit_succeeded:
        confidence = min(confidence + 0.1, 0.98)

    elapsed = round((time.perf_counter() - t0) * 1000, 1)

    logger.info(
        "[proof/simulated] fs=%s exploit_succeeded=%s blocked_at=%s coverage=%.0f%% elapsed=%dms",
        logical_proof.failure_state_id[:8],
        exploit_succeeded,
        blocked_at,
        governor_coverage * 100,
        elapsed,
    )

    return SimulatedProof(
        failure_state_id=logical_proof.failure_state_id,
        exploit_succeeded=exploit_succeeded,
        blocked_at_step=blocked_at,
        steps=list(sim_steps),
        confidence=confidence,
        governor_coverage=governor_coverage,
        elapsed_ms=elapsed,
    )
