"""Legacy /decisions/* query endpoints.

These predate the /audit/* router. Kept at their original paths for
backward-compat with any SDK clients using them directly.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["decisions"])


class DecisionQueryResponse(BaseModel):
    decisions: List[Dict[str, Any]]
    total: int
    limit: int


@router.get("/decisions/query", response_model=DecisionQueryResponse)
async def query_decisions(
    request: Request,
    action_id: Optional[str] = None,
    verdict: Optional[str] = None,
    intent_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    limit: int = 100,
):
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 1000")
    db = request.app.state.db
    decisions = db.query_decisions(
        action_id=action_id,
        verdict=verdict,
        intent_id=intent_id,
        agent_id=agent_id,
        limit=limit,
    )
    return DecisionQueryResponse(decisions=decisions, total=len(decisions), limit=limit)


@router.get("/decisions/{decision_id}")
async def get_decision(decision_id: str, request: Request):
    db = request.app.state.db
    decision = db.get_decision(decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")
    return decision
