"""EDON Autonomous Loop control endpoints.

GET  /v1/autonomous/status     — current loop state + last cycle summary
POST /v1/autonomous/run        — trigger one cycle immediately
POST /v1/autonomous/start      — start background loop
POST /v1/autonomous/stop       — stop background loop

Auth: X-Bootstrap-Secret (same as Jarvis / admin).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from ..logging_config import get_logger
from ..security.bootstrap_auth import check_bootstrap_auth as _check_auth
from ..autonomous.loop import (
    get_loop_status,
    run_cycle_now,
    start_autonomous_loop,
    stop_autonomous_loop,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/v1/autonomous", tags=["autonomous"])


@router.get("/status")
async def autonomous_status(request: Request):
    """Return current autonomous loop state and last cycle summary."""
    _check_auth(request)
    return get_loop_status()


class RunRequest(BaseModel):
    tenant_id: Optional[str] = None


@router.post("/run")
async def autonomous_run(req: RunRequest, request: Request):
    """Trigger one full observe→harden→heal→verify cycle immediately."""
    _check_auth(request)
    try:
        from ..persistence import get_db
        from ..governor import EDONGovernor
        db = get_db()
        governor = EDONGovernor(db=db)
        result = await run_cycle_now(tenant_id=req.tenant_id, governor=governor)
        return result
    except Exception as exc:
        logger.error("[autonomous] manual run error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/start")
async def autonomous_start(request: Request):
    """Start the background autonomous loop (if not already running)."""
    _check_auth(request)
    try:
        from ..persistence import get_db
        from ..governor import EDONGovernor
        db = get_db()
        governor = EDONGovernor(db=db)
        start_autonomous_loop(governor=governor)
        return {"started": True, "status": get_loop_status()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/stop")
async def autonomous_stop(request: Request):
    """Stop the background autonomous loop."""
    _check_auth(request)
    stop_autonomous_loop()
    return {"stopped": True, "status": get_loop_status()}
