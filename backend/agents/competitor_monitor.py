"""EDON Competitor Monitor — weekly scan of what competitors are shipping.

Monitors the AI governance and compliance space for product updates, pricing changes,
funding, new features, and anything that affects EDON's positioning.

Competitors tracked:
  - Pangea (pangea.cloud) — API security / auth
  - Securiti.ai — data privacy + AI governance
  - Guardrails AI (guardrailsai.com) — LLM guardrails
  - Patronus AI (patronus.ai) — LLM evaluation
  - Lakera (lakera.ai) — prompt injection / LLM security
  - Credal.ai — enterprise AI access control
  - Arthur AI (arthur.ai) — ML monitoring / AI safety
  - Holistic AI (holisticai.com) — AI risk management
  - Meridian (trymeridian.com) — healthcare AI compliance
  - Responsible AI Institute — frameworks/certs

Uses Claude Sonnet + web_search to find recent news, then produces:
  - What changed this week
  - What it means for EDON
  - Talking points to counter / differentiate
  - Opportunities to exploit

Delivers via Telegram + saves to agents/competitor_reports/{date}.json

Usage:
    ANTHROPIC_API_KEY=xxx python -m agents.competitor_monitor

GitHub Actions: .github/workflows/competitor_monitor.yml — runs weekly Wednesday 9am UTC.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import requests
import anthropic

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

AGENTS_DIR = Path(__file__).parent

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

COMPETITORS = [
    {"name": "Pangea", "domain": "pangea.cloud", "focus": "API security and AI guardrails"},
    {"name": "Securiti", "domain": "securiti.ai", "focus": "data privacy and AI governance"},
    {"name": "Guardrails AI", "domain": "guardrailsai.com", "focus": "LLM output validation"},
    {"name": "Patronus AI", "domain": "patronus.ai", "focus": "LLM evaluation and safety"},
    {"name": "Lakera", "domain": "lakera.ai", "focus": "prompt injection and LLM security"},
    {"name": "Credal", "domain": "credal.ai", "focus": "enterprise AI access control"},
    {"name": "Arthur AI", "domain": "arthur.ai", "focus": "ML monitoring and AI safety"},
    {"name": "Holistic AI", "domain": "holisticai.com", "focus": "AI risk management"},
]

EDON_CONTEXT = """EDON is an AI governance platform purpose-built for healthtech.
Key differentiators:
- Clinical safety rules mapped to HIPAA, HITECH, FDA SaMD, DEA, Joint Commission, ISO 13485
- Real-time decision governance (every AI agent action goes through EDON before execution)
- Multi-tenant SaaS with per-tenant policy packs
- CAV (Clinical Adversarial Validation) for adversarial testing
- Built for regulated healthcare environments — not general-purpose AI safety
Target customers: hospitals, clinical SaaS companies, medical device makers, health insurers
Price point: enterprise SaaS ($2k-$10k/month per tenant)"""


# ── Web search ────────────────────────────────────────────────────────────────

def research_competitor(competitor: dict[str, Any]) -> dict[str, Any]:
    """Use Claude with web_search to research a competitor."""
    name = competitor["name"]
    domain = competitor["domain"]
    focus = competitor["focus"]

    print(f"  Researching {name}…")

    tools: Any = [{"type": "web_search_20250305", "name": "web_search"}]

    messages: Any = [
        {
            "role": "user",
            "content": (
                f"Research {name} ({domain}) — {focus}. Find:\n"
                f"1. Any product updates, new features, or announcements in the last 2 weeks\n"
                f"2. Any pricing changes or new tiers\n"
                f"3. Any funding rounds, partnerships, or acquisitions\n"
                f"4. Any new healthcare or compliance-specific features\n"
                f"5. Customer wins or case studies mentioned publicly\n"
                f"6. Any negative news (outages, complaints, lawsuits)\n\n"
                f"Search for: site:{domain} OR '{name} AI' news announcements features 2026\n"
                f"Be specific about dates and sources. If nothing significant found, say so."
            ),
        }
    ]

    research = ""
    for _ in range(3):  # max 3 tool use rounds
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            tools=tools,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    research = str(getattr(block, "text", block))
            break

        # Process tool use
        messages.append({"role": "assistant", "content": response.content})
        tool_results: Any = []
        for block in response.content:
            if block.type == "tool_use":
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": f"Search completed for: {getattr(block, 'input', {}).get('query', '')}",
                })
        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    return {"name": name, "domain": domain, "research": research}


# ── Analysis ──────────────────────────────────────────────────────────────────

def analyse_competitive_landscape(research_results: list[dict[str, Any]], today: str) -> dict[str, Any]:
    """Use Claude Opus to synthesise research into actionable intelligence."""
    print("Analysing competitive landscape…")

    context = f"""You are a competitive intelligence analyst for EDON.

EDON CONTEXT:
{EDON_CONTEXT}

TODAY: {today}

COMPETITOR RESEARCH:
{json.dumps(research_results, indent=2)}

Produce a structured competitive intelligence report. Return ONLY valid JSON:
{{
  "date": "{today}",
  "headline": "One sentence on the most important competitive development this week",
  "threat_level": "low | medium | high",
  "competitors": [
    {{
      "name": "...",
      "notable_this_week": "...",
      "threat_to_edon": "low | medium | high",
      "why": "..."
    }}
  ],
  "biggest_threat": {{
    "competitor": "...",
    "what_they_did": "...",
    "why_it_matters": "...",
    "how_to_counter": "..."
  }},
  "opportunities": [
    {{
      "opportunity": "...",
      "why_now": "...",
      "action": "..."
    }}
  ],
  "talking_points": [
    "A specific thing to say when a prospect mentions [competitor]"
  ],
  "market_trends": ["..."],
  "recommended_actions": [
    {{"priority": 1, "action": "...", "rationale": "..."}}
  ],
  "founder_note": "Direct 2-3 sentence note: what matters most from this week's competitive scan and what you should do about it."
}}"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": context}],
    )

    raw = str(getattr(msg.content[0], "text", msg.content[0]))
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1:
        return {"error": "Failed to parse", "raw": raw}
    try:
        return json.loads(raw[start:end])
    except json.JSONDecodeError:
        return {"error": "Invalid JSON", "raw": raw}


# ── Delivery ──────────────────────────────────────────────────────────────────

def format_telegram(report: dict[str, Any]) -> str:
    threat_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(
        report.get("threat_level", "low"), "⚪"
    )
    lines = [
        f"{threat_emoji} *Competitor Monitor — {report.get('date', 'Today')}*",
        f"_{report.get('headline', '')}_\n",
    ]

    biggest = report.get("biggest_threat", {})
    if biggest.get("competitor"):
        lines.append(f"⚠️ *Biggest threat: {biggest['competitor']}*")
        lines.append(f"{biggest.get('what_they_did', '')}")
        lines.append(f"Counter: _{biggest.get('how_to_counter', '')}_\n")

    opportunities = report.get("opportunities", [])
    if opportunities:
        lines.append("💡 *Opportunities this week:*")
        for opp in opportunities[:2]:
            lines.append(f"• {opp.get('opportunity', '')} → {opp.get('action', '')}")
        lines.append("")

    actions = report.get("recommended_actions", [])
    if actions:
        lines.append("🎯 *Actions:*")
        for a in actions[:3]:
            lines.append(f"{a.get('priority', '')}. {a.get('action', '')}")
        lines.append("")

    note = report.get("founder_note", "")
    if note:
        lines.append(f"📋 *Note:* {note}")

    return "\n".join(lines)


def send_telegram(message: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("No Telegram config — skipping")
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
        print("Report delivered via Telegram")
    except Exception as exc:
        print(f"Telegram failed: {exc}")


def save_report(report: dict[str, Any], today: str) -> Path:
    output_dir = AGENTS_DIR / "competitor_reports"
    output_dir.mkdir(exist_ok=True)
    path = output_dir / f"report_{today}.json"
    path.write_text(json.dumps(report, indent=2))
    latest = AGENTS_DIR / "competitor_report_latest.json"
    latest.write_text(json.dumps(report, indent=2))
    print(f"Report saved to {path}")
    return path


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"EDON Competitor Monitor — {today}")
    print(f"{'='*60}\n")

    print("Researching competitors…")
    research_results = []
    for competitor in COMPETITORS:
        result = research_competitor(competitor)
        research_results.append(result)

    report = analyse_competitive_landscape(research_results, today)

    if "error" in report:
        print(f"ERROR: {report}")
        return

    path = save_report(report, today)

    print("\n" + "="*60)
    print("COMPETITIVE INTELLIGENCE REPORT")
    print("="*60)
    print(json.dumps(report, indent=2))

    message = format_telegram(report)
    send_telegram(message)

    threat = report.get("threat_level", "unknown")
    headline = report.get("headline", "")
    print(f"\n✓ Report complete — threat level: {threat.upper()}")
    print(f"  {headline}")
    print(f"  Saved to: {path}")


if __name__ == "__main__":
    main()
