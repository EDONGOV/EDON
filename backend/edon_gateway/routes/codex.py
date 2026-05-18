"""EDON Codex — self-governing code agent REST endpoints.

POST /v1/codex/task         — submit a natural language coding instruction
GET  /v1/codex/task/{id}    — poll task status
GET  /v1/codex/tasks        — list recent tasks

The agent plans changes, governs each file write through EDON, applies them,
and opens a GitHub PR. Tasks run in the background — poll for completion.

Auth: X-Bootstrap-Secret.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from ..logging_config import get_logger
from ..security.bootstrap_auth import check_bootstrap_auth as _check_auth
from ..autonomous.code_task import run_code_task, get_task, list_tasks

logger = get_logger(__name__)
router = APIRouter(prefix="/v1/codex", tags=["codex"])


class CodexTaskRequest(BaseModel):
    instruction: str
    agent_id: Optional[str] = "edon-codex"


@router.post("/task")
async def codex_submit(req: CodexTaskRequest, background_tasks: BackgroundTasks, request: Request):
    """Submit a natural language coding instruction.

    The agent is governed: every file write is checked by EDON before execution.
    Returns a task_id immediately — poll GET /v1/codex/task/{id} for status.
    """
    _check_auth(request)

    if not req.instruction.strip():
        raise HTTPException(status_code=400, detail="instruction is empty")

    task_id = uuid.uuid4().hex[:12]
    background_tasks.add_task(run_code_task, task_id, req.instruction, req.agent_id or "edon-codex")
    logger.info("[codex] submitted task=%s instruction=%r", task_id, req.instruction[:80])
    return {"task_id": task_id, "status": "running"}


@router.get("/task/{task_id}")
async def codex_status(task_id: str, request: Request):
    """Get task status and result."""
    _check_auth(request)
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@router.get("/tasks")
async def codex_list(request: Request, limit: int = 20):
    """List recent codex tasks."""
    _check_auth(request)
    return {"tasks": list_tasks(limit=limit)}
