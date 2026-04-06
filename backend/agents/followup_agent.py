"""EDON Follow-up Agent — tracks prospects and reminds you when to follow up.

Reads your outbound drafts, maintains a follow-up tracker, generates follow-up
emails when prospects go cold, and sends you a Telegram reminder every morning
with who needs a nudge today.

Tracker file: agents/followup_tracker.json
  {
    "prospect_slug": {
      "company": "Acme Health",
      "contact": "Jane Smith",
      "email": "jane@acmehealth.com",
      "first_sent": "2026-04-05",
      "last_contact": "2026-04-05",
      "follow_up_due": "2026-04-08",
      "status": "sent | replied | meeting_booked | no_response | closed_won | closed_lost",
      "notes": "...",
      "follow_up_count": 0,
      "thread": []   # list of {date, type: sent|reply|note, content}
    }
  }

Usage:
    # Log that you sent the initial email to a prospect
    python -m agents.followup_agent --log-sent <slug>

    # Update status after a reply
    python -m agents.followup_agent --update <slug> --status replied --note "Interested, wants a demo"

    # Generate a follow-up email for a prospect
    python -m agents.followup_agent --followup <slug>

    # Check who needs follow-up today (also runs automatically daily)
    python -m agents.followup_agent --check

    # List all prospects and their status
    python -m agents.followup_agent --list

GitHub Actions: .github/workflows/followup_agent.yml — runs daily at 8am UTC.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, UTC, timedelta
from pathlib import Path
from typing import Any

import requests
import anthropic

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

AGENTS_DIR = Path(__file__).parent
TRACKER_FILE = AGENTS_DIR / "followup_tracker.json"
OUTBOUND_DIR = AGENTS_DIR / "outbound_drafts"

# Days before first follow-up, second follow-up, give up
FOLLOW_UP_SCHEDULE = [3, 7, 14]  # days after last contact

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ── Tracker helpers ───────────────────────────────────────────────────────────

def load_tracker() -> dict[str, Any]:
    if TRACKER_FILE.exists():
        try:
            return json.loads(TRACKER_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_tracker(tracker: dict[str, Any]) -> None:
    TRACKER_FILE.write_text(json.dumps(tracker, indent=2))


def today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def days_since(date_str: str) -> int:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
        return (datetime.now(UTC) - d).days
    except Exception:
        return 0


def due_follow_ups(tracker: dict[str, Any]) -> list[dict[str, Any]]:
    due = []
    for slug, p in tracker.items():
        if p.get("status") in ("replied", "meeting_booked", "closed_won", "closed_lost"):
            continue
        last = p.get("last_contact", p.get("first_sent", today()))
        count = p.get("follow_up_count", 0)
        if count >= len(FOLLOW_UP_SCHEDULE):
            continue
        threshold = FOLLOW_UP_SCHEDULE[count]
        if days_since(last) >= threshold:
            due.append({"slug": slug, **p, "days_overdue": days_since(last) - threshold})
    return sorted(due, key=lambda x: x.get("days_overdue", 0), reverse=True)


# ── Telegram ──────────────────────────────────────────────────────────────────

def send_telegram(message: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("No Telegram config — printing to console only")
        return
    try:
        chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
        for chunk in chunks:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": chunk, "parse_mode": "Markdown"},
                timeout=10,
            )
            r.raise_for_status()
    except Exception as exc:
        print(f"Telegram failed: {exc}")


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_log_sent(slug: str) -> None:
    """Log that you sent the initial outbound email to a prospect."""
    tracker = load_tracker()

    # Try to load context from outbound draft
    draft_path = OUTBOUND_DIR / f"{slug}.md"
    company = slug.replace("-", " ").title()
    contact = ""
    email = ""

    if draft_path.exists():
        content = draft_path.read_text(encoding="utf-8")
        # Parse frontmatter if present
        for line in content.splitlines()[:10]:
            if line.startswith("company:"):
                company = line.split(":", 1)[1].strip()
            elif line.startswith("contact:"):
                contact = line.split(":", 1)[1].strip()
            elif line.startswith("email:"):
                email = line.split(":", 1)[1].strip()

    now = today()
    tracker[slug] = {
        "company": company,
        "contact": contact,
        "email": email,
        "first_sent": now,
        "last_contact": now,
        "follow_up_due": (datetime.now(UTC) + timedelta(days=FOLLOW_UP_SCHEDULE[0])).strftime("%Y-%m-%d"),
        "status": "sent",
        "notes": "",
        "follow_up_count": 0,
        "thread": [{"date": now, "type": "sent", "content": "Initial outbound email sent"}],
    }
    save_tracker(tracker)
    print(f"✓ Logged: {company} — follow-up due in {FOLLOW_UP_SCHEDULE[0]} days")


def cmd_update(slug: str, status: str, note: str) -> None:
    """Update a prospect's status."""
    tracker = load_tracker()
    if slug not in tracker:
        print(f"Prospect '{slug}' not found. Run --log-sent first.")
        sys.exit(1)

    now = today()
    tracker[slug]["status"] = status
    tracker[slug]["last_contact"] = now
    if note:
        tracker[slug]["notes"] = note
        tracker[slug]["thread"].append({"date": now, "type": "note", "content": note})

    save_tracker(tracker)
    print(f"✓ Updated {tracker[slug]['company']}: {status}")
    if note:
        print(f"  Note: {note}")


def cmd_followup(slug: str) -> None:
    """Generate a follow-up email for a specific prospect."""
    tracker = load_tracker()
    if slug not in tracker:
        print(f"Prospect '{slug}' not found.")
        sys.exit(1)

    p = tracker[slug]
    count = p.get("follow_up_count", 0) + 1

    # Load original outbound draft for context
    draft_path = OUTBOUND_DIR / f"{slug}.md"
    original_email = draft_path.read_text(encoding="utf-8") if draft_path.exists() else ""

    prompt = f"""You are writing a follow-up email for EDON, an AI governance platform for healthtech.

Prospect: {p.get('company')} — {p.get('contact')} ({p.get('email')})
Days since last contact: {days_since(p.get('last_contact', today()))}
Follow-up number: {count}
Status: {p.get('status')}
Notes: {p.get('notes', 'None')}

Original email sent:
{original_email[:1000] if original_email else 'Not available'}

Thread history:
{json.dumps(p.get('thread', []), indent=2)}

Write a {('short, casual' if count == 1 else 'brief, direct')} follow-up email.
- Follow-up {count}: {'gentle check-in, add one new insight or value point' if count == 1 else 'direct ask for 15 min call or a no'}
- Don't be pushy or repeat the entire pitch
- Reference something specific about their company or the healthcare AI regulation landscape
- End with a clear, easy call to action

Return JSON:
{{
  "subject": "...",
  "body": "...",
  "suggested_send_time": "morning | afternoon",
  "confidence": "high | medium | low"
}}"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = str(getattr(msg.content[0], "text", msg.content[0]))
    start = raw.find("{")
    end = raw.rfind("}") + 1
    result = json.loads(raw[start:end]) if start != -1 else {"error": raw}

    # Save follow-up draft
    output_dir = OUTBOUND_DIR / "followups"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{slug}_followup_{count}.md"
    output_path.write_text(
        f"---\ncompany: {p.get('company')}\ncontact: {p.get('contact')}\nfollow_up: {count}\ndate: {today()}\n---\n\n"
        f"Subject: {result.get('subject', '')}\n\n{result.get('body', '')}"
    )

    print(f"\n{'='*50}")
    print(f"Follow-up #{count} for {p.get('company')}")
    print(f"{'='*50}")
    print(f"Subject: {result.get('subject', '')}")
    print(f"\n{result.get('body', '')}")
    print(f"\nSaved to: {output_path}")

    # Update tracker
    tracker[slug]["follow_up_count"] = count
    tracker[slug]["last_contact"] = today()
    tracker[slug]["thread"].append({
        "date": today(),
        "type": "sent",
        "content": f"Follow-up #{count}: {result.get('subject', '')}",
    })
    save_tracker(tracker)


def cmd_check() -> None:
    """Check who needs follow-up today and send Telegram reminder."""
    tracker = load_tracker()
    due = due_follow_ups(tracker)

    # Stats
    total = len(tracker)
    by_status: dict[str, int] = {}
    for p in tracker.values():
        s = p.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1

    print(f"\nFollow-up tracker — {today()}")
    print(f"Total prospects: {total}")
    print(f"Status breakdown: {by_status}")
    print(f"Due today: {len(due)}")

    if not due:
        msg = f"✅ *Follow-up Tracker — {today()}*\nNo follow-ups due today.\n_{total} prospects tracked: {', '.join(f'{v} {k}' for k, v in by_status.items())}_"
        send_telegram(msg)
        return

    lines = [f"📬 *Follow-up Tracker — {today()}*", f"_{len(due)} follow-up(s) due today_\n"]
    for p in due[:10]:
        overdue = p.get("days_overdue", 0)
        lines.append(
            f"• *{p.get('company')}* ({p.get('contact', 'Unknown')})\n"
            f"  Follow-up #{p.get('follow_up_count', 0) + 1} · "
            f"{'⚠️ ' + str(overdue) + 'd overdue' if overdue > 0 else 'due today'}\n"
            f"  Run: `python -m agents.followup_agent --followup {p.get('slug')}`"
        )

    lines.append(f"\n_{total} total · {by_status.get('sent', 0)} sent · {by_status.get('replied', 0)} replied · {by_status.get('meeting_booked', 0)} meetings_")
    send_telegram("\n".join(lines))
    print("\n".join(lines))


def cmd_list() -> None:
    """List all prospects and their status."""
    tracker = load_tracker()
    if not tracker:
        print("No prospects tracked yet. Use --log-sent <slug> to add one.")
        return

    print(f"\n{'Slug':<30} {'Company':<25} {'Status':<15} {'Last Contact':<15} {'Follow-ups'}")
    print("-" * 100)
    for slug, p in sorted(tracker.items(), key=lambda x: x[1].get("last_contact", ""), reverse=True):
        print(f"{slug:<30} {p.get('company', ''):<25} {p.get('status', ''):<15} {p.get('last_contact', ''):<15} {p.get('follow_up_count', 0)}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="EDON Follow-up Agent")
    parser.add_argument("--log-sent", metavar="SLUG", help="Log that initial email was sent to prospect")
    parser.add_argument("--update", metavar="SLUG", help="Update prospect status")
    parser.add_argument("--status", default="replied", help="New status for --update")
    parser.add_argument("--note", default="", help="Note for --update")
    parser.add_argument("--followup", metavar="SLUG", help="Generate follow-up email for prospect")
    parser.add_argument("--check", action="store_true", help="Check due follow-ups and notify via Telegram")
    parser.add_argument("--list", action="store_true", help="List all prospects")
    args = parser.parse_args()

    if args.log_sent:
        cmd_log_sent(args.log_sent)
    elif args.update:
        cmd_update(args.update, args.status, args.note)
    elif args.followup:
        cmd_followup(args.followup)
    elif args.list:
        cmd_list()
    else:
        # Default: check (runs daily in CI)
        cmd_check()


if __name__ == "__main__":
    main()
