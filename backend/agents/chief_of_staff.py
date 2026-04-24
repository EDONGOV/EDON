"""EDON Chief of Staff — daily unified briefing across all agents and systems.

Collects data from every agent's output, pulls live gateway metrics, checks GitHub,
and synthesises everything into one structured daily brief delivered to you.

Covers:
  - Gateway health + compliance status
  - Incident baseline (what happened overnight)
  - Security monitor findings
  - Account manager health across all tenants
  - Ops pain points and priorities
  - Product intelligence insights
  - Content pipeline status
  - Outbound pipeline (drafts ready for review)
  - Regulatory gaps
  - CI/CD status
  - What needs your attention TODAY

Usage:
    ANTHROPIC_API_KEY=xxx EDON_API_TOKEN=xxx GITHUB_TOKEN=xxx \\
      BRIEFING_WEBHOOK_URL=https://hooks.slack.com/... \\
      python -m agents.chief_of_staff

GitHub Actions: .github/workflows/chief_of_staff.yml — runs daily at 7:30am UTC.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import requests
import anthropic

from .self_govern import gov_check

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GATEWAY_URL = os.environ.get("EDON_GATEWAY_URL", "https://edon-gateway-prod.fly.dev").rstrip("/")
API_TOKEN = os.environ.get("EDON_API_TOKEN", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "EDONGOV/EDON")
ADMIN_TENANT_ID = os.environ.get("EDON_ADMIN_TENANT_ID", "tenant_dev")
BRIEFING_WEBHOOK_URL = os.environ.get("BRIEFING_WEBHOOK_URL", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

AGENTS_DIR = Path(__file__).parent
REPO_ROOT = Path(__file__).resolve().parents[2]

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _headers() -> dict[str, str]:
    h = {"Content-Type": "application/json", "X-Tenant-ID": ADMIN_TENANT_ID}
    if API_TOKEN:
        h["X-EDON-TOKEN"] = API_TOKEN
    return h


def _fetch(path: str, params: dict | None = None) -> Any:
    try:
        r = requests.get(f"{GATEWAY_URL}{path}", headers=_headers(), params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        return {"error": str(exc)}


def _load_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return None
    return None



# ── Data collection ───────────────────────────────────────────────────────────

def collect_gateway_data() -> dict[str, Any]:
    print("Collecting gateway data…")
    health = _fetch("/health")
    compliance = _fetch("/compliance/health")
    timeseries = _fetch("/timeseries", {"days": 7})
    block_reasons = _fetch("/block-reasons", {"days": 7})
    recent_decisions = _fetch("/audit/query", {"limit": 50})
    agents = _fetch("/agents")

    # Compute 24h totals from timeseries
    totals = {"allowed": 0, "blocked": 0, "confirm": 0}
    if isinstance(timeseries, list) and timeseries:
        last_point = timeseries[-1]
        if isinstance(last_point, dict):
            totals = {
                "allowed": last_point.get("allowed", 0),
                "blocked": last_point.get("blocked", 0),
                "confirm": last_point.get("confirm", 0),
            }

    return {
        "health": health,
        "compliance": compliance,
        "timeseries_7d": timeseries,
        "block_reasons": block_reasons,
        "recent_decisions_count": recent_decisions.get("count", 0) if isinstance(recent_decisions, dict) else 0,
        "last_24h": totals,
        "agents": agents,
    }


def collect_agent_outputs() -> dict[str, Any]:
    print("Collecting agent outputs…")
    outputs: dict[str, Any] = {}

    # Incident baseline
    baseline = _load_json(AGENTS_DIR / "incident_baseline.json")
    if baseline:
        outputs["incident_baseline"] = baseline

    # Product intelligence report
    pi_report = _load_json(AGENTS_DIR / "product_intelligence_report.json")
    if pi_report:
        outputs["product_intelligence"] = pi_report

    # Account manager memory (all tenants)
    am_dir = AGENTS_DIR / "am_memory"
    if am_dir.exists():
        tenant_summaries = []
        for f in am_dir.glob("*.json"):
            mem = _load_json(f)
            if mem and isinstance(mem, dict):
                tenant_summaries.append({
                    "tenant_id": f.stem,
                    "company": mem.get("company_name", f.stem),
                    "health_score": mem.get("health_score"),
                    "open_items": mem.get("open_items", []),
                    "last_updated": mem.get("last_updated"),
                })
        outputs["account_health"] = tenant_summaries

    # Content topics queue
    content_topics = _load_json(AGENTS_DIR / "content_topics.json")
    if content_topics:
        outputs["content_queue"] = content_topics

    # Outbound drafts (count + titles)
    outbound_dir = AGENTS_DIR / "outbound_drafts"
    if outbound_dir.exists():
        drafts = list(outbound_dir.glob("*.md"))
        outputs["outbound_drafts"] = {
            "count": len(drafts),
            "ready_for_review": [f.stem for f in drafts[max(0, len(drafts)-5):]],
        }

    # SDK examples generated
    sdk_dir = REPO_ROOT / "sdk" / "examples"
    if sdk_dir.exists():
        examples = list(sdk_dir.rglob("*.*"))
        outputs["sdk_examples"] = len(examples)

    return outputs


def collect_github_data() -> dict[str, Any]:
    print("Collecting GitHub data…")
    if not GITHUB_TOKEN:
        return {"error": "No GITHUB_TOKEN"}

    gh_headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    def gh_get(path: str) -> Any:
        try:
            r = requests.get(f"https://api.github.com/repos/{GITHUB_REPO}{path}",
                             headers=gh_headers, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            return {"error": str(exc)}

    # Recent CI runs
    runs_data = gh_get("/actions/runs?per_page=10")
    runs = []
    if isinstance(runs_data, dict) and "workflow_runs" in runs_data:
        for r in runs_data["workflow_runs"][:10]:
            runs.append({
                "name": r.get("name"),
                "status": r.get("status"),
                "conclusion": r.get("conclusion"),
                "created_at": r.get("created_at"),
            })

    # Open issues
    issues_data = gh_get("/issues?state=open&per_page=20")
    issues = []
    if isinstance(issues_data, list):
        for issue in issues_data:
            issues.append({
                "number": issue.get("number"),
                "title": issue.get("title"),
                "labels": [l.get("name") for l in issue.get("labels", [])],
                "created_at": issue.get("created_at"),
            })

    return {
        "recent_ci_runs": runs,
        "open_issues": issues,
        "open_issues_count": len(issues),
    }


# ── Brief generation ──────────────────────────────────────────────────────────

def generate_brief(
    gateway: dict[str, Any],
    agent_outputs: dict[str, Any],
    github: dict[str, Any],
    today: str,
) -> dict[str, Any]:
    print("Generating brief with Claude Opus…")

    context = f"""You are the Chief of Staff for EDON, an AI governance SaaS for healthtech.
The founder (1 person) needs a complete daily briefing on everything that happened across the business.
Today is {today}.

=== GATEWAY STATUS ===
{json.dumps(gateway, indent=2)}

=== AGENT OUTPUTS (from all 15 AI agents) ===
{json.dumps(agent_outputs, indent=2)}

=== GITHUB / CI STATUS ===
{json.dumps(github, indent=2)}

Generate a structured daily brief. Return ONLY valid JSON with this exact structure:
{{
  "date": "{today}",
  "headline": "One sentence summary of the day",
  "overall_status": "green | yellow | red",
  "needs_attention_today": [
    {{"priority": 1, "item": "...", "why": "...", "action": "..."}}
  ],
  "gateway": {{
    "status": "...",
    "uptime": "...",
    "decisions_24h": 0,
    "compliance_status": "...",
    "notable": "..."
  }},
  "security": {{
    "status": "...",
    "alerts": [],
    "summary": "..."
  }},
  "customers": {{
    "total_tenants": 0,
    "health_summary": "...",
    "at_risk": [],
    "highlights": []
  }},
  "pipeline": {{
    "outbound_drafts_ready": 0,
    "content_posts_ready": 0,
    "sdk_examples": 0,
    "summary": "..."
  }},
  "engineering": {{
    "ci_status": "...",
    "open_issues": 0,
    "critical_issues": [],
    "summary": "..."
  }},
  "product": {{
    "top_insights": [],
    "upsell_opportunities": [],
    "summary": "..."
  }},
  "whats_working": ["..."],
  "what_needs_fixing": ["..."],
  "founder_note": "A direct, honest 2-3 sentence note from your Chief of Staff about where things really stand today and what the founder should focus on."
}}"""

    msg = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": context}],
    )

    raw = str(getattr(msg.content[0], "text", msg.content[0]))

    # Extract JSON
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        return {"error": "Failed to parse brief", "raw": raw}

    try:
        return json.loads(raw[start:end])
    except json.JSONDecodeError:
        return {"error": "Invalid JSON in response", "raw": raw}


# ── Delivery ──────────────────────────────────────────────────────────────────

def format_for_webhook(brief: dict[str, Any]) -> str:
    status_emoji = {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(
        brief.get("overall_status", ""), "⚪"
    )
    lines = [
        f"{status_emoji} **EDON Daily Brief — {brief.get('date', 'Today')}**",
        f"_{brief.get('headline', '')}_",
        "",
    ]

    attention = brief.get("needs_attention_today", [])
    if attention:
        lines.append("**🎯 Needs your attention today:**")
        for item in attention[:3]:
            lines.append(f"• **{item.get('item', '')}** — {item.get('action', '')}")
        lines.append("")

    gw = brief.get("gateway", {})
    lines.append(f"**Gateway:** {gw.get('status', '?')} · {gw.get('decisions_24h', 0)} decisions · {gw.get('compliance_status', '?')}")

    eng = brief.get("engineering", {})
    lines.append(f"**Engineering:** {eng.get('ci_status', '?')} · {eng.get('open_issues', 0)} open issues")

    pipe = brief.get("pipeline", {})
    lines.append(f"**Pipeline:** {pipe.get('outbound_drafts_ready', 0)} outbound drafts · {pipe.get('content_posts_ready', 0)} posts ready")

    note = brief.get("founder_note", "")
    if note:
        lines.append(f"\n**📋 Note:** {note}")

    return "\n".join(lines)


def send_webhook(message: str, overall_status: str = "") -> None:
    if not BRIEFING_WEBHOOK_URL:
        return
    webhook_decision = gov_check(
        agent_id="chief_of_staff",
        action_type="message.send",
        parameters={"channel": "slack", "message_length": len(message)},
        stated_intent="deliver daily operational briefing to founder via Slack",
        context={"overall_status": overall_status},
    )
    if not webhook_decision:
        print(f"[self_govern] Slack delivery blocked: {webhook_decision.reason}")
        return
    try:
        if "discord" in BRIEFING_WEBHOOK_URL:
            payload = {"content": message}
        else:
            payload = {"text": message}
        r = requests.post(BRIEFING_WEBHOOK_URL, json=payload, timeout=10)
        r.raise_for_status()
        print("Brief delivered via webhook")
    except Exception as exc:
        print(f"Webhook delivery failed: {exc}")


def send_telegram(message: str, overall_status: str = "") -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("No TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID — skipping Telegram delivery")
        return
    tg_decision = gov_check(
        agent_id="chief_of_staff",
        action_type="message.send",
        parameters={"channel": "telegram", "message_length": len(message)},
        stated_intent="deliver daily operational briefing to founder via Telegram",
        context={"overall_status": overall_status},
    )
    if not tg_decision:
        print(f"[self_govern] Telegram delivery blocked: {tg_decision.reason}")
        return
    try:
        # Split into chunks if message exceeds Telegram's 4096 char limit
        chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
        for chunk in chunks:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": chunk, "parse_mode": "Markdown"},
                timeout=10,
            )
            r.raise_for_status()
        print(f"Brief delivered to Telegram chat {TELEGRAM_CHAT_ID}")
    except Exception as exc:
        print(f"Telegram delivery failed: {exc}")


def save_brief(brief: dict[str, Any], today: str) -> Path:
    output_dir = AGENTS_DIR / "briefs"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"brief_{today}.json"
    output_path.write_text(json.dumps(brief, indent=2))
    # Also save latest brief for easy access
    latest = AGENTS_DIR / "daily_brief_latest.json"
    latest.write_text(json.dumps(brief, indent=2))
    print(f"Brief saved to {output_path}")
    return output_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"EDON Chief of Staff — {today}")
    print(f"{'='*60}\n")

    gateway = collect_gateway_data()
    agent_outputs = collect_agent_outputs()
    github = collect_github_data()

    brief = generate_brief(gateway, agent_outputs, github, today)

    if "error" in brief:
        print(f"ERROR generating brief: {brief}")
        sys.exit(1)

    path = save_brief(brief, today)

    # Print to console
    print("\n" + "="*60)
    print("DAILY BRIEF")
    print("="*60)
    print(json.dumps(brief, indent=2))

    # Deliver
    message = format_for_webhook(brief)
    overall_status = brief.get("overall_status", "")
    send_webhook(message, overall_status=overall_status)
    send_telegram(message, overall_status=overall_status)

    # Summary
    status = brief.get("overall_status", "unknown")
    headline = brief.get("headline", "")
    attention_count = len(brief.get("needs_attention_today", []))
    print(f"\n✓ Brief complete — {status.upper()} — {attention_count} items need attention")
    print(f"  {headline}")
    print(f"  Saved to: {path}")


if __name__ == "__main__":
    main()
