"""Routes for querying shadow execution findings.

GET  /v1/shadow/findings            — list findings filtered by severity
GET  /v1/shadow/traces              — list recently captured traces
GET  /v1/shadow/summary             — verdict-change count breakdown by severity
GET  /v1/shadow/baseline/{trace_id} — Mode A baseline result for a trace
GET  /v1/shadow/confirmed-bypasses  — persisted confirmed bypass records
POST /v1/shadow/chain-stress        — session-level multi-step cascade test
GET  /v1/shadow/export              — structured audit report (JSON or CSV)
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, UTC
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..tenancy import get_request_tenant_id

router = APIRouter(prefix="/v1/shadow", tags=["shadow"])


@router.get("/findings")
async def get_shadow_findings(
    request: Request,
    severity: Optional[str] = Query(None, enum=["stable", "advisory", "critical"]),
    limit: int = Query(100, le=500),
):
    """Return shadow execution findings, newest first.

    critical — original block/escalate became ALLOW (policy bypass)
    advisory — verdict changed but not a clear bypass
    stable   — verdict held under perturbation
    """
    from ..shadow.trace_capture import get_trace_store
    tenant_id = get_request_tenant_id(request)
    findings = get_trace_store().recent_findings(
        tenant_id=tenant_id,
        severity=severity,
        limit=limit,
    )
    return {"findings": findings, "count": len(findings)}


@router.get("/traces")
async def get_shadow_traces(
    request: Request,
    limit: int = Query(50, le=200),
):
    """Return recently captured agent traces."""
    from ..shadow.trace_capture import get_trace_store
    tenant_id = get_request_tenant_id(request)
    traces = get_trace_store().get_recent_traces(tenant_id=tenant_id, limit=limit)
    return {
        "traces": [
            {
                "trace_id": t.trace_id,
                "captured_at": t.captured_at,
                "agent_id": t.agent_id,
                "action_type": t.action_type,
                "original_verdict": t.original_verdict,
                "original_latency_ms": t.original_latency_ms,
            }
            for t in traces
        ],
        "count": len(traces),
    }


@router.get("/summary")
async def get_shadow_summary(request: Request):
    """Return finding count breakdown by severity."""
    from ..shadow.trace_capture import get_trace_store
    tenant_id = get_request_tenant_id(request)
    store = get_trace_store()
    return {
        **store.finding_summary(tenant_id=tenant_id),
        "non_determinism_count": store.non_determinism_count(tenant_id=tenant_id),
    }


@router.get("/confirmed-bypasses")
async def get_confirmed_bypasses(
    request: Request,
    limit: int = Query(100, le=500),
):
    """Return persisted confirmed bypass records.

    A confirmed bypass = critical shadow finding (blocked action became ALLOW
    under perturbation) AND the agent subsequently reported a successful
    real execution. These are the highest priority findings to fix.
    """
    from ..shadow.trace_capture import get_trace_store
    tenant_id = get_request_tenant_id(request)
    bypasses = get_trace_store().get_confirmed_bypasses(tenant_id=tenant_id, limit=limit)
    return {"confirmed_bypasses": bypasses, "count": len(bypasses)}


@router.post("/chain-stress")
async def run_chain_stress(
    request: Request,
    session_id: str = Query(..., description="Session ID to stress-test"),
    perturbation_types: Optional[str] = Query(
        None,
        description="Comma-separated perturbation types to apply "
                    "(prompt_injection, context_poisoning, privilege_escalation, ...)"
    ),
    max_perturbations: int = Query(3, le=10),
):
    """Run session-level multi-step chain stress test.

    Injects adversarial perturbations at each step in a session's trace
    sequence and evaluates whether the effect cascades into verdict changes
    at downstream steps. Catches multi-step attack patterns that
    single-action shadow testing misses.
    """
    from ..shadow.replay import session_chain_stress
    from ..shadow.trace_capture import get_trace_store

    governor = getattr(request.app.state, "governor", None)
    if governor is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Governor not initialised")

    tenant_id = get_request_tenant_id(request)
    store = get_trace_store()

    types_filter = [t.strip() for t in perturbation_types.split(",")] if perturbation_types else None

    results = await session_chain_stress(
        session_id=session_id,
        governor=governor,
        store=store,
        tenant_id=tenant_id,
        perturbation_types=types_filter,
        max_perturbations=max_perturbations,
    )

    if not results:
        return {
            "session_id": session_id,
            "message": "Not enough traces in session for chain stress (need ≥ 2 steps)",
            "results": [],
        }

    summary = {
        "total_tests": len(results),
        "critical": sum(1 for r in results if r.severity == "critical"),
        "advisory": sum(1 for r in results if r.severity == "advisory"),
        "stable": sum(1 for r in results if r.severity == "stable"),
        "max_cascade": max(r.cascade_count for r in results),
    }

    return {
        "session_id": session_id,
        "summary": summary,
        "results": [
            {
                "injection_step": r.injection_step,
                "injection_trace_id": r.injection_trace_id,
                "perturbation_name": r.perturbation_name,
                "perturbation_type": r.perturbation_type,
                "steps_after": r.steps_after,
                "cascade_count": r.cascade_count,
                "severity": r.severity,
                "cascade_verdicts": r.cascade_verdicts,
            }
            for r in results
        ],
    }


@router.get("/export")
async def export_findings(
    request: Request,
    format: str = Query("json", enum=["json", "csv"]),
    severity: Optional[str] = Query(None, enum=["stable", "advisory", "critical"]),
):
    """Export shadow execution findings as a structured audit report.

    JSON — full structured report for API consumers and dashboards.
    CSV  — flat table for CISO review, compliance filing, and spreadsheet analysis.

    The report includes: audit header, summary stats, confirmed bypasses,
    critical and advisory findings, non-determinism events, and a
    policy recommendation for each finding type.
    """
    from ..shadow.trace_capture import get_trace_store
    tenant_id = get_request_tenant_id(request)
    store = get_trace_store()

    findings = store.recent_findings(tenant_id=tenant_id, severity=severity, limit=1000)
    bypasses = store.get_confirmed_bypasses(tenant_id=tenant_id, limit=500)
    summary = store.finding_summary(tenant_id=tenant_id)
    nd_count = store.non_determinism_count(tenant_id=tenant_id)

    if format == "csv":
        return _export_csv(findings, bypasses, summary, nd_count, tenant_id)
    return _export_json(findings, bypasses, summary, nd_count, tenant_id)


# ── Export helpers ─────────────────────────────────────────────────────────────

_POLICY_RECOMMENDATIONS: dict[str, str] = {
    "prompt_injection": (
        "Add or strengthen prompt injection detection rules for the affected "
        "tool/operation. Review payload sanitisation and consider blocking "
        "known injection patterns at the gateway level."
    ),
    "privilege_escalation": (
        "Add an explicit BLOCK rule for the escalated action_type. Audit the "
        "permission escalation map to ensure all higher-privilege operations "
        "require explicit approval."
    ),
    "context_poisoning": (
        "Restrict intent-based policy overrides for the affected tool/operation. "
        "Do not allow stated_intent or user_message fields to override "
        "explicit BLOCK rules."
    ),
    "malformed_payload": (
        "Add input schema validation for the affected tool/operation. "
        "Reject malformed payloads with a 400 before policy evaluation runs."
    ),
    "boundary_input": (
        "Add payload size limits and type constraints for the affected "
        "tool/operation. Consider adding a payload normalisation step before "
        "policy evaluation."
    ),
}


def _policy_recommendation(perturbation_type: str) -> str:
    return _POLICY_RECOMMENDATIONS.get(
        perturbation_type,
        "Review policy rules for the affected tool/operation.",
    )


def _export_json(findings, bypasses, summary, nd_count, tenant_id) -> dict:
    critical = [f for f in findings if f.get("severity") == "critical"]
    advisory = [f for f in findings if f.get("severity") == "advisory"]

    def _enrich(f: dict) -> dict:
        f = dict(f)
        f["policy_recommendation"] = _policy_recommendation(f.get("perturbation_type", ""))
        f["findings"] = f.get("findings") if isinstance(f.get("findings"), list) else []
        return f

    return {
        "report": {
            "generated_at": datetime.now(UTC).isoformat(),
            "tenant_id": tenant_id,
            "tool": "EDON Shadow Execution — Audit Report",
        },
        "summary": {
            **summary,
            "non_determinism_count": nd_count,
            "confirmed_bypasses": len(bypasses),
            "total_findings": len(findings),
        },
        "confirmed_bypasses": bypasses,
        "critical_findings": [_enrich(f) for f in critical],
        "advisory_findings": [_enrich(f) for f in advisory],
    }


def _export_csv(findings, bypasses, summary, nd_count, tenant_id) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.writer(buf)

    # Header block
    writer.writerow(["EDON Shadow Execution — Audit Report"])
    writer.writerow(["Generated", datetime.now(UTC).isoformat()])
    writer.writerow(["Tenant", tenant_id or "all"])
    writer.writerow([])
    writer.writerow(["SUMMARY"])
    writer.writerow(["Critical findings", summary.get("critical", 0)])
    writer.writerow(["Advisory findings", summary.get("advisory", 0)])
    writer.writerow(["Stable (held)", summary.get("stable", 0)])
    writer.writerow(["Governor non-determinism events", nd_count])
    writer.writerow(["Confirmed bypasses", len(bypasses)])
    writer.writerow([])

    # Confirmed bypasses
    if bypasses:
        writer.writerow(["CONFIRMED BYPASSES"])
        writer.writerow([
            "confirmed_at", "action_id", "agent_id", "action_type",
            "perturbation_name", "perturbation_type",
            "original_verdict", "shadow_verdict", "real_outcome",
            "policy_recommendation",
        ])
        for b in bypasses:
            writer.writerow([
                b.get("confirmed_at"), b.get("action_id"), b.get("agent_id"),
                b.get("action_type"), b.get("perturbation_name"),
                b.get("perturbation_type"), b.get("original_verdict"),
                b.get("shadow_verdict"), b.get("real_outcome"),
                _policy_recommendation(b.get("perturbation_type", "")),
            ])
        writer.writerow([])

    # All findings
    writer.writerow(["FINDINGS"])
    writer.writerow([
        "created_at", "severity", "trace_id", "agent_id", "action_type",
        "perturbation_name", "perturbation_type", "perturbed_field",
        "original_verdict", "shadow_verdict", "verdict_changed",
        "finding_text", "policy_recommendation",
    ])
    for f in findings:
        finding_texts = f.get("findings", [])
        text = " | ".join(finding_texts) if isinstance(finding_texts, list) else str(finding_texts)
        writer.writerow([
            f.get("created_at"), f.get("severity"), f.get("trace_id"),
            f.get("agent_id"), f.get("action_type"),
            f.get("perturbation_name"), f.get("perturbation_type"),
            f.get("perturbed_field"), f.get("trace_original_verdict"),
            f.get("shadow_verdict"), f.get("verdict_changed"),
            text, _policy_recommendation(f.get("perturbation_type", "")),
        ])

    buf.seek(0)
    filename = f"edon_shadow_report_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/baseline/{trace_id}")
async def get_baseline(trace_id: str):
    """Return the Mode A baseline result for a specific trace.

    non_determinism_flag=true means the governor produced a different verdict
    on the same input since capture — policy or runtime state has changed.
    """
    from ..shadow.trace_capture import get_trace_store
    row = get_trace_store().get_baseline(trace_id)
    if not row:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=404,
            detail=f"No baseline recorded for trace '{trace_id}'. "
                   "Baselines are written on the next shadow sample after capture."
        )
    return row


# ── Fix proposals ─────────────────────────────────────────────────────────────


@router.get("/fix-proposals")
async def get_fix_proposals(
    request: Request,
    status: Optional[str] = Query("pending_review", enum=["pending_review", "approved", "rejected", "applied"]),
    severity: Optional[str] = Query(None, enum=["critical", "advisory"]),
    limit: int = Query(100, le=500),
):
    """Return shadow-generated policy fix proposals queued for human review.

    These are auto-generated whenever a critical or advisory shadow finding is
    detected. Each proposal contains a suggested policy rule and the rationale.
    Approve or reject via the dedicated endpoints below.
    """
    from ..shadow.fix_pipeline import get_proposals
    tenant_id = get_request_tenant_id(request)
    proposals = get_proposals(tenant_id=tenant_id, status=status, severity=severity, limit=limit)
    return {"proposals": proposals, "count": len(proposals)}


@router.get("/fix-proposals/summary")
async def get_fix_proposals_summary(request: Request):
    """Return count breakdown of fix proposals by status and severity."""
    from ..shadow.fix_pipeline import proposal_summary
    tenant_id = get_request_tenant_id(request)
    return proposal_summary(tenant_id=tenant_id)


@router.post("/fix-proposals/{proposal_id}/approve")
async def approve_fix_proposal(
    proposal_id: str,
    request: Request,
    resolved_by: str = Query("api"),
    note: Optional[str] = Query(None),
):
    """Approve a fix proposal. Marks it as approved for the next policy push.

    Approved proposals are NOT automatically applied to live policy. An operator
    must explicitly push the rule via the policy management API.
    """
    from ..shadow.fix_pipeline import approve_proposal
    from fastapi import HTTPException
    result = approve_proposal(proposal_id, resolved_by=resolved_by, note=note)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found")
    return result


@router.post("/fix-proposals/{proposal_id}/reject")
async def reject_fix_proposal(
    proposal_id: str,
    request: Request,
    resolved_by: str = Query("api"),
    note: Optional[str] = Query(None),
):
    """Reject a fix proposal. Records rejection with optional explanation."""
    from ..shadow.fix_pipeline import reject_proposal
    from fastapi import HTTPException
    result = reject_proposal(proposal_id, resolved_by=resolved_by, note=note)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found")
    return result


# ── Governance validation gate ────────────────────────────────────────────────


class PolicyRuleBody(BaseModel):
    tool: Optional[str] = None
    operation: Optional[str] = None
    action: str = "BLOCK"
    reason: str = "Proposed policy rule"


class ValidatePolicyBody(BaseModel):
    rule: PolicyRuleBody
    limit: int = 50
    include_stable: bool = True


@router.post("/validate-policy")
async def validate_policy(request: Request, body: ValidatePolicyBody):
    """Run the governance validation gate for a proposed policy rule.

    Replays recent shadow findings through the governor with the proposed rule
    injected. Returns a regression report showing:
      - bypasses_fixed  — critical/advisory findings the rule would fix
      - regressions     — stable ALLOW traces the rule would incorrectly block
      - net_improvement — bypasses_fixed minus regressions (positive = safe)
      - recommendation  — "apply" | "review" | "reject" | "inconclusive"

    The rule is NEVER applied to live policy by this endpoint. It is purely
    advisory — human approval is always required before applying any rule change.

    Example body:
        {
            "rule": {
                "tool": "email",
                "operation": "send",
                "action": "BLOCK",
                "reason": "Block all email sends pending security review"
            },
            "limit": 50
        }
    """
    from ..shadow.policy_validator import validate_proposed_rule_async
    from ..shadow.trace_capture import get_trace_store
    from fastapi import HTTPException

    governor = getattr(request.app.state, "governor", None)
    if governor is None:
        raise HTTPException(status_code=503, detail="Governor not initialised")

    tenant_id = get_request_tenant_id(request)
    store = get_trace_store()

    rule_dict = {
        "tool": body.rule.tool,
        "operation": body.rule.operation,
        "action": body.rule.action,
        "reason": body.rule.reason,
    }

    from dataclasses import asdict
    report = await validate_proposed_rule_async(
        rule_dict,
        governor=governor,
        store=store,
        tenant_id=tenant_id,
        limit=max(1, min(body.limit, 200)),
        include_stable=body.include_stable,
    )

    return asdict(report)
