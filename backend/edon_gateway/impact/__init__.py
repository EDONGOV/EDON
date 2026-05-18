"""EDON Impact — Continuous AI Risk Intelligence System.

Four-engine architecture:

  A. Deterministic Graph Kernel  (graph.py)
     Builds execution graph from real agent telemetry. Enumerates failure states
     by graph traversal — pure deterministic logic, no AI.

  B. AI Red Team Generator       (red_team.py)
     Expands each failure state into N exploitation scenarios using Claude,
     bounded strictly to the real graph. AI cannot invent topology.

  C. Deterministic Re-Validator  (validator.py)
     Checks every AI-generated scenario against the live graph and governor.
     Only VALID scenarios become confirmed findings.

  D. Coverage Expansion Loop     (loop.py)
     Continuously cycles A→B→C, diffs coverage state, queues new discoveries.

Typical integration:
    from ..impact.loop import run_cycle
    await run_cycle(tenant_id=tenant_id, governor=governor, shadow_store=store)
"""

from .schemas import (
    AgentNode, ToolNode, ExecutionEdge,
    FailureState, RedTeamScenario, ValidationResult, CoverageSnapshot,
)
from .store import ImpactStore, get_impact_store
from .graph import ingest_trace, build_graph_from_store, enumerate_failure_states
from .red_team import generate_scenarios, generate_scenarios_async
from .validator import validate_scenario, validate_all_scenarios, validate_all_scenarios_async
from .loop import run_cycle, start_background_scheduler, stop_background_scheduler

__all__ = [
    # Schemas
    "AgentNode", "ToolNode", "ExecutionEdge",
    "FailureState", "RedTeamScenario", "ValidationResult", "CoverageSnapshot",
    # Store
    "ImpactStore", "get_impact_store",
    # Engine A
    "ingest_trace", "build_graph_from_store", "enumerate_failure_states",
    # Engine B
    "generate_scenarios", "generate_scenarios_async",
    # Engine C
    "validate_scenario", "validate_all_scenarios", "validate_all_scenarios_async",
    # Engine D
    "run_cycle", "start_background_scheduler", "stop_background_scheduler",
]
