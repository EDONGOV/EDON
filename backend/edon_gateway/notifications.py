"""EDON Gateway — notification dispatcher for human review events.

Dispatches alerts when actions are escalated to the human review queue.
Supports Slack webhooks and SendGrid email. Both are optional and fail-open
so that a missing config never blocks governance decisions.

Environment variables:
    SLACK_WEBHOOK_URL       Slack incoming webhook URL (optional)
    SENDGRID_API_KEY        SendGrid API key (optional)
    EDON_NOTIFY_EMAIL_TO    Comma-separated recipient email addresses (optional)
    EDON_NOTIFY_EMAIL_FROM  Sender address for review alerts (optional)
"""

import os
import json
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

_SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "").strip()
_SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "").strip()
_EMAIL_TO = [e.strip() for e in os.getenv("EDON_NOTIFY_EMAIL_TO", "").split(",") if e.strip()]
_EMAIL_FROM = os.getenv("EDON_NOTIFY_EMAIL_FROM", "noreply@edoncore.com").strip()


def _send_slack(payload: dict) -> None:
    """Fire-and-forget Slack webhook POST."""
    if not _SLACK_WEBHOOK_URL:
        return
    try:
        import urllib.request
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            _SLACK_WEBHOOK_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status not in (200, 204):
                logger.warning("Slack notification returned HTTP %s", resp.status)
    except Exception as exc:
        logger.warning("Slack notification failed: %s", exc)


def _send_email(subject: str, body: str) -> None:
    """Send email via SendGrid REST API."""
    if not _SENDGRID_API_KEY or not _EMAIL_TO:
        return
    try:
        import urllib.request
        payload = {
            "personalizations": [{"to": [{"email": addr} for addr in _EMAIL_TO]}],
            "from": {"email": _EMAIL_FROM},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://api.sendgrid.com/v3/mail/send",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {_SENDGRID_API_KEY}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status not in (200, 202):
                logger.warning("SendGrid notification returned HTTP %s", resp.status)
    except Exception as exc:
        logger.warning("Email notification failed: %s", exc)


def notify_review_required(
    review_id: str,
    action_id: str,
    agent_id: str,
    reason: str,
    tenant_id: Optional[str] = None,
) -> None:
    """Dispatch a human review required notification (non-blocking).

    Called when an action is escalated to the human review queue.
    Runs Slack and email dispatch in a background thread so it never
    adds latency to the governance decision path.
    """
    message = (
        f":rotating_light: *EDON — Human Review Required*\n"
        f"• Review ID: `{review_id}`\n"
        f"• Action ID: `{action_id}`\n"
        f"• Agent: `{agent_id}`\n"
        f"• Reason: {reason}\n"
        f"• Tenant: `{tenant_id or 'unknown'}`\n"
        f"Review at: https://console.edoncore.com/review/{review_id}"
    )

    slack_payload = {"text": message}
    email_subject = f"[EDON] Human Review Required — {review_id}"
    email_body = message.replace("*", "").replace("`", "").replace(":rotating_light:", "[!]")

    def _dispatch():
        _send_slack(slack_payload)
        _send_email(email_subject, email_body)

    thread = threading.Thread(target=_dispatch, daemon=True, name=f"notify-{review_id[:8]}")
    thread.start()
    logger.debug("Review notification dispatched for review_id=%s", review_id)
