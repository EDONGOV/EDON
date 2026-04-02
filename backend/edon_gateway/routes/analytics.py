"""Analytics stub routes for EDON Gateway (timeseries and block-reasons)."""

from fastapi import APIRouter, Query
from typing import List, Dict
from pydantic import BaseModel
from datetime import datetime, timedelta, UTC

from ..persistence import get_db

class TimeseriesPoint(BaseModel):
    timestamp: str
    label: str
    allowed: int
    blocked: int
    confirm: int


class BlockReasonItem(BaseModel):
    reason: str
    count: int


router = APIRouter(tags=["analytics"])


@router.get(
    "/timeseries",
    response_model=List[TimeseriesPoint],
    summary="Timeseries data",
)
async def get_timeseries(days: int = Query(7, ge=1, le=30)) -> List[TimeseriesPoint]:
    """Return timeseries data from audit events."""
    now = datetime.now(UTC)
    start_day = (now - timedelta(days=days - 1)).date()
    start_ts = datetime.combine(start_day, datetime.min.time(), tzinfo=UTC).isoformat()

    # Pre-fill days
    points_by_label: Dict[str, TimeseriesPoint] = {}
    for i in range(days):
        d = (now - timedelta(days=days - 1 - i)).date()
        label = d.strftime("%Y-%m-%d")
        ts = datetime.combine(d, datetime.min.time(), tzinfo=UTC).isoformat()
        points_by_label[label] = TimeseriesPoint(
            timestamp=ts,
            label=label,
            allowed=0,
            blocked=0,
            confirm=0,
        )

    # Pull audit events for the window and aggregate
    db = get_db()
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT timestamp, decision_verdict FROM audit_events WHERE timestamp >= ?",
            (start_ts,),
        )
        rows = cursor.fetchall()

    for row in rows:
        ts = row["timestamp"] or ""
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        try:
            event_dt = datetime.fromisoformat(ts)
        except Exception:
            continue
        label = event_dt.strftime("%Y-%m-%d")
        point = points_by_label.get(label)
        if not point:
            continue
        verdict = (row["decision_verdict"] or "").upper()
        if verdict == "ALLOW":
            point.allowed += 1
        elif verdict == "CONFIRM":
            point.confirm += 1
        else:
            point.blocked += 1

    return list(points_by_label.values())


@router.get(
    "/block-reasons",
    response_model=List[BlockReasonItem],
    summary="Block reasons",
)
async def get_block_reasons(days: int = Query(7, ge=1, le=30)) -> List[BlockReasonItem]:
    now = datetime.now(UTC)
    start_day = (now - timedelta(days=days - 1)).date()
    start_ts = datetime.combine(start_day, datetime.min.time(), tzinfo=UTC).isoformat()

    db = get_db()
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT decision_reason_code, COUNT(*) as count
            FROM audit_events
            WHERE timestamp >= ?
              AND decision_reason_code IS NOT NULL
              AND decision_reason_code != ''
            GROUP BY decision_reason_code
            ORDER BY count DESC
            """,
            (start_ts,),
        )
        rows = cursor.fetchall()

    results: List[BlockReasonItem] = []
    for row in rows:
        reason = row["decision_reason_code"] or "unknown"
        results.append(BlockReasonItem(reason=reason, count=int(row["count"] or 0)))
    return results
