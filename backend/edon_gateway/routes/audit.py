"""Audit trail management routes: export, chain verification, human review queue."""

import asyncio
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
from ..config import config

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


@router.get("/stream")
async def stream_audit_events(request: Request):
    """SSE stream of real-time audit events for SIEM integration (Splunk, Datadog, Elastic).

    Connect once; each governance decision fires an event within milliseconds.
    Events are JSON objects encoded as SSE data frames.
    A keep-alive comment (`: heartbeat`) is sent every 15 s so proxies don't close idle connections.

    Tenant-scoped: only events belonging to the caller's tenant are pushed.

    Example frame:
        data: {"timestamp":"2026-04-25T10:00:00Z","verdict":"BLOCK","reason_code":"INV-003-RISK-GATE",...}
    """
    from ..audit_queue import subscribe_sse, unsubscribe_sse

    tenant_id = get_request_tenant_id(request)

    async def event_generator():
        q = subscribe_sse(maxsize=200)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                    # Tenant isolation: drop events not belonging to this tenant
                    if tenant_id and event.get("tenant_id") not in (tenant_id, None):
                        continue
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        except (asyncio.CancelledError, GeneratorExit):
            pass
        finally:
            unsubscribe_sse(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── CEF / JSON-LD helpers ──────────────────────────────────────────────────────

_CEF_VERDICT_SEVERITY: dict = {
    "ALLOW": 3, "DEGRADE": 4, "PAUSE": 5, "ESCALATE": 6, "BLOCK": 8, "ERROR": 8,
}


def _cef_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("=", "\\=").replace("\n", "\\n").replace("\r", "")


def _event_to_cef(event: dict) -> str:
    """Render one audit event as a CEF:0 line (ArcSight Common Event Format)."""
    action  = event.get("action") or {}
    decision = event.get("decision") or {}
    verdict    = (decision.get("verdict") or event.get("decision_verdict") or "UNKNOWN").upper()
    reason     = decision.get("reason_code") or event.get("decision_reason_code") or "UNKNOWN"
    explanation = decision.get("explanation") or event.get("decision_explanation") or ""
    agent_id   = action.get("agent_id") or event.get("agent_id") or ""
    tool       = action.get("tool") or event.get("action_tool") or ""
    op         = action.get("op") or event.get("action_op") or ""
    intent_id  = event.get("intent_id") or action.get("intent_id") or ""
    ts         = event.get("timestamp") or event.get("created_at") or ""
    tenant_id  = event.get("customer_id") or event.get("tenant_id") or ""

    # CEF severity 0-10
    severity = _CEF_VERDICT_SEVERITY.get(verdict, 5)

    # rt = epoch milliseconds
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else datetime.now(UTC)
        rt = int(dt.timestamp() * 1000)
    except Exception:
        rt = ""

    ext_parts = [
        f"suser={_cef_escape(agent_id)}",
        f"sproc={_cef_escape(f'{tool}.{op}')}",
        f"act={_cef_escape(verdict)}",
        f"outcome={_cef_escape(verdict)}",
        f"dvchost=edon-gateway",
        f"tenantId={_cef_escape(tenant_id)}",
    ]
    if intent_id:
        ext_parts.append(f"cs1={_cef_escape(intent_id)}")
        ext_parts.append("cs1Label=IntentId")
    if rt:
        ext_parts.append(f"rt={rt}")

    name = _cef_escape(explanation[:255])
    sig_id = _cef_escape(reason)

    return f"CEF:0|EDON|GovernanceGateway|1.0|{sig_id}|{name}|{severity}|{' '.join(ext_parts)}"


_JSONLD_CONTEXT = {
    "@vocab": "https://edoncore.com/schema/governance#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "schema": "https://schema.org/",
    "timestamp": {"@type": "xsd:dateTime"},
    "verdict": {"@id": "https://edoncore.com/schema/governance#Verdict"},
    "agent": {"@id": "schema:softwareAgent"},
}


def _event_to_jsonld(event: dict) -> dict:
    """Render one audit event as a JSON-LD node."""
    action   = event.get("action") or {}
    decision = event.get("decision") or {}
    action_id = action.get("id") or event.get("action_id") or ""
    return {
        "@type": "GovernanceDecision",
        "@id": f"urn:edon:decision:{action_id}" if action_id else None,
        "timestamp": event.get("timestamp") or event.get("created_at"),
        "agentId": action.get("agent_id") or event.get("agent_id"),
        "tool": action.get("tool") or event.get("action_tool"),
        "operation": action.get("op") or event.get("action_op"),
        "verdict": decision.get("verdict") or event.get("decision_verdict"),
        "reasonCode": decision.get("reason_code") or event.get("decision_reason_code"),
        "explanation": decision.get("explanation") or event.get("decision_explanation"),
        "intentId": event.get("intent_id"),
        "tenantId": event.get("customer_id"),
        "anomalyScore": event.get("anomaly_score"),
        "latencyMs": event.get("processing_latency_ms"),
    }


@router.get("/export")
async def export_audit_trail(
    request: Request,
    format: str = Query("json", pattern="^(json|csv|parquet|cef|jsonld)$"),
    agent_id: Optional[str] = Query(None),
    verdict: Optional[str] = Query(None),
    limit: int = Query(10000, le=100000),
    include_chain_proof: bool = Query(False),
    from_ts: Optional[str] = Query(None, description="ISO-8601 start (inclusive)"),
    to_ts: Optional[str] = Query(None, description="ISO-8601 end (inclusive)"),
):
    """Export audit trail in JSON, CSV, or Parquet format.

    Implements Spec 4.8: paginated export with optional chain verification proof.

    SIEM formats:
      cef    — ArcSight Common Event Format (CEF:0), one line per decision, for Splunk/QRadar/ArcSight
      jsonld — JSON-LD graph document for semantic/RDF-based SIEM pipelines
    """
    db = get_db()
    tenant_id = get_request_tenant_id(request)

    events = db.query_audit_events(
        agent_id=agent_id,
        verdict=verdict,
        customer_id=tenant_id,
        limit=limit,
    )

    if from_ts or to_ts:
        def _in_range(ev: dict) -> bool:
            ts = ev.get("timestamp") or ev.get("created_at") or ""
            if from_ts and ts < from_ts:
                return False
            if to_ts and ts > to_ts:
                return False
            return True
        events = [e for e in events if _in_range(e)]

    chain_proof = None
    if include_chain_proof:
        chain_proof = db.verify_audit_chain()

    ts_str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    if format == "cef":
        lines = [_event_to_cef(e) for e in events]
        content = "\n".join(lines) + ("\n" if lines else "")
        return StreamingResponse(
            iter([content.encode()]),
            media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename=edon_audit_{ts_str}.cef"},
        )

    if format == "jsonld":
        nodes = [_event_to_jsonld(e) for e in events]
        doc = {
            "@context": _JSONLD_CONTEXT,
            "@graph": nodes,
            "exportedAt": datetime.now(UTC).isoformat(),
            "tenantId": tenant_id,
            "count": len(nodes),
        }
        content = json.dumps(doc, indent=2, default=str).encode()
        return StreamingResponse(
            iter([content]),
            media_type="application/ld+json",
            headers={"Content-Disposition": f"attachment; filename=edon_audit_{ts_str}.jsonld"},
        )

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


# ── Compliance Report Export ───────────────────────────────────────────────────

_INV_REGULATION_MAP: dict = {
    "INV-001-TENANT-RULES":     ("Custom Policy Rules",       "Tenant-defined governance policy override"),
    "INV-002-SCOPE-BOUNDARY":   ("Scope Boundary",            "HIPAA §164.308(a)(4) Minimum Necessary; SOC2 CC6.1"),
    "INV-003-RISK-GATE":        ("Risk Level Gate",           "FDA SaMD Guidance; ISO 14971 §6; Joint Commission NPSG.15.01.01"),
    "INV-004-INTENT-ALIGNMENT": ("Intent Alignment",          "HIPAA §164.308(a)(1) Security Management Process"),
    "INV-005-MAG-AUTH":         ("MAG Authorization",         "SOC2 CC9.2 Vendor/Partner Management"),
    "INV-006-INTENT-FRESH":     ("Intent Freshness",          "HIPAA §164.308(a)(5) Workforce Training"),
    "INV-007-SEQ-DRIFT":        ("Sequence Drift Detection",  "HIPAA §164.308(a)(1)(ii)(D) Activity Review; FDA SaMD Anomaly Handling"),
    "INV-090-POLICY-ENGINE":    ("Policy Engine Health",      "SOC2 CC7.1 System Monitoring"),
}

_VERDICT_REGULATION_MAP: dict = {
    "ALLOW":    "HIPAA §164.308(a)(4) Minimum Necessary — Approved",
    "BLOCK":    "HIPAA §164.308(a)(1); SOC2 CC6.1; ISO 14971 §6",
    "ESCALATE": "FDA SaMD Human Oversight; Joint Commission NPSG.15.01.01",
    "DEGRADE":  "ISO 14971 §6 Risk Control — Safe Alternative Applied",
    "PAUSE":    "HIPAA §164.308(a)(1)(ii)(D) Activity Review",
    "ERROR":    "HIPAA §164.308(a)(1) Security Management",
}


def _build_report_payload(
    events: list,
    tenant_id: Optional[str],
    from_ts: Optional[str],
    to_ts: Optional[str],
) -> dict:
    total = len(events)
    verdict_counts: dict = {}
    latencies: list = []
    agents: set = set()

    for e in events:
        v = (e.get("decision", {}).get("verdict") or e.get("decision_verdict") or "UNKNOWN").upper()
        verdict_counts[v] = verdict_counts.get(v, 0) + 1
        lat = e.get("processing_latency_ms")
        if lat is not None:
            try:
                latencies.append(float(lat))
            except (ValueError, TypeError):
                pass
        a = e.get("action", {}).get("agent_id") or e.get("agent_id")
        if a:
            agents.add(a)

    allowed   = verdict_counts.get("ALLOW", 0)
    blocked   = verdict_counts.get("BLOCK", 0) + verdict_counts.get("ERROR", 0)
    escalated = verdict_counts.get("ESCALATE", 0) + verdict_counts.get("PAUSE", 0)
    degraded  = verdict_counts.get("DEGRADE", 0)
    compliance_rate = round((allowed + degraded) / total, 4) if total > 0 else 1.0
    avg_lat = round(sum(latencies) / len(latencies), 1) if latencies else None

    regulations: set = set()
    for e in events:
        v = (e.get("decision", {}).get("verdict") or e.get("decision_verdict") or "").upper()
        reg = _VERDICT_REGULATION_MAP.get(v, "")
        if reg:
            regulations.update(r.strip() for r in reg.split(";"))
        ctx = e.get("context") or {}
        for inv in ctx.get("invariant_results", []):
            inv_id = (inv.get("id") or "").upper()
            for key, (_, reg_str) in _INV_REGULATION_MAP.items():
                if key in inv_id:
                    regulations.update(r.strip() for r in reg_str.split(";"))

    decision_records = []
    for e in events:
        action   = e.get("action", {})
        decision = e.get("decision", {})
        verdict  = (decision.get("verdict") or e.get("decision_verdict") or "").upper()
        ctx = e.get("context") or {}
        inv_checks = ctx.get("invariant_results", [])
        inv_summary = []
        for inv in inv_checks:
            inv_id = inv.get("id", "").upper()
            meta = _INV_REGULATION_MAP.get(inv_id, ("", ""))
            inv_summary.append({
                "check":      inv.get("id", ""),
                "label":      meta[0],
                "status":     inv.get("status", ""),
                "regulation": meta[1],
                "details":    inv.get("details", ""),
            })
        decision_records.append({
            "decision_id":      e.get("id") or action.get("id") or "",
            "timestamp":        e.get("timestamp") or e.get("created_at") or "",
            "agent_id":         action.get("agent_id") or e.get("agent_id") or "",
            "tool":             action.get("tool") or e.get("action_tool") or "",
            "operation":        action.get("op") or e.get("action_op") or "",
            "verdict":          verdict,
            "reason_code":      decision.get("reason_code") or e.get("decision_reason_code") or "",
            "explanation":      decision.get("explanation") or e.get("decision_explanation") or "",
            "regulation":       _VERDICT_REGULATION_MAP.get(verdict, ""),
            "latency_ms":       e.get("processing_latency_ms"),
            "anomaly_score":    e.get("anomaly_score"),
            "intent_id":        e.get("intent_id") or action.get("intent_id") or "",
            "invariant_checks": inv_summary,
        })

    return {
        "report_id":          f"rpt_{uuid.uuid4().hex[:16]}",
        "generated_at":       datetime.now(UTC).isoformat(),
        "tenant_id":          tenant_id or "",
        "period":             {"from": from_ts, "to": to_ts},
        "summary": {
            "total_decisions": total,
            "allowed":         allowed,
            "blocked":         blocked,
            "escalated":       escalated,
            "degraded":        degraded,
            "compliance_rate": compliance_rate,
            "avg_latency_ms":  avg_lat,
            "unique_agents":   len(agents),
            "verdict_breakdown": verdict_counts,
        },
        "regulatory_coverage": sorted(regulations),
        "decisions":           decision_records,
    }


@router.get("/report/export")
async def export_compliance_report(
    request: Request,
    format: str = Query("json", pattern="^(json|pdf)$"),
    from_ts: Optional[str] = Query(None),
    to_ts: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
    verdict: Optional[str] = Query(None),
    limit: int = Query(1000, ge=1, le=5000),
):
    """Export structured compliance report for bank/enterprise auditors.

    Returns decision log with regulation mappings, INV check translations,
    and summary statistics. Supports JSON (machine-readable) and PDF formats.
    """
    db = get_db()
    tenant_id = get_request_tenant_id(request)

    events = db.query_audit_events(
        agent_id=agent_id,
        verdict=verdict,
        customer_id=tenant_id,
        limit=limit,
    )

    if from_ts or to_ts:
        def _in_range(ev: dict) -> bool:
            ts = ev.get("timestamp") or ev.get("created_at") or ""
            if from_ts and ts < from_ts:
                return False
            if to_ts and ts > to_ts:
                return False
            return True
        events = [e for e in events if _in_range(e)]

    report = _build_report_payload(events, tenant_id, from_ts, to_ts)
    ts_str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    if format == "json":
        content = json.dumps(report, indent=2, default=str).encode()
        return StreamingResponse(
            iter([content]),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=edon_compliance_report_{ts_str}.json"},
        )

    # PDF format
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.lib.colors import HexColor, white
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="PDF export requires reportlab. Install with: pip install reportlab",
        )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm, bottomMargin=20 * mm,
        title=f"EDON Compliance Report — {tenant_id or 'Unknown'}",
    )

    styles = getSampleStyleSheet()
    PRIMARY = HexColor("#6366f1")
    MUTED   = HexColor("#71717a")
    RED     = HexColor("#ef4444")
    GREEN   = HexColor("#22c55e")
    AMBER   = HexColor("#f59e0b")
    BLUE    = HexColor("#3b82f6")

    h1    = ParagraphStyle("rh1",  parent=styles["Heading1"], fontSize=20, textColor=PRIMARY, spaceAfter=4)
    h2    = ParagraphStyle("rh2",  parent=styles["Heading2"], fontSize=13, textColor=PRIMARY, spaceAfter=4, spaceBefore=12)
    small = ParagraphStyle("rsm",  parent=styles["Normal"],   fontSize=8,  textColor=MUTED,   leading=11)

    VERDICT_COLORS = {
        "ALLOW":    GREEN,
        "BLOCK":    RED,
        "ESCALATE": AMBER,
        "DEGRADE":  BLUE,
        "PAUSE":    AMBER,
        "ERROR":    RED,
    }

    story = []

    # Header
    story.append(Paragraph("EDON Governance Platform", small))
    story.append(Paragraph("Compliance Audit Report", h1))
    story.append(HRFlowable(width="100%", thickness=1, color=PRIMARY, spaceAfter=8))

    meta_rows = [
        ["Report ID:",      report["report_id"]],
        ["Tenant:",         report["tenant_id"] or "—"],
        ["Generated:",      datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")],
        ["Period:",         f"{from_ts or 'All time'} → {to_ts or 'Now'}"],
        ["Total records:",  str(report["summary"]["total_decisions"])],
    ]
    meta_tbl = Table(meta_rows, colWidths=[45 * mm, 120 * mm])
    meta_tbl.setStyle(TableStyle([
        ("FONT",         (0, 0), (0, -1), "Helvetica-Bold", 8),
        ("FONT",         (1, 0), (1, -1), "Helvetica",      8),
        ("TEXTCOLOR",    (0, 0), (0, -1), MUTED),
        ("TEXTCOLOR",    (1, 0), (1, -1), HexColor("#27272a")),
        ("TOPPADDING",   (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 2),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 10 * mm))

    # Executive summary
    story.append(Paragraph("Executive Summary", h2))
    s = report["summary"]
    summary_rows = [
        ["Metric",                       "Value"],
        ["Total Decisions",              str(s["total_decisions"])],
        ["Allowed",                      str(s["allowed"])],
        ["Blocked",                      str(s["blocked"])],
        ["Escalated (Human Review)",     str(s["escalated"])],
        ["Degraded (Safe Alternative)",  str(s["degraded"])],
        ["Compliance Rate",              f"{s['compliance_rate'] * 100:.1f}%"],
        ["Avg Decision Latency",         f"{s['avg_latency_ms']} ms" if s["avg_latency_ms"] else "—"],
        ["Unique Agents",                str(s["unique_agents"])],
    ]
    sum_tbl = Table(summary_rows, colWidths=[90 * mm, 60 * mm])
    sum_tbl.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR",      (0, 0), (-1, 0), white),
        ("FONT",           (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("FONT",           (0, 1), (-1, -1), "Helvetica",     9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#f4f4f5"), white]),
        ("GRID",           (0, 0), (-1, -1), 0.5, HexColor("#e4e4e7")),
        ("TOPPADDING",     (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
        ("LEFTPADDING",    (0, 0), (-1, -1), 8),
    ]))
    story.append(sum_tbl)
    story.append(Spacer(1, 8 * mm))

    # Regulatory coverage
    story.append(Paragraph("Regulatory Coverage", h2))
    reg_text = " · ".join(report["regulatory_coverage"]) if report["regulatory_coverage"] else "None mapped in this period."
    story.append(Paragraph(reg_text, small))
    story.append(Spacer(1, 8 * mm))

    # Decision log
    story.append(Paragraph(f"Decision Log ({len(report['decisions'])} records)", h2))
    decisions = report["decisions"]
    if decisions:
        cap = 500
        header = ["#", "Timestamp", "Agent", "Tool / Op", "Verdict", "Reason Code", "Regulation"]
        rows = [header]
        for i, d in enumerate(decisions[:cap], 1):
            tool_op = f"{d['tool']}.{d['operation']}" if d["tool"] or d["operation"] else "—"
            ts_fmt  = (d["timestamp"] or "")[:19].replace("T", " ") or "—"
            rows.append([
                str(i),
                ts_fmt,
                (d["agent_id"] or "—")[:24],
                tool_op,
                d["verdict"] or "—",
                (d["reason_code"] or "—")[:30],
                (d["regulation"] or "—")[:55],
            ])

        col_widths = [8 * mm, 32 * mm, 28 * mm, 25 * mm, 18 * mm, 26 * mm, 31 * mm]
        dec_tbl = Table(rows, colWidths=col_widths, repeatRows=1)
        dec_tbl.setStyle(TableStyle([
            ("BACKGROUND",     (0, 0), (-1, 0), PRIMARY),
            ("TEXTCOLOR",      (0, 0), (-1, 0), white),
            ("FONT",           (0, 0), (-1, 0), "Helvetica-Bold", 7),
            ("FONT",           (0, 1), (-1, -1), "Helvetica",     7),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#f4f4f5"), white]),
            ("GRID",           (0, 0), (-1, -1), 0.3, HexColor("#e4e4e7")),
            ("TOPPADDING",     (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING",  (0, 0), (-1, -1), 3),
            ("LEFTPADDING",    (0, 0), (-1, -1), 4),
            ("VALIGN",         (0, 0), (-1, -1), "TOP"),
        ]))
        for i, d in enumerate(decisions[:cap], 1):
            color = VERDICT_COLORS.get(d["verdict"], MUTED)
            dec_tbl.setStyle(TableStyle([
                ("TEXTCOLOR", (4, i), (4, i), color),
                ("FONT",      (4, i), (4, i), "Helvetica-Bold", 7),
            ]))
        story.append(dec_tbl)
        if len(decisions) > cap:
            story.append(Spacer(1, 3 * mm))
            story.append(Paragraph(
                f"Note: PDF capped at {cap} records. Download JSON for all {len(decisions)} records.", small
            ))
    else:
        story.append(Paragraph("No decisions found for this period.", small))

    story.append(Spacer(1, 10 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor("#e4e4e7")))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        f"Generated by EDON Governance Platform · {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')} · "
        f"Report ID: {report['report_id']} · "
        f"All decisions are cryptographically chained and tamper-evident. "
        f"For chain proof, download the evidence package from /audit/evidence-package.",
        small,
    ))

    doc.build(story)
    buf.seek(0)

    filename = f"edon_compliance_report_{tenant_id or 'unknown'}_{ts_str}.pdf"
    return StreamingResponse(
        iter([buf.read()]),
        media_type="application/pdf",
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
        change_id = db.log_policy_change(
            tenant_id=tenant_id,
            change_type=change_type,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            diff_json=diff_json,
            changed_by=changed_by,
        )
        audit_action = {
            "id": f"policy-change-{change_id}",
            "tool": "policy",
            "op": change_type,
            "params": {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "entity_name": entity_name,
                "diff": diff_json or {},
            },
            "source": "policy_admin",
            "estimated_risk": "medium",
            "requested_at": datetime.now(UTC).isoformat(),
        }
        audit_decision = {
            "verdict": "ALLOW",
            "reason_code": "POLICY_CHANGE_RECORDED",
            "explanation": f"Policy {change_type} recorded for {entity_type}",
            "policy_version": "policy-change-log",
            "policy_rule_id": None,
        }
        db.save_audit_event(
            action=audit_action,
            decision=audit_decision,
            intent_id=None,
            agent_id=changed_by,
            context={
                "policy_change_id": change_id,
                "tenant_id": tenant_id,
                "change_type": change_type,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "entity_name": entity_name,
            },
            customer_id=tenant_id,
            action_summary=f"policy {change_type} for {entity_type}",
            stated_intent="Policy mutation audit",
            user_message=(json.dumps(diff_json) if diff_json else None),
        )
    except Exception as exc:
        if config.is_production():
            raise
        logger.warning("Failed to log policy change: %s", exc)
