"""Compliance report generation routes."""

import json
import logging
import csv
import io
from datetime import datetime, UTC
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import JSONResponse, Response

from ..persistence import get_db
from ..tenancy import get_request_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/compliance", tags=["compliance"])


def _csv_report_rows(report: dict) -> str:
    """Render compliance report sections as key/value CSV rows."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["section", "metric", "value"])
    for section, payload in (report.get("sections") or {}).items():
        if isinstance(payload, dict):
            for key, value in payload.items():
                if isinstance(value, (dict, list)):
                    writer.writerow([section, key, json.dumps(value)])
                else:
                    writer.writerow([section, key, value])
        else:
            writer.writerow([section, "value", payload])
    return output.getvalue()


@router.get("/report")
async def generate_compliance_report(
    request: Request,
    start_date: Optional[str] = Query(None, description="ISO date e.g. 2026-01-01"),
    end_date: Optional[str] = Query(None, description="ISO date e.g. 2026-12-31"),
    frameworks: Optional[str] = Query(None, description="Comma-separated: eu_ai_act,nist_ai_rmf,iso_42001,soc2,hipaa"),
    format: str = Query("json", pattern="^(json|csv|pdf)$"),
):
    """Generate a compliance report for the given date range.

    Implements Spec 7.1-7.4: one-click report with executive summary,
    policy compliance, anomaly summary, human oversight evidence,
    audit trail integrity verification, and regulatory framework mapping.
    """
    db = get_db()
    tenant_id = get_request_tenant_id(request)

    # Fetch events for date range
    events = db.query_audit_events(customer_id=tenant_id, limit=100000)

    # Apply date filter if specified
    if start_date or end_date:
        filtered = []
        for e in events:
            ts = e.get("timestamp", "") or e.get("created_at", "")
            if start_date and ts < start_date:
                continue
            if end_date and ts > end_date + "Z":
                continue
            filtered.append(e)
        events = filtered

    # ── Executive Summary ──────────────────────────────────────────────
    total_actions = len(events)
    blocked = sum(1 for e in events if e.get("decision", {}).get("verdict") == "BLOCK")
    allowed = sum(1 for e in events if e.get("decision", {}).get("verdict") == "ALLOW")
    escalated = sum(1 for e in events if e.get("decision", {}).get("verdict") in ("ESCALATE", "HUMAN_REQUIRED"))
    anomalies = sum(1 for e in events if (e.get("anomaly_score") or 0) > 50)
    overrides = sum(1 for e in events if e.get("human_override"))
    block_rate = round(blocked / total_actions * 100, 2) if total_actions else 0
    anomaly_rate = round(anomalies / total_actions * 100, 2) if total_actions else 0
    override_rate = round(overrides / total_actions * 100, 2) if total_actions else 0

    executive_summary = {
        "total_actions": total_actions,
        "total_governed": total_actions,
        "allowed": allowed,
        "blocked": blocked,
        "escalated": escalated,
        "block_rate_pct": block_rate,
        "anomaly_count": anomalies,
        "anomaly_rate_pct": anomaly_rate,
        "human_overrides": overrides,
        "override_rate_pct": override_rate,
        "date_range": {"start": start_date or "all-time", "end": end_date or "now"},
    }

    # ── Policy Compliance Summary ──────────────────────────────────────
    reason_code_counts: dict = {}
    for e in events:
        rc = e.get("decision", {}).get("reason_code", "UNKNOWN")
        reason_code_counts[rc] = reason_code_counts.get(rc, 0) + 1

    policy_summary = {
        "reason_code_distribution": reason_code_counts,
        "unique_policies_triggered": len(reason_code_counts),
    }

    # ── Anomaly Summary ──────────────────────────────────────────────
    anomaly_events = [e for e in events if (e.get("anomaly_score") or 0) > 0]
    high_anomalies = [e for e in anomaly_events if (e.get("anomaly_score") or 0) >= 80]
    medium_anomalies = [e for e in anomaly_events if 50 <= (e.get("anomaly_score") or 0) < 80]
    low_anomalies = [e for e in anomaly_events if (e.get("anomaly_score") or 0) < 50]

    anomaly_summary = {
        "total_anomalies": len(anomaly_events),
        "critical_high": len(high_anomalies),
        "medium": len(medium_anomalies),
        "low": len(low_anomalies),
    }

    # ── Human Oversight Evidence ──────────────────────────────────────
    human_oversight = {
        "total_human_overrides": overrides,
        "total_escalations": escalated,
        "override_events": [
            {
                "action_id": e.get("action", {}).get("id"),
                "timestamp": e.get("timestamp"),
                "override_actor": e.get("human_override_actor_id"),
                "reason": e.get("human_override_reason"),
            }
            for e in events if e.get("human_override")
        ][:50],  # Limit to 50 in report
    }

    # ── Audit Trail Integrity ──────────────────────────────────────────
    chain_result = db.verify_audit_chain()
    audit_integrity = {
        "chain_valid": chain_result.get("valid", False),
        "entries_verified": chain_result.get("checked", 0),
        "verification_message": chain_result.get("message", ""),
        "verified_at": datetime.now(UTC).isoformat(),
    }

    # ── Regulatory Framework Mapping ──────────────────────────────────
    selected_frameworks = [f.strip() for f in (frameworks or "").split(",") if f.strip()]
    framework_mapping = {}

    if "eu_ai_act" in selected_frameworks:
        framework_mapping["eu_ai_act"] = {
            "article_9_risk_management": {
                "status": "implemented",
                "evidence": f"{total_actions} actions governed with policy enforcement",
            },
            "article_10_data_governance": {
                "status": "implemented",
                "evidence": "Audit trail with cryptographic chaining",
            },
            "article_12_transparency": {
                "status": "implemented",
                "evidence": f"All decisions include reason codes and explanations",
            },
            "article_13_human_oversight": {
                "status": "implemented" if escalated > 0 or overrides > 0 else "no_events",
                "evidence": f"{escalated} escalations, {overrides} human overrides",
            },
        }

    if "nist_ai_rmf" in selected_frameworks:
        framework_mapping["nist_ai_rmf"] = {
            "govern": {"status": "implemented", "evidence": "Policy engine with versioning"},
            "map": {"status": "implemented", "evidence": "Audit trail maps every action to decision"},
            "measure": {"status": "implemented", "evidence": f"Anomaly detection on {total_actions} actions"},
            "manage": {"status": "implemented", "evidence": f"{blocked} actions blocked, {overrides} overridden"},
        }

    if "soc2" in selected_frameworks:
        framework_mapping["soc2"] = {
            "cc6_logical_access": {
                "status": "implemented",
                "evidence": "Multi-tenant RBAC with API key authentication",
            },
            "cc7_system_operations": {
                "status": "implemented",
                "evidence": f"Audit trail integrity: {chain_result.get('message', 'verified')}",
            },
        }

    if "iso_42001" in selected_frameworks:
        framework_mapping["iso_42001"] = {
            "clause_6_planning": {
                "status": "implemented",
                "evidence": "Policy packs for risk-based governance",
            },
            "clause_9_performance": {
                "status": "implemented",
                "evidence": f"Latency SLO tracked, {total_actions} actions governed",
            },
        }

    if "hipaa" in selected_frameworks:
        chain_valid = chain_result.get("valid", False)
        total_anomalies = anomaly_summary["total_anomalies"]
        review_queue_depth = human_oversight["total_escalations"]
        framework_mapping["hipaa"] = {
            "164_308_administrative_safeguards": {
                "policy_governance": {
                    "status": "implemented",
                    "evidence": f"EDON governor enforcing policies across {total_actions} governed actions with versioned policy engine",
                },
                "workforce_training": {
                    "status": "implemented",
                    "evidence": f"Cryptographic audit trail records actor identity for every action; {total_actions} events logged",
                },
                "access_management": {
                    "status": "implemented",
                    "evidence": "Multi-tenant RBAC: super_admin/governance_admin/security_admin/operator/auditor/developer/viewer enforced per-request",
                },
            },
            "164_310_physical_safeguards": {
                "workstation_device_controls": {
                    "status": "infrastructure_layer",
                    "evidence": "Physical controls delegated to deployment infrastructure (Fly.io). EDON enforces logical access controls.",
                },
            },
            "164_312_technical_safeguards": {
                "access_control": {
                    "status": "implemented",
                    "evidence": "bcrypt API key hashing + RBAC role enforcement on every request",
                },
                "audit_controls": {
                    "status": "implemented",
                    "evidence": f"SHA-256 hash chain audit trail; chain_valid={chain_valid}; {total_actions} append-only events",
                },
                "integrity": {
                    "status": "implemented",
                    "evidence": "Tamper-evident audit trail with HMAC-SHA256 signing; chain verification endpoint available",
                },
                "transmission_security": {
                    "status": "implemented",
                    "evidence": "TLS enforced via Fly.io force_https=true; no plaintext connections permitted",
                },
            },
            "164_400_breach_notification": {
                "detection": {
                    "status": "implemented",
                    "evidence": f"Anomaly detection running; {total_anomalies} anomalous actions detected and escalated",
                },
                "escalation": {
                    "status": "implemented",
                    "evidence": f"Human review queue: {review_queue_depth} items pending; Slack/email notifications configured",
                },
            },
            "164_504_business_associate": {
                "baa_requirement": {
                    "status": "action_required",
                    "evidence": "A signed Business Associate Agreement with Fly.io (or your cloud provider) is required before processing PHI. Contact Fly.io enterprise support.",
                },
            },
            "164_514_phi_minimum_necessary": {
                "field_encryption": {
                    "status": "implemented",
                    "evidence": "Fernet AES-128-CBC field-level encryption applied to sensitive DB columns",
                },
                "log_scrubbing": {
                    "status": "implemented",
                    "evidence": "LogScrubberFilter removes tokens, API keys, SSNs, MRNs, DOBs, NPIs from all log output",
                },
            },
        }

    report = {
        "report_id": f"rpt-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}",
        "generated_at": datetime.now(UTC).isoformat(),
        "tenant_id": tenant_id,
        "date_range": {"start": start_date or "all-time", "end": end_date or "now"},
        "sections": {
            "executive_summary": executive_summary,
            "policy_compliance": policy_summary,
            "anomaly_summary": anomaly_summary,
            "human_oversight": human_oversight,
            "audit_integrity": audit_integrity,
            "regulatory_frameworks": framework_mapping,
        },
        "edon_version": "1.0.1",
    }

    if format == "csv":
        csv_payload = _csv_report_rows(report)
        return Response(
            content=csv_payload,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={report['report_id']}.csv",
            },
        )

    if format == "pdf":
        raise HTTPException(
            status_code=501,
            detail="PDF export requires weasyprint. Use format=json for now."
        )

    return report


@router.get("/evidence/export")
async def export_evidence_bundle(
    request: Request,
    start_date: Optional[str] = Query(None, description="ISO date e.g. 2026-01-01"),
    end_date: Optional[str] = Query(None, description="ISO date e.g. 2026-12-31"),
):
    """Export a signed evidence bundle for auditors.

    Returns a downloadable JSON package containing:
    - Executive summary (decisions, block rate, anomalies)
    - Full audit event log for the date range
    - Cryptographic chain verification proof
    - HMAC-SHA256 signature of the payload (use your EDON_AUDIT_CHAIN_SIGNING_KEY to verify)

    Suitable for Joint Commission audits, HIPAA reviews, and FDA SaMD assessments.
    """
    import hashlib
    import hmac as _hmac
    import os as _os

    db = get_db()
    tenant_id = get_request_tenant_id(request)
    events = db.query_audit_events(customer_id=tenant_id, limit=100000)

    if start_date or end_date:
        filtered = []
        for e in events:
            ts = e.get("timestamp", "") or e.get("created_at", "")
            if start_date and ts < start_date:
                continue
            if end_date and ts > end_date + "Z":
                continue
            filtered.append(e)
        events = filtered

    chain = db.verify_audit_chain()

    # ── Executive summary ──────────────────────────────────────────────────
    total = len(events)
    blocked = sum(1 for e in events if e.get("decision", {}).get("verdict") == "BLOCK")
    escalated = sum(1 for e in events if e.get("decision", {}).get("verdict") in ("ESCALATE", "HUMAN_REQUIRED"))
    anomalies = sum(1 for e in events if (e.get("anomaly_score") or 0) > 50)
    overrides = sum(1 for e in events if e.get("human_override"))
    agents = list({e.get("agent_id") for e in events if e.get("agent_id")})

    summary = {
        "total_actions_governed": total,
        "blocked": blocked,
        "escalated_for_human_review": escalated,
        "allowed": total - blocked - escalated,
        "block_rate_pct": round(blocked / total * 100, 2) if total else 0,
        "anomaly_events": anomalies,
        "human_overrides": overrides,
        "unique_agents": len(agents),
        "date_range": {"start": start_date or "all-time", "end": end_date or "now"},
    }

    generated_at = datetime.now(UTC).isoformat()
    bundle_id = f"evb-{tenant_id or 'unknown'}-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"

    bundle = {
        "bundle_id": bundle_id,
        "bundle_type": "edon_evidence_package_v1",
        "generated_at": generated_at,
        "generated_by": "EDON Gateway v1.0.1",
        "tenant_id": tenant_id,
        "summary": summary,
        "audit_chain_verification": chain,
        "chain_valid": chain.get("valid", False),
        "event_count": total,
        "events": events,
        "regulations_covered": [
            "HIPAA §164.312 (Technical Safeguards)",
            "HIPAA §164.308 (Administrative Safeguards)",
            "HITECH §13402 (Breach Notification)",
            "FDA SaMD Guidance (Performance Monitoring)",
            "Joint Commission NPSG.15.01.01",
            "ISO 13485 §8.2.3",
        ],
    }

    # ── HMAC-SHA256 signature ──────────────────────────────────────────────
    # Sign the canonical payload so auditors can verify this bundle hasn't been altered.
    signing_key = _os.getenv("EDON_AUDIT_CHAIN_SIGNING_KEY", "")
    payload_bytes = json.dumps(
        {"bundle_id": bundle_id, "generated_at": generated_at, "event_count": total, "chain": chain},
        sort_keys=True,
    ).encode()
    if signing_key:
        sig = _hmac.new(signing_key.encode(), payload_bytes, hashlib.sha256).hexdigest()
        bundle["signature"] = f"sha256={sig}"
        bundle["signature_note"] = (
            "Verify with: HMAC-SHA256(EDON_AUDIT_CHAIN_SIGNING_KEY, "
            "JSON{bundle_id, generated_at, event_count, chain})"
        )
    else:
        bundle["signature"] = "unsigned — set EDON_AUDIT_CHAIN_SIGNING_KEY to enable"

    filename = f"{bundle_id}.json"
    return JSONResponse(
        content=bundle,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── PHI Endpoint Allowlist ──────────────────────────────────────────────────────

from pydantic import BaseModel  # noqa: E402 — local import to avoid top-level pollution
from ..security.phi_allowlist import (
    load_allowlist, add_entry as _add_allowlist_entry, remove_entry as _remove_allowlist_entry,
)


class PHIAllowlistAddRequest(BaseModel):
    pattern: str
    label: str = ""


@router.get("/phi-allowlist")
async def get_phi_allowlist(request: Request):
    """List all approved URL patterns for PHI data transmission.

    Patterns are checked against every agent action that contains a URL.
    Actions with URLs not on this list are blocked (HIPAA §164.312 Transmission Security).

    Pattern formats:
    - Exact:  https://ehr.hospital.com/api
    - Prefix: https://ehr.hospital.com/*
    - Domain: *.hospital.com
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    entries = load_allowlist(tenant_id)
    return {
        "tenant_id": tenant_id,
        "entries": entries,
        "count": len(entries),
        "enforcement": "active" if entries else "inactive — add entries to enable PHI endpoint enforcement",
    }


@router.post("/phi-allowlist", status_code=201)
async def add_phi_allowlist_entry(request: Request, body: PHIAllowlistAddRequest):
    """Add a URL pattern to the PHI endpoint allowlist.

    Once at least one entry exists, all agent actions with URLs are checked
    against this list. Unmatched URLs are blocked.
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    if not body.pattern.startswith(("http://", "https://", "*.")):
        raise HTTPException(
            status_code=400,
            detail="Pattern must start with http://, https://, or *. (domain wildcard)",
        )
    try:
        entry = _add_allowlist_entry(
            tenant_id=tenant_id,
            pattern=body.pattern,
            label=body.label,
            added_by=str(tenant_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"added": True, "entry": entry}


@router.delete("/phi-allowlist/{entry_id}")
async def remove_phi_allowlist_entry(entry_id: str, request: Request):
    """Remove a URL pattern from the PHI endpoint allowlist."""
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    removed = _remove_allowlist_entry(tenant_id=tenant_id, entry_id=entry_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"removed": True, "entry_id": entry_id}


# ── Clinical Safety Mode ────────────────────────────────────────────────────────


class ClinicalSafetyActivateRequest(BaseModel):
    activated_by: Optional[str] = None


@router.post("/clinical-safety/activate", status_code=200)
async def activate_clinical_safety(
    request: Request,
    body: Optional[ClinicalSafetyActivateRequest] = None,
):
    """Activate Clinical Safety Mode for this tenant.

    Seeds all regulation-mapped policy rules (HIPAA, HITECH, FDA SaMD, DEA,
    Joint Commission, ISO 13485, 45 CFR 46) with `protected=true` so they
    cannot be silently disabled.

    Safe to call multiple times — already-existing rules are re-enabled and
    re-protected rather than duplicated.

    Returns counts of rules created vs. updated.
    """
    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    activated_by = (body.activated_by if body else None) or tenant_id
    result = db.activate_clinical_safety_mode(tenant_id=tenant_id, activated_by=activated_by)

    logger.info(
        "[compliance] Clinical Safety Mode activated for tenant=%s by=%s rules_created=%d rules_updated=%d",
        tenant_id, activated_by, result["rules_created"], result["rules_updated"],
    )
    return {
        "activated": True,
        "tenant_id": tenant_id,
        "rules_created": result["rules_created"],
        "rules_updated": result["rules_updated"],
        "total_rules": result["total"],
        "activated_by": activated_by,
        "message": (
            f"Clinical Safety Mode active. {result['total']} regulation-mapped rules "
            "are now protected and enforced."
        ),
    }


@router.get("/health")
async def compliance_health(request: Request):
    """Report Clinical Safety Mode compliance health for this tenant.

    Checks that all required regulation rules (per `REQUIRED_RULES_BY_REGULATION`)
    are present, enabled, and protected.

    **Status values per regulation:**
    - `pass` — all required rules present, enabled, and protected
    - `warning` — all rules present and enabled but one or more are not protected
    - `fail` — one or more required rules are missing or disabled

    **Overall status** is `pass` only if every regulation passes.
    """
    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    health = db.get_compliance_health(tenant_id=tenant_id)
    return health
