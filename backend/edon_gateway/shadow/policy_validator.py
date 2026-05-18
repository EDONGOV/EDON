"""Governance Validation Gate — pre-commit policy regression test.

Before a policy rule change is applied, this module replays recent shadow
findings through the governor with the proposed rule injected. It answers:

    "If I apply this rule, which bypasses get fixed?
     And does it accidentally block anything that's working today?"

The output is a ValidationReport with three buckets:
  - bypasses_fixed  — critical/advisory traces now get the right verdict
  - regressions     — previously-stable ALLOW traces now get BLOCK/ESCALATE
  - no_effect       — proposed rule had no impact on the verdict

Net improvement = bypasses_fixed - regressions. Positive = safe to apply.

Design:
  - Pure function: validate_proposed_rule(rule, governor, store, tenant_id)
  - Never modifies live policy. Rule is injected only for the replay session.
  - Runs synchronously (call from an async handler via asyncio.to_thread if needed).
  - Fail-open: errors in individual trace evaluations are caught and counted.

Integration:
    POST /v1/shadow/validate-policy
    Body: { rule: {...}, limit: 50 }

The rule dict follows the same schema as tenant policy rules in the DB:
    {
        "tool":      "email",          # optional — None matches any tool
        "operation": "send",           # optional — None matches any operation
        "action":    "BLOCK",          # "BLOCK" | "ESCALATE"
        "reason":    "Human-readable description"
    }
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from typing import Optional

from ..logging_config import get_logger

logger = get_logger(__name__)


# ── Result models ──────────────────────────────────────────────────────────────


@dataclass
class TraceValidationResult:
    """Outcome of evaluating a single trace against the proposed rule."""

    trace_id: str
    action_type: str
    original_verdict: str        # what the live governor said at capture time
    baseline_verdict: str        # what the governor says now (without rule)
    proposed_verdict: str        # what the governor says with the rule injected
    category: str                # "bypass_fixed" | "regression" | "no_effect" | "error"
    severity: str                # original shadow finding severity ("critical" | "advisory" | "stable")
    latency_ms: int


@dataclass
class ValidationReport:
    """Full regression report for a proposed policy rule."""

    proposed_rule: dict
    tenant_id: Optional[str]
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    # Counts
    traces_evaluated: int = 0
    bypasses_fixed: int = 0      # critical/advisory → now correctly blocked/escalated
    regressions: int = 0         # stable ALLOW → now blocked (false positives)
    no_effect: int = 0           # rule had no impact on verdict
    errors: int = 0              # evaluation failed

    # Signed score: positive = net improvement, negative = net harm
    net_improvement: int = 0

    # Recommendation
    recommendation: str = "inconclusive"   # "apply" | "review" | "reject" | "inconclusive"
    recommendation_reason: str = ""

    # Per-trace detail
    results: list[dict] = field(default_factory=list)


# ── Core logic ─────────────────────────────────────────────────────────────────


def _rule_matches(rule: dict, action_type: str) -> bool:
    """Return True if the proposed rule's tool/operation matches this action_type."""
    if not action_type:
        return False
    parts = action_type.split(".", 1)
    tool_str = parts[0].lower() if parts else ""
    op_str = parts[1].lower() if len(parts) > 1 else ""

    rule_tool = (rule.get("tool") or "").strip().lower()
    rule_op = (rule.get("operation") or "").strip().lower()

    tool_match = (not rule_tool) or (rule_tool == tool_str)
    op_match = (not rule_op) or (rule_op == op_str)
    return tool_match and op_match


def _evaluate_with_rule(trace, rule: dict, governor) -> tuple[str, int]:
    """Evaluate a trace through the governor with the proposed rule injected.

    The rule is prepended to tenant_rules so it takes highest priority.
    Returns (verdict_str, latency_ms).
    """
    from ..schemas import Action, Tool, IntentContract, RiskLevel, ActionSource

    parts = (trace.action_type or "unknown").split(".", 1)
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
        tags=["validate_policy"],
    )

    intent = IntentContract(
        objective="Policy validation replay",
        scope={},
        constraints={},
        risk_level=RiskLevel.MEDIUM,
        approved_by_user=False,
    )

    context = {
        "agent_id": trace.agent_id,
        "tenant_id": trace.tenant_id,
        "_shadow": True,
        "_shadow_mode": "policy_validation",
        **trace.context,
    }

    # Build a minimal rule object the governor understands
    injected_rule = {
        "tool": rule.get("tool") or "",
        "operation": rule.get("operation") or "",
        "action": rule.get("action", "BLOCK"),
        "reason": rule.get("reason", "Proposed policy rule (validation replay)"),
        "enabled": True,
    }

    start = time.time()
    try:
        decision = governor.evaluate(
            action=action,
            intent=intent,
            context=context,
            tenant_rules=[injected_rule],   # prepended — highest priority
        )
        verdict = decision.verdict.value
    except Exception as exc:
        logger.debug("[policy_validator] evaluate error trace=%s: %s", trace.trace_id[:8], exc)
        verdict = "ERROR"

    latency_ms = int((time.time() - start) * 1000)
    return verdict, latency_ms


def _evaluate_baseline(trace, governor) -> str:
    """Re-evaluate trace without any extra rule. Returns verdict."""
    from ..schemas import Action, Tool, IntentContract, RiskLevel, ActionSource

    parts = (trace.action_type or "unknown").split(".", 1)
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
        tags=["validate_baseline"],
    )

    intent = IntentContract(
        objective="Policy validation baseline",
        scope={},
        constraints={},
        risk_level=RiskLevel.MEDIUM,
        approved_by_user=False,
    )

    context = {
        "agent_id": trace.agent_id,
        "tenant_id": trace.tenant_id,
        "_shadow": True,
        "_shadow_mode": "policy_validation_baseline",
        **trace.context,
    }

    try:
        decision = governor.evaluate(
            action=action,
            intent=intent,
            context=context,
            tenant_rules=[],
        )
        return decision.verdict.value
    except Exception:
        return "ERROR"


def _classify(
    original_verdict: str,
    baseline_verdict: str,
    proposed_verdict: str,
    shadow_severity: str,
    rule_matched: bool,
) -> str:
    """Classify the per-trace outcome into one of four categories.

    bypass_fixed — finding was critical/advisory and rule now forces the correct (non-ALLOW) verdict
    regression   — baseline was ALLOW (legitimate action) and rule now blocks it
    no_effect    — rule had no impact on the verdict
    error        — evaluation errored
    """
    if proposed_verdict == "ERROR":
        return "error"

    verdict_changed = proposed_verdict != baseline_verdict

    if not verdict_changed:
        return "no_effect"

    # Did the rule fix a critical/advisory finding?
    # A finding is "fixed" when a previously-ALLOW verdict (the bypass) becomes BLOCK/ESCALATE.
    if shadow_severity in ("critical", "advisory"):
        # The bypass was: baseline=ALLOW (or same as original non-block)
        # Fixed means: proposed now blocks/escalates what baseline allowed
        if baseline_verdict == "ALLOW" and proposed_verdict in ("BLOCK", "ESCALATE"):
            return "bypass_fixed"
        # Also fixed if original verdict was BLOCK/ESCALATE and baseline drifted to ALLOW
        if original_verdict in ("BLOCK", "ESCALATE") and proposed_verdict in ("BLOCK", "ESCALATE"):
            return "bypass_fixed"

    # Was this a regression on a stable ALLOW trace?
    if shadow_severity == "stable" and baseline_verdict == "ALLOW":
        if proposed_verdict in ("BLOCK", "ESCALATE", "PAUSE"):
            return "regression"

    return "no_effect"


# ── Public API ─────────────────────────────────────────────────────────────────


def validate_proposed_rule(
    rule: dict,
    *,
    governor,
    store,
    tenant_id: Optional[str] = None,
    limit: int = 50,
    include_stable: bool = True,
) -> ValidationReport:
    """Run the governance validation gate for a proposed policy rule.

    Args:
        rule:           The proposed rule dict (tool, operation, action, reason).
        governor:       EDONGovernor instance.
        store:          TraceStore instance (source of recent traces + findings).
        tenant_id:      Filter traces by tenant. None = all tenants.
        limit:          Max traces to evaluate. Default 50.
        include_stable: Whether to also replay stable traces to detect regressions.
                        Set False to only test against known findings (faster).

    Returns:
        ValidationReport with per-trace results and aggregate recommendation.
    """
    report = ValidationReport(proposed_rule=rule, tenant_id=tenant_id)

    # ── Gather traces to evaluate ─────────────────────────────────────────────
    # Priority: critical findings first (most important to fix), then advisory,
    # then stable (regression check). Cap total to limit.

    critical_findings = store.recent_findings(
        tenant_id=tenant_id, severity="critical", limit=limit // 2 or 10
    )
    advisory_findings = store.recent_findings(
        tenant_id=tenant_id, severity="advisory", limit=limit // 4 or 5
    )
    stable_findings: list[dict] = []
    if include_stable:
        stable_findings = store.recent_findings(
            tenant_id=tenant_id, severity="stable", limit=limit // 4 or 10
        )

    # Map findings to trace objects
    all_findings = (
        [(f, "critical") for f in critical_findings]
        + [(f, "advisory") for f in advisory_findings]
        + [(f, "stable") for f in stable_findings]
    )

    # Resolve trace objects (findings have trace_id)
    evaluated_trace_ids: set[str] = set()
    traces_with_severity: list[tuple] = []   # (trace, severity)

    for finding, severity in all_findings:
        trace_id = finding.get("trace_id")
        if not trace_id or trace_id in evaluated_trace_ids:
            continue
        trace = store.get_trace(trace_id)
        if trace is None:
            continue
        evaluated_trace_ids.add(trace_id)
        traces_with_severity.append((trace, severity))
        if len(traces_with_severity) >= limit:
            break

    if not traces_with_severity:
        report.recommendation = "inconclusive"
        report.recommendation_reason = (
            "No recent shadow traces found to validate against. "
            "Run /v1/action calls first to capture traces."
        )
        return report

    # ── Evaluate each trace ───────────────────────────────────────────────────
    rule_tool = (rule.get("tool") or "").strip().lower()
    rule_op = (rule.get("operation") or "").strip().lower()

    for trace, shadow_severity in traces_with_severity:
        rule_matched = _rule_matches(rule, trace.action_type)

        try:
            baseline_verdict = _evaluate_baseline(trace, governor)
            if rule_matched:
                proposed_verdict, latency_ms = _evaluate_with_rule(trace, rule, governor)
            else:
                proposed_verdict = baseline_verdict
                latency_ms = 0

            category = _classify(
                original_verdict=trace.original_verdict,
                baseline_verdict=baseline_verdict,
                proposed_verdict=proposed_verdict,
                shadow_severity=shadow_severity,
                rule_matched=rule_matched,
            )

        except Exception as exc:
            logger.debug("[policy_validator] trace=%s error: %s", trace.trace_id[:8], exc)
            baseline_verdict = "ERROR"
            proposed_verdict = "ERROR"
            latency_ms = 0
            category = "error"

        result = TraceValidationResult(
            trace_id=trace.trace_id,
            action_type=trace.action_type,
            original_verdict=trace.original_verdict,
            baseline_verdict=baseline_verdict,
            proposed_verdict=proposed_verdict,
            category=category,
            severity=shadow_severity,
            latency_ms=latency_ms,
        )
        report.results.append(asdict(result))
        report.traces_evaluated += 1

        if category == "bypass_fixed":
            report.bypasses_fixed += 1
        elif category == "regression":
            report.regressions += 1
        elif category == "no_effect":
            report.no_effect += 1
        elif category == "error":
            report.errors += 1

    report.net_improvement = report.bypasses_fixed - report.regressions

    # ── Recommendation ────────────────────────────────────────────────────────
    if report.traces_evaluated == 0:
        report.recommendation = "inconclusive"
        report.recommendation_reason = "No traces matched the proposed rule scope."
    elif report.net_improvement > 0 and report.regressions == 0:
        report.recommendation = "apply"
        report.recommendation_reason = (
            f"Rule fixes {report.bypasses_fixed} bypass(es) with zero regressions. "
            "Safe to apply."
        )
    elif report.net_improvement > 0 and report.regressions > 0:
        report.recommendation = "review"
        report.recommendation_reason = (
            f"Rule fixes {report.bypasses_fixed} bypass(es) but introduces "
            f"{report.regressions} regression(s). Review regression traces before applying."
        )
    elif report.net_improvement == 0 and report.regressions == 0:
        report.recommendation = "inconclusive"
        report.recommendation_reason = (
            "Rule had no effect on evaluated traces. "
            "Verify the tool/operation scope matches the intended target."
        )
    else:
        report.recommendation = "reject"
        report.recommendation_reason = (
            f"Rule introduces {report.regressions} regression(s) "
            f"but fixes only {report.bypasses_fixed} bypass(es). "
            "Net harm — do not apply."
        )

    logger.info(
        "[policy_validator] rule=%s/%s action=%s → "
        "fixed=%d regressions=%d no_effect=%d net=%d recommendation=%s",
        rule_tool or "*",
        rule_op or "*",
        rule.get("action", "BLOCK"),
        report.bypasses_fixed,
        report.regressions,
        report.no_effect,
        report.net_improvement,
        report.recommendation,
    )

    return report


async def validate_proposed_rule_async(
    rule: dict,
    *,
    governor,
    store,
    tenant_id: Optional[str] = None,
    limit: int = 50,
    include_stable: bool = True,
) -> ValidationReport:
    """Async wrapper — runs the synchronous validation in a thread pool."""
    return await asyncio.to_thread(
        validate_proposed_rule,
        rule,
        governor=governor,
        store=store,
        tenant_id=tenant_id,
        limit=limit,
        include_stable=include_stable,
    )
