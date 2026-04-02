"""Privacy compliance routes — data retention, DSAR (GDPR/CCPA)."""

import logging
from fastapi import APIRouter, HTTPException, Query, Request

from ..middleware.rbac import check_permission
from ..persistence import get_db
from ..tenancy import get_request_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/privacy", tags=["privacy"])

_MIN_RETENTION_DAYS = 30   # Regulatory floor (most frameworks require ≥30 days)
_MAX_RETENTION_DAYS = 3650  # 10 years hard cap

# ── Retention Policy ──────────────────────────────────────────────────────────

@router.get("/retention")
async def get_retention_policy(request: Request):
    """Get current data retention policy for this tenant.

    Returns:
        retention_days: How many days audit events are kept before purge.
        purge_log:      Last 10 purge run records.
    """
    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    retention_days = db.get_tenant_retention_days(tenant_id)
    purge_log = db.list_purge_log(tenant_id=tenant_id, limit=10)
    return {
        "tenant_id": tenant_id,
        "retention_days": retention_days,
        "purge_log": purge_log,
    }


@router.put("/retention")
async def set_retention_policy(request: Request):
    """Update data retention window for this tenant. Admin role required.

    Body:
        retention_days (int, required) — 30–3650
    """
    tenant_info = getattr(request.state, "tenant_info", None) or {}
    if not check_permission(tenant_info, "admin"):
        raise HTTPException(status_code=403, detail="Admin role required")

    body = await request.json()
    retention_days = body.get("retention_days")
    if retention_days is None:
        raise HTTPException(status_code=400, detail="retention_days is required")
    try:
        retention_days = int(retention_days)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="retention_days must be an integer")
    if not (_MIN_RETENTION_DAYS <= retention_days <= _MAX_RETENTION_DAYS):
        raise HTTPException(
            status_code=400,
            detail=f"retention_days must be between {_MIN_RETENTION_DAYS} and {_MAX_RETENTION_DAYS}",
        )

    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    db.set_tenant_retention_days(tenant_id=tenant_id, retention_days=retention_days)
    logger.info("Retention updated: tenant=%s days=%d", tenant_id, retention_days)
    return {"tenant_id": tenant_id, "retention_days": retention_days, "updated": True}


@router.post("/retention/purge")
async def trigger_purge(request: Request):
    """Manually trigger a data purge for events beyond the retention window.

    Admin role required. Returns count of events purged.
    Uses current retention_days setting unless override is provided in body.

    Body (optional):
        retention_days_override (int) — use a custom window for this purge only
    """
    tenant_info = getattr(request.state, "tenant_info", None) or {}
    if not check_permission(tenant_info, "admin"):
        raise HTTPException(status_code=403, detail="Admin role required")

    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    override = body.get("retention_days_override")
    if override is not None:
        try:
            override = int(override)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="retention_days_override must be an integer")
        if not (_MIN_RETENTION_DAYS <= override <= _MAX_RETENTION_DAYS):
            raise HTTPException(
                status_code=400,
                detail=f"retention_days_override must be between {_MIN_RETENTION_DAYS} and {_MAX_RETENTION_DAYS}",
            )
        retention_days = override
    else:
        retention_days = db.get_tenant_retention_days(tenant_id)

    purged_count = db.purge_old_events(tenant_id=tenant_id, retention_days=retention_days)
    logger.info(
        "Purge complete: tenant=%s retention_days=%d purged=%d",
        tenant_id, retention_days, purged_count,
    )
    return {
        "tenant_id": tenant_id,
        "retention_days_used": retention_days,
        "purged_count": purged_count,
    }


# ── DSAR (Subject Data Access / Deletion) ─────────────────────────────────────

@router.get("/subject-data")
async def get_subject_data(
    request: Request,
    subject_id: str = Query(..., description="Agent ID or subject identifier"),
):
    """GDPR/CCPA subject access request — return all data for a subject.

    Records a DSAR 'access' request and returns matching audit events.
    """
    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    # Log the DSAR request
    req_id = db.create_dsar_request(
        tenant_id=tenant_id,
        subject_id=subject_id,
        request_type="access",
        notes="Data access request via API",
    )

    events = db.get_subject_audit_events(tenant_id=tenant_id, subject_id=subject_id)

    # Mark completed immediately for access requests
    from ..persistence.database import Database
    if isinstance(db, Database):
        with db._get_connection() as conn:
            from datetime import datetime, UTC
            now = datetime.now(UTC).isoformat()
            conn.execute(
                "UPDATE dsar_requests SET status='completed', completed_at=? WHERE id=?",
                (now, req_id),
            )
            conn.commit()

    logger.info(
        "DSAR access: req_id=%s subject=%s tenant=%s events=%d",
        req_id, subject_id, tenant_id, len(events),
    )
    return {
        "dsar_request_id": req_id,
        "subject_id": subject_id,
        "event_count": len(events),
        "events": events,
    }


@router.delete("/subject-data")
async def delete_subject_data(
    request: Request,
    subject_id: str = Query(..., description="Agent ID or subject identifier"),
):
    """GDPR right-to-erasure — anonymize all subject data.

    Does NOT hard-delete rows (preserves audit chain integrity).
    Scrubs: agent_id, action_params, context, user_message, stated_intent.
    Admin role required.
    """
    tenant_info = getattr(request.state, "tenant_info", None) or {}
    if not check_permission(tenant_info, "admin"):
        raise HTTPException(status_code=403, detail="Admin role required to process DSAR deletion")

    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    # Log the DSAR deletion request first
    req_id = db.create_dsar_request(
        tenant_id=tenant_id,
        subject_id=subject_id,
        request_type="deletion",
        notes="Right-to-erasure request via API — fields anonymized, rows preserved for chain integrity",
    )

    anonymized_count = db.anonymize_subject_data(tenant_id=tenant_id, subject_id=subject_id)

    logger.info(
        "DSAR deletion: req_id=%s subject=%s tenant=%s anonymized=%d",
        req_id, subject_id, tenant_id, anonymized_count,
    )
    return {
        "dsar_request_id": req_id,
        "subject_id": subject_id,
        "anonymized_count": anonymized_count,
        "note": (
            "PHI fields (agent_id, action_params, context, user_message, stated_intent) "
            "have been replaced with [REDACTED-DSAR]. Audit rows are preserved to maintain "
            "chain integrity per HIPAA §164.530(j) and SOC 2 CC7.2."
        ),
    }


@router.get("/dsar-requests")
async def list_dsar_requests(
    request: Request,
    limit: int = Query(100, ge=1, le=1000),
):
    """List all DSAR requests for this tenant. Admin role required."""
    tenant_info = getattr(request.state, "tenant_info", None) or {}
    if not check_permission(tenant_info, "admin"):
        raise HTTPException(status_code=403, detail="Admin role required")

    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    requests_list = db.list_dsar_requests(tenant_id=tenant_id, limit=limit)
    return {"requests": requests_list, "count": len(requests_list)}
