"""CREAO Engine Routes.

GET  /v1/creao/status              — current mode, proposal summary
GET  /v1/creao/proposals           — list pending proposals
GET  /v1/creao/lineage/{id}        — full audit trail for a proposal
POST /v1/creao/approve/{id}        — approve a proposal
POST /v1/creao/reject/{id}         — reject a proposal
POST /v1/creao/mode                — change operating mode at runtime
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel
from typing import Optional

from ..tenancy import get_request_tenant_id
from ..logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v1/creao", tags=["creao"])


class ResolveBody(BaseModel):
    resolved_by: str
    note: Optional[str] = None


class ModeBody(BaseModel):
    mode: str  # suggest_only | assisted | autonomous


@router.get("/status")
async def get_creao_status(request: Request):
    """Return current CREAO mode and proposal summary."""
    from ..creao.engine import get_creao_engine
    tenant_id = get_request_tenant_id(request)
    engine = get_creao_engine()
    return engine.summary(tenant_id)


@router.get("/proposals")
async def list_proposals(
    request: Request,
    status: Optional[str] = Query("pending_review"),
    severity: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
):
    """List fix proposals, filtered by status and severity."""
    from ..creao.engine import get_creao_engine
    from ..shadow.fix_pipeline import get_proposals
    tenant_id = get_request_tenant_id(request)
    proposals = get_proposals(
        tenant_id=tenant_id,
        status=status,
        severity=severity,
        limit=limit,
    )
    return {"proposals": proposals, "count": len(proposals), "mode": get_creao_engine().get_mode()}


@router.get("/lineage/{proposal_id}")
async def get_lineage(proposal_id: str, request: Request):
    """Return full audit trail for a proposal (shadow → CREAO → deploy → verify)."""
    from ..creao.engine import get_creao_engine
    trail = get_creao_engine().lineage(proposal_id)
    if trail is None:
        raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found")
    return trail


@router.post("/approve/{proposal_id}")
async def approve_proposal(proposal_id: str, body: ResolveBody, request: Request):
    """Approve a pending fix proposal."""
    from ..creao.engine import get_creao_engine
    result = get_creao_engine().approve(proposal_id, body.resolved_by, body.note)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found")
    return result


@router.post("/reject/{proposal_id}")
async def reject_proposal(proposal_id: str, body: ResolveBody, request: Request):
    """Reject a pending fix proposal."""
    from ..creao.engine import get_creao_engine
    result = get_creao_engine().reject(proposal_id, body.resolved_by, body.note)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found")
    return result


@router.post("/mode")
async def set_mode(body: ModeBody):
    """Change CREAO operating mode at runtime.

    suggest_only — proposals only, no deployment
    assisted     — deploy with human approval
    autonomous   — deploy automatically within policy bounds
    """
    from ..creao.engine import get_creao_engine, CREAOMode
    try:
        new_mode = CREAOMode(body.mode)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{body.mode}'. Must be: suggest_only | assisted | autonomous",
        )
    engine = get_creao_engine()
    old_mode = engine.get_mode()
    engine.set_mode(new_mode)
    logger.warning("[creao/route] mode changed via API: %s → %s", old_mode, new_mode.value)
    return {"previous_mode": old_mode, "mode": new_mode.value}
