"""AI Advisory API routes.

Surfaces AI-generated governance insights via REST API:
- GET  /ai/policy-suggestions   — latest pattern-based policy suggestions
- POST /ai/policy-author         — natural language → draft policy rule
- GET  /ai/audit-mining          — latest nightly audit anomaly findings
- GET  /ai/status                — AI advisory layer availability

All outputs are advisory only. No AI output is applied automatically.
Human review and explicit API submission is required for any rule changes.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List

from ..tenancy import get_request_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai-advisory"])


# ── Models ────────────────────────────────────────────────────────────────────

class PolicyAuthorRequest(BaseModel):
    description: str = Field(..., min_length=10, max_length=500,
                              description="Plain-English description of the desired policy rule")
    examples: Optional[List[str]] = Field(None, max_length=5,
                                           description="Optional example action strings")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/status")
async def ai_advisory_status(request: Request):
    """Check AI advisory layer availability and configuration."""
    try:
        from ..ai.client import is_ai_available
        available = is_ai_available()
    except Exception:
        available = False

    return {
        "ai_advisory_available": available,
        "note": (
            "AI advisory layer is active. All outputs are advisory only — "
            "governance verdicts are always determined by the deterministic policy engine."
            if available else
            "AI advisory layer not configured. Set ANTHROPIC_API_KEY to enable. "
            "Governance functions normally without it."
        ),
    }


@router.get("/policy-suggestions")
async def get_policy_suggestions(request: Request):
    """Return the latest AI-generated policy rule suggestions.

    Suggestions are derived from patterns in recent audit events.
    They are ADVISORY ONLY — submit via POST /policy/rules to apply.

    Requires human review before any suggestion is applied.
    """
    try:
        from ..ai.policy_suggester import get_cached_suggestions
        return get_cached_suggestions()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Policy suggester unavailable: {exc}")


@router.post("/policy-author")
async def author_policy_rule(request: Request, req: PolicyAuthorRequest):
    """Convert a plain-English description into a draft policy rule.

    The returned rule is a DRAFT. Review it carefully before submitting
    to POST /policy/rules. It will NOT take effect automatically.

    The AI may produce incorrect or overly broad rules — always review
    condition_tool, condition_op, and action before applying.
    """
    try:
        from ..ai.policy_author import author_policy_rule as _author
        result = _author(description=req.description, examples=req.examples)
        return {
            **result,
            "next_step": (
                "Review the draft rule above, then POST to /policy/rules with "
                "the rule JSON to apply it. Remove 'source' and 'status' fields first."
                if result.get("rule") else
                "Rule could not be generated. See warnings for details."
            ),
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Policy author unavailable: {exc}")


@router.get("/audit-mining")
async def get_audit_mining_report(request: Request):
    """Return the latest AI audit trail anomaly mining report.

    The report is generated nightly from the audit trail and surfaces
    potential security patterns, behavioral drift, and threat vectors.
    All findings are advisory — no automatic action is taken.
    """
    try:
        from ..ai.audit_miner import get_cached_mining_report
        report = get_cached_mining_report()
        if not report.get("generated_at"):
            return {
                "report": None,
                "generated_at": None,
                "finding_count": 0,
                "note": "Audit mining runs nightly. No report available yet — check back after the first overnight run.",
            }
        return report
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Audit miner unavailable: {exc}")
