"""EDON Telegram Bot — two-way command interface for the founder.

Receives webhook updates from Telegram and responds with live data from
the gateway and agent outputs. Lets you control your agent team from
your phone.

Commands:
  /health     — live gateway health
  /brief      — latest Chief of Staff daily brief
  /followup   — who needs a follow-up today
  /compete    — latest competitor intelligence report
  /status     — all agents and their last run times
  /decisions  — last 10 decisions through the gateway
  /compliance — compliance health across all regulations
  /run <agent>— trigger an agent via GitHub Actions
  /help       — list all commands

Setup:
  1. Set TELEGRAM_BOT_TOKEN and TELEGRAM_OWNER_CHAT_ID in Fly.io secrets
  2. Register webhook: POST https://api.telegram.org/bot{token}/setWebhook
     {"url": "https://edon-gateway-prod.fly.dev/telegram/bot-webhook",
      "secret_token": "<TELEGRAM_WEBHOOK_SECRET>"}
  3. Set TELEGRAM_WEBHOOK_SECRET in Fly.io secrets
"""

from __future__ import annotations

import json
import os
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import requests as http_requests
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from ..persistence import get_db
from ..logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram-bot"])

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_OWNER_CHAT_ID = os.getenv("TELEGRAM_OWNER_CHAT_ID", "")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "EDONGOV/EDON")

AGENTS_DIR = Path(__file__).resolve().parents[3] / "agents"

# Agents that can be triggered via /run
TRIGGERABLE_AGENTS = {
    "qa": "nightly_qa.yml",
    "outbound": "outbound_agent.yml",
    "security": "security_monitor.yml",
    "brief": "chief_of_staff.yml",
    "compete": "competitor_monitor.yml",
    "followup": "followup_agent.yml",
    "account": "account_manager.yml",
    "regulatory": "regulatory_watcher.yml",
    "product": "product_intelligence.yml",
}


# ── Telegram API helpers ──────────────────────────────────────────────────────

def send_message(chat_id: str | int, text: str, parse_mode: str = "Markdown") -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set")
        return
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        try:
            http_requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": chunk, "parse_mode": parse_mode},
                timeout=10,
            ).raise_for_status()
        except Exception as exc:
            logger.error("Telegram send failed: %s", exc)


def is_owner(chat_id: int | str) -> bool:
    """Only respond to the owner's chat."""
    if not TELEGRAM_OWNER_CHAT_ID:
        return True  # If not set, allow all (dev mode)
    return str(chat_id) == str(TELEGRAM_OWNER_CHAT_ID)


# ── Data helpers ──────────────────────────────────────────────────────────────

def _load_agent_file(filename: str) -> Any:
    path = AGENTS_DIR / filename
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return None
    return None



# ── Command handlers ──────────────────────────────────────────────────────────

def handle_health(chat_id: int) -> None:
    from ..config import config
    try:
        db = get_db()
        with db._get_connection() as conn:
            conn.execute("SELECT 1")
        db_status = "✅ healthy"
    except Exception as exc:
        db_status = f"❌ {exc}"

    env = os.getenv("EDON_ENV", os.getenv("ENVIRONMENT", "unknown"))
    msg = (
        f"🟢 *EDON Gateway Health*\n"
        f"Database: {db_status}\n"
        f"Auth: {'enabled' if config.AUTH_ENABLED else 'disabled'}\n"
        f"Environment: {env}\n"
        f"Time: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    send_message(chat_id, msg)


def handle_brief(chat_id: int) -> None:
    brief = _load_agent_file("daily_brief_latest.json")
    if not brief:
        send_message(chat_id, "No brief available yet. Trigger one with `/run brief`")
        return

    status_emoji = {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(brief.get("overall_status", ""), "⚪")
    lines = [
        f"{status_emoji} *Daily Brief — {brief.get('date', 'Today')}*",
        f"_{brief.get('headline', '')}_\n",
    ]

    attention = brief.get("needs_attention_today", [])
    if attention:
        lines.append("*🎯 Needs attention:*")
        for item in attention[:3]:
            lines.append(f"• *{item.get('item', '')}* — {item.get('action', '')}")
        lines.append("")

    gw = brief.get("gateway", {})
    lines.append(f"*Gateway:* {gw.get('status', '?')} · {gw.get('decisions_24h', 0)} decisions")
    eng = brief.get("engineering", {})
    lines.append(f"*Engineering:* {eng.get('ci_status', '?')} · {eng.get('open_issues', 0)} issues")
    pipe = brief.get("pipeline", {})
    lines.append(f"*Pipeline:* {pipe.get('outbound_drafts_ready', 0)} drafts · {pipe.get('content_posts_ready', 0)} posts")

    note = brief.get("founder_note", "")
    if note:
        lines.append(f"\n📋 {note}")

    send_message(chat_id, "\n".join(lines))


def handle_followup(chat_id: int) -> None:
    tracker = _load_agent_file("followup_tracker.json")
    if not tracker:
        send_message(chat_id, "No prospects tracked yet.\nUse: `python -m agents.followup_agent --log-sent <slug>`")
        return

    today_str = datetime.now(UTC).strftime("%Y-%m-%d")
    due = []
    follow_up_schedule = [3, 7, 14]

    for slug, p in tracker.items():
        if p.get("status") in ("replied", "meeting_booked", "closed_won", "closed_lost"):
            continue
        last = p.get("last_contact", p.get("first_sent", today_str))
        count = p.get("follow_up_count", 0)
        if count >= len(follow_up_schedule):
            continue
        try:
            d = datetime.strptime(last, "%Y-%m-%d").replace(tzinfo=UTC)
            days = (datetime.now(UTC) - d).days
        except Exception:
            days = 0
        threshold = follow_up_schedule[count]
        if days >= threshold:
            due.append({"slug": slug, "company": p.get("company", slug),
                        "contact": p.get("contact", ""), "count": count,
                        "days": days, "threshold": threshold})

    total = len(tracker)
    by_status: dict[str, int] = {}
    for p in tracker.values():
        s = p.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1

    if not due:
        summary = " · ".join(f"{v} {k}" for k, v in by_status.items())
        send_message(chat_id, f"✅ *No follow-ups due today*\n_{total} prospects: {summary}_")
        return

    lines = [f"📬 *{len(due)} follow-up(s) due*\n"]
    for p in due[:8]:
        lines.append(
            f"• *{p['company']}* ({p['contact']})\n"
            f"  Follow-up #{p['count'] + 1} · {p['days']}d since last contact\n"
            f"  `/run followup` or `followup --followup {p['slug']}`"
        )
    summary = " · ".join(f"{v} {k}" for k, v in by_status.items())
    lines.append(f"\n_{total} total: {summary}_")
    send_message(chat_id, "\n".join(lines))


def handle_compete(chat_id: int) -> None:
    report = _load_agent_file("competitor_report_latest.json")
    if not report:
        send_message(chat_id, "No competitor report yet. Trigger one with `/run compete`")
        return

    threat_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(report.get("threat_level", "low"), "⚪")
    lines = [
        f"{threat_emoji} *Competitor Intel — {report.get('date', 'Latest')}*",
        f"_{report.get('headline', '')}_\n",
    ]

    biggest = report.get("biggest_threat", {})
    if biggest.get("competitor"):
        lines.append(f"⚠️ *{biggest['competitor']}:* {biggest.get('what_they_did', '')}")
        lines.append(f"Counter: _{biggest.get('how_to_counter', '')}_\n")

    for opp in report.get("opportunities", [])[:2]:
        lines.append(f"💡 {opp.get('opportunity', '')} → _{opp.get('action', '')}_")

    note = report.get("founder_note", "")
    if note:
        lines.append(f"\n📋 {note}")

    send_message(chat_id, "\n".join(lines))


def handle_decisions(chat_id: int) -> None:
    try:
        db = get_db()
        events = db.query_audit_events(limit=10)
        if not events:
            send_message(chat_id, "No decisions recorded yet.")
            return

        lines = ["📊 *Last 10 Decisions*\n"]
        for e in events:
            verdict = e.get("decision_verdict", "?")
            emoji = {"ALLOW": "✅", "BLOCK": "🚫", "ESCALATE": "⚠️"}.get(verdict, "❓")
            agent = (e.get("agent_id") or "?")[:20]
            tool = e.get("tool_name") or "?"
            ts = (e.get("timestamp") or "")[:16].replace("T", " ")
            lines.append(f"{emoji} `{agent}` · {tool} · {ts}")

        send_message(chat_id, "\n".join(lines))
    except Exception as exc:
        send_message(chat_id, f"❌ Failed to fetch decisions: {exc}")


def handle_compliance(chat_id: int) -> None:
    try:
        r = http_requests.get(
            f"{os.getenv('EDON_GATEWAY_URL', 'http://localhost:8080')}/compliance/health",
            headers={"X-EDON-TOKEN": os.getenv("EDON_API_TOKEN", "")},
            timeout=10,
        )
        data = r.json()
    except Exception as exc:
        send_message(chat_id, f"❌ Could not fetch compliance data: {exc}")
        return

    overall = data.get("overall", "?")
    emoji = "✅" if overall == "pass" else "❌"
    lines = [f"{emoji} *Compliance Health: {overall.upper()}*\n"]

    for reg, info in data.get("regulations", {}).items():
        status = info.get("status", "?")
        reg_emoji = "✅" if status == "pass" else "❌"
        active = info.get("rules_active", 0)
        required = info.get("rules_required", 0)
        lines.append(f"{reg_emoji} {reg}: {active}/{required} rules")

    send_message(chat_id, "\n".join(lines))


def handle_status(chat_id: int) -> None:
    lines = ["🤖 *Agent Status*\n"]

    agent_files = [
        ("Chief of Staff", "daily_brief_latest.json", "date"),
        ("Competitor Monitor", "competitor_report_latest.json", "date"),
        ("Follow-up Tracker", "followup_tracker.json", None),
        ("Incident Baseline", "incident_baseline.json", "last_updated"),
        ("Product Intelligence", "product_intelligence_report.json", "generated_at"),
    ]

    for name, filename, date_key in agent_files:
        path = AGENTS_DIR / filename
        if path.exists():
            try:
                data = json.loads(path.read_text())
                if date_key and isinstance(data, dict):
                    last_run = data.get(date_key, "unknown")[:10]
                elif isinstance(data, dict):
                    last_run = f"{len(data)} records"
                else:
                    last_run = "has data"
                lines.append(f"✅ {name}: {last_run}")
            except Exception:
                lines.append(f"⚠️ {name}: file exists but unreadable")
        else:
            lines.append(f"⭕ {name}: no data yet")

    lines.append(f"\nTriggerable: {', '.join(TRIGGERABLE_AGENTS.keys())}")
    lines.append("Use `/run <name>` to trigger any agent")
    send_message(chat_id, "\n".join(lines))


def handle_run(chat_id: int, agent_name: str) -> None:
    workflow = TRIGGERABLE_AGENTS.get(agent_name.lower())
    if not workflow:
        send_message(chat_id, f"Unknown agent: `{agent_name}`\nAvailable: {', '.join(TRIGGERABLE_AGENTS.keys())}")
        return

    if not GITHUB_TOKEN:
        send_message(chat_id, "❌ GITHUB_TOKEN not configured — cannot trigger workflows")
        return

    try:
        r = http_requests.post(
            f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{workflow}/dispatches",
            headers={
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json",
            },
            json={"ref": "master"},
            timeout=10,
        )
        if r.status_code == 204:
            send_message(chat_id, f"✅ *{agent_name}* triggered successfully.\nCheck progress: https://github.com/{GITHUB_REPO}/actions")
        else:
            send_message(chat_id, f"❌ Failed to trigger {agent_name}: {r.status_code} {r.text[:200]}")
    except Exception as exc:
        send_message(chat_id, f"❌ Error: {exc}")


def handle_jarvis(chat_id: int, question: str) -> None:
    """Ask Jarvis a natural language question. Uses live EDON data."""
    if not question.strip():
        send_message(chat_id, "Usage: `/jarvis <question>`\nExample: `/jarvis how many clients had blocks today?`")
        return

    send_message(chat_id, "🔍 Checking live data…")

    gateway_url = os.getenv("EDON_GATEWAY_URL", "http://localhost:8080")
    bootstrap_secret = os.getenv("EDON_BOOTSTRAP_SECRET", "")

    try:
        r = http_requests.post(
            f"{gateway_url}/v1/jarvis/ask",
            headers={
                "Content-Type": "application/json",
                "X-Bootstrap-Secret": bootstrap_secret,
            },
            json={"question": question},
            timeout=60,
        )
        r.raise_for_status()
        answer = r.json().get("answer", "No answer returned.")
        send_message(chat_id, answer)
    except Exception as exc:
        send_message(chat_id, f"❌ Jarvis error: {exc}")


def handle_voice_message(chat_id: int, file_id: str) -> None:
    """Download voice message, transcribe via Whisper, pass to Jarvis."""
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if not openai_key:
        send_message(chat_id, "🎙 Voice received but OPENAI_API_KEY not set — can't transcribe.\nType your question instead.")
        return

    if not TELEGRAM_BOT_TOKEN:
        return

    try:
        # Get file path from Telegram
        r = http_requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile",
            params={"file_id": file_id},
            timeout=10,
        )
        r.raise_for_status()
        file_path = r.json()["result"]["file_path"]

        # Download the OGG/voice file
        audio_r = http_requests.get(
            f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}",
            timeout=30,
        )
        audio_r.raise_for_status()
        audio_bytes = audio_r.content

        # Transcribe via Whisper
        send_message(chat_id, "🎙 Transcribing…")
        files = {"file": ("voice.ogg", audio_bytes, "audio/ogg")}
        data  = {"model": "whisper-1"}
        whisper_r = http_requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {openai_key}"},
            files=files,
            data=data,
            timeout=30,
        )
        whisper_r.raise_for_status()
        transcript = whisper_r.json().get("text", "").strip()

        if not transcript:
            send_message(chat_id, "❌ Couldn't transcribe — audio may be too short or unclear.")
            return

        send_message(chat_id, f"🎙 _{transcript}_")
        handle_jarvis(chat_id, transcript)

    except Exception as exc:
        logger.error("Voice message handling failed: %s", exc)
        send_message(chat_id, f"❌ Voice processing failed: {exc}")


def handle_help(chat_id: int) -> None:
    msg = """🤖 *EDON Command Centre*

*Information*
/health — gateway health check
/brief — today's Chief of Staff brief
/followup — prospects due for follow-up
/compete — latest competitor intelligence
/decisions — last 10 governance decisions
/compliance — compliance health status
/status — all agent last run times

*Jarvis (natural language)*
/jarvis <question> — ask anything about EDON
🎙 Send a voice message — auto-transcribed, passed to Jarvis

*Trigger agents*
/run brief — generate fresh daily brief
/run compete — run competitor scan
/run followup — check follow-ups
/run qa — run QA regression tests
/run ops — run ops health scan
/run security — run security scan
/run outbound — run outbound agent
/run account — run account manager
/run regulatory — run regulatory watcher
/run product — run product intelligence

_All agent runs take 1-3 minutes._"""
    send_message(chat_id, msg)


# ── Webhook endpoint ──────────────────────────────────────────────────────────

class TelegramUpdate(BaseModel):
    update_id: int
    message: dict | None = None
    callback_query: dict | None = None


@router.post("/bot-webhook")
async def telegram_webhook(request: Request) -> dict:
    # Verify webhook secret
    if TELEGRAM_WEBHOOK_SECRET:
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if secret != TELEGRAM_WEBHOOK_SECRET:
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    body = await request.json()
    message = body.get("message") or body.get("edited_message")
    if not message:
        return {"ok": True}

    chat_id = message.get("chat", {}).get("id")
    text = (message.get("text") or "").strip()

    if not chat_id:
        return {"ok": True}

    # Voice message — transcribe and pass to Jarvis
    voice = message.get("voice") or message.get("audio")
    if voice and not text:
        if not is_owner(chat_id):
            return {"ok": True}
        handle_voice_message(chat_id, voice["file_id"])
        return {"ok": True}

    if not text:
        return {"ok": True}

    # Owner-only
    if not is_owner(chat_id):
        logger.warning("Telegram message from unknown chat_id: %s", chat_id)
        return {"ok": True}

    logger.info("Telegram command from %s: %s", chat_id, text[:100])

    parts = text.split()
    cmd = parts[0].lower().lstrip("/")
    args = parts[1:] if len(parts) > 1 else []

    try:
        if cmd in ("health", "status_check"):
            handle_health(chat_id)
        elif cmd == "brief":
            handle_brief(chat_id)
        elif cmd == "followup":
            handle_followup(chat_id)
        elif cmd in ("compete", "competitors"):
            handle_compete(chat_id)
        elif cmd == "decisions":
            handle_decisions(chat_id)
        elif cmd == "compliance":
            handle_compliance(chat_id)
        elif cmd == "status":
            handle_status(chat_id)
        elif cmd == "run":
            agent = args[0] if args else ""
            if agent:
                handle_run(chat_id, agent)
            else:
                send_message(chat_id, "Usage: `/run <agent_name>`\nAvailable: " + ", ".join(TRIGGERABLE_AGENTS.keys()))
        elif cmd == "jarvis":
            question = " ".join(args) if args else ""
            handle_jarvis(chat_id, question)
        elif cmd in ("help", "start"):
            handle_help(chat_id)
        else:
            # Unknown command — send to Jarvis as a free-form question
            handle_jarvis(chat_id, text)
    except Exception as exc:
        logger.exception("Error handling Telegram command %s: %s", cmd, exc)
        send_message(chat_id, f"❌ Error processing `/{cmd}`: {exc}")

    return {"ok": True}
