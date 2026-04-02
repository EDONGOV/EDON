"""Webhook event dispatcher with HMAC-SHA256 signature and retry logic."""
import hashlib
import hmac
import json
import logging
import time
import uuid
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

SUPPORTED_EVENTS = {
    "action.allowed", "action.blocked", "action.escalated",
    "anomaly.detected", "review.required",
}


def dispatch_event(
    event_type: str,
    payload: Dict[str, Any],
    tenant_id: str,
    db=None,
) -> None:
    """Dispatch a governance event to all matching tenant webhooks.

    Non-blocking: failures are logged but not raised.
    """
    if event_type not in SUPPORTED_EVENTS:
        return
    if db is None:
        from ..persistence import get_db
        db = get_db()
    try:
        webhooks = db.get_webhooks(tenant_id)
    except Exception as exc:
        logger.warning("Failed to load webhooks for tenant %s: %s", tenant_id, exc)
        return

    for wh in webhooks:
        if event_type not in wh.get("events", []):
            continue
        _deliver_webhook(wh, event_type, payload, db)


def _deliver_webhook(
    webhook: Dict,
    event_type: str,
    payload: Dict[str, Any],
    db,
    max_retries: int = 3,
) -> None:
    delivery_id = f"del_{uuid.uuid4().hex[:16]}"
    body = json.dumps({
        "event": event_type,
        "payload": payload,
        "webhook_id": webhook["id"],
        "delivery_id": delivery_id,
    }).encode("utf-8")

    sig = _sign(body, webhook.get("secret") or "")
    headers = {
        "Content-Type": "application/json",
        "X-EDON-Event": event_type,
        "X-EDON-Delivery": delivery_id,
        "X-EDON-Signature": sig,
    }

    status = "failed"
    response_status = None
    attempts = 0
    backoff = 1.0

    for attempt in range(max_retries):
        attempts = attempt + 1
        try:
            req = urllib.request.Request(
                webhook["url"], data=body, headers=headers, method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                response_status = resp.status
                if 200 <= resp.status < 300:
                    status = "delivered"
                    break
                logger.warning(
                    "Webhook %s delivery attempt %d: HTTP %d",
                    webhook["id"], attempt + 1, resp.status,
                )
        except Exception as exc:
            logger.warning(
                "Webhook %s delivery attempt %d failed: %s",
                webhook["id"], attempt + 1, exc,
            )
        if attempt < max_retries - 1:
            time.sleep(backoff)
            backoff *= 2

    try:
        db.save_webhook_delivery(
            delivery_id=delivery_id,
            webhook_id=webhook["id"],
            event_type=event_type,
            payload={"event": event_type, "payload": payload},
            status=status,
            response_status=response_status,
            attempts=attempts,
        )
    except Exception as exc:
        logger.warning("Failed to save webhook delivery record: %s", exc)


def _sign(body: bytes, secret: str) -> str:
    if not secret:
        return ""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
