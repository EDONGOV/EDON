"""Human review queue for HUMAN_REQUIRED escalations.

When the governance engine returns ESCALATE/HUMAN_REQUIRED, the decision is
stored here. Clinicians or IT staff can approve or reject via this API.
The console polls this queue to show the live review panel.

Endpoints:
    GET  /compliance/review/queue         — list pending escalations
    GET  /compliance/review/{decision_id} — get one escalation
    POST /compliance/review/{decision_id}/approve
    POST /compliance/review/{decision_id}/reject
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, UTC, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..tenancy import get_request_tenant_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/compliance/review", tags=["review-queue"])

# ── In-memory store (survives process lifetime; persisted to disk for durability) ──
_lock = threading.Lock()
_queue: Dict[str, Dict[str, Any]] = {}  # decision_id → record
_TTL_HOURS = int(os.getenv("EDON_REVIEW_TTL_HOURS", "48"))


def _data_dir() -> Path:
    url = os.getenv("EDON_DB_URL", "").strip()
    if url.startswith("sqlite:///"):
        p = Path(url.replace("sqlite:///", "", 1)).parent
        p.mkdir(parents=True, exist_ok=True)
        return p
    db_path = os.getenv("EDON_DATABASE_PATH", "").strip()
    if db_path:
        p = Path(db_path).parent
        p.mkdir(parents=True, exist_ok=True)
        return p
    p = Path("/data") if Path("/data").exists() else Path("/tmp/edon_data")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _queue_path() -> Path:
    return _data_dir() / "review_queue.json"


def _load_from_disk() -> None:
    path = _queue_path()
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text())
        cutoff = (datetime.now(UTC) - timedelta(hours=_TTL_HOURS)).isoformat()
        with _lock:
            for k, v in data.items():
                if v.get("created_at", "") >= cutoff:
                    _queue[k] = v
    except Exception as exc:
        logger.warning("review_queue: failed to load from disk: %s", exc)


def _persist() -> None:
    try:
        _queue_path().write_text(json.dumps(_queue, indent=2))
    except Exception as exc:
        logger.warning("review_queue: failed to persist: %s", exc)


# Load on import
_load_from_disk()


def enqueue_escalation(
    decision_id: str,
    tenant_id: str,
    agent_id: str,
    action_type: str,
    action_payload: Dict[str, Any],
    escalation_question: str,
    explanation: str,
    meta: Dict[str, Any],
) -> None:
    """Called from v1_action when a HUMAN_REQUIRED verdict is issued."""
    record = {
        "decision_id": decision_id,
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "action_type": action_type,
        "action_payload": action_payload,
        "escalation_question": escalation_question,
        "explanation": explanation,
        "meta": meta,
        "status": "pending",
        "created_at": datetime.now(UTC).isoformat(),
        "resolved_at": None,
        "resolved_by": None,
        "resolution": None,
        "resolution_note": None,
    }
    with _lock:
        _queue[decision_id] = record
        _persist()
    logger.info(
        "review_queue: escalation enqueued decision=%s tenant=%s agent=%s",
        decision_id, tenant_id, agent_id,
    )


def _send_telegram_escalation(record: Dict[str, Any]) -> None:
    """Fire Telegram notification for a new escalation (non-blocking)."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_OWNER_CHAT_ID", "") or os.getenv("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        return
    try:
        import requests as _req
        msg = (
            f"🔴 *HUMAN REVIEW REQUIRED*\n\n"
            f"*Agent:* `{record['agent_id']}`\n"
            f"*Action:* `{record['action_type']}`\n"
            f"*Tenant:* `{record['tenant_id']}`\n\n"
            f"*Question:* {record['escalation_question']}\n\n"
            f"*Decision ID:* `{record['decision_id']}`\n"
            f"Approve or reject at: https://console.edoncore.com"
        )
        _req.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
            timeout=8,
        )
    except Exception as exc:
        logger.warning("review_queue: Telegram notify failed: %s", exc)


def notify_escalation_async(record: Dict[str, Any]) -> None:
    """Send Telegram notification in a background thread."""
    import threading
    threading.Thread(target=_send_telegram_escalation, args=(record,), daemon=True).start()


# ── Routes ────────────────────────────────────────────────────────────────────

class ReviewDecisionBody(BaseModel):
    resolved_by: str = "unknown"
    note: Optional[str] = None


@router.get("/queue")
async def list_review_queue(request: Request, status: str = "pending"):
    """List escalations in the review queue."""
    tenant_id = get_request_tenant_id(request)
    cutoff = (datetime.now(UTC) - timedelta(hours=_TTL_HOURS)).isoformat()
    with _lock:
        items = [
            v for v in _queue.values()
            if (tenant_id is None or v["tenant_id"] == tenant_id)
            and v.get("status") == status
            and v.get("created_at", "") >= cutoff
        ]
    items.sort(key=lambda x: x["created_at"], reverse=True)
    return {"queue": items, "count": len(items)}


@router.get("/{decision_id}")
async def get_review_item(decision_id: str, request: Request):
    """Get a single escalation by decision ID."""
    tenant_id = get_request_tenant_id(request)
    with _lock:
        record = _queue.get(decision_id)
    if not record:
        raise HTTPException(status_code=404, detail="Escalation not found")
    if tenant_id and record["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return record


@router.post("/{decision_id}/approve")
async def approve_escalation(decision_id: str, request: Request, body: ReviewDecisionBody):
    """Approve a pending escalation — agent may proceed with this action."""
    tenant_id = get_request_tenant_id(request)
    with _lock:
        record = _queue.get(decision_id)
        if not record:
            raise HTTPException(status_code=404, detail="Escalation not found")
        if tenant_id and record["tenant_id"] != tenant_id:
            raise HTTPException(status_code=403, detail="Access denied")
        if record["status"] != "pending":
            raise HTTPException(status_code=409, detail=f"Already resolved: {record['status']}")
        record["status"] = "approved"
        record["resolved_at"] = datetime.now(UTC).isoformat()
        record["resolved_by"] = body.resolved_by
        record["resolution"] = "approved"
        record["resolution_note"] = body.note
        _persist()
    logger.info(
        "review_queue: APPROVED decision=%s by=%s tenant=%s",
        decision_id, body.resolved_by, tenant_id,
    )
    return {
        "decision_id": decision_id,
        "resolution": "approved",
        "resolved_by": body.resolved_by,
        "resolved_at": record["resolved_at"],
        "message": "Action approved. The agent may proceed.",
    }


@router.post("/{decision_id}/reject")
async def reject_escalation(decision_id: str, request: Request, body: ReviewDecisionBody):
    """Reject a pending escalation — agent action is permanently blocked."""
    tenant_id = get_request_tenant_id(request)
    with _lock:
        record = _queue.get(decision_id)
        if not record:
            raise HTTPException(status_code=404, detail="Escalation not found")
        if tenant_id and record["tenant_id"] != tenant_id:
            raise HTTPException(status_code=403, detail="Access denied")
        if record["status"] != "pending":
            raise HTTPException(status_code=409, detail=f"Already resolved: {record['status']}")
        record["status"] = "rejected"
        record["resolved_at"] = datetime.now(UTC).isoformat()
        record["resolved_by"] = body.resolved_by
        record["resolution"] = "rejected"
        record["resolution_note"] = body.note
        _persist()
    logger.info(
        "review_queue: REJECTED decision=%s by=%s tenant=%s",
        decision_id, body.resolved_by, tenant_id,
    )
    return {
        "decision_id": decision_id,
        "resolution": "rejected",
        "resolved_by": body.resolved_by,
        "resolved_at": record["resolved_at"],
        "message": "Action rejected and permanently blocked. This decision is audit-logged.",
    }
