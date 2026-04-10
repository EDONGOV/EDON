"""Async webhook delivery service.

Delivers governance event payloads to tenant-configured webhook URLs.
Uses asyncio so delivery never blocks the request path.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, UTC
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


async def deliver_webhook(
    tenant_id: str,
    event_type: str,
    payload: Dict[str, Any],
    db=None,
) -> None:
    """Look up enabled webhooks for the tenant that subscribe to *event_type*
    and POST the event payload to each URL.

    Non-blocking: call via ``asyncio.create_task(deliver_webhook(...))``.
    Failures are logged as warnings and never raised.
    """
    if db is None:
        from ..persistence import get_db
        db = get_db()

    try:
        webhooks = db.get_webhooks(tenant_id)
    except Exception as exc:
        logger.warning("deliver_webhook: failed to load webhooks tenant=%s: %s", tenant_id, exc)
        return

    for wh in webhooks:
        subscribed_events = wh.get("events", [])
        # Match exact event type OR the legacy dispatcher-compat aliases
        if event_type not in subscribed_events:
            # Allow e.g. "decision.blocked" → also match "action.blocked"
            _alias_map = {
                "decision.blocked": "action.blocked",
                "decision.escalated": "action.escalated",
            }
            alias = _alias_map.get(event_type)
            if alias not in subscribed_events:
                continue
        asyncio.create_task(_post_webhook(wh, event_type, payload, tenant_id, db))


async def _post_webhook(
    webhook: Dict[str, Any],
    event_type: str,
    payload: Dict[str, Any],
    tenant_id: str,
    db,
) -> None:
    """POST a single webhook with HMAC signature. Fire-and-forget."""
    import aiohttp  # optional dep; fall back to urllib if not available

    delivery_id = f"del_{uuid.uuid4().hex[:16]}"
    body_dict = {
        "event": event_type,
        "timestamp": datetime.now(UTC).isoformat(),
        "tenant_id": tenant_id,
        "data": payload,
    }
    body_bytes = json.dumps(body_dict).encode("utf-8")
    secret = webhook.get("secret") or ""
    sig = _hmac_sign(body_bytes, secret)

    headers = {
        "Content-Type": "application/json",
        "X-EDON-Event": event_type,
        "X-EDON-Delivery": delivery_id,
    }
    if sig:
        headers["X-EDON-Signature"] = sig

    status = "failed"
    response_status: Optional[int] = None
    attempts = 0

    try:
        try:
            async with aiohttp.ClientSession() as session:
                for attempt in range(3):
                    attempts = attempt + 1
                    try:
                        async with session.post(
                            webhook["url"],
                            data=body_bytes,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=10),
                        ) as resp:
                            response_status = resp.status
                            if 200 <= resp.status < 300:
                                status = "delivered"
                                break
                            logger.warning(
                                "deliver_webhook: attempt %d HTTP %d wh=%s",
                                attempt + 1, resp.status, webhook["id"],
                            )
                    except Exception as exc:
                        logger.warning(
                            "deliver_webhook: attempt %d error wh=%s: %s",
                            attempt + 1, webhook["id"], exc,
                        )
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
        except ImportError:
            # aiohttp not available — fall back to stdlib urllib (sync, but we're already in a task)
            import urllib.request
            import urllib.error

            for attempt in range(3):
                attempts = attempt + 1
                try:
                    req = urllib.request.Request(
                        webhook["url"], data=body_bytes, headers=headers, method="POST"
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        response_status = resp.status
                        if 200 <= resp.status < 300:
                            status = "delivered"
                            break
                except Exception as exc:
                    logger.warning(
                        "deliver_webhook (urllib): attempt %d wh=%s: %s",
                        attempt + 1, webhook["id"], exc,
                    )
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
    except Exception as exc:
        logger.warning("deliver_webhook: unexpected error wh=%s: %s", webhook["id"], exc)

    # Record delivery outcome
    try:
        db.save_webhook_delivery(
            delivery_id=delivery_id,
            webhook_id=webhook["id"],
            event_type=event_type,
            payload=body_dict,
            status=status,
            response_status=response_status,
            attempts=attempts,
        )
    except Exception as exc:
        logger.warning("deliver_webhook: failed to save delivery record: %s", exc)


def _hmac_sign(body: bytes, secret: str) -> str:
    """Return HMAC-SHA256 signature string or empty string when no secret."""
    if not secret:
        return ""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
