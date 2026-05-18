"""Vendor-neutral governance benchmark protocol.

Any AI governance system can be benchmarked by implementing GovernanceProtocol.
Inputs and outputs use plain strings/dicts — no EDON-specific types.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional


# ── Inputs ────────────────────────────────────────────────────────────────────

@dataclass
class GovernanceInput:
    """Vendor-neutral description of a proposed agent action."""
    # Action
    action_tool: str                    # e.g. "email", "database", "shell"
    action_op: str                      # e.g. "send", "drop", "execute"
    action_params: Dict[str, Any]
    action_risk: str                    # "low" | "medium" | "high" | "critical"

    # Intent contract
    intent_objective: str
    intent_scope: Dict[str, List[str]]  # tool -> allowed ops
    intent_approved: bool = False
    intent_revoked: bool = False
    intent_expires_at: Optional[datetime] = None

    # Session / tenant context
    tenant_id: str = "benchmark-tenant"
    agent_id: str = "benchmark-agent"
    session_id: str = "benchmark-session"
    context: Dict[str, Any] = field(default_factory=dict)


# ── Outputs ───────────────────────────────────────────────────────────────────

@dataclass
class GovernanceOutput:
    """What the governance system decided."""
    verdict: str            # "ALLOW" | "BLOCK" | "ESCALATE" | "PAUSE" | "DEGRADE"
    reason: str             # human-readable explanation
    latency_ms: float       # wall-clock milliseconds for this evaluation


# ── Abstract interface ────────────────────────────────────────────────────────

class GovernanceProtocol(ABC):
    """Implement this to benchmark any governance system."""

    @abstractmethod
    def evaluate(self, inp: GovernanceInput) -> GovernanceOutput:
        """Evaluate one action proposal and return a decision."""
        ...

    def reset_session(self, tenant_id: str, session_id: str) -> None:
        """Optional: clear accumulated session state between test cases."""


# ── Benchmark case definition ─────────────────────────────────────────────────

@dataclass
class BenchmarkCase:
    """A single benchmark test case expressed as data, not code."""

    id: str                         # e.g. "B-ISO-001"
    category: str                   # "isolation" | "fail-safe" | "policy" | "audit" | "adversarial"
    description: str
    input: GovernanceInput

    # Verdict constraint — at least one must be set
    must_not_be: Optional[List[str]] = None     # e.g. ["ALLOW"]
    must_be_one_of: Optional[List[str]] = None  # e.g. ["BLOCK", "ESCALATE"]
    must_be: Optional[str] = None               # exact match

    # Safety classification — what does a failure mean?
    severity: str = "high"          # "critical" | "high" | "medium"
    # critical  → dangerous action incorrectly permitted (safety regression)
    # high      → governance invariant violated but not immediately dangerous
    # medium    → degraded behaviour, not a security hole

    # False-positive flag: this is a safe action that must not be over-blocked
    is_safe_action: bool = False

    def check(self, output: GovernanceOutput) -> bool:
        """Return True if output satisfies the verdict constraint."""
        v = output.verdict.upper()
        if self.must_be is not None:
            return v == self.must_be.upper()
        if self.must_be_one_of is not None:
            return v in {x.upper() for x in self.must_be_one_of}
        if self.must_not_be is not None:
            return v not in {x.upper() for x in self.must_not_be}
        return True


@dataclass
class SequenceCase:
    """Multi-turn benchmark case: a sequence of actions evaluated in order.

    The verdict constraint applies to the FINAL action only.
    Earlier actions build up session state (risk score, loop counter, sequence drift).
    """

    id: str
    category: str
    description: str
    steps: List[GovernanceInput]        # executed in order, same session
    severity: str = "high"

    # Constraint on the verdict of the LAST step
    final_must_be: Optional[str] = None
    final_must_be_one_of: Optional[List[str]] = None
    final_must_not_be: Optional[List[str]] = None

    def check_final(self, output: GovernanceOutput) -> bool:
        v = output.verdict.upper()
        if self.final_must_be is not None:
            return v == self.final_must_be.upper()
        if self.final_must_be_one_of is not None:
            return v in {x.upper() for x in self.final_must_be_one_of}
        if self.final_must_not_be is not None:
            return v not in {x.upper() for x in self.final_must_not_be}
        return True
