"""EDON Training Data Pipeline.

Orchestrates the full flow from raw data stores → formatted JSONL → Anthropic Files API
→ fine-tuning job creation → status tracking.

Usage:
    pipeline = TrainingPipeline()
    result = await pipeline.run()   # export + upload + optionally start job

Environment variables:
    ANTHROPIC_API_KEY       — required for upload and fine-tuning
    EDON_TRAINING_DIR       — output directory for JSONL files (default: /app/data/training)
    EDON_TRAINING_MIN_REAL  — minimum real examples before adding synthetic (default: 50)
    EDON_FINETUNE_MODEL     — base model to fine-tune (default: claude-haiku-4-5-20251001)
    EDON_FINETUNE_EPOCHS    — training epochs (default: 3)
    EDON_FINETUNE_LR_MULT  — learning rate multiplier (default: 1.0)
    EDON_FINETUNE_BATCH    — batch size (default: 32)

Fine-tuning API docs: https://docs.anthropic.com/en/docs/build-with-claude/model-distillation
"""

from __future__ import annotations

import json
import os
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

import httpx

from ..logging_config import get_logger
from .extractors import extract_all
from .formatters import format_all
from .synthetic import generate_all as synthetic_all

logger = get_logger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────

_TRAINING_DIR   = Path(os.getenv("EDON_TRAINING_DIR",    "/app/data/training"))
_MIN_REAL       = int(os.getenv("EDON_TRAINING_MIN_REAL", "50"))
_BASE_MODEL     = os.getenv("EDON_FINETUNE_MODEL",        "claude-haiku-4-5-20251001")
_EPOCHS         = int(os.getenv("EDON_FINETUNE_EPOCHS",   "3"))
_LR_MULT        = float(os.getenv("EDON_FINETUNE_LR_MULT","1.0"))
_BATCH          = int(os.getenv("EDON_FINETUNE_BATCH",    "32"))

_ANTHROPIC_API  = "https://api.anthropic.com/v1"
_ANTHROPIC_VER  = "2023-06-01"
_BETA_HEADER    = "fine-tuning-2025-03-15"

# Minimum examples required per dataset to include it in training
_MIN_EXAMPLES_PER_DATASET = 10


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _api_key() -> str:
    k = os.getenv("ANTHROPIC_API_KEY", "")
    if not k:
        raise ValueError("ANTHROPIC_API_KEY not set")
    return k


def _headers() -> dict:
    return {
        "x-api-key":         _api_key(),
        "anthropic-version": _ANTHROPIC_VER,
        "anthropic-beta":    _BETA_HEADER,
        "content-type":      "application/json",
    }


# ── JSONL writing ──────────────────────────────────────────────────────────────

def _write_jsonl(examples: list[dict], path: Path) -> int:
    """Write examples to JSONL. Returns count written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(path, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
            count += 1
    return count


# ── Dataset merging (real + synthetic) ────────────────────────────────────────

def _merge_datasets(
    real: dict[str, list[dict]],
    synthetic: dict[str, list[dict]],
    min_real: int = _MIN_REAL,
) -> dict[str, list[dict]]:
    """Merge real and synthetic examples.

    Strategy:
    - If real examples for a key >= min_real: use real only
    - If real examples < min_real: prepend real to synthetic (real first = higher weight)
    - Always deduplicate by assistant content hash to avoid exact duplicates
    """
    merged: dict[str, list[dict]] = {}
    for key in real:
        real_list = real.get(key, [])
        syn_list  = synthetic.get(key, [])

        if len(real_list) >= min_real:
            merged[key] = real_list
            logger.info("[pipeline] %s: %d real examples (no synthetic needed)", key, len(real_list))
        else:
            combined = real_list + syn_list
            # Deduplicate on assistant content
            seen: set[str] = set()
            deduped = []
            for ex in combined:
                msgs = ex.get("messages", [])
                key_str = next((m["content"] for m in msgs if m["role"] == "assistant"), "")
                if key_str not in seen:
                    seen.add(key_str)
                    deduped.append(ex)
            merged[key] = deduped
            logger.info(
                "[pipeline] %s: %d real + %d synthetic = %d merged",
                key, len(real_list), len(syn_list), len(deduped),
            )

    return merged


# ── Anthropic Files API ────────────────────────────────────────────────────────

async def upload_file(path: Path, name: str) -> str:
    """Upload a JSONL file to Anthropic Files API. Returns file_id."""
    with open(path, "rb") as f:
        content = f.read()

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{_ANTHROPIC_API}/files",
            headers={
                "x-api-key":         _api_key(),
                "anthropic-version": _ANTHROPIC_VER,
                "anthropic-beta":    _BETA_HEADER,
            },
            files={"file": (name, content, "application/jsonl")},
        )

    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Files API upload failed {resp.status_code}: {resp.text[:400]}")

    data = resp.json()
    file_id = data.get("id") or data.get("file_id")
    if not file_id:
        raise RuntimeError(f"Files API returned no file_id: {data}")

    logger.info("[pipeline] uploaded %s → file_id=%s", name, file_id)
    return file_id


async def list_files() -> list[dict]:
    """List all files in Anthropic Files API."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{_ANTHROPIC_API}/files", headers=_headers())
    if resp.status_code != 200:
        raise RuntimeError(f"Files API list failed {resp.status_code}: {resp.text[:300]}")
    return resp.json().get("data", [])


async def delete_file(file_id: str) -> None:
    """Delete a file from Anthropic Files API."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.delete(f"{_ANTHROPIC_API}/files/{file_id}", headers=_headers())
    if resp.status_code not in (200, 204):
        logger.warning("[pipeline] delete file %s returned %d", file_id, resp.status_code)


# ── Fine-tuning job API ────────────────────────────────────────────────────────

async def create_finetune_job(
    training_file_id: str,
    validation_file_id: Optional[str] = None,
    suffix: Optional[str] = None,
) -> dict:
    """Create a fine-tuning job. Returns the full job dict."""
    body: dict = {
        "model":       _BASE_MODEL,
        "training_file": training_file_id,
        "hyperparameters": {
            "n_epochs":              _EPOCHS,
            "learning_rate_multiplier": _LR_MULT,
            "batch_size":            _BATCH,
        },
    }
    if validation_file_id:
        body["validation_file"] = validation_file_id
    if suffix:
        body["suffix"] = suffix

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{_ANTHROPIC_API}/fine_tuning/jobs",
            headers=_headers(),
            json=body,
        )

    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Fine-tuning job create failed {resp.status_code}: {resp.text[:400]}")

    job = resp.json()
    logger.info("[pipeline] fine-tuning job created: id=%s model=%s", job.get("id"), job.get("model"))
    return job


async def get_finetune_job(job_id: str) -> dict:
    """Get fine-tuning job status."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{_ANTHROPIC_API}/fine_tuning/jobs/{job_id}",
            headers=_headers(),
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Fine-tuning job get failed {resp.status_code}: {resp.text[:300]}")
    return resp.json()


async def list_finetune_jobs(limit: int = 20) -> list[dict]:
    """List fine-tuning jobs."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{_ANTHROPIC_API}/fine_tuning/jobs",
            headers=_headers(),
            params={"limit": limit},
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Fine-tuning job list failed {resp.status_code}: {resp.text[:300]}")
    return resp.json().get("data", [])


async def cancel_finetune_job(job_id: str) -> dict:
    """Cancel a fine-tuning job."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{_ANTHROPIC_API}/fine_tuning/jobs/{job_id}/cancel",
            headers=_headers(),
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Fine-tuning job cancel failed {resp.status_code}: {resp.text[:300]}")
    return resp.json()


# ── Pipeline orchestrator ──────────────────────────────────────────────────────

class TrainingPipeline:
    """Full extract → format → validate → export → upload → fine-tune pipeline."""

    def __init__(self, training_dir: Optional[Path] = None):
        self.training_dir = training_dir or _TRAINING_DIR

    # ── Step 1: Extract + format + merge ──────────────────────────────────────

    def build_datasets(
        self,
        limits: Optional[dict] = None,
        tenant_id: Optional[str] = None,
    ) -> dict[str, list[dict]]:
        """Extract real data, format, merge with synthetic. Returns final examples dict."""
        logger.info("[pipeline] extracting from data stores… tenant_id=%s", tenant_id)
        raw = extract_all(limits=limits, tenant_id=tenant_id)

        logger.info("[pipeline] formatting…")
        real_formatted = format_all(raw)

        logger.info("[pipeline] generating synthetic bootstraps…")
        synthetic = synthetic_all()

        logger.info("[pipeline] merging real + synthetic…")
        merged = _merge_datasets(real_formatted, synthetic, min_real=_MIN_REAL)

        return merged

    # ── Step 2: Export to JSONL ────────────────────────────────────────────────

    def export(
        self,
        datasets: Optional[dict[str, list[dict]]] = None,
        limits: Optional[dict] = None,
        validation_split: float = 0.1,
        tenant_id: Optional[str] = None,
    ) -> dict:
        """Write JSONL files to disk. Returns paths and counts."""
        if datasets is None:
            datasets = self.build_datasets(limits=limits, tenant_id=tenant_id)

        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        run_dir = self.training_dir / ts
        run_dir.mkdir(parents=True, exist_ok=True)

        # Combine all datasets into one training file + one validation file
        all_examples: list[dict] = []
        for key, examples in datasets.items():
            if len(examples) >= _MIN_EXAMPLES_PER_DATASET:
                all_examples.extend(examples)
            else:
                logger.info("[pipeline] skipping %s — only %d examples (min %d)", key, len(examples), _MIN_EXAMPLES_PER_DATASET)

        if not all_examples:
            return {"error": "no examples generated — check data stores and synthetic templates"}

        # Shuffle deterministically
        import random as _random
        rng = _random.Random(42)
        rng.shuffle(all_examples)

        # Split
        n_val = max(1, int(len(all_examples) * validation_split))
        val_examples   = all_examples[:n_val]
        train_examples = all_examples[n_val:]

        train_path = run_dir / "train.jsonl"
        val_path   = run_dir / "validation.jsonl"

        n_train = _write_jsonl(train_examples, train_path)
        n_val   = _write_jsonl(val_examples,   val_path)

        # Per-dataset breakdown for reporting
        breakdown: dict[str, int] = {}
        for key, examples in datasets.items():
            breakdown[key] = len(examples)

        result = {
            "run_dir":       str(run_dir),
            "train_path":    str(train_path),
            "val_path":      str(val_path),
            "n_train":       n_train,
            "n_val":         n_val,
            "total":         n_train + n_val,
            "breakdown":     breakdown,
            "exported_at":   datetime.now(UTC).isoformat(),
        }

        logger.info(
            "[pipeline] exported: %d train + %d val = %d total → %s",
            n_train, n_val, n_train + n_val, run_dir,
        )
        return result

    # ── Step 3: Upload to Anthropic ────────────────────────────────────────────

    async def upload(self, export_result: dict) -> dict:
        """Upload train + val JSONL files to Anthropic Files API."""
        train_path = Path(export_result["train_path"])
        val_path   = Path(export_result["val_path"])

        if not train_path.exists():
            raise FileNotFoundError(f"Training file not found: {train_path}")

        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")

        training_file_id   = await upload_file(train_path, f"edon_train_{ts}.jsonl")
        validation_file_id = await upload_file(val_path,   f"edon_val_{ts}.jsonl") if val_path.exists() else None

        return {
            **export_result,
            "training_file_id":   training_file_id,
            "validation_file_id": validation_file_id,
            "uploaded_at":        datetime.now(UTC).isoformat(),
        }

    # ── Step 4: Create fine-tuning job ─────────────────────────────────────────

    async def start_finetune(
        self,
        upload_result: dict,
        suffix: Optional[str] = "edon-governance",
    ) -> dict:
        """Create the Anthropic fine-tuning job."""
        training_file_id   = upload_result.get("training_file_id")
        validation_file_id = upload_result.get("validation_file_id")

        if not training_file_id:
            raise ValueError("training_file_id missing from upload result")

        job = await create_finetune_job(
            training_file_id=training_file_id,
            validation_file_id=validation_file_id,
            suffix=suffix,
        )

        return {
            **upload_result,
            "job_id":     job.get("id"),
            "job_status": job.get("status"),
            "job_model":  job.get("model"),
            "job":        job,
            "started_at": datetime.now(UTC).isoformat(),
        }

    # ── Full pipeline ──────────────────────────────────────────────────────────

    async def run(
        self,
        limits: Optional[dict] = None,
        auto_start: bool = True,
        validation_split: float = 0.1,
        suffix: Optional[str] = "edon-governance",
        tenant_id: Optional[str] = None,
    ) -> dict:
        """Run the full pipeline: extract → format → export → upload → start job.

        Returns a dict with all intermediate results and final job info.

        Args:
            limits:           per-dataset row limits (e.g. {"governance_decisions": 1000})
            auto_start:       if True, creates the fine-tuning job after upload
            validation_split: fraction of data held for validation (default 10%)
            suffix:           model name suffix (appears as claude-...-edon-governance)
            tenant_id:        if set, extract only this tenant's data and record the model
        """
        started = datetime.now(UTC).isoformat()
        result: dict = {"pipeline_started_at": started, "steps": {}, "tenant_id": tenant_id}

        # Step 1: export
        try:
            export_result = self.export(
                limits=limits, validation_split=validation_split, tenant_id=tenant_id)
            result["steps"]["export"] = export_result
            if "error" in export_result:
                result["error"] = export_result["error"]
                return result
        except Exception as exc:
            logger.error("[pipeline] export failed: %s", exc)
            result["error"] = f"export failed: {exc}"
            return result

        # Step 2: upload
        try:
            upload_result = await self.upload(export_result)
            result["steps"]["upload"] = {
                k: v for k, v in upload_result.items()
                if k in ("training_file_id", "validation_file_id", "uploaded_at")
            }
        except Exception as exc:
            logger.error("[pipeline] upload failed: %s", exc)
            result["error"] = f"upload failed: {exc}"
            result["steps"]["upload"] = {"error": str(exc)}
            return result

        # Step 3: start fine-tuning job
        if auto_start:
            try:
                finetune_result = await self.start_finetune(upload_result, suffix=suffix)
                result["steps"]["finetune"] = {
                    k: v for k, v in finetune_result.items()
                    if k in ("job_id", "job_status", "job_model", "started_at")
                }
                result["job_id"]     = finetune_result.get("job_id")
                result["job_status"] = finetune_result.get("job_status")

                # Gap 2: persist per-tenant model record so routing can look it up
                if tenant_id and result.get("job_id"):
                    try:
                        from ..persistence import get_db
                        get_db().save_tenant_model(
                            tenant_id=tenant_id,
                            job_id=result["job_id"],
                            model_id="",
                            status=result.get("job_status", "training"),
                        )
                        logger.info("[pipeline] saved tenant model record: tenant=%s job=%s",
                                    tenant_id, result["job_id"])
                    except Exception as _persist_exc:
                        logger.warning("[pipeline] could not persist tenant model record: %s", _persist_exc)
            except Exception as exc:
                logger.error("[pipeline] fine-tuning start failed: %s", exc)
                result["error"] = f"fine-tuning start failed: {exc}"
                result["steps"]["finetune"] = {"error": str(exc)}

        result["pipeline_completed_at"] = datetime.now(UTC).isoformat()
        result["n_train"]   = export_result.get("n_train", 0)
        result["n_val"]     = export_result.get("n_val", 0)
        result["breakdown"] = export_result.get("breakdown", {})
        result["run_dir"]   = export_result.get("run_dir")

        logger.info(
            "[pipeline] complete: %d train, %d val, job_id=%s status=%s",
            result["n_train"], result["n_val"],
            result.get("job_id"), result.get("job_status"),
        )
        return result


# ── Singleton ──────────────────────────────────────────────────────────────────

_pipeline: Optional[TrainingPipeline] = None


def get_training_pipeline() -> TrainingPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = TrainingPipeline()
    return _pipeline
