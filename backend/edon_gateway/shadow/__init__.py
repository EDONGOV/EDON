"""EDON Shadow Execution Module.

Four-component adversarial simulation system:

  1. trace_capture  — instruments /v1/action to snapshot real agent calls
  2. perturbations  — library of adversarial mutations (injection, malformed,
                      boundary, escalation, context poisoning)
  3. replay         — re-executes captured traces under perturbation through
                      the governor (async, probabilistically sampled)
  4. diff_eval      — compares original vs shadow decision, classifies severity

Typical integration (in /v1/action, after audit write):

    from ..shadow import shadow_should_sample, capture_trace, shadow_run_trace

    trace = capture_trace(
        agent_id=req.agent_id,
        tenant_id=tenant_id,
        action_type=req.action_type,
        action_payload=dict(req.action_payload or {}),
        context=req_context,
        timestamp=req.timestamp,
        intent_id=effective_intent_id,
        verdict=verdict_str,
        reason=decision.explanation or "",
        latency_ms=latency_ms,
        meta=decision.meta or {},
    )

    if shadow_should_sample():
        asyncio.create_task(shadow_run_trace(trace, governor=governor, db=db))
"""

from .trace_capture import AgentTrace, TraceStore, get_trace_store, capture_trace
from .replay import BaselineResult, ShadowRunResult, shadow_should_sample, shadow_run_trace, replay_baseline
from .diff_eval import evaluate_diff
from .perturbations import PERTURBATIONS, get_perturbations

__all__ = [
    "AgentTrace",
    "TraceStore",
    "get_trace_store",
    "capture_trace",
    "ShadowRunResult",
    "shadow_should_sample",
    "shadow_run_trace",
    "evaluate_diff",
    "PERTURBATIONS",
    "get_perturbations",
]
