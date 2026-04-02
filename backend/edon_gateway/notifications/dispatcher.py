"""Notification dispatcher: Slack webhook and SendGrid email for review queue events."""
import os
import json
import logging
import urllib.request
import urllib.error
from typing import Optional

logger = logging.getLogger(__name__)

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL", "noreply@edoncore.com")
SENDGRID_ALERT_TO = os.getenv("SENDGRID_ALERT_TO", "")  # comma-separated list


def notify_review_required(
    review_id: str,
    action_id: str,
    agent_id: str,
    reason: str,
    tenant_id: Optional[str] = None,
) -> None:
    """Send notifications when a human review is required.

    Sends Slack webhook and/or email if configured. Failures are logged but not raised.
    """
    message = (
        f"🔍 *Human Review Required*\n"
        f"• Review ID: `{review_id}`\n"
        f"• Action ID: `{action_id}`\n"
        f"• Agent: `{agent_id}`\n"
        f"• Tenant: `{tenant_id or 'unknown'}`\n"
        f"• Reason: {reason}"
    )
    _send_slack(message)
    _send_email(
        subject=f"[EDON] Human Review Required: {action_id}",
        body=message,
    )


def notify_anomaly_detected(
    agent_id: str,
    score: float,
    pattern: str,
    tenant_id: Optional[str] = None,
) -> None:
    """Send alert when a behavioral anomaly is detected at CRITICAL level."""
    message = (
        f"🚨 *Anomaly Detected*\n"
        f"• Agent: `{agent_id}`\n"
        f"• Score: `{score:.2f}`\n"
        f"• Pattern: `{pattern}`\n"
        f"• Tenant: `{tenant_id or 'unknown'}`"
    )
    _send_slack(message)
    _send_email(
        subject=f"[EDON] Anomaly Detected: agent={agent_id} score={score:.2f}",
        body=message,
    )


def _send_slack(message: str) -> None:
    if not SLACK_WEBHOOK_URL:
        return
    try:
        payload = json.dumps({"text": message}).encode("utf-8")
        req = urllib.request.Request(
            SLACK_WEBHOOK_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status not in (200, 201):
                logger.warning("Slack notification failed: HTTP %s", resp.status)
    except Exception as exc:
        logger.warning("Slack notification error (non-blocking): %s", exc)


def _send_email(subject: str, body: str) -> None:
    if not SENDGRID_API_KEY or not SENDGRID_ALERT_TO:
        return
    to_emails = [e.strip() for e in SENDGRID_ALERT_TO.split(",") if e.strip()]
    if not to_emails:
        return
    try:
        payload = json.dumps({
            "personalizations": [{"to": [{"email": e} for e in to_emails]}],
            "from": {"email": SENDGRID_FROM_EMAIL},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}],
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.sendgrid.com/v3/mail/send",
            data=payload,
            headers={
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status not in (200, 201, 202):
                logger.warning("SendGrid email failed: HTTP %s", resp.status)
    except Exception as exc:
        logger.warning("SendGrid email error (non-blocking): %s", exc)
