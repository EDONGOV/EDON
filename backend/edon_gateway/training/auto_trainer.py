"""Continuous per-tenant training loop.

Monitors new labeled governance events per tenant. When a tenant accumulates
enough new data since its last fine-tune run, automatically triggers a new
training pipeline run for that tenant only.

Controlled by:
    EDON_AUTO_TRAIN_ENABLED   — "true" to enable (default: false)
    EDON_AUTO_TRAIN_THRESHOLD — new event count needed to trigger (default: 500)
    EDON_AUTO_TRAIN_INTERVAL  — check interval in seconds (default: 3600)
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, UTC
from typing import Optional

from ..logging_config import get_logger
from .pipeline import get_training_pipeline

logger = get_logger(__name__)

_ENABLED   = os.getenv("EDON_AUTO_TRAIN_ENABLED", "false").lower() == "true"
_THRESHOLD = int(os.getenv("EDON_AUTO_TRAIN_THRESHOLD", "500"))
_INTERVAL  = int(os.getenv("EDON_AUTO_TRAIN_INTERVAL",  "3600"))


class AutoTrainer:
    def __init__(self) -> None:
        # ISO timestamp of last successful pipeline run per tenant
        self._last_run: dict[str, str] = {}
        self._running = False

    def start(self) -> None:
        if not _ENABLED:
            logger.info("[auto_trainer] disabled (set EDON_AUTO_TRAIN_ENABLED=true to enable)")
            return
        if self._running:
            return
        self._running = True
        asyncio.create_task(self._loop())
        logger.info(
            "[auto_trainer] started — threshold=%d events, interval=%ds",
            _THRESHOLD, _INTERVAL,
        )

    async def _loop(self) -> None:
        # Short warm-up so the gateway finishes booting before first check
        await asyncio.sleep(120)
        while self._running:
            await self._check_all_tenants()
            await asyncio.sleep(_INTERVAL)

    async def _check_all_tenants(self) -> None:
        try:
            from ..persistence import get_db
            db = get_db()
            tenants = db.list_tenants() if hasattr(db, "list_tenants") else []
        except Exception as exc:
            logger.warning("[auto_trainer] could not list tenants: %s", exc)
            return

        for tenant in tenants:
            tenant_id = tenant.get("id") or tenant.get("tenant_id")
            if not tenant_id:
                continue
            await self._check_tenant(tenant_id)

    async def _check_tenant(self, tenant_id: str) -> None:
        try:
            from ..persistence import get_db
            db = get_db()
            since = self._last_run.get(tenant_id, "1970-01-01T00:00:00+00:00")
            new_count = db.count_new_audit_events(tenant_id, since)

            if new_count < _THRESHOLD:
                logger.debug(
                    "[auto_trainer] tenant=%s new_events=%d < threshold=%d, skipping",
                    tenant_id, new_count, _THRESHOLD,
                )
                return

            logger.info(
                "[auto_trainer] tenant=%s: %d new events >= threshold=%d — triggering training",
                tenant_id, new_count, _THRESHOLD,
            )
            pipeline = get_training_pipeline()
            result = await pipeline.run(
                tenant_id=tenant_id,
                auto_start=True,
                suffix=f"edon-{tenant_id[:8]}",
            )
            if "error" in result:
                logger.warning(
                    "[auto_trainer] tenant=%s pipeline error: %s", tenant_id, result["error"]
                )
            else:
                self._last_run[tenant_id] = datetime.now(UTC).isoformat()
                logger.info(
                    "[auto_trainer] tenant=%s training triggered — job_id=%s train=%d val=%d",
                    tenant_id, result.get("job_id"),
                    result.get("n_train", 0), result.get("n_val", 0),
                )
        except Exception as exc:
            logger.warning("[auto_trainer] tenant=%s check failed: %s", tenant_id, exc)


_auto_trainer: Optional[AutoTrainer] = None


def get_auto_trainer() -> AutoTrainer:
    global _auto_trainer
    if _auto_trainer is None:
        _auto_trainer = AutoTrainer()
    return _auto_trainer


def start_auto_trainer() -> None:
    get_auto_trainer().start()
