"""Incident alerting routes — anomaly threshold rules + webhook delivery."""

import asyncio
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, Request

from ..persistence import get_db
from ..tenancy import get_request_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])

_VALID_METRICS = {"anomaly_score", "block_rate", "escalation_count"}
_VALID_OPERATORS = {"gt", "gte", "lt", "lte", "eq"}
_VALID_SEVERITIES = {"info", "warning", "critical"}


# ── Alert Rules ────────────────────────────────────────────────────────────────

@router.post("/rules")
async def create_alert_rule(request: Request):
    """Create an anomaly threshold alert rule.

    Body:
        name           (str, required)
        metric         (str, required) — 'anomaly_score' | 'block_rate' | 'escalation_count'
        operator       (str, required) — 'gt' | 'gte' | 'lt' | 'lte' | 'eq'
        threshold      (float, required)
        webhook_url    (str, required) — HTTPS endpoint to POST alert payload
        window_minutes (int, default 60) — rolling evaluation window
        severity       (str, default 'warning') — 'info' | 'warning' | 'critical'
    """
    body = await request.json()

    name = body.get("name", "").strip()
    metric = body.get("metric", "").strip()
    operator = body.get("operator", "").strip()
    threshold = body.get("threshold")
    webhook_url = body.get("webhook_url", "").strip()

    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if metric not in _VALID_METRICS:
        raise HTTPException(
            status_code=400,
            detail=f"metric must be one of: {sorted(_VALID_METRICS)}",
        )
    if operator not in _VALID_OPERATORS:
        raise HTTPException(
            status_code=400,
            detail=f"operator must be one of: {sorted(_VALID_OPERATORS)}",
        )
    if threshold is None:
        raise HTTPException(status_code=400, detail="threshold is required")
    if not webhook_url:
        raise HTTPException(status_code=400, detail="webhook_url is required")
    if not webhook_url.startswith("https://"):
        raise HTTPException(status_code=400, detail="webhook_url must use HTTPS")

    severity = body.get("severity", "warning")
    if severity not in _VALID_SEVERITIES:
        raise HTTPException(
            status_code=400,
            detail=f"severity must be one of: {sorted(_VALID_SEVERITIES)}",
        )
    window_minutes = int(body.get("window_minutes", 60))
    if window_minutes < 1 or window_minutes > 10080:
        raise HTTPException(status_code=400, detail="window_minutes must be 1–10080")

    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    rule_id = db.create_alert_rule(
        tenant_id=tenant_id,
        name=name,
        metric=metric,
        operator=operator,
        threshold=float(threshold),
        webhook_url=webhook_url,
        window_minutes=window_minutes,
        severity=severity,
    )
    return {
        "rule_id": rule_id,
        "name": name,
        "metric": metric,
        "operator": operator,
        "threshold": float(threshold),
        "webhook_url": webhook_url,
        "window_minutes": window_minutes,
        "severity": severity,
        "enabled": True,
    }


@router.get("/rules")
async def list_alert_rules(request: Request):
    """List all alert rules for this tenant."""
    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")
    rules = db.list_alert_rules(tenant_id)
    return {"rules": rules, "count": len(rules)}


@router.delete("/rules/{rule_id}")
async def delete_alert_rule(rule_id: str, request: Request):
    """Delete an alert rule."""
    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")
    deleted = db.delete_alert_rule(rule_id=rule_id, tenant_id=tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Alert rule not found: {rule_id}")
    return {"rule_id": rule_id, "deleted": True}


# ── Alert Incidents ────────────────────────────────────────────────────────────

@router.get("/incidents")
async def list_alert_incidents(
    request: Request,
    rule_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    """List fired alert incidents for this tenant."""
    db = get_db()
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")
    incidents = db.list_alert_incidents(tenant_id=tenant_id, rule_id=rule_id, limit=limit)
    return {"incidents": incidents, "count": len(incidents)}


# ── Alert Evaluation (called internally after each audit event) ────────────────

async def _deliver_webhook(
    incident_id: str,
    webhook_url: str,
    payload: dict,
    tenant_id: str,
    db,
    max_attempts: int = 3,
) -> None:
    """Fire-and-forget webhook delivery with retry."""
    for attempt in range(1, max_attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json", "X-EDON-Alert": "1"},
                )
            if resp.status_code < 300:
                db.update_alert_incident_webhook(incident_id, "delivered", attempt)
                logger.info(
                    "Alert webhook delivered: incident=%s tenant=%s attempt=%d",
                    incident_id, tenant_id, attempt,
                )
                return
            logger.warning(
                "Alert webhook HTTP %d: incident=%s attempt=%d",
                resp.status_code, incident_id, attempt,
            )
        except Exception as exc:
            logger.warning(
                "Alert webhook error: incident=%s attempt=%d error=%s",
                incident_id, attempt, exc,
            )
        if attempt < max_attempts:
            await asyncio.sleep(2 ** attempt)  # 2s, 4s backoff

    db.update_alert_incident_webhook(incident_id, "failed", max_attempts)
    logger.error("Alert webhook failed after %d attempts: incident=%s", max_attempts, incident_id)


async def evaluate_and_fire_alerts(tenant_id: str) -> None:
    """Evaluate all alert rules for tenant and fire webhooks for triggered rules.

    Called after each audit event is recorded. Non-blocking — exceptions are swallowed.
    """
    try:
        db = get_db()
        triggered = db.evaluate_alert_rules(tenant_id)
        for rule in triggered:
            payload = {
                "event": "edon.alert.triggered",
                "tenant_id": tenant_id,
                "rule_id": rule["id"],
                "rule_name": rule["name"],
                "severity": rule["severity"],
                "metric": rule["metric"],
                "operator": rule["operator"],
                "threshold": rule["threshold"],
                "observed_value": rule["observed_value"],
                "window_minutes": rule.get("window_minutes", 60),
            }
            incident_id = db.create_alert_incident(
                tenant_id=tenant_id,
                rule_id=rule["id"],
                rule_name=rule["name"],
                severity=rule["severity"],
                metric=rule["metric"],
                threshold=float(rule["threshold"]),
                observed_value=float(rule["observed_value"]),
                window_minutes=int(rule.get("window_minutes", 60)),
                webhook_url=rule["webhook_url"],
                payload=payload,
            )
            asyncio.create_task(
                _deliver_webhook(
                    incident_id=incident_id,
                    webhook_url=rule["webhook_url"],
                    payload=payload,
                    tenant_id=tenant_id,
                    db=db,
                )
            )
    except Exception as exc:
        logger.warning("Alert evaluation error for tenant %s: %s", tenant_id, exc)
