"""Decision-volume metering for EDON billing.

Records every governance decision as a usage event and aggregates them for
billing purposes. Recording is fire-and-forget — it never blocks the
governance pipeline.

Usage:
    # In v1_action.py, after a decision is made:
    import asyncio
    asyncio.create_task(record_decision_async(
        customer_id=tenant_id,
        verdict=decision.verdict.value,
        action_type=req.action_type,
    ))
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# In-memory counters (per-tenant, per-period) — flushed to DB periodically
# Structure: {tenant_id: {period_start: {verdict: count}}}
_counters: Dict[str, Dict[str, Dict[str, int]]] = {}
_FLUSH_EVERY_N = int(os.getenv("EDON_METERING_FLUSH_EVERY", "50"))
_flush_counter = 0


@dataclass
class UsageReport:
    tenant_id: str
    period_start: str  # YYYY-MM-01
    period_end: str    # YYYY-MM-DD (today or end of month)
    total_decisions: int
    by_verdict: Dict[str, int] = field(default_factory=dict)
    by_action_type: Dict[str, int] = field(default_factory=dict)


def _current_period() -> str:
    """Return the current billing period start as YYYY-MM-01."""
    now = datetime.now(UTC)
    return f"{now.year}-{now.month:02d}-01"


def record_decision(
    customer_id: str,
    verdict: str,
    action_type: str = "",
) -> None:
    """Record one governance decision for metering. Never raises.

    This is the synchronous version — call it from background tasks or
    fire-and-forget coroutines. Do NOT await this directly from hot paths.
    """
    global _flush_counter
    if not customer_id:
        return

    try:
        period = _current_period()
        tenant_counters = _counters.setdefault(customer_id, {})
        period_counters = tenant_counters.setdefault(period, {})
        period_counters[verdict] = period_counters.get(verdict, 0) + 1

        _flush_counter += 1
        if _flush_counter >= _FLUSH_EVERY_N:
            _flush_counter = 0
            _flush_to_db(customer_id, period, period_counters)
    except Exception as exc:
        logger.debug("Metering record error (non-fatal): %s", exc)


async def record_decision_async(
    customer_id: str,
    verdict: str,
    action_type: str = "",
) -> None:
    """Async wrapper for use with asyncio.create_task()."""
    record_decision(customer_id, verdict, action_type)


def get_usage(
    customer_id: str,
    period_start: Optional[str] = None,
) -> UsageReport:
    """Return usage for the given tenant and billing period.

    Reads from the database first, then adds any in-memory counts not yet flushed.
    """
    if not period_start:
        period_start = _current_period()
    now = datetime.now(UTC)
    period_end = f"{now.year}-{now.month:02d}-{now.day:02d}"

    # Read from DB
    by_verdict: Dict[str, int] = {}
    try:
        from ..persistence import get_db
        db = get_db()
        if hasattr(db, "get_tenant_usage_by_verdict"):
            by_verdict = db.get_tenant_usage_by_verdict(customer_id, period_start) or {}
        else:
            # Fallback: count from audit_events
            by_verdict = _count_from_audit(db, customer_id, period_start, period_end)
    except Exception as exc:
        logger.debug("Usage DB read error (non-fatal): %s", exc)

    # Add in-memory counts not yet flushed
    in_mem = _counters.get(customer_id, {}).get(period_start, {})
    for verdict, count in in_mem.items():
        by_verdict[verdict] = by_verdict.get(verdict, 0) + count

    total = sum(by_verdict.values())
    return UsageReport(
        tenant_id=customer_id,
        period_start=period_start,
        period_end=period_end,
        total_decisions=total,
        by_verdict=by_verdict,
    )


def get_usage_history(customer_id: str, months: int = 12) -> list[UsageReport]:
    """Return monthly usage summaries for the last N months."""
    reports = []
    now = datetime.now(UTC)
    for i in range(months):
        month = now.month - i
        year = now.year
        while month <= 0:
            month += 12
            year -= 1
        period_start = f"{year}-{month:02d}-01"
        reports.append(get_usage(customer_id, period_start))
    return reports


def _flush_to_db(customer_id: str, period: str, counters: Dict[str, int]) -> None:
    """Flush in-memory counters to the database. Best-effort."""
    try:
        from ..persistence import get_db
        db = get_db()
        total = sum(counters.values())
        if hasattr(db, "upsert_tenant_usage"):
            db.upsert_tenant_usage(customer_id, period, total)
    except Exception as exc:
        logger.debug("Metering flush error (non-fatal): %s", exc)


def _count_from_audit(db, customer_id: str, period_start: str, period_end: str) -> Dict[str, int]:
    """Count decisions by verdict from the audit_events table."""
    try:
        with db._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT decision_verdict, COUNT(*) as cnt
                FROM audit_events
                WHERE customer_id = ?
                  AND timestamp >= ?
                  AND timestamp <= ?
                GROUP BY decision_verdict
                """,
                (customer_id, period_start, period_end + "T23:59:59"),
            ).fetchall()
        return {row[0]: row[1] for row in rows if row[0]}
    except Exception:
        return {}
