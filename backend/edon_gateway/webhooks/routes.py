"""Webhook management routes."""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from ..persistence import get_db
from ..tenancy import get_request_tenant_id
from ..logging_config import get_logger
from .dispatcher import SUPPORTED_EVENTS

logger = get_logger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class WebhookCreateRequest(BaseModel):
    url: str
    secret: Optional[str] = None
    events: List[str] = list(SUPPORTED_EVENTS)
    retry_count: int = 3


@router.post("", status_code=201)
async def create_webhook(request: Request, body: WebhookCreateRequest):
    """Register a webhook endpoint to receive governance events."""
    tenant_id = get_request_tenant_id(request)
    db = get_db()

    invalid = [e for e in body.events if e not in SUPPORTED_EVENTS]
    if invalid:
        raise HTTPException(400, detail=f"Unknown event types: {invalid}. Supported: {sorted(SUPPORTED_EVENTS)}")

    webhook_id = f"wh_{uuid.uuid4().hex[:16]}"
    db.save_webhook(
        webhook_id=webhook_id,
        tenant_id=tenant_id or "default",
        url=body.url,
        secret=body.secret,
        events=body.events,
        retry_count=body.retry_count,
    )
    logger.info("[webhooks] created id=%s tenant=%s url=%s", webhook_id, tenant_id, body.url)
    return {"webhook_id": webhook_id, "status": "active", "events": body.events}


@router.get("")
async def list_webhooks(request: Request):
    """List all active webhooks for this tenant."""
    tenant_id = get_request_tenant_id(request)
    db = get_db()
    webhooks = db.get_webhooks(tenant_id or "default")
    # Strip secret from response
    for wh in webhooks:
        wh.pop("secret", None)
    return {"webhooks": webhooks, "count": len(webhooks)}


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(webhook_id: str, request: Request):
    """Remove a webhook registration."""
    tenant_id = get_request_tenant_id(request)
    db = get_db()
    deleted = db.delete_webhook(webhook_id, tenant_id or "default")
    if not deleted:
        raise HTTPException(404, detail=f"Webhook not found: {webhook_id}")
    logger.info("[webhooks] deleted id=%s tenant=%s", webhook_id, tenant_id)


@router.get("/{webhook_id}/deliveries")
async def get_webhook_deliveries(webhook_id: str, limit: int = 50):
    """Get delivery history for a webhook."""
    db = get_db()
    deliveries = db.get_webhook_deliveries(webhook_id, limit=limit)
    return {"webhook_id": webhook_id, "deliveries": deliveries, "count": len(deliveries)}
