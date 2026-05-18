"""Policy proposal review queue — GET/POST /v1/policy/proposals.

ADAPT submits proposals here. Humans (or an external reviewer) apply or
reject them. The production EDON instance cannot self-approve.
"""
from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..policy.proposals import get_proposal_store
from ..persistence import get_db
from ..tenancy import get_request_tenant_id
from ..logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/policy/proposals", tags=["policy"])


class ApplyRequest(BaseModel):
    reviewed_by: str = "human"


class RejectRequest(BaseModel):
    reviewed_by: str = "human"
    reason: str


class BatchApplyRequest(BaseModel):
    proposal_ids: list[str]
    reviewed_by:  str = "human"


class BatchRejectRequest(BaseModel):
    proposal_ids: list[str]
    reviewed_by:  str = "human"
    reason:       str


@router.get("")
async def list_proposals(request: Request, status: Optional[str] = None):
    """List policy proposals for this tenant."""
    tenant_id = get_request_tenant_id(request)
    store = get_proposal_store()
    if status == "pending" or status is None:
        proposals = store.list_pending(tenant_id=tenant_id)
    else:
        proposals = [p for p in store.list_all(tenant_id or "", limit=200)
                     if p["status"] == status]
    return {"proposals": proposals, "total": len(proposals)}


@router.post("/{proposal_id}/apply")
async def apply_proposal(proposal_id: str, request: Request, body: ApplyRequest):
    """Apply a pending proposal — converts it to a live policy rule."""
    tenant_id = get_request_tenant_id(request)
    store = get_proposal_store()
    proposal = store.get(proposal_id)

    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if tenant_id and proposal["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Proposal belongs to another tenant")
    if proposal["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"Proposal is already {proposal['status']}")

    db = get_db()
    applied = store.apply(proposal_id, reviewed_by=body.reviewed_by, db=db)
    if not applied:
        raise HTTPException(status_code=500, detail="Failed to apply proposal")

    logger.info(
        "[proposals] APPLIED: %s by=%s tenant=%s rule=%s",
        proposal_id, body.reviewed_by, tenant_id, proposal["name"],
    )
    return {"proposal_id": proposal_id, "status": "applied", "reviewed_by": body.reviewed_by}


@router.post("/{proposal_id}/reject")
async def reject_proposal(proposal_id: str, request: Request, body: RejectRequest):
    """Reject a pending proposal."""
    tenant_id = get_request_tenant_id(request)
    store = get_proposal_store()
    proposal = store.get(proposal_id)

    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if tenant_id and proposal["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Proposal belongs to another tenant")

    store.reject(proposal_id, reviewed_by=body.reviewed_by, reason=body.reason)
    logger.info(
        "[proposals] REJECTED: %s by=%s reason=%s", proposal_id, body.reviewed_by, body.reason
    )
    return {"proposal_id": proposal_id, "status": "rejected"}


@router.post("/batch/apply")
async def batch_apply_proposals(request: Request, body: BatchApplyRequest):
    """Apply multiple pending proposals in one call."""
    if not body.proposal_ids:
        raise HTTPException(status_code=400, detail="proposal_ids is required")
    tenant_id = get_request_tenant_id(request)
    store     = get_proposal_store()
    db        = get_db()
    results   = store.batch_apply(body.proposal_ids, reviewed_by=body.reviewed_by, db=db)
    applied   = [pid for pid, ok in results.items() if ok]
    failed    = [pid for pid, ok in results.items() if not ok]
    logger.info(
        "[proposals] BATCH_APPLIED: applied=%d failed=%d by=%s tenant=%s",
        len(applied), len(failed), body.reviewed_by, tenant_id,
    )
    return {"applied": applied, "failed": failed, "reviewed_by": body.reviewed_by}


@router.post("/batch/reject")
async def batch_reject_proposals(request: Request, body: BatchRejectRequest):
    """Reject multiple pending proposals in one call."""
    if not body.proposal_ids:
        raise HTTPException(status_code=400, detail="proposal_ids is required")
    store   = get_proposal_store()
    results = store.batch_reject(body.proposal_ids, reviewed_by=body.reviewed_by, reason=body.reason)
    rejected = [pid for pid, ok in results.items() if ok]
    failed   = [pid for pid, ok in results.items() if not ok]
    return {"rejected": rejected, "failed": failed}


@router.get("/sla-breached")
async def sla_breached_proposals(request: Request):
    """Return proposals that have exceeded their SLA review deadline."""
    tenant_id = get_request_tenant_id(request)
    store     = get_proposal_store()
    proposals = store.sla_breached(tenant_id=tenant_id)
    return {"proposals": proposals, "total": len(proposals)}


@router.get("/{proposal_id}")
async def get_proposal(proposal_id: str, request: Request):
    tenant_id = get_request_tenant_id(request)
    store = get_proposal_store()
    proposal = store.get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if tenant_id and proposal["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Proposal belongs to another tenant")
    return proposal
