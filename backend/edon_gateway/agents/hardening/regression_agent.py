"""Hardening Agent 3 — Regression Agent.

After any policy change, automatically runs the governance validation gate
against recent shadow traces to detect regressions before the change reaches
production.

Without this agent: policy changes are applied manually and regressions are
discovered in production when legitimate agent actions start getting blocked.

With this agent: every rule marked "rule_ready" by the policy agent is
pre-validated against recent trace history. Regressions are surfaced as
a report before the operator applies the rule.

Design:
  - Reads "rule_ready" rules from the policy agent output (in-memory, not DB)
  - Runs validate_proposed_rule_async from shadow/policy_validator.py
  - Returns a regression report per rule
  - Rules with regressions are flagged — operator sees the blast radius before applying
  - Fail-open: validation errors produce inconclusive, never block the pipeline
"""

from __future__ import annotations

import asyncio
from typing import Optional

from ...logging_config import get_logger

logger = get_logger(__name__)


async def run(
    *,
    rules: list[dict],
    governor,
    tenant_id: Optional[str] = None,
    limit_traces: int = 40,
) -> dict:
    """Run the regression agent: validate rule_ready rules against trace history.

    Args:
        rules:          List of rule dicts from policy_agent.run() output.
        governor:       EDONGovernor instance.
        tenant_id:      Scope to this tenant.
        limit_traces:   Max traces to replay per rule.

    Returns:
        Summary dict with per-rule regression reports.
    """
    from ...shadow.policy_validator import validate_proposed_rule_async
    from ...shadow.trace_capture import get_trace_store

    store = get_trace_store()

    summary = {
        "agent": "regression",
        "rules_tested": 0,
        "rules_safe": 0,
        "rules_with_regressions": 0,
        "rules_inconclusive": 0,
        "errors": 0,
        "reports": [],
    }

    for rule in rules:
        rule_key = f"{rule.get('tool') or '*'}/{rule.get('operation') or '*'}"
        try:
            report = await validate_proposed_rule_async(
                rule,
                governor=governor,
                store=store,
                tenant_id=tenant_id,
                limit=limit_traces,
                include_stable=True,
            )

            from dataclasses import asdict
            report_dict = asdict(report)
            report_dict["rule"] = rule
            report_dict["rule_key"] = rule_key
            summary["reports"].append(report_dict)
            summary["rules_tested"] += 1

            if report.recommendation == "apply":
                summary["rules_safe"] += 1
            elif report.recommendation in ("review", "reject"):
                summary["rules_with_regressions"] += 1
            else:
                summary["rules_inconclusive"] += 1

            logger.info(
                "[hardening/regression] rule=%s recommendation=%s "
                "fixed=%d regressions=%d net=%d",
                rule_key,
                report.recommendation,
                report.bypasses_fixed,
                report.regressions,
                report.net_improvement,
            )
        except Exception as exc:
            logger.warning(
                "[hardening/regression] validation failed for rule=%s: %s",
                rule_key, exc,
            )
            summary["errors"] += 1
            summary["rules_inconclusive"] += 1

    return summary
