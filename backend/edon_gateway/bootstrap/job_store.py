"""Bootstrap job store — tracks async bootstrap runs.

Jobs move through: pending → running → complete | failed

Backed by in-memory dict + JSON file persistence (same pattern as fix_pipeline).
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

from ..logging_config import get_logger

logger = get_logger(__name__)

_lock = threading.Lock()
_jobs: dict[str, dict] = {}


def _data_dir() -> Path:
    db_path = os.getenv("EDON_DATABASE_PATH", "").strip()
    if db_path:
        p = Path(db_path).parent
    else:
        url = os.getenv("EDON_DB_URL", "").strip()
        if url.startswith("sqlite:///"):
            p = Path(url.replace("sqlite:///", "", 1)).parent
        else:
            p = Path("/tmp/edon_data")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _jobs_path() -> Path:
    return _data_dir() / "bootstrap_jobs.json"


def _persist() -> None:
    try:
        _jobs_path().write_text(json.dumps(_jobs, indent=2))
    except Exception as exc:
        logger.warning("[bootstrap/jobs] persist failed: %s", exc)


def _load() -> None:
    path = _jobs_path()
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text())
        with _lock:
            _jobs.update(data)
    except Exception as exc:
        logger.warning("[bootstrap/jobs] load failed: %s", exc)


_load()


def create_job(tenant_id: Optional[str], artifact_types: list[str]) -> str:
    """Create a new bootstrap job. Returns job_id."""
    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "tenant_id": tenant_id,
        "artifact_types": artifact_types,
        "status": "pending",
        "progress": 0,
        "progress_message": "queued",
        "created_at": datetime.now(UTC).isoformat(),
        "started_at": None,
        "completed_at": None,
        "report": None,
        "error": None,
    }
    with _lock:
        _jobs[job_id] = job
        _persist()
    return job_id


def update_job(
    job_id: str,
    status: Optional[str] = None,
    progress: Optional[int] = None,
    progress_message: Optional[str] = None,
    report: Optional[dict] = None,
    error: Optional[str] = None,
) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        if status:
            job["status"] = status
            if status == "running" and not job.get("started_at"):
                job["started_at"] = datetime.now(UTC).isoformat()
            if status in ("complete", "failed"):
                job["completed_at"] = datetime.now(UTC).isoformat()
        if progress is not None:
            job["progress"] = progress
        if progress_message:
            job["progress_message"] = progress_message
        if report is not None:
            job["report"] = report
        if error:
            job["error"] = error
        _persist()


def get_job(job_id: str) -> Optional[dict]:
    with _lock:
        return dict(_jobs[job_id]) if job_id in _jobs else None


def list_jobs(tenant_id: Optional[str] = None, limit: int = 20) -> list[dict]:
    with _lock:
        jobs = list(_jobs.values())
    if tenant_id:
        jobs = [j for j in jobs if j.get("tenant_id") == tenant_id]
    jobs.sort(key=lambda j: j.get("created_at", ""), reverse=True)
    return jobs[:limit]
