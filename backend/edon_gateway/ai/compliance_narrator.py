"""AI-powered compliance report narration.

Generates an executive-level plain-English narrative summarizing a
compliance report. The narrative is ADDITIVE — the full structured
report is always returned alongside the AI summary.

Fail-open: if AI unavailable, report is returned without narrative.
"""

from __future__ import annotations

import logging
from typing import Optional

from .client import call_advisory

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a compliance officer writing an executive summary of an AI governance
compliance report. Your audience is C-suite executives and board members.

You receive a JSON object with compliance metrics. Write a 3–5 sentence
executive summary that:
1. States the overall compliance posture (compliant / at-risk / non-compliant)
2. Highlights the top 1–2 strengths
3. Identifies the top 1–2 areas requiring attention
4. Recommends one immediate action

Be direct, use plain English, avoid jargon. No markdown, no bullets, no headers.
Output ONLY the plain-text narrative paragraph.
"""


def narrate_compliance_report(report: dict) -> Optional[str]:
    """Generate an executive narrative for a compliance report.

    Args:
        report: Compliance report dict (from compliance route).

    Returns:
        Plain-text narrative string, or None if AI unavailable.
    """
    import json as _json

    # Extract key metrics only — no raw audit content
    safe_payload = {}

    for key in (
        "framework", "period_days", "overall_score", "status",
        "total_decisions", "block_rate", "escalate_rate", "allow_rate",
        "audit_chain_valid", "policy_engine_status", "findings",
    ):
        if key in report:
            val = report[key]
            if isinstance(val, (str, int, float, bool)):
                safe_payload[key] = val
            elif isinstance(val, list) and len(val) <= 10:
                safe_payload[key] = [str(v)[:100] for v in val[:10]]

    if not safe_payload:
        return None

    payload = _json.dumps(safe_payload, separators=(",", ":"))
    result = call_advisory(_SYSTEM_PROMPT, payload, expect_json=False, max_tokens=300)

    if result and isinstance(result, str) and len(result.strip()) > 20:
        return result.strip()

    return None


def enrich_report_with_narrative(report: dict) -> dict:
    """Add AI executive narrative to a compliance report dict.

    Args:
        report: Compliance report dict.

    Returns:
        Report dict with "executive_summary" key added (or unchanged on failure).
    """
    try:
        narrative = narrate_compliance_report(report)
        if narrative:
            report = dict(report)
            report["executive_summary"] = narrative
    except Exception as exc:
        logger.debug("Compliance narrative generation failed (fail-open): %s", exc)
    return report
