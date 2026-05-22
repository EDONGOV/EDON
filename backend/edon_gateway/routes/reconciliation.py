"""Fleet reconciliation endpoints.

This covers the Operations tab: compare an imported source inventory against
the EDON fleet, classify rows, and apply cohort actions such as hold,
promote, and duplicate merge.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, UTC
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..config import config
from ..logging_config import get_logger
from ..persistence import get_db
from ..tenancy import get_request_tenant_id
from ..department_scope import get_department_scope

logger = get_logger(__name__)
router = APIRouter(prefix="/v1/operations/reconciliation", tags=["operations"])
ADMIN_ROLES = {"admin", "super_admin", "governance_admin", "security_admin"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _norm(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _require_operations_admin(request: Request) -> None:
    tenant_info = getattr(request.state, "tenant_info", None)
    if not tenant_info and not config.AUTH_ENABLED:
        return
    role = (tenant_info or {}).get("role", "viewer")
    if role not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Operations admin role required")


def _assert_department_scope(request: Request, department: Optional[str]) -> None:
    scope = get_department_scope(request)
    if scope and department and department != scope:
        raise HTTPException(status_code=403, detail="Department-scoped users cannot reconcile another department")


def _row_key(row: dict) -> str:
    seed = "|".join([
        _norm(row.get("agent_id") or row.get("name")),
        _norm(row.get("vendor_id") or row.get("vendor")),
        _norm(row.get("department")),
        _norm(row.get("scope")),
    ])
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _risk_from_row(row: dict) -> str:
    text = " ".join([
        row.get("scope", ""),
        row.get("action", ""),
        " ".join(row.get("connectors") or []),
    ]).lower()
    if any(k in text for k in ("writeback", "medication", "delete", "destroy", "admin")):
        return "high"
    if any(k in text for k in ("export", "phi", "ehr", "note", "draft")):
        return "medium"
    return "low"


def _classify_row(incoming: dict, existing: Optional[dict], seen_keys: set[str]) -> dict:
    key = _row_key(incoming)
    duplicate = key in seen_keys
    seen_keys.add(key)
    risk = _risk_from_row(incoming)
    status = "duplicate" if duplicate else "new"
    action = "Merge duplicate IDs" if duplicate else "Register audit-only"
    comparison = {}
    if existing is not None and not duplicate:
        existing_scope = " ".join(existing.get("capabilities") or [])
        existing_dept = existing.get("department") or ""
        existing_vendor = existing.get("vendor_id") or ""
        changed = any([
            _norm(existing_vendor) != _norm(incoming.get("vendor_id") or incoming.get("vendor")),
            _norm(existing_dept) != _norm(incoming.get("department")),
            _norm(existing_scope) != _norm(incoming.get("scope")),
        ])
        if changed:
            status = "changed"
            action = "Review scope drift"
        else:
            status = "ready"
            action = "Promote low-risk batch" if risk in {"low", "medium"} else "Hold until reviewed"
        comparison = {
            "existing_department": existing_dept,
            "existing_vendor_id": existing_vendor,
            "existing_scope": existing_scope,
        }
    elif duplicate:
        comparison = {"duplicate_of": key}

    return {
        "row_key": key,
        "name": incoming.get("name", ""),
        "vendor": incoming.get("vendor") or incoming.get("vendor_name") or "",
        "vendor_id": incoming.get("vendor_id") or "",
        "department": incoming.get("department") or "",
        "scope": incoming.get("scope") or "",
        "action": incoming.get("action") or action,
        "runtime_type": incoming.get("runtime_type") or "Service",
        "connectors": incoming.get("connectors") or [],
        "status": status,
        "risk": risk,
        "matched_agent_id": existing.get("agent_id") if existing else None,
        "comparison": comparison,
        "selected": False,
    }


def _audit_reconciliation_event(tenant_id: str, *, action_op: str, verdict: str, actor: str, batch: dict, notes: str = "") -> None:
    db = get_db()
    action = {
        "id": f"{action_op}-{batch['batch_id']}",
        "tool": "reconciliation",
        "op": action_op,
        "params": batch,
        "source": "operations",
        "estimated_risk": json.dumps(batch.get("summary", {}).get("risk_mix", {})),
        "computed_risk": batch.get("summary", {}).get("ready", 0),
        "requested_at": batch.get("updated_at") or batch.get("created_at") or _now(),
    }
    decision = {
        "verdict": verdict,
        "reason_code": "FLEET_RECONCILIATION",
        "explanation": notes or batch.get("summary", {}).get("message", "Fleet reconciliation updated."),
        "policy_version": batch.get("cohort_mode", "purpose"),
        "action_summary": f"{action_op}: {batch['batch_id']}",
    }
    context = {
        "tenant_id": tenant_id,
        "batch_id": batch["batch_id"],
        "source_system": batch.get("source_system"),
        "vendor_name": batch.get("vendor_name"),
        "vendor_id": batch.get("vendor_id"),
        "source_type": batch.get("source_type"),
        "cohort_mode": batch.get("cohort_mode"),
        "posture": batch.get("posture"),
        "status": batch.get("status"),
        "summary": batch.get("summary", {}),
        "actor": actor,
        "notes": notes,
    }
    try:
        db.save_audit_event(
            action,
            decision,
            intent_id=batch["batch_id"],
            agent_id=None,
            context=context,
            customer_id=tenant_id,
            action_summary=decision["action_summary"],
            stated_intent="fleet reconciliation",
            user_message=notes or None,
        )
    except Exception as exc:
        logger.warning("[reconciliation] could not persist audit event: %s", exc)


class ReconciliationInventoryRow(BaseModel):
    name: str
    vendor: str = ""
    vendor_name: str = ""
    vendor_id: str = ""
    department: str = ""
    scope: str = ""
    action: str = ""
    runtime_type: str = "Service"
    agent_id: Optional[str] = None
    connectors: list[str] = Field(default_factory=list)


class ReconciliationImportRequest(BaseModel):
    source_system: str
    vendor_name: str = ""
    vendor_id: str = ""
    source_type: str = ""
    department: str = ""
    cohort_mode: str = "purpose"
    posture: str = "audit-only"
    inventory: list[ReconciliationInventoryRow] = Field(default_factory=list)


class ReconciliationRowActionRequest(BaseModel):
    actor: str
    action: str
    notes: Optional[str] = None


def _build_batch_summary(rows: list[dict], missing: list[dict]) -> dict:
    counts = {"new": 0, "changed": 0, "missing": len(missing), "duplicate": 0, "ready": 0}
    risk_mix = {"low": 0, "medium": 0, "high": 0}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
        risk_mix[row["risk"]] = risk_mix.get(row["risk"], 0) + 1
    selected = next((r for r in rows if r["status"] in ("ready", "new") and r["risk"] in ("low", "medium")), rows[0] if rows else None)
    return {
        **counts,
        "risk_mix": risk_mix,
        "selected_row_key": selected["row_key"] if selected else None,
        "selected_batch": selected["name"] if selected else None,
        "message": (
            "Ready rows can be promoted, changed rows need review, duplicate rows should be merged, and missing rows should be held."
        ),
    }


@router.post("/import")
async def import_inventory(request: Request, body: ReconciliationImportRequest):
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    _require_operations_admin(request)
    _assert_department_scope(request, body.department)

    db = get_db()
    try:
        existing_agents = db.list_agents(tenant_id)
    except Exception:
        existing_agents = []
    existing_by_id = {a.get("agent_id"): a for a in existing_agents if a.get("agent_id")}
    existing_by_sig = {
        "|".join([
            _norm(a.get("name")),
            _norm(a.get("vendor_id")),
            _norm(a.get("department")),
        ]): a
        for a in existing_agents
    }

    rows: list[dict] = []
    seen: set[str] = set()
    incoming_keys: set[str] = set()
    matched_existing_ids: set[str] = set()
    for item in body.inventory:
        payload = item.model_dump()
        key = _row_key(payload)
        incoming_keys.add(key)
        existing = None
        if payload.get("agent_id"):
            existing = existing_by_id.get(payload["agent_id"])
        if existing is None:
            sig = "|".join([
                _norm(payload.get("name")),
                _norm(payload.get("vendor_id") or payload.get("vendor")),
                _norm(payload.get("department")),
            ])
            existing = existing_by_sig.get(sig)
        if existing is not None and existing.get("agent_id"):
            matched_existing_ids.add(existing["agent_id"])
        rows.append(_classify_row(payload, existing, seen))

    missing = [
        {
            "agent_id": agent.get("agent_id"),
            "name": agent.get("name"),
            "vendor_id": agent.get("vendor_id"),
            "department": agent.get("department"),
            "status": "missing",
            "action": "Hold until re-found",
        }
        for agent in existing_agents
        if agent.get("agent_id") not in matched_existing_ids
    ]

    summary = _build_batch_summary(rows, missing)
    batch_id = f"rb-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{hashlib.sha256((tenant_id + body.source_system + _now()).encode()).hexdigest()[:8]}"
    batch = {
        "batch_id": batch_id,
        "source_system": body.source_system,
        "vendor_name": body.vendor_name,
        "vendor_id": body.vendor_id,
        "source_type": body.source_type,
        "department": body.department,
        "cohort_mode": body.cohort_mode,
        "posture": body.posture,
        "rows": rows,
        "missing": missing,
        "summary": summary,
        "selected_row_key": summary.get("selected_row_key"),
        "selected_batch": summary.get("selected_batch"),
        "created_at": _now(),
        "updated_at": _now(),
    }
    db.create_reconciliation_batch(
        batch_id=batch_id,
        tenant_id=tenant_id,
        source_system=body.source_system,
        vendor_name=body.vendor_name,
        vendor_id=body.vendor_id,
        source_type=body.source_type,
        cohort_mode=body.cohort_mode,
        posture=body.posture,
        data=batch,
        status="open",
    )
    _audit_reconciliation_event(tenant_id, action_op="import_batch", verdict="ALLOW", actor="system", batch=batch)
    return {
        "batch": batch,
        "next_step": {
            "action": f"POST /v1/operations/reconciliation/{batch_id}/promote",
            "description": "Promote low-risk rows after review",
        },
    }


@router.get("")
async def list_batches(request: Request):
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    _require_operations_admin(request)
    db = get_db()
    batches = db.list_reconciliation_batches(tenant_id)
    scope = get_department_scope(request)
    if scope:
        batches = [batch for batch in batches if batch.get("department") == scope]
    return {"batches": batches, "count": len(batches)}


@router.get("/{batch_id}")
async def get_batch(batch_id: str, request: Request):
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    db = get_db()
    batch = db.get_reconciliation_batch(batch_id, tenant_id=tenant_id)
    if batch is None:
        raise HTTPException(404, "Reconciliation batch not found")
    _require_operations_admin(request)
    _assert_department_scope(request, batch.get("department"))
    return {"batch": batch}


@router.post("/{batch_id}/hold")
async def hold_batch(batch_id: str, request: Request, body: ReconciliationRowActionRequest):
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    _require_operations_admin(request)
    db = get_db()
    batch = db.get_reconciliation_batch(batch_id, tenant_id=tenant_id)
    if batch is None:
        raise HTTPException(404, "Reconciliation batch not found")
    _assert_department_scope(request, batch.get("department"))
    batch["status"] = "held"
    batch["data"].setdefault("summary", {})
    batch["data"]["summary"]["message"] = "Batch held pending review."
    batch["updated_at"] = _now()
    stored = db.update_reconciliation_batch(batch_id, tenant_id, status="held", patch=batch["data"])
    _audit_reconciliation_event(tenant_id, action_op="hold_batch", verdict="BLOCK", actor=body.actor, batch=stored or batch, notes=body.notes or "Batch held")
    return {"batch": stored or batch, "message": "Batch held."}


@router.post("/{batch_id}/merge")
async def merge_duplicates(batch_id: str, request: Request, body: ReconciliationRowActionRequest):
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    _require_operations_admin(request)
    db = get_db()
    batch = db.get_reconciliation_batch(batch_id, tenant_id=tenant_id)
    if batch is None:
        raise HTTPException(404, "Reconciliation batch not found")
    _assert_department_scope(request, batch.get("department"))
    rows = batch.get("data", {}).get("rows", [])
    merged = 0
    for row in rows:
        if row.get("status") == "duplicate":
            row["status"] = "merged"
            row["action"] = "Merge duplicate IDs"
            merged += 1
    batch["data"]["rows"] = rows
    batch["status"] = "merged"
    batch["data"]["summary"]["merged"] = merged
    batch["updated_at"] = _now()
    stored = db.update_reconciliation_batch(batch_id, tenant_id, status="merged", patch=batch["data"])
    _audit_reconciliation_event(tenant_id, action_op="merge_duplicates", verdict="ALLOW", actor=body.actor, batch=stored or batch, notes=body.notes or "Merged duplicate inventory rows")
    return {"batch": stored or batch, "merged": merged}


@router.post("/{batch_id}/promote")
async def promote_batch(batch_id: str, request: Request, body: ReconciliationRowActionRequest):
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    _require_operations_admin(request)
    db = get_db()
    batch = db.get_reconciliation_batch(batch_id, tenant_id=tenant_id)
    if batch is None:
        raise HTTPException(404, "Reconciliation batch not found")
    _assert_department_scope(request, batch.get("department"))

    rows = batch.get("data", {}).get("rows", [])
    promoted = 0
    for row in rows:
        if row.get("risk") in {"low", "medium"} and row.get("status") in {"ready", "new"}:
            agent_id = row.get("agent_id") or row.get("row_key")
            db.register_agent_full(
                agent_id=agent_id,
                tenant_id=tenant_id,
                name=row.get("name") or agent_id,
                agent_type=(row.get("runtime_type") or "service").lower(),
                description=row.get("action") or row.get("scope") or "",
                capabilities=[row.get("scope")] if row.get("scope") else [],
                policy_pack="hospital",
                mag_enabled=False,
                metadata={
                    "source_system": batch.get("source_system"),
                    "vendor_name": batch.get("vendor_name"),
                    "vendor_id": batch.get("vendor_id"),
                    "department": row.get("department") or batch.get("department"),
                    "cohort_mode": batch.get("cohort_mode"),
                    "reconciliation_batch_id": batch_id,
                    "reconciliation_status": row.get("status"),
                    "risk": row.get("risk"),
                    "connectors": row.get("connectors") or [],
                },
                vendor_id=row.get("vendor_id") or batch.get("vendor_id") or None,
                department=row.get("department") or batch.get("department") or None,
            )
            try:
                db.register_agent(tenant_id, agent_id)
            except Exception:
                pass
            row["status"] = "promoted"
            row["action"] = "Promote low-risk batch"
            promoted += 1
    batch["data"]["rows"] = rows
    batch["status"] = "promoted"
    batch["data"]["summary"]["promoted"] = promoted
    batch["updated_at"] = _now()
    stored = db.update_reconciliation_batch(batch_id, tenant_id, status="promoted", patch=batch["data"])
    _audit_reconciliation_event(tenant_id, action_op="promote_batch", verdict="ALLOW", actor=body.actor, batch=stored or batch, notes=body.notes or "Promoted low-risk rows")
    return {"batch": stored or batch, "promoted": promoted}


@router.post("/{batch_id}/rows/{row_key}/action")
async def act_on_row(batch_id: str, row_key: str, request: Request, body: ReconciliationRowActionRequest):
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    _require_operations_admin(request)
    db = get_db()
    batch = db.get_reconciliation_batch(batch_id, tenant_id=tenant_id)
    if batch is None:
        raise HTTPException(404, "Reconciliation batch not found")
    _assert_department_scope(request, batch.get("department"))
    rows = batch.get("data", {}).get("rows", [])
    target = next((row for row in rows if row.get("row_key") == row_key), None)
    if target is None:
        raise HTTPException(404, "Row not found")
    _assert_department_scope(request, target.get("department") or batch.get("department"))

    action = body.action.lower().strip()
    if action == "register_audit_only":
        target["status"] = "audit-only"
        target["action"] = "Register audit-only"
        verdict = "ALLOW"
    elif action == "review_scope_drift":
        target["status"] = "changed"
        target["action"] = "Review scope drift"
        verdict = "ESCALATE"
    elif action in {"hold_until_re_found", "hold"}:
        target["status"] = "held"
        target["action"] = "Hold until re-found"
        verdict = "BLOCK"
    elif action in {"merge_duplicate_ids", "merge"}:
        target["status"] = "merged"
        target["action"] = "Merge duplicate IDs"
        verdict = "ALLOW"
    elif action in {"promote_low_risk_batch", "promote"}:
        target["status"] = "promoted"
        target["action"] = "Promote low-risk batch"
        verdict = "ALLOW"
        db.register_agent_full(
            agent_id=target.get("agent_id") or target["row_key"],
            tenant_id=tenant_id,
            name=target.get("name") or target["row_key"],
            agent_type=(target.get("runtime_type") or "service").lower(),
            description=target.get("scope") or "",
            capabilities=[target.get("scope")] if target.get("scope") else [],
            policy_pack="hospital",
            metadata={
                "source_system": batch.get("source_system"),
                "vendor_name": batch.get("vendor_name"),
                "vendor_id": batch.get("vendor_id"),
                "department": target.get("department") or batch.get("department"),
                "reconciliation_batch_id": batch_id,
                "reconciliation_status": target.get("status"),
                "risk": target.get("risk"),
            },
            vendor_id=target.get("vendor_id") or batch.get("vendor_id") or None,
            department=target.get("department") or batch.get("department") or None,
        )
        try:
            db.register_agent(tenant_id, target.get("agent_id") or target["row_key"])
        except Exception:
            pass
    else:
        raise HTTPException(400, f"Unsupported row action '{body.action}'")

    target.setdefault("audit", [])
    target["audit"].append({
        "action": action,
        "actor": body.actor,
        "notes": body.notes or "",
        "time": _now(),
    })
    batch["data"]["rows"] = rows
    batch["updated_at"] = _now()
    stored = db.update_reconciliation_batch(batch_id, tenant_id, patch=batch["data"])
    _audit_reconciliation_event(tenant_id, action_op=f"row_{action}", verdict=verdict, actor=body.actor, batch=stored or batch, notes=body.notes or action)
    return {"batch": stored or batch, "row": target}
