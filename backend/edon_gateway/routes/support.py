"""Tenant-safe support case intake and retrieval."""
from __future__ import annotations

import uuid
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional

import requests
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field

from ..config import config
from ..logging_config import get_logger
from ..persistence import get_db
from ..tenancy import get_request_tenant_id

logger = get_logger(__name__)

router = APIRouter(prefix="/support", tags=["support"])

_VALID_SEVERITIES = {"sev1", "sev2", "sev3", "sev4"}


class SupportDiagnosticsBundle(BaseModel):
    support_code: Optional[str] = None
    tenant_id: Optional[str] = None
    role: Optional[str] = None
    plan: Optional[str] = None
    vertical: Optional[str] = None
    gateway_version: Optional[str] = None
    request_id: Optional[str] = None
    decision_id: Optional[str] = None
    action_id: Optional[str] = None
    trace_id: Optional[str] = None
    conversation_id: Optional[str] = None
    problem_description: Optional[str] = None
    affected_system: Optional[str] = None
    workflow_id: Optional[str] = None
    connector: Optional[str] = None


class SupportTicketCreate(BaseModel):
    summary: str = Field(min_length=3, max_length=500)
    severity: str = Field(default="sev3")
    tab: str = Field(default="settings", max_length=80)
    reviewer_name: Optional[str] = Field(default=None, max_length=120)
    department: Optional[str] = Field(default=None, max_length=120)
    issue_type: str = Field(default="incident", max_length=80)
    chat_history: List[Dict[str, Any]] = Field(default_factory=list)
    notes: Optional[str] = Field(default=None, max_length=2000)
    diagnostics: SupportDiagnosticsBundle


def _normalize_severity(value: str) -> str:
    severity = (value or "sev3").strip().lower()
    if severity not in _VALID_SEVERITIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported severity '{value}'. Use one of: {sorted(_VALID_SEVERITIES)}",
        )
    return severity


def _build_support_case(body: SupportTicketCreate, tenant_id: str) -> Dict[str, Any]:
    diag = body.diagnostics.model_dump()
    now = datetime.now(UTC).isoformat()
    support_code = (diag.get("support_code") or f"SUP-{uuid.uuid4().hex[:8].upper()}").strip()
    case_id = f"case_{uuid.uuid4().hex[:12]}"
    connector = diag.get("connector") or None
    affected_system = diag.get("affected_system") or connector or body.tab or None
    timeline = [
        {
            "at": now,
            "event": "created",
            "actor": body.reviewer_name or "tenant-console",
            "message": "Support case submitted from console diagnostics",
            "severity": body.severity,
        }
    ]
    issue_payload = {
        "summary": body.summary,
        "severity": body.severity,
        "tab": body.tab,
        "reviewer_name": body.reviewer_name,
        "department": body.department,
        "issue_type": body.issue_type,
        "chat_history": body.chat_history,
        "notes": body.notes,
    }
    return {
        "case_id": case_id,
        "tenant_id": tenant_id,
        "support_code": support_code,
        "severity": _normalize_severity(body.severity),
        "status": "open",
        "assigned_owner": None,
        "summary": body.summary.strip(),
        "issue_type": body.issue_type.strip().lower(),
        "affected_system": affected_system,
        "workflow_id": diag.get("workflow_id"),
        "connector": connector,
        "decision_id": diag.get("decision_id"),
        "action_id": diag.get("action_id"),
        "trace_id": diag.get("trace_id"),
        "conversation_id": diag.get("conversation_id"),
        "request_id": diag.get("request_id"),
        "created_by": body.reviewer_name or body.department or "tenant-console",
        "created_at": now,
        "updated_at": now,
        "timeline": timeline,
        "evidence_bundle": diag,
        "issue_payload": issue_payload,
    }


def _forward_support_case(url: str, case: Dict[str, Any]) -> None:
    try:
        requests.post(
            url,
            json={
                "case_id": case["case_id"],
                "tenant_id": case["tenant_id"],
                "support_code": case.get("support_code"),
                "severity": case.get("severity"),
                "summary": case.get("summary"),
                "status": case.get("status"),
                "assigned_owner": case.get("assigned_owner"),
                "affected_system": case.get("affected_system"),
                "workflow_id": case.get("workflow_id"),
                "connector": case.get("connector"),
                "decision_id": case.get("decision_id"),
                "action_id": case.get("action_id"),
                "trace_id": case.get("trace_id"),
                "conversation_id": case.get("conversation_id"),
                "request_id": case.get("request_id"),
                "timeline": case.get("timeline", []),
                "evidence_bundle": case.get("evidence_bundle", {}),
                "issue_payload": case.get("issue_payload", {}),
            },
            timeout=8,
        )
    except Exception as exc:
        logger.warning("support.case.forward_failed: case=%s error=%s", case.get("case_id"), exc)


@router.post("/ticket")
async def create_support_ticket(request: Request, body: SupportTicketCreate, background_tasks: BackgroundTasks):
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    case = _build_support_case(body, tenant_id)
    db = get_db()
    if not hasattr(db, "save_support_case"):
        raise HTTPException(status_code=501, detail="Support cases not supported by this backend")

    try:
        db.save_support_case(case)
    except Exception as exc:
        logger.warning("support.case.save_failed: tenant=%s error=%s", tenant_id, exc)
        raise HTTPException(status_code=500, detail="Failed to create support case")

    webhook_url = (config.SUPPORT_WEBHOOK_URL or "").strip()
    if webhook_url:
        background_tasks.add_task(_forward_support_case, webhook_url, case)

    logger.info("support.case_created: tenant=%s case=%s severity=%s", tenant_id, case["case_id"], case["severity"])
    return {
        "case_id": case["case_id"],
        "support_code": case.get("support_code"),
        "status": case.get("status"),
        "severity": case.get("severity"),
        "tenant_id": tenant_id,
        "support_url": f"/support/cases/{case['case_id']}",
        "message": "Support case created. Share the case ID with EDON support.",
    }


@router.get("/cases")
async def list_support_cases(request: Request, limit: int = 50):
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    db = get_db()
    if not hasattr(db, "list_support_cases"):
        raise HTTPException(status_code=501, detail="Support cases not supported by this backend")
    cases = db.list_support_cases(tenant_id, limit=limit)
    return {"tenant_id": tenant_id, "cases": cases, "count": len(cases)}


@router.get("/cases/{case_id}")
async def get_support_case(request: Request, case_id: str):
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    db = get_db()
    if not hasattr(db, "get_support_case"):
        raise HTTPException(status_code=501, detail="Support cases not supported by this backend")
    case = db.get_support_case(case_id, tenant_id=tenant_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Support case not found: {case_id}")
    return case
