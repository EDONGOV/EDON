"""EDON Bootstrap Routes — cold-start intake for new prospects.

POST /v1/bootstrap              — submit artifacts, start bootstrap job
GET  /v1/bootstrap/{job_id}    — poll job status + progress
GET  /v1/bootstrap/{job_id}/report — get full first-findings report
GET  /v1/bootstrap/jobs        — list recent jobs for this tenant

Accepts JSON body with any combination of:
  openapi_spec:  dict      — OpenAPI 3.x or Swagger 2.x spec object
  openapi_yaml:  str       — Raw YAML/JSON string (alternative to openapi_spec)
  agent_config:  dict|list — Agent config (EDON / OpenAI / Anthropic format)
  log_lines:     list[str] — JSONL log lines (up to 10,000)
  tenant_id:     str       — Optional tenant override (falls back to X-Tenant-ID header)

The bootstrap runs asynchronously. Poll /v1/bootstrap/{job_id} until
status == "complete", then fetch the full report.

For synchronous usage (demos, small payloads) set wait=true:
  POST /v1/bootstrap?wait=true
  Returns the full report directly (blocks until complete, max 60s).
"""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Query, BackgroundTasks
from pydantic import BaseModel, Field

from ..tenancy import get_request_tenant_id
from ..logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v1/bootstrap", tags=["bootstrap"])


# ── Request model ──────────────────────────────────────────────────────────────

class BootstrapRequest(BaseModel):
    openapi_spec:  Optional[dict]            = Field(None, description="OpenAPI spec object")
    openapi_yaml:  Optional[str]             = Field(None, description="OpenAPI YAML/JSON string")
    agent_config:  Optional[dict | list]     = Field(None, description="Agent config")
    log_lines:     Optional[list[str]]       = Field(None, description="JSONL log lines (max 10k)")
    tenant_id:     Optional[str]             = Field(None, description="Tenant override")

    class Config:
        # Allow both dict and list for agent_config
        arbitrary_types_allowed = True


# ── Background runner ──────────────────────────────────────────────────────────

async def _run_job(
    job_id: str,
    tenant_id: Optional[str],
    body: BootstrapRequest,
    impact_store,
) -> None:
    """Fire-and-forget bootstrap job."""
    from ..bootstrap.engine import run_bootstrap
    from ..bootstrap.job_store import update_job
    try:
        await run_bootstrap(
            tenant_id=tenant_id,
            openapi_spec=body.openapi_spec,
            openapi_yaml=body.openapi_yaml,
            agent_config=body.agent_config,
            log_lines=(body.log_lines or [])[:10_000],
            job_id=job_id,
            impact_store=impact_store,
        )
    except Exception as exc:
        logger.error("[bootstrap/route] job %s failed: %s", job_id[:8], exc)
        update_job(job_id, status="failed", error=str(exc))


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("")
async def start_bootstrap(
    body: BootstrapRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    wait: bool = Query(False, description="Block until complete (max 60s, for demos)"),
):
    """Submit system artifacts and start a bootstrap analysis job.

    Returns immediately with a job_id unless wait=true.
    """
    from ..bootstrap.job_store import create_job

    # Validate: at least one artifact required
    if not any([body.openapi_spec, body.openapi_yaml, body.agent_config, body.log_lines]):
        raise HTTPException(
            status_code=400,
            detail=(
                "At least one artifact is required: "
                "openapi_spec, openapi_yaml, agent_config, or log_lines"
            ),
        )

    tenant_id = body.tenant_id or get_request_tenant_id(request)
    impact_store = getattr(request.app.state, "impact_store", None)

    # Determine which artifact types were provided
    artifact_types = []
    if body.openapi_spec or body.openapi_yaml:
        artifact_types.append("openapi")
    if body.agent_config:
        artifact_types.append("agent_config")
    if body.log_lines:
        artifact_types.append("logs")

    job_id = create_job(tenant_id, artifact_types)
    logger.info(
        "[bootstrap/route] job created: id=%s tenant=%s artifacts=%s",
        job_id[:8], tenant_id, artifact_types,
    )

    if wait:
        # Synchronous path — run inline, return full report (demo mode)
        try:
            from ..bootstrap.engine import run_bootstrap
            report = await asyncio.wait_for(
                run_bootstrap(
                    tenant_id=tenant_id,
                    openapi_spec=body.openapi_spec,
                    openapi_yaml=body.openapi_yaml,
                    agent_config=body.agent_config,
                    log_lines=(body.log_lines or [])[:10_000],
                    job_id=job_id,
                    impact_store=impact_store,
                ),
                timeout=60.0,
            )
            from dataclasses import asdict
            return {"job_id": job_id, "status": "complete", "report": asdict(report)}
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="Bootstrap timed out after 60s. Use async mode (wait=false) for large artifacts.",
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    # Async path — queue and return immediately
    background_tasks.add_task(_run_job, job_id, tenant_id, body, impact_store)
    return {
        "job_id": job_id,
        "status": "pending",
        "artifact_types": artifact_types,
        "poll_url": f"/v1/bootstrap/{job_id}",
        "report_url": f"/v1/bootstrap/{job_id}/report",
        "message": "Bootstrap job queued. Poll poll_url for progress.",
    }


@router.get("/jobs")
async def list_jobs(
    request: Request,
    limit: int = Query(20, le=100),
):
    """List recent bootstrap jobs for this tenant."""
    from ..bootstrap.job_store import list_jobs
    tenant_id = get_request_tenant_id(request)
    jobs = list_jobs(tenant_id=tenant_id, limit=limit)
    # Strip full reports from list — use /report endpoint for that
    return {
        "jobs": [
            {k: v for k, v in j.items() if k != "report"}
            for j in jobs
        ],
        "count": len(jobs),
    }


@router.get("/{job_id}")
async def get_job_status(job_id: str):
    """Poll bootstrap job status and progress."""
    from ..bootstrap.job_store import get_job
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    # Return status without the full report (use /report for that)
    return {k: v for k, v in job.items() if k != "report"}


@router.get("/{job_id}/report")
async def get_report(job_id: str):
    """Fetch the full first-findings report for a completed bootstrap job.

    Returns 202 Accepted if the job is still running.
    """
    from ..bootstrap.job_store import get_job
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    if job["status"] == "failed":
        raise HTTPException(
            status_code=500,
            detail=f"Bootstrap job failed: {job.get('error', 'unknown error')}",
        )

    if job["status"] != "complete":
        # Return 202 with progress so the client can display a progress bar
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=202,
            content={
                "status": job["status"],
                "progress": job.get("progress", 0),
                "progress_message": job.get("progress_message", ""),
                "message": "Bootstrap in progress. Poll /v1/bootstrap/{job_id}/report again shortly.",
            },
        )

    return job["report"]
