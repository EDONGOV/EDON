"""EDON Training Data Pipeline.

Exports governance decisions, vulnerability findings, and risk labels
from all EDON data stores into Anthropic fine-tuning JSONL format.

Usage:
    from edon_gateway.training.pipeline import TrainingPipeline
    pipeline = TrainingPipeline()
    result = pipeline.run()

    # Or via API:
    POST /v1/training/export   — export datasets to disk
    POST /v1/training/upload   — upload to Anthropic Files API
    POST /v1/training/start    — create fine-tuning job
    GET  /v1/training/status/{job_id}
"""
from .pipeline import TrainingPipeline, get_training_pipeline

__all__ = ["TrainingPipeline", "get_training_pipeline"]
