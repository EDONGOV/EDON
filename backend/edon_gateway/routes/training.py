"""EDON Training Data Pipeline Routes.

POST /v1/training/export          — extract + format + write JSONL to disk
POST /v1/training/upload          — upload JSONL files to Anthropic Files API
POST /v1/training/start           — create Anthropic fine-tuning job
GET  /v1/training/status/{job_id} — get fine-tuning job status
GET  /v1/training/jobs            — list all fine-tuning jobs
POST /v1/training/run             — full pipeline: export + upload + start
GET  /v1/training/datasets        — show available dataset sizes (dry run)
DELETE /v1/training/jobs/{job_id} — cancel a fine-tuning job

All routes require a valid API token. Training is tenant-agnostic (trains on
the full cross-tenant dataset to improve the shared governance model).
Only EDON admin accounts should have access to these routes.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field

from ..logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v1/training", tags=["training"])


# ── Request / response models ──────────────────────────────────────────────────

class ExportRequest(BaseModel):
    validation_split: float = Field(0.1, ge=0.0, le=0.5, description="Fraction of data for validation")
    limits: Optional[dict] = Field(None, description="Per-dataset row limits, e.g. {'governance_decisions': 1000}")


class UploadRequest(BaseModel):
    train_path: str  = Field(..., description="Absolute path to train.jsonl (from export step)")
    val_path: str    = Field(..., description="Absolute path to validation.jsonl (from export step)")


class StartJobRequest(BaseModel):
    training_file_id:   str            = Field(..., description="Anthropic Files API file_id for training data")
    validation_file_id: Optional[str]  = Field(None)
    suffix: str                        = Field("edon-governance", description="Model name suffix")


class RunPipelineRequest(BaseModel):
    validation_split: float         = Field(0.1, ge=0.0, le=0.5)
    limits: Optional[dict]          = Field(None)
    suffix: str                     = Field("edon-governance")
    auto_start: bool                = Field(True, description="Start fine-tuning job immediately after upload")


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/datasets")
async def get_dataset_sizes():
    """Dry run: show how many examples each extractor would produce."""
    try:
        from ..training.extractors import extract_all
        from ..training.formatters import format_all
        from ..training.synthetic import generate_all as synthetic_all

        raw = extract_all(limits={
            "governance_decisions": 1000,
            "shadow_findings":      500,
            "risk_labels":          500,
            "vulnerabilities":      200,
            "deployed_rules":       200,
        })
        real = format_all(raw)
        synthetic = synthetic_all()

        return {
            "real": {k: len(v) for k, v in real.items()},
            "synthetic": {k: len(v) for k, v in synthetic.items()},
            "total_real": sum(len(v) for v in real.values()),
            "total_synthetic": sum(len(v) for v in synthetic.values()),
        }
    except Exception as exc:
        logger.error("[training/datasets] %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/export")
async def export_datasets(req: ExportRequest):
    """Extract all data stores → format → merge with synthetic → write JSONL to disk.

    Returns paths to the train.jsonl and validation.jsonl files.
    Does NOT call the Anthropic API (no API key needed for this step).
    """
    try:
        from ..training.pipeline import get_training_pipeline
        pipeline = get_training_pipeline()
        result = pipeline.export(
            limits=req.limits,
            validation_split=req.validation_split,
        )
        if "error" in result:
            raise HTTPException(status_code=422, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[training/export] %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/upload")
async def upload_to_anthropic(req: UploadRequest):
    """Upload train.jsonl and validation.jsonl to Anthropic Files API.

    Requires ANTHROPIC_API_KEY to be set.
    Returns training_file_id and validation_file_id.
    """
    from pathlib import Path
    train_path = Path(req.train_path)
    val_path   = Path(req.val_path)

    if not train_path.exists():
        raise HTTPException(status_code=404, detail=f"train_path not found: {req.train_path}")

    try:
        from ..training.pipeline import upload_file
        training_file_id   = await upload_file(train_path, train_path.name)
        validation_file_id = await upload_file(val_path, val_path.name) if val_path.exists() else None

        return {
            "training_file_id":   training_file_id,
            "validation_file_id": validation_file_id,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("[training/upload] %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/start")
async def start_finetune_job(req: StartJobRequest):
    """Create an Anthropic fine-tuning job from already-uploaded file IDs.

    Requires ANTHROPIC_API_KEY to be set.
    Returns job_id and initial status.
    """
    try:
        from ..training.pipeline import create_finetune_job
        job = await create_finetune_job(
            training_file_id=req.training_file_id,
            validation_file_id=req.validation_file_id,
            suffix=req.suffix,
        )
        return {
            "job_id":     job.get("id"),
            "status":     job.get("status"),
            "model":      job.get("model"),
            "created_at": job.get("created_at"),
            "job":        job,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("[training/start] %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/status/{job_id}")
async def get_job_status(job_id: str):
    """Get fine-tuning job status, metrics, and result model ID when complete."""
    try:
        from ..training.pipeline import get_finetune_job
        job = await get_finetune_job(job_id)
        return {
            "job_id":           job.get("id"),
            "status":           job.get("status"),
            "model":            job.get("model"),
            "fine_tuned_model": job.get("fine_tuned_model"),
            "trained_tokens":   job.get("trained_tokens"),
            "created_at":       job.get("created_at"),
            "finished_at":      job.get("finished_at"),
            "error":            job.get("error"),
            "job":              job,
        }
    except Exception as exc:
        logger.error("[training/status] job_id=%s error=%s", job_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/jobs")
async def list_jobs(limit: int = 20):
    """List all fine-tuning jobs sorted by creation date."""
    try:
        from ..training.pipeline import list_finetune_jobs
        jobs = await list_finetune_jobs(limit=limit)
        return {
            "jobs": [
                {
                    "job_id":           j.get("id"),
                    "status":           j.get("status"),
                    "model":            j.get("model"),
                    "fine_tuned_model": j.get("fine_tuned_model"),
                    "created_at":       j.get("created_at"),
                    "finished_at":      j.get("finished_at"),
                }
                for j in jobs
            ],
            "count": len(jobs),
        }
    except Exception as exc:
        logger.error("[training/jobs] %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    """Cancel a running fine-tuning job."""
    try:
        from ..training.pipeline import cancel_finetune_job
        job = await cancel_finetune_job(job_id)
        return {
            "job_id": job.get("id"),
            "status": job.get("status"),
        }
    except Exception as exc:
        logger.error("[training/cancel] job_id=%s error=%s", job_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/run")
async def run_full_pipeline(req: RunPipelineRequest):
    """Full pipeline: extract → format → export → upload → start fine-tuning job.

    This is the one-shot endpoint — call this to kick off the entire training cycle.
    Requires ANTHROPIC_API_KEY to be set.

    The pipeline:
    1. Extracts data from all EDON stores (audit_events, shadow, fleet_learning, impact)
    2. Formats to Anthropic fine-tuning JSONL
    3. Merges with synthetic bootstrap examples where real data is sparse
    4. Writes train.jsonl + validation.jsonl to EDON_TRAINING_DIR
    5. Uploads both files to Anthropic Files API
    6. Creates fine-tuning job (if auto_start=True)

    Returns job_id and full pipeline summary.
    """
    try:
        from ..training.pipeline import get_training_pipeline
        pipeline = get_training_pipeline()
        result = await pipeline.run(
            limits=req.limits,
            auto_start=req.auto_start,
            validation_split=req.validation_split,
            suffix=req.suffix,
        )
        if "error" in result:
            raise HTTPException(status_code=422, detail=result["error"])
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("[training/run] %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
