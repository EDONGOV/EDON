"""EDON Alert Dispatcher — fires notifications for critical events.

Handles:
  impact.confirmed_finding  — Engine C confirmed a red team scenario as a real finding
  impact.cycle_complete     — An Impact cycle finished with new confirmed findings
  healing.rule_deployed     — Self-healing deployed a new governance rule
  healing.states_mitigated  — Self-healing mitigated one or more failure states
  gateway.crash_recovered   — Gateway restarted after an unexpected crash
  self_govern.blocked       — An internal EDON agent was blocked by governance

Channels (all fail-open, all configurable via env):
  Webhook (Slack / PagerDuty / custom):  EDON_ALERT_WEBHOOK_URL
  Telegram:                              EDON_ALERT_TELEGRAM_BOT_TOKEN + EDON_ALERT_TELEGRAM_CHAT_ID
  Both channels fire in parallel daemon threads — a failure in one never blocks the other.
"""

from __future__ import annotations

import collections
import hashlib
import hmac
import json
import os
import threading
from datetime import datetime, UTC
from typing import Any, Optional

import requests

from ..logging_config import get_logger

logger = get_logger(__name__)

# ── In-memory alert log (last 200 events, thread-safe) ────────────────────────
_alert_log: collections.deque = collections.deque(maxlen=200)
_alert_log_lock = threading.Lock()


def get_recent_alerts(limit: int = 50) -> list[dict]:
    """Return the most recent fired alerts, newest first. Falls back to DB if in-memory log is empty."""
    with _alert_log_lock:
        items = list(_alert_log)
    if items:
        items.reverse()
        return items[:limit]
    # In-memory log empty (fresh boot) — read from DB
    try:
        from ..persistence import get_db
        db = get_db()
        with db._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alert_history (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    event     TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    payload   TEXT NOT NULL DEFAULT '{}'
                )
            """)
            rows = conn.execute(
                "SELECT event, timestamp, payload FROM alert_history ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [{"event": r["event"], "timestamp": r["timestamp"],
                 "payload": json.loads(r["payload"] or "{}")} for r in rows]
    except Exception:
        return []

_WEBHOOK_URL    = os.getenv("EDON_ALERT_WEBHOOK_URL", "").strip()
_WEBHOOK_SECRET = os.getenv("EDON_ALERT_WEBHOOK_SECRET", "").strip()
_TIMEOUT        = float(os.getenv("EDON_ALERT_TIMEOUT_SEC", "5"))

# Telegram channel — uses same bot token as the gateway Telegram integration
# Falls back to TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID for backwards compat
_TG_BOT  = (os.getenv("EDON_ALERT_TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
_TG_CHAT = (os.getenv("EDON_ALERT_TELEGRAM_CHAT_ID")  or os.getenv("TELEGRAM_CHAT_ID",    "")).strip()

# Severity → Telegram emoji
_SEVERITY_EMOJI = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}


def _telegram_message(event: str, payload: dict[str, Any]) -> str:
    """Build a concise Telegram message for an alert event."""
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    tenant = payload.get("tenant_id", "global")

    if event == "impact.confirmed_finding":
        sev = payload.get("severity_label", "unknown")
        emoji = _SEVERITY_EMOJI.get(sev, "⚠️")
        return (
            f"{emoji} *EDON — New Finding Confirmed*\n\n"
            f"*{payload.get('title', 'Unknown')}*\n"
            f"Severity: `{sev}` ({payload.get('severity_score', '?')})\n"
            f"Class: `{payload.get('vulnerability_class', '?')}`\n"
            f"Tenant: `{tenant}`\n"
            f"Finding: `{payload.get('failure_state_id', '?')}`\n\n"
            f"Action: Review at /impact and apply hardening rule.\n"
            f"_{ts}_"
        )
    if event == "impact.cycle_complete":
        return (
            f"🔵 *EDON — Impact Cycle Complete*\n\n"
            f"New findings: `{payload.get('confirmed_findings', 0)}`\n"
            f"Total failure states: `{payload.get('failure_states_found', 0)}`\n"
            f"Coverage: `{payload.get('coverage_pct', 0)}%`\n"
            f"Cycle: `#{payload.get('cycle_number', '?')}`\n"
            f"Tenant: `{tenant}`\n"
            f"_{ts}_"
        )
    if event == "healing.rule_deployed":
        return (
            f"✅ *EDON — Self-Healing: Rule Deployed*\n\n"
            f"Rule: `{payload.get('rule_name', '?')}`\n"
            f"Action: `{payload.get('action', '?')}` on `{payload.get('tool', '?')}.{payload.get('op', '?')}`\n"
            f"Tenant: `{tenant}`\n"
            f"States mitigated: `{payload.get('states_mitigated', 0)}`\n"
            f"_{ts}_"
        )
    if event == "healing.states_mitigated":
        return (
            f"🛡️ *EDON — Self-Healing: States Mitigated*\n\n"
            f"Mitigated: `{payload.get('count', 0)}` failure state(s)\n"
            f"Tenant: `{tenant}`\n"
            f"_{ts}_"
        )
    if event == "gateway.crash_recovered":
        return (
            f"🔄 *EDON — Gateway Restarted*\n\n"
            f"The gateway recovered from an unexpected restart.\n"
            f"All loops restarted automatically.\n"
            f"_{ts}_"
        )
    if event == "self_govern.blocked":
        return (
            f"🚫 *EDON — Internal Agent Blocked*\n\n"
            f"Agent: `{payload.get('agent_id', '?')}`\n"
            f"Action: `{payload.get('action_type', '?')}`\n"
            f"Reason: {payload.get('reason', '?')}\n"
            f"_{ts}_"
        )
    if event == "physical.comm_loss":
        return (
            f"📡 *EDON — Robot Communication Loss*\n\n"
            f"Robot: `{payload.get('robot_id', '?')}`\n"
            f"Tenant: `{tenant}`\n"
            f"TTL: `{payload.get('ttl_s', '?')}s`\n"
            f"Fail-safe posture: `{payload.get('comm_loss_posture', '?')}`\n"
            f"E-stop: TRIGGERED\n"
            f"_{ts}_"
        )
    if event == "physical.execution_anomaly":
        return (
            f"⚠️ *EDON — Execution Anomaly Detected*\n\n"
            f"Robot: `{payload.get('robot_id', '?')}`\n"
            f"Action: `{payload.get('action_id', '?')}`\n"
            f"Tenant: `{tenant}`\n"
            f"Reason: {payload.get('reason', '?')}\n"
            f"E-stop: TRIGGERED\n"
            f"_{ts}_"
        )
    if event == "physical.force_violation":
        return (
            f"🦾 *EDON — ISO 15066 Force Violation*\n\n"
            f"Robot: `{payload.get('robot_id', '?')}`\n"
            f"Tenant: `{tenant}`\n"
            f"Violation: {payload.get('violation', '?')}\n"
            f"Action: BLOCKED\n"
            f"_{ts}_"
        )
    if event == "healing.canary_rollback":
        block_pct = round(payload.get("block_rate", 0) * 100, 1)
        base_pct  = round(payload.get("baseline", 0) * 100, 1)
        return (
            f"🔁 *EDON — Canary Rollback*\n\n"
            f"Rule: `{payload.get('rule_id', '?')}`\n"
            f"Tenant: `{tenant}`\n"
            f"Block rate: `{block_pct}%` (baseline `{base_pct}%`)\n"
            f"Samples: `{payload.get('samples', '?')}`\n"
            f"Rule has been *disabled* automatically.\n"
            f"_{ts}_"
        )
    # Generic fallback
    return (
        f"⚠️ *EDON Alert: {event}*\n\n"
        + "\n".join(f"`{k}`: {str(v)[:120]}" for k, v in payload.items())
        + f"\n_{ts}_"
    )


def _send_telegram(event: str, payload: dict[str, Any]) -> None:
    """Send a Telegram message. Fail-open."""
    if not _TG_BOT or not _TG_CHAT:
        return
    try:
        msg = _telegram_message(event, payload)
        requests.post(
            f"https://api.telegram.org/bot{_TG_BOT}/sendMessage",
            json={"chat_id": _TG_CHAT, "text": msg, "parse_mode": "Markdown"},
            timeout=_TIMEOUT,
        )
        logger.debug("[alerts/telegram] sent event=%s", event)
    except Exception as exc:
        logger.warning("[alerts/telegram] failed for event=%s: %s", event, exc)


def _sign(payload_bytes: bytes) -> Optional[str]:
    if not _WEBHOOK_SECRET:
        return None
    sig = hmac.new(_WEBHOOK_SECRET.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def _dispatch(event: str, payload: dict[str, Any]) -> None:
    """Fire all alert channels in parallel daemon threads. Always fail-open."""
    now = datetime.now(UTC).isoformat()
    body = {
        "event": event,
        "timestamp": now,
        "payload": payload,
    }
    entry = {"event": event, "timestamp": now, "payload": payload}
    with _alert_log_lock:
        _alert_log.append(entry)

    def _persist_to_db() -> None:
        try:
            from ..persistence import get_db
            db = get_db()
            with db._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS alert_history (
                        id        INTEGER PRIMARY KEY AUTOINCREMENT,
                        event     TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        payload   TEXT NOT NULL DEFAULT '{}'
                    )
                """)
                conn.execute(
                    "INSERT INTO alert_history (event, timestamp, payload) VALUES (?, ?, ?)",
                    (event, now, json.dumps(payload)),
                )
                conn.commit()
        except Exception as exc:
            logger.debug("[alerts] DB persist failed (non-blocking): %s", exc)

    threading.Thread(target=_persist_to_db, daemon=True, name=f"alert-db-{event}").start()

    def _send_webhook() -> None:
        if not _WEBHOOK_URL:
            return
        try:
            raw = json.dumps(body).encode()
            headers: dict[str, str] = {"Content-Type": "application/json"}
            sig = _sign(raw)
            if sig:
                headers["X-EDON-Signature"] = sig

            if "hooks.slack.com" in _WEBHOOK_URL or "slack.com/services" in _WEBHOOK_URL:
                slack_body = {
                    "text": f"*EDON Alert: {event}*",
                    "attachments": [{
                        "color": "#ff4444" if "finding" in event else "#36a64f",
                        "fields": [
                            {"title": k, "value": str(v)[:200], "short": True}
                            for k, v in payload.items()
                            if k not in ("attack_steps", "remediation_steps")
                        ],
                        "footer": f"EDON · {body['timestamp']}",
                    }],
                }
                requests.post(_WEBHOOK_URL, json=slack_body, headers={"Content-Type": "application/json"}, timeout=_TIMEOUT)
            else:
                requests.post(_WEBHOOK_URL, data=raw, headers=headers, timeout=_TIMEOUT)
            logger.debug("[alerts/webhook] dispatched event=%s", event)
        except Exception as exc:
            logger.warning("[alerts/webhook] failed for event=%s: %s", event, exc)

    threading.Thread(target=_send_webhook, daemon=True, name=f"alert-wh-{event}").start()
    threading.Thread(target=_send_telegram, args=(event, payload), daemon=True, name=f"alert-tg-{event}").start()


# ── Public API ─────────────────────────────────────────────────────────────────

def fire_impact_alert(
    *,
    scenario_id: str,
    failure_state_id: str,
    vulnerability_class: str,
    severity_score: float,
    title: str,
    tenant_id: Optional[str] = None,
    attack_steps: Optional[list[str]] = None,
) -> None:
    """Fire an alert when Engine C confirms a red team scenario as a real finding.

    Called from impact/validator.py after vr.status == "valid".
    Fail-open: never raises.
    """
    _dispatch("impact.confirmed_finding", {
        "scenario_id": scenario_id[:16] + "…",
        "failure_state_id": failure_state_id[:16] + "…",
        "vulnerability_class": vulnerability_class,
        "severity_score": round(severity_score, 3),
        "severity_label": _severity_label(severity_score),
        "title": title,
        "tenant_id": tenant_id or "global",
        "attack_step_count": len(attack_steps or []),
        "action_required": "Review at /impact and apply recommended hardening rule.",
    })


def fire_cycle_alert(
    *,
    confirmed_findings: int,
    failure_states_found: int,
    coverage_pct: float,
    cycle_number: int,
    tenant_id: Optional[str] = None,
) -> None:
    """Fire an alert after an Impact cycle that produced new confirmed findings.

    Called from impact/loop.py after each completed cycle with findings > 0.
    Fail-open: never raises.
    """
    _dispatch("impact.cycle_complete", {
        "confirmed_findings": confirmed_findings,
        "failure_states_found": failure_states_found,
        "coverage_pct": round(coverage_pct, 1),
        "cycle_number": cycle_number,
        "tenant_id": tenant_id or "global",
    })


def fire_healing_alert(
    *,
    tenant_id: Optional[str] = None,
    rule_name: str,
    action: str,
    tool: Optional[str] = None,
    op: Optional[str] = None,
    states_mitigated: int = 0,
) -> None:
    """Fire when self-healing deploys a new governance rule."""
    _dispatch("healing.rule_deployed", {
        "rule_name": rule_name,
        "action": action,
        "tool": tool or "any",
        "op": op or "any",
        "states_mitigated": states_mitigated,
        "tenant_id": tenant_id or "global",
    })


def fire_gateway_recovery_alert() -> None:
    """Fire on gateway startup to signal a recovered crash (vs. normal cold start)."""
    _dispatch("gateway.crash_recovered", {
        "message": "EDON Gateway restarted — all background loops re-initialized",
    })


def fire_self_govern_block_alert(
    *,
    agent_id: str,
    action_type: str,
    reason: str,
    tenant_id: Optional[str] = None,
) -> None:
    """Fire when an internal EDON agent is blocked by self-governance."""
    _dispatch("self_govern.blocked", {
        "agent_id": agent_id,
        "action_type": action_type,
        "reason": reason,
        "tenant_id": tenant_id or "internal",
    })


def _severity_label(score: float) -> str:
    if score >= 0.75: return "critical"
    if score >= 0.50: return "high"
    if score >= 0.25: return "medium"
    return "low"
