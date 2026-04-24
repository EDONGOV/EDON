"""Hardening Agent 1 — Coverage Agent.

Finds failure states with no shadow probe coverage and runs targeted
adversarial traces against them. Closes the gap between Impact discovery
and Shadow validation.

Without this agent: Impact finds a failure state, but Shadow has never
actually tested that specific path. The failure state is theoretically
real but has no empirical probe result.

With this agent: every failure state gets at least one targeted shadow
probe, producing a real verdict under adversarial conditions.

Design:
  - Reads unprobed failure states from Impact store
  - Constructs minimal synthetic traces that exercise each failure state path
  - Runs them through shadow_run_trace (same engine as real traffic)
  - Never generates or records real agent credentials or data
  - Fail-open: errors are logged, agent continues to next state
  - Produces findings that feed the fix pipeline automatically

Scope: bounded to paths already in the Impact graph. Cannot probe
systems or tools not evidenced in real telemetry.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, UTC
from typing import Optional

from ...logging_config import get_logger
from ...impact.store import ImpactStore
from ...shadow.trace_capture import AgentTrace, TraceStore

logger = get_logger(__name__)


def _build_synthetic_trace(
    failure_state: dict,
    tenant_id: Optional[str],
) -> AgentTrace:
    """Build a minimal synthetic AgentTrace that exercises a failure state path.

    The trace is tagged _synthetic=True so it can be filtered from real metrics.
    Payload is the minimum required to exercise the path — no real data.
    """
    path = failure_state.get("path", [])

    # Extract agent_id, tool, operation from path elements
    agent_id = "hardening-coverage-agent"
    tool_str = "custom"
    operation = "probe"

    for element in path:
        if element.startswith("agent:"):
            agent_id = element.split(":", 1)[1]
        elif element.startswith("tool:"):
            tool_str = element.split(":", 1)[1]
        elif element.startswith("op:"):
            operation = element.split(":", 1)[1]
        elif element.startswith("read:") or element.startswith("write:"):
            raw = element.split(":", 1)[1]
            parts = raw.split(".", 1)
            if tool_str == "custom":
                tool_str = parts[0]
            if operation == "probe" and len(parts) > 1:
                operation = parts[1]

    action_type = f"{tool_str}.{operation}"

    # Synthetic payload — minimal, no real data
    payload: dict = {
        "_synthetic": True,
        "_hardening_probe": True,
        "_failure_state_id": failure_state.get("failure_state_id", ""),
        "_vulnerability_class": failure_state.get("vulnerability_class", ""),
    }

    # Add placeholder values for known sensitive field names to trigger detection
    data_classes = failure_state.get("data_classes", [])
    if "PHI" in data_classes:
        payload["patient_id"] = "SYNTHETIC-PHI-PROBE"
    if "PII" in data_classes:
        payload["email"] = "probe@hardening.internal"
    if "PCI" in data_classes:
        payload["card_number"] = "SYNTHETIC-PCI-PROBE"

    return AgentTrace(
        trace_id=str(uuid.uuid4()),
        captured_at=datetime.now(UTC).isoformat(),
        agent_id=agent_id,
        tenant_id=tenant_id,
        action_type=action_type,
        action_payload=payload,
        context={
            "stated_intent": f"hardening probe for {failure_state.get('vulnerability_class', 'unknown')}",
            "session_id": f"hardening:{failure_state.get('failure_state_id', '')[:8]}",
            "_synthetic": True,
            "_hardening_probe": True,
        },
        timestamp=datetime.now(UTC).isoformat(),
        intent_id=None,
        original_verdict="UNKNOWN",
        original_reason="synthetic hardening probe",
        original_latency_ms=0,
        original_meta={"_synthetic": True},
    )


async def run(
    *,
    impact_store: ImpactStore,
    shadow_store: TraceStore,
    governor,
    tenant_id: Optional[str] = None,
    max_states: int = 10,
) -> dict:
    """Run the coverage agent: probe unscenarioed failure states.

    Returns summary dict with counts.
    """
    from ...shadow.replay import shadow_run_trace

    summary = {
        "agent": "coverage",
        "failure_states_probed": 0,
        "findings_generated": 0,
        "errors": 0,
    }

    # Find failure states with no existing scenarios
    all_states = impact_store.get_failure_states(
        tenant_id=tenant_id, verified_only=False, limit=max_states * 3
    )
    unprobed = [
        fs for fs in all_states
        if not impact_store.get_scenarios(failure_state_id=fs["failure_state_id"], limit=1)
    ]
    # Prioritize by severity
    unprobed.sort(key=lambda x: x.get("severity_score", 0), reverse=True)
    batch = unprobed[:max_states]

    for fs in batch:
        try:
            trace = _build_synthetic_trace(fs, tenant_id)
            # Save synthetic trace to shadow store so replay can persist results
            shadow_store.save_trace(trace)

            results = await shadow_run_trace(
                trace,
                governor=governor,
                db=None,
            )
            summary["failure_states_probed"] += 1
            summary["findings_generated"] += len(results)

            logger.info(
                "[hardening/coverage] probed fs=%s findings=%d",
                fs["failure_state_id"], len(results),
            )
        except Exception as exc:
            logger.warning(
                "[hardening/coverage] probe failed for fs=%s: %s",
                fs.get("failure_state_id", "?"), exc,
            )
            summary["errors"] += 1

    return summary
