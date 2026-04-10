"""Webhook alert management — tenants configure Slack/PagerDuty push notifications."""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from ..persistence import get_db
from ..tenancy import get_request_tenant_id
from ..logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

VALID_EVENTS = {
    "decision.blocked",
    "decision.escalated",
    "risk.high",
    "compliance.violation",
    # Legacy / dispatcher-compatible names kept for backward compat
    "action.allowed",
    "action.blocked",
    "action.escalated",
    "anomaly.detected",
    "review.required",
}


class WebhookCreateRequest(BaseModel):
    name: str
    url: str
    events: List[str] = list(VALID_EVENTS)
    secret: Optional[str] = None


@router.get("")
async def list_webhooks(request: Request):
    """List all configured webhooks for this tenant."""
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    db = get_db()
    webhooks = db.get_webhooks(tenant_id)
    # Strip secrets from response
    for wh in webhooks:
        wh.pop("secret", None)
    return {"webhooks": webhooks}


@router.post("", status_code=201)
async def create_webhook(request: Request, body: WebhookCreateRequest):
    """Register a webhook endpoint to receive governance events."""
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    invalid = [e for e in body.events if e not in VALID_EVENTS]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown event types: {invalid}. Supported: {sorted(VALID_EVENTS)}",
        )

    webhook_id = f"wh_{uuid.uuid4().hex[:16]}"
    db = get_db()
    db.save_webhook(
        webhook_id=webhook_id,
        tenant_id=tenant_id,
        name=body.name,
        url=body.url,
        events=body.events,
        secret=body.secret,
        enabled=True,
    )
    logger.info("[webhooks] created id=%s tenant=%s url=%s", webhook_id, tenant_id, body.url)
    return {
        "id": webhook_id,
        "name": body.name,
        "url": body.url,
        "events": body.events,
        "enabled": True,
    }


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(webhook_id: str, request: Request):
    """Remove a webhook registration."""
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    db = get_db()
    deleted = db.delete_webhook(webhook_id, tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Webhook not found: {webhook_id}")
    logger.info("[webhooks] deleted id=%s tenant=%s", webhook_id, tenant_id)


@router.post("/{webhook_id}/test", status_code=200)
async def test_webhook(webhook_id: str, request: Request):
    """Send a test payload to the webhook URL."""
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    db = get_db()
    wh = db.get_webhook(webhook_id, tenant_id)
    if not wh:
        raise HTTPException(status_code=404, detail=f"Webhook not found: {webhook_id}")

    from ..services.webhook_delivery import deliver_webhook
    import asyncio

    asyncio.create_task(
        deliver_webhook(
            tenant_id=tenant_id,
            event_type="test",
            payload={
                "message": "EDON webhook test",
                "webhook_id": webhook_id,
            },
        )
    )
    return {"ok": True, "message": "Test payload queued for delivery"}
