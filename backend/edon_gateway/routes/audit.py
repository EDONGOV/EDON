"""Audit trail management routes: export, chain verification, human review queue."""

import csv
import hashlib
import io
import json
import os
import secrets
import uuid
import zipfile
import logging
from datetime import datetime, UTC, timedelta
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse

from ..persistence import get_db
from ..tenancy import get_request_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/query")
async def query_audit(
    request: Request,
    agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
    verdict: Optional[str] = Query(None, description="Filter by verdict: ALLOW, BLOCK, ESCALATE, DEGRADE, PAUSE"),
    intent_id: Optional[str] = Query(None, description="Filter by intent ID"),
    from_ts: Optional[str] = Query(None, description="ISO-8601 start timestamp (inclusive)"),
    to_ts: Optional[str] = Query(None, description="ISO-8601 end timestamp (inclusive)"),
    limit: int = Query(100, ge=1, le=10000),
):
    """Query audit events with optional filters.

    Supports filtering by agent_id, verdict, intent_id, and date range.
    Tenant-scoped: results are always restricted to the caller's tenant.
    """
    db = get_db()
    tenant_id = get_request_tenant_id(request)

    events = db.query_audit_events(
        agent_id=agent_id,
        verdict=verdict,
        intent_id=intent_id,
        customer_id=tenant_id,
        limit=limit,
    )

    # Apply timestamp range filter in Python (DB layer doesn't accept date range)
    if from_ts or to_ts:
        def _in_range(ev: dict) -> bool:
            ts = ev.get("timestamp") or ev.get("created_at") or ""
            if from_ts and ts < from_ts:
                return False
            if to_ts and ts > to_ts:
                return False
            return True
        events = [e for e in events if _in_range(e)]

    return {
        "events": events,
        "count": len(events),
        "filters": {
            "agent_id": agent_id,
            "verdict": verdict,
            "intent_id": intent_id,
            "from_ts": from_ts,
            "to_ts": to_ts,
        },
    }


@router.get("/decisions/{action_id}")
async def get_decision(action_id: str, request: Request):
    """Look up the governance decision for a specific action ID."""
    db = get_db()
    tenant_id = get_request_tenant_id(request)

    # query_audit_events enforces tenant isolation
    events = db.query_audit_events(customer_id=tenant_id, limit=1)
    # Use the audit table (most complete record) for point lookup
    try:
        with db._get_connection() as conn:
            q = "SELECT * FROM audit_events WHERE action_id = ?"
            params: list = [action_id]
            if tenant_id is not None:
                q += " AND customer_id = ?"
                params.append(tenant_id)
            q += " ORDER BY id DESC LIMIT 1"
            cursor = conn.cursor()
            cursor.execute(q, params)
            row = cursor.fetchone()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")

    if not row:
        raise HTTPException(status_code=404, detail=f"Decision not found for action_id: {action_id}")

    import json as _json
    return {
        "action_id": row["action_id"],
        "agent_id": row["agent_id"],
        "verdict": row["decision_verdict"],
        "reason_code": row["decision_reason_code"],
        "explanation": row["decision_explanation"],
        "policy_version": row["decision_policy_version"],
        "intent_id": row["intent_id"],
        "action_tool": row["action_tool"],
        "action_op": row["action_op"],
        "action_summary": row["action_summary"],
        "timestamp": row["timestamp"],
        "created_at": row["created_at"],
        "latency_ms": row["processing_latency_ms"],
        "policy_rule_id": row["policy_rule_id"],
        "context": _json.loads(row["context"]) if row["context"] else {},
    }


@router.get("/verify-chain")
async def verify_audit_chain(request: Request, limit: Optional[int] = Query(None)):
    """Verify cryptographic integrity of audit trail hash chain.

    Returns verification result including whether chain is valid,
    how many entries were checked, and where breakage occurred if any.
    """
    db = get_db()
    result = db.verify_audit_chain(limit=limit)
    status_code = 200 if result.get("valid") else 409
    return JSONResponse(content=result, status_code=status_code)


@router.get("/export")
async def export_audit_trail(
    request: Request,
    format: str = Query("json", pattern="^(json|csv|parquet)$"),
    agent_id: Optional[str] = Query(None),
    verdict: Optional[str] = Query(None),
    limit: int = Query(10000, le=100000),
    include_chain_proof: bool = Query(False),
):
    """Export audit trail in JSON, CSV, or Parquet format.

    Implements Spec 4.8: paginated export with optional chain verification proof.
    """
    db = get_db()
    tenant_id = get_request_tenant_id(request)

    events = db.query_audit_events(
        agent_id=agent_id,
        verdict=verdict,
        customer_id=tenant_id,
        limit=limit,
    )

    chain_proof = None
    if include_chain_proof:
        chain_proof = db.verify_audit_chain()

    if format == "json":
        payload = {"events": events, "count": len(events), "tenant_id": tenant_id}
        if chain_proof:
            payload["chain_verification"] = chain_proof
        return JSONResponse(content=payload)

    elif format == "csv":
        output = io.StringIO()
        if events:
            fieldnames = ["timestamp", "action_id", "agent_id", "action_tool", "action_op",
                         "verdict", "reason_code", "policy_version", "anomaly_score", "created_at"]
            writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for e in events:
                row = {
                    "timestamp": e.get("timestamp", ""),
                    "action_id": e.get("action", {}).get("id", ""),
                    "agent_id": e.get("action", {}).get("agent_id", ""),
                    "action_tool": e.get("action", {}).get("tool", ""),
                    "action_op": e.get("action", {}).get("op", ""),
                    "verdict": e.get("decision", {}).get("verdict", ""),
                    "reason_code": e.get("decision", {}).get("reason_code", ""),
                    "policy_version": e.get("decision", {}).get("policy_version", ""),
                    "anomaly_score": e.get("anomaly_score", ""),
                    "created_at": e.get("created_at", ""),
                }
                writer.writerow(row)
        csv_content = output.getvalue()
        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=audit_export_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv"}
        )

    elif format == "parquet":
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq

            if not events:
                raise HTTPException(status_code=404, detail="No events to export")

            flat_records = []
            for e in events:
                flat_records.append({
                    "timestamp": e.get("timestamp", ""),
                    "action_id": e.get("action", {}).get("id", ""),
                    "action_tool": e.get("action", {}).get("tool", ""),
                    "action_op": e.get("action", {}).get("op", ""),
                    "verdict": e.get("decision", {}).get("verdict", ""),
                    "reason_code": e.get("decision", {}).get("reason_code", ""),
                    "policy_version": e.get("decision", {}).get("policy_version", ""),
                    "created_at": e.get("created_at", ""),
                })

            table = pa.Table.from_pylist(flat_records)
            buf = io.BytesIO()
            pq.write_table(table, buf)
            buf.seek(0)

            return StreamingResponse(
                iter([buf.read()]),
                media_type="application/octet-stream",
                headers={"Content-Disposition": f"attachment; filename=audit_export_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.parquet"}
            )
        except ImportError:
            raise HTTPException(
                status_code=501,
                detail="Parquet export requires pyarrow. Install with: pip install pyarrow"
            )

    raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")


@router.get("/evidence-package")
async def export_evidence_package(
    request: Request,
    from_ts: Optional[str] = Query(None, description="ISO-8601 start timestamp (inclusive)"),
    to_ts: Optional[str] = Query(None, description="ISO-8601 end timestamp (inclusive)"),
    limit: int = Query(50000, le=100000),
):
    """Export a self-contained evidence package (ZIP) for auditors.

    Contents:
    - events.json     — full audit trail with all fields
    - events.csv      — tabular view of the same records
    - chain_verification.json — cryptographic integrity proof
    - manifest.json   — SHA-256 hash of every file + package metadata
    """
    import hashlib as _hashlib
    import json as _json
    import zipfile as _zipfile

    db = get_db()
    tenant_id = get_request_tenant_id(request)
    now_str = datetime.now(UTC).isoformat()

    events = db.query_audit_events(customer_id=tenant_id, limit=limit)

    # Apply optional timestamp filter
    if from_ts or to_ts:
        def _in_range(ev: dict) -> bool:
            ts = ev.get("timestamp") or ev.get("created_at") or ""
            if from_ts and ts < from_ts:
                return False
            if to_ts and ts > to_ts:
                return False
            return True
        events = [e for e in events if _in_range(e)]

    chain_result = db.verify_audit_chain()

    # ── Build file contents ──────────────────────────────────────────────────
    events_json_bytes = _json.dumps(
        {"events": events, "count": len(events), "tenant_id": tenant_id, "exported_at": now_str},
        indent=2, default=str,
    ).encode()

    csv_buf = io.StringIO()
    if events:
        fieldnames = ["timestamp", "action_id", "agent_id", "action_tool", "action_op",
                      "verdict", "reason_code", "policy_version", "anomaly_score", "created_at"]
        writer = csv.DictWriter(csv_buf, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for e in events:
            writer.writerow({
                "timestamp":      e.get("timestamp", ""),
                "action_id":      e.get("action", {}).get("id", ""),
                "agent_id":       e.get("action", {}).get("agent_id", ""),
                "action_tool":    e.get("action", {}).get("tool", ""),
                "action_op":      e.get("action", {}).get("op", ""),
                "verdict":        e.get("decision", {}).get("verdict", ""),
                "reason_code":    e.get("decision", {}).get("reason_code", ""),
                "policy_version": e.get("decision", {}).get("policy_version", ""),
                "anomaly_score":  e.get("anomaly_score", ""),
                "created_at":     e.get("created_at", ""),
            })
    csv_bytes = csv_buf.getvalue().encode()

    chain_json_bytes = _json.dumps(chain_result, indent=2).encode()

    def _sha256(data: bytes) -> str:
        return _hashlib.sha256(data).hexdigest()

    package_id = f"pkg_{uuid.uuid4().hex[:16]}"
    manifest = {
        "package_id": package_id,
        "tenant_id": tenant_id,
        "generated_at": now_str,
        "record_count": len(events),
        "chain_valid": chain_result.get("valid"),
        "date_range": {"from": from_ts, "to": to_ts},
        "files": {
            "events.json":              {"sha256": _sha256(events_json_bytes), "size_bytes": len(events_json_bytes)},
            "events.csv":               {"sha256": _sha256(csv_bytes),         "size_bytes": len(csv_bytes)},
            "chain_verification.json":  {"sha256": _sha256(chain_json_bytes),  "size_bytes": len(chain_json_bytes)},
        },
    }
    manifest_bytes = _json.dumps(manifest, indent=2).encode()
    # Add manifest's own hash after the fact
    manifest["files"]["manifest.json"] = {"sha256": _sha256(manifest_bytes), "size_bytes": len(manifest_bytes)}
    manifest_bytes = _json.dumps(manifest, indent=2).encode()

    # ── Assemble ZIP ────────────────────────────────────────────────────────
    zip_buf = io.BytesIO()
    with _zipfile.ZipFile(zip_buf, mode="w", compression=_zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("events.json",            events_json_bytes)
        zf.writestr("events.csv",             csv_bytes)
        zf.writestr("chain_verification.json", chain_json_bytes)
        zf.writestr("manifest.json",          manifest_bytes)
    zip_buf.seek(0)

    filename = f"edon_evidence_{tenant_id}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.zip"
    return StreamingResponse(
        iter([zip_buf.read()]),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Human Review Queue ─────────────────────────────────────────────────────────

router_review = APIRouter(prefix="/review", tags=["human-review"])


@router_review.get("/queue")
async def get_review_queue(
    request: Request,
    status: str = Query("pending", pattern="^(pending|approved|blocked|timeout)$"),
    limit: int = Query(50, le=500),
):
    """Get human review queue for actions requiring human decision."""
    db = get_db()
    tenant_id = get_request_tenant_id(request)
    items = db.get_review_queue(tenant_id=tenant_id, status=status, limit=limit)
    return {"queue": items, "count": len(items), "status_filter": status}


@router_review.post("/queue/{review_id}/decide")
async def decide_review(
    review_id: str,
    request: Request,
):
    """Submit human decision for a queued review.

    Body: {"decision": "approve"|"block", "reason": "optional reason"}
    """
    body = await request.json()
    decision = body.get("decision", "").lower()
    if decision not in ("approve", "block"):
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'block'")
    reason = body.get("reason", "")

    # Capture the individual reviewer identity (user_id + email preferred over tenant_id)
    tenant_info = getattr(request.state, "tenant_info", None) or {}
    user_id = tenant_info.get("user_id")
    email = tenant_info.get("email")
    tenant_id = getattr(request.state, "tenant_id", "unknown")

    if user_id and email:
        reviewer_id = f"{user_id}:{email}"
    elif email:
        reviewer_id = email
    elif user_id:
        reviewer_id = user_id
    else:
        reviewer_id = tenant_id  # fallback (dev/auth-disabled)

    db = get_db()

    updated = db.resolve_review_item(
        review_id=review_id,
        decision=decision,
        reviewer_id=reviewer_id,
        reason=reason,
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Review item not found: {review_id}")

    return {"review_id": review_id, "decision": decision, "reviewer_id": reviewer_id}


@router_review.post("/queue")
async def enqueue_review(request: Request):
    """Enqueue an action for human review (called internally by governor)."""
    body = await request.json()
    required = ["action_id", "agent_id", "action_type", "reason"]
    for field in required:
        if not body.get(field):
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")
    review_id = db.enqueue_review(
        tenant_id=tenant_id,
        action_id=body["action_id"],
        agent_id=body["agent_id"],
        action_type=body["action_type"],
        reason=body["reason"],
        context=body.get("context", {}),
        timeout_seconds=body.get("timeout_seconds", 300),
    )
    return {"review_id": review_id, "status": "pending"}


# ── Auditor Access Management ──────────────────────────────────────────────────

router_auditors = APIRouter(prefix="/auditors", tags=["auditors"])

_MAX_EXPIRES_HOURS = 720  # 30 days hard cap


@router_auditors.post("/invite")
async def invite_auditor(request: Request):
    """Create a time-limited read-only API key for an external auditor.

    Body:
        auditor_email  (str, required)  — email for labeling/tracking
        expires_in_hours (int, default 72, max 720) — how long the key is valid
        scope_note (str, optional) — e.g. "Q1 2026 SOC 2 Type II audit"

    Returns the raw API key (shown once — not stored in plaintext).
    Requires admin role.
    """
    from ..middleware.rbac import check_permission
    tenant_info = getattr(request.state, "tenant_info", None) or {}
    if not check_permission(tenant_info, "admin"):
        raise HTTPException(status_code=403, detail="Admin role required to invite auditors")

    body = await request.json()
    auditor_email = body.get("auditor_email", "").strip()
    if not auditor_email:
        raise HTTPException(status_code=400, detail="auditor_email is required")

    expires_in_hours = min(int(body.get("expires_in_hours", 72)), _MAX_EXPIRES_HOURS)
    scope_note = body.get("scope_note", "")
    expires_at = (datetime.now(UTC) + timedelta(hours=expires_in_hours)).isoformat()

    raw_key = f"edon_aud_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    label = f"Auditor: {auditor_email}" + (f" — {scope_note}" if scope_note else "")

    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    key_id = db.create_api_key(
        tenant_id=tenant_id,
        key_hash=key_hash,
        name=label,
        role="auditor",
        expires_at=expires_at,
    )

    logger.info("Auditor access granted: key_id=%s email=%s expires_at=%s tenant=%s",
                key_id, auditor_email, expires_at, tenant_id)

    return {
        "key_id": key_id,
        "api_key": raw_key,
        "auditor_email": auditor_email,
        "scope_note": scope_note,
        "role": "auditor",
        "expires_at": expires_at,
        "expires_in_hours": expires_in_hours,
        "warning": "Store this key securely — it will not be shown again.",
        "permissions": ["GET /audit/query", "GET /audit/verify-chain", "GET /audit/export", "GET /audit/evidence-package"],
    }


@router_auditors.get("")
async def list_auditor_grants(request: Request):
    """List all auditor access grants for this tenant. Requires admin role."""
    from ..middleware.rbac import check_permission
    tenant_info = getattr(request.state, "tenant_info", None) or {}
    if not check_permission(tenant_info, "admin"):
        raise HTTPException(status_code=403, detail="Admin role required")

    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    grants = db.list_auditor_grants(tenant_id=tenant_id)
    now = datetime.now(UTC).isoformat()
    for g in grants:
        g["expired"] = bool(g.get("expires_at") and g["expires_at"] < now)
    return {"grants": grants, "count": len(grants)}


@router_auditors.delete("/{key_id}")
async def revoke_auditor_grant(key_id: str, request: Request):
    """Revoke an auditor access key immediately. Requires admin role."""
    from ..middleware.rbac import check_permission
    tenant_info = getattr(request.state, "tenant_info", None) or {}
    if not check_permission(tenant_info, "admin"):
        raise HTTPException(status_code=403, detail="Admin role required")

    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    revoked = db.revoke_api_key_scoped(key_id=key_id, tenant_id=tenant_id)
    if not revoked:
        raise HTTPException(status_code=404, detail=f"Auditor key not found: {key_id}")

    logger.info("Auditor access revoked: key_id=%s tenant=%s", key_id, tenant_id)
    return {"key_id": key_id, "status": "revoked"}


# ── Policy Change Log ──────────────────────────────────────────────────────────

@router.get("/policy-changes")
async def list_policy_changes(
    request: Request,
    entity_type: Optional[str] = Query(None, description="Filter: 'policy_rule' | 'policy_pack' | 'active_preset'"),
    limit: int = Query(200, ge=1, le=1000),
):
    """Return append-only log of every policy mutation for this tenant.

    Supports filtering by entity_type. Records are immutable once written —
    this endpoint provides evidence for SOC 2 CC6.1 change management.
    """
    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    changes = db.list_policy_changes(
        tenant_id=tenant_id,
        entity_type=entity_type,
        limit=limit,
    )
    return {"changes": changes, "count": len(changes)}


def record_policy_change(
    tenant_id: str,
    change_type: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    entity_name: Optional[str] = None,
    diff_json: Optional[dict] = None,
    changed_by: Optional[str] = None,
) -> None:
    """Helper called by policy write endpoints to log every mutation.

    Non-blocking: errors are logged but do not fail the primary request.
    """
    try:
        db = get_db()
        db.log_policy_change(
            tenant_id=tenant_id,
            change_type=change_type,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            diff_json=diff_json,
            changed_by=changed_by,
        )
    except Exception as exc:
        logger.warning("Failed to log policy change: %s", exc)
