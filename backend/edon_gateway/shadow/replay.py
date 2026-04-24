"""Component 2 — Shadow replay runner.

Re-executes captured agent traces through the EDON governor under adversarial
perturbation. Runs asynchronously after the real evaluation — never blocks
the production flow.

Usage (called from /v1/action after audit write):

    if shadow_should_sample():
        asyncio.create_task(
            shadow_run_trace(trace, governor=governor, db=db)
        )
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Optional

from ..logging_config import get_logger

logger = get_logger(__name__)

# Fraction of live traces to shadow-replay (env-configurable, default 10%)
_SAMPLE_RATE = float(os.getenv("EDON_SHADOW_SAMPLE_RATE", "0.10"))

# Max perturbations to run per trace (keep it bounded — full suite is ~35+)
_MAX_PERTURBATIONS = int(os.getenv("EDON_SHADOW_MAX_PERTURBATIONS", "6"))


# ── Result models ──────────────────────────────────────────────────────────────


@dataclass
class BaselineResult:
    """Mode A — deterministic re-evaluation of a trace with zero perturbation.

    The baseline is the ground truth for all adversarial comparisons in the
    same session. It answers: "what does the governor produce on the exact
    same input today?"

    If baseline_verdict != original_verdict the governor is non-deterministic
    on this trace — that itself is a finding worth logging.
    """

    trace_id: str
    baseline_verdict: str
    baseline_reason: str
    baseline_latency_ms: int
    matches_original: bool      # baseline_verdict == trace.original_verdict
    non_determinism_flag: bool  # True when governor drifted from capture


@dataclass
class ShadowRunResult:
    trace_id: str
    perturbation_name: str
    perturbation_type: str
    perturbed_field: Optional[str]
    shadow_verdict: str
    shadow_reason: str
    shadow_latency_ms: int
    # Set by diff_eval after replay
    verdict_changed: bool = False
    severity: str = "stable"
    findings: list[str] = field(default_factory=list)


# ── Sampling gate ──────────────────────────────────────────────────────────────


def shadow_should_sample() -> bool:
    """Return True probabilistically at configured sample rate."""
    return random.random() < _SAMPLE_RATE


# ── Mode A — deterministic baseline ───────────────────────────────────────────


async def replay_baseline(trace, *, governor) -> BaselineResult:
    """Mode A: re-evaluate the trace through the governor with no perturbation.

    Uses asyncio.to_thread so the governor's synchronous evaluate() call
    does not block the event loop.
    """
    return await asyncio.to_thread(_baseline_sync, trace, governor)


@dataclass
class ChainStressResult:
    """Result of a session-level multi-step chain stress test.

    Injects a perturbation at step N in a session trace sequence and evaluates
    whether that perturbation cascades into verdict changes at steps N+1 onward.
    """

    session_id: str
    injection_step: int             # index of the trace where perturbation was injected
    injection_trace_id: str
    perturbation_name: str
    perturbation_type: str
    steps_after: int                # number of steps evaluated after injection
    cascade_count: int              # steps after injection that changed verdict
    cascade_verdicts: list[dict]    # [{step, trace_id, original, shadow}]
    severity: str                   # "stable" | "advisory" | "critical"


async def session_chain_stress(
    session_id: str,
    *,
    governor,
    store,
    tenant_id: Optional[str] = None,
    perturbation_types: Optional[list[str]] = None,
    max_perturbations: int = 3,
) -> list[ChainStressResult]:
    """Multi-step chain stress: inject perturbation at each step, observe cascade.

    For each step N in the session:
      1. Apply a perturbation at step N.
      2. Propagate the perturbed context into step N+1's evaluation.
      3. Record whether the verdict at N+1 (and beyond) changes.

    This catches failure modes that single-action shadow testing misses —
    attacks that look safe action-by-action but are dangerous in sequence.
    """
    from .perturbations import get_perturbations

    traces = store.get_session_traces(session_id, tenant_id=tenant_id)
    if len(traces) < 2:
        return []  # Need at least 2 steps for cascade analysis

    pool = get_perturbations(perturbation_types)
    sampled_perturbs = random.sample(pool, min(max_perturbations, len(pool)))
    results: list[ChainStressResult] = []

    for injection_idx in range(len(traces) - 1):
        injection_trace = traces[injection_idx]
        downstream_traces = traces[injection_idx + 1:]

        for perturb in sampled_perturbs:
            try:
                result = await asyncio.to_thread(
                    _chain_stress_sync,
                    injection_trace,
                    downstream_traces,
                    perturb,
                    governor,
                    injection_idx,
                    session_id,
                )
                results.append(result)

                if result.severity in ("advisory", "critical"):
                    logger.warning(
                        "[shadow/chain] %s | session=%s injection_step=%d "
                        "perturbation=%s cascade=%d/%d",
                        result.severity.upper(),
                        session_id[:12],
                        injection_idx,
                        result.perturbation_name,
                        result.cascade_count,
                        result.steps_after,
                    )
            except Exception as exc:
                logger.debug("[shadow/chain] step=%d perturb=%s error=%s",
                             injection_idx, perturb.name, exc)

    return results


def _chain_stress_sync(
    injection_trace,
    downstream_traces,
    perturb,
    governor,
    injection_idx: int,
    session_id: str,
) -> ChainStressResult:
    """Synchronous chain stress — runs in thread pool."""
    from ..schemas import Action, Tool, IntentContract, RiskLevel, ActionSource

    # Apply perturbation at injection point to get the poisoned context
    mutated_payload, mutated_context, mutated_action_type, _ = perturb.apply(
        injection_trace.action_payload,
        injection_trace.context,
        injection_trace.action_type,
    )

    # Build the "leaked" context — what a downstream step would inherit
    # if the injection at step N was allowed to propagate.
    # We propagate: stated_intent, user_message, and any injected fields.
    leaked_context_additions: dict = {}
    for key in ("stated_intent", "user_message", "_injected"):
        if key in mutated_context and mutated_context.get(key) != injection_trace.context.get(key):
            leaked_context_additions[f"_chain_leaked_{key}"] = mutated_context[key]
    if mutated_payload != injection_trace.action_payload:
        leaked_context_additions["_chain_prior_action_payload"] = str(mutated_payload)[:500]

    cascade_verdicts: list[dict] = []
    cascade_count = 0

    for step_offset, downstream in enumerate(downstream_traces):
        parts = downstream.action_type.split(".", 1)
        tool_str = parts[0] if len(parts) == 2 else downstream.action_type
        operation = parts[1] if len(parts) == 2 else "unknown"

        payload = dict(downstream.action_payload or {})
        try:
            tool = Tool(tool_str.lower())
        except ValueError:
            tool = Tool.CUSTOM
            payload["_custom_tool"] = tool_str.lower()

        action = Action(
            tool=tool,
            op=operation,
            params=payload,
            requested_at=datetime.now(UTC),
            source=ActionSource.AGENT,
            tags=["shadow_chain"],
        )

        intent = IntentContract(
            objective="Chain stress replay",
            scope={},
            constraints={},
            risk_level=RiskLevel.MEDIUM,
            approved_by_user=False,
        )

        # Downstream context inherits the leaked poisoned fields
        downstream_context = {
            "agent_id": downstream.agent_id,
            "tenant_id": downstream.tenant_id,
            "_shadow": True,
            "_shadow_mode": "chain_stress",
            **downstream.context,
            **leaked_context_additions,
        }

        try:
            decision = governor.evaluate(
                action=action,
                intent=intent,
                context=downstream_context,
                tenant_rules=[],
            )
            shadow_verdict = decision.verdict.value
        except Exception as exc:
            shadow_verdict = "ERROR"

        original_verdict = downstream.original_verdict
        if shadow_verdict != original_verdict:
            cascade_count += 1
            cascade_verdicts.append({
                "step": injection_idx + 1 + step_offset,
                "trace_id": downstream.trace_id,
                "action_type": downstream.action_type,
                "original": original_verdict,
                "shadow": shadow_verdict,
            })

    # Classify severity
    has_critical = any(
        (v["original"], v["shadow"]) in {
            ("BLOCK", "ALLOW"), ("ESCALATE", "ALLOW"), ("PAUSE", "ALLOW")
        }
        for v in cascade_verdicts
    )
    severity = (
        "critical" if has_critical
        else "advisory" if cascade_count > 0
        else "stable"
    )

    return ChainStressResult(
        session_id=session_id,
        injection_step=injection_idx,
        injection_trace_id=injection_trace.trace_id,
        perturbation_name=perturb.name,
        perturbation_type=perturb.type,
        steps_after=len(downstream_traces),
        cascade_count=cascade_count,
        cascade_verdicts=cascade_verdicts,
        severity=severity,
    )


def _baseline_sync(trace, governor) -> BaselineResult:
    """Synchronous inner baseline replay — exact reconstruction, no mutation."""
    from ..schemas import Action, Tool, IntentContract, RiskLevel, ActionSource

    parts = trace.action_type.split(".", 1)
    tool_str = parts[0] if len(parts) == 2 else trace.action_type
    operation = parts[1] if len(parts) == 2 else "unknown"

    payload = dict(trace.action_payload or {})
    try:
        tool = Tool(tool_str.lower())
    except ValueError:
        tool = Tool.CUSTOM
        payload["_custom_tool"] = tool_str.lower()

    action = Action(
        tool=tool,
        op=operation,
        params=payload,
        requested_at=datetime.now(UTC),
        source=ActionSource.AGENT,
        tags=["shadow_baseline"],
    )

    intent = IntentContract(
        objective="Baseline replay",
        scope={},
        constraints={},
        risk_level=RiskLevel.MEDIUM,
        approved_by_user=False,
    )

    context_for_eval = {
        "agent_id": trace.agent_id,
        "tenant_id": trace.tenant_id,
        "_shadow": True,
        "_shadow_mode": "baseline",
        **trace.context,
    }

    start = time.time()
    try:
        decision = governor.evaluate(
            action=action,
            intent=intent,
            context=context_for_eval,
            tenant_rules=[],
        )
        baseline_verdict = decision.verdict.value
        baseline_reason = decision.explanation or ""
    except Exception as exc:
        baseline_verdict = "ERROR"
        baseline_reason = str(exc)

    latency_ms = int((time.time() - start) * 1000)
    matches = baseline_verdict == trace.original_verdict

    if not matches:
        logger.warning(
            "[shadow/baseline] NON-DETERMINISM: trace=%s original=%s baseline=%s — "
            "governor produced a different verdict on the same input. "
            "Policy or state has changed since capture.",
            trace.trace_id[:8],
            trace.original_verdict,
            baseline_verdict,
        )

    return BaselineResult(
        trace_id=trace.trace_id,
        baseline_verdict=baseline_verdict,
        baseline_reason=baseline_reason,
        baseline_latency_ms=latency_ms,
        matches_original=matches,
        non_determinism_flag=not matches,
    )


# ── Core replay ────────────────────────────────────────────────────────────────


async def shadow_run_trace(
    trace,                   # AgentTrace — imported at call site to avoid circular deps
    *,
    governor,                # EDONGovernor instance from app.state
    db=None,                 # Database instance (reserved for future per-tenant rules)
    perturbation_types: Optional[list[str]] = None,
) -> list[ShadowRunResult]:
    """Run a set of perturbations against a captured trace through the governor.

    Returns results. Critical/advisory findings are logged as warnings.
    All writes to the trace store happen here.
    """
    from .perturbations import get_perturbations
    from .diff_eval import evaluate_diff
    from .trace_capture import get_trace_store

    store = get_trace_store()
    pool = get_perturbations(perturbation_types)

    # ── Mode A: run baseline first ─────────────────────────────────────────────
    # All adversarial results diff against the fresh baseline verdict, not the
    # stored capture. This isolates perturbation effects from governor drift.
    baseline: Optional[BaselineResult] = None
    try:
        baseline = await replay_baseline(trace, governor=governor)
        store.save_baseline(baseline)
    except Exception as exc:
        logger.debug("[shadow] baseline replay failed: %s", exc)

    # ── Mode B: adversarial perturbations ──────────────────────────────────────
    sampled = random.sample(pool, min(_MAX_PERTURBATIONS, len(pool)))
    results: list[ShadowRunResult] = []

    for perturb in sampled:
        try:
            result = await _replay_one(trace, perturb, governor)
            result = evaluate_diff(trace, result, baseline=baseline)
            store.save_result(result)
            results.append(result)

            if result.severity in ("advisory", "critical"):
                logger.warning(
                    "[shadow] %s | trace=%s perturbation=%s "
                    "baseline=%s shadow=%s field=%s",
                    result.severity.upper(),
                    trace.trace_id[:8],
                    result.perturbation_name,
                    baseline.baseline_verdict if baseline else trace.original_verdict,
                    result.shadow_verdict,
                    result.perturbed_field,
                )
                # ── Shadow → CREAO Engine ─────────────────────────────────
                # Route all critical/advisory findings through the unified
                # CREAO orchestrator (which wraps fix_pipeline internally).
                # CREAO also records proposals in meta-governance loop detection.
                # Fail-open: errors never affect governance.
                try:
                    from ..creao.engine import get_creao_engine
                    get_creao_engine().generate(result, trace)
                except Exception as _fp_err:
                    logger.debug("[shadow] creao.generate failed (fail-open): %s", _fp_err)
        except Exception as exc:
            logger.debug(
                "[shadow] perturbation '%s' errored: %s", perturb.name, exc
            )

    return results


async def _replay_one(trace, perturb, governor) -> ShadowRunResult:
    """Apply one perturbation and evaluate through the governor synchronously.

    Wrapped in asyncio.to_thread so the governor's (potentially blocking)
    evaluate() call doesn't block the event loop.
    """
    return await asyncio.to_thread(_replay_one_sync, trace, perturb, governor)


def _replay_one_sync(trace, perturb, governor) -> ShadowRunResult:
    """Synchronous inner replay — runs in thread pool via asyncio.to_thread."""
    from ..schemas import Action, Tool, IntentContract, RiskLevel, ActionSource

    # Apply perturbation
    mutated_payload, mutated_context, mutated_action_type, perturbed_field = perturb.apply(
        trace.action_payload,
        trace.context,
        trace.action_type,
    )

    # Parse mutated action_type
    parts = mutated_action_type.split(".", 1)
    tool_str = parts[0] if len(parts) == 2 else mutated_action_type
    operation = parts[1] if len(parts) == 2 else "unknown"

    try:
        tool = Tool(tool_str.lower())
        payload = dict(mutated_payload or {})
    except ValueError:
        tool = Tool.CUSTOM
        payload = dict(mutated_payload or {})
        payload["_custom_tool"] = tool_str.lower()

    action = Action(
        tool=tool,
        op=operation,
        params=payload,
        requested_at=datetime.now(UTC),
        source=ActionSource.AGENT,
        tags=["shadow"],
    )

    intent = IntentContract(
        objective="Shadow replay",
        scope={},
        constraints={},
        risk_level=RiskLevel.MEDIUM,
        approved_by_user=False,
    )

    context_for_eval = {
        "agent_id": trace.agent_id,
        "tenant_id": trace.tenant_id,
        "_shadow": True,
        **mutated_context,
    }

    start = time.time()
    try:
        decision = governor.evaluate(
            action=action,
            intent=intent,
            context=context_for_eval,
            tenant_rules=[],
        )
        shadow_verdict = decision.verdict.value
        shadow_reason = decision.explanation or ""
    except Exception as exc:
        shadow_verdict = "ERROR"
        shadow_reason = str(exc)

    latency_ms = int((time.time() - start) * 1000)

    return ShadowRunResult(
        trace_id=trace.trace_id,
        perturbation_name=perturb.name,
        perturbation_type=perturb.type,
        perturbed_field=perturbed_field,
        shadow_verdict=shadow_verdict,
        shadow_reason=shadow_reason,
        shadow_latency_ms=latency_ms,
    )
