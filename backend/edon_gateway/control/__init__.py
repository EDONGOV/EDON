"""EDON Control Plane — self-governance layer.

This package governs EDON itself:
  decision_kernel   — loop orchestration: apply vs escalate vs notify
  meta_governance   — EDON self-audit: drift, misalignment, unsafe loops
  execution_auth    — hierarchical execution stage gating

The Control Plane sits between the Execution Plane (Shadow/Impact/CREAO)
and the Customer Plane (console UI) and ensures every autonomous action
is bounded, auditable, and reversible.
"""

from .decision_kernel import DecisionKernel, LoopDecision, DecisionOutcome
from .meta_governance import MetaGovernance, GovernanceHealth
from .execution_auth import ExecutionAuthLayer, ExecutionStage, require_stage

__all__ = [
    "DecisionKernel", "LoopDecision", "DecisionOutcome",
    "MetaGovernance", "GovernanceHealth",
    "ExecutionAuthLayer", "ExecutionStage", "require_stage",
]
