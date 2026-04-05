"""EDON Outbound Agent — researches prospects and drafts personalised cold outreach.

Takes a prospect list, researches each company using web search (recent AI
initiatives, HIPAA incidents, job postings, funding), then drafts a cold email
so specific it could only have been written for that company.

You review and send. Nothing is sent automatically.

Usage:
    # Run from a prospect list file
    ANTHROPIC_API_KEY=xxx python -m agents.outbound_agent --input prospects.json

    # Research and draft for a single company
    ANTHROPIC_API_KEY=xxx python -m agents.outbound_agent \\
      --company "Memorial Health System" --website "memorialhealth.com" \\
      --context "Large regional health system, recently announced AI initiative"

Prospect list format (prospects.json):
    [
      {
        "company": "Acme Health",
        "website": "acmehealth.com",
        "context": "Series B clinical AI startup, 200 employees",
        "contact_name": "Jane Smith",   (optional)
        "contact_title": "CTO"          (optional)
      }
    ]

Drafts are saved to agents/outbound_drafts/{company_slug}.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import anthropic

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
REPO_ROOT = Path(__file__).resolve().parents[2]
DRAFTS_DIR = Path(__file__).parent / "outbound_drafts"
DRAFTS_DIR.mkdir(exist_ok=True)

# What EDON does — used as sender context in every email
EDON_PITCH = """EDON is an AI governance platform — a compliance and safety layer that sits between
AI agents and the real world. Every action an AI agent takes (send email, access patient records,
command a device) passes through EDON first. EDON evaluates it against HIPAA/HITECH/FDA rules,
logs it to a tamper-proof audit trail, and returns a verdict in under 100ms.

Target customers: health systems, clinical SaaS companies, and medical device companies
deploying AI agents in regulated workflows.

Key differentiators:
- Pre-built HIPAA, HITECH, FDA SaMD, DEA, Joint Commission rule packs — active in one API call
- Every decision is cryptographically logged (SHA-256 chain hash)
- Works with any AI agent — LLM-based, robotic, or physical
- Under 100ms p95 latency — not in the data path, only the decision path"""


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def research_and_draft(
    company: str,
    website: str = "",
    context: str = "",
    contact_name: str = "",
    contact_title: str = "",
) -> dict[str, Any]:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    print(f"  [outbound] Researching {company}...")

    # Step 1: Research the company with web search
    search_query = f"{company} AI governance compliance HIPAA 2025 2026"
    if website:
        search_query += f" site:{website}"

    research_prompt = f"""Research {company} ({website or 'unknown website'}) for a sales outreach context.

Find:
1. Any recent AI or automation initiatives they've announced
2. Any HIPAA violations, data breaches, or compliance incidents in the last 2 years
3. Job postings that signal AI/ML investment (e.g. AI engineer, ML ops, AI governance roles)
4. Recent funding, acquisitions, or major partnerships
5. Their primary product/service and how AI fits into it

Additional context provided: {context or 'none'}

Summarise findings in 4-6 bullet points. Be specific — company names, dates, dollar amounts where available.
If you can't find specific information, note that rather than guessing."""

    research_msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],  # type: ignore[list-item]
        messages=[{"role": "user", "content": research_prompt}],
    )

    # Extract text from response (may include tool use blocks)
    research_text = ""
    for block in research_msg.content:
        research_text += str(getattr(block, "text", ""))

    if not research_text.strip():
        research_text = f"Context provided: {context or 'No additional context.'}"

    print(f"  [outbound] Drafting email for {company}...")

    # Step 2: Draft the email
    draft_prompt = f"""You are writing a cold outreach email on behalf of EDON to {company}.

## About EDON (sender)
{EDON_PITCH}

## Research findings about {company}
{research_text}

## Contact (if known)
Name: {contact_name or 'unknown'}
Title: {contact_title or 'unknown'}

## Instructions
Write a cold outreach email that:
1. Opens with ONE specific, relevant observation about {company} from the research (not generic)
2. Connects that observation to a real problem EDON solves — be specific about which rule or capability
3. Makes a low-friction ask (15-min call, not a demo)
4. Is under 150 words total
5. Sounds like a person wrote it, not a marketing bot
6. Does NOT use phrases like "I hope this finds you well", "touch base", "synergy", "revolutionary"

Format as:
Subject: <subject line>

<email body>"""

    draft_msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        messages=[{"role": "user", "content": draft_prompt}],
    )
    draft_text = str(getattr(draft_msg.content[0], "text", draft_msg.content[0]))

    # Parse subject and body
    subject = ""
    body = draft_text
    if "Subject:" in draft_text:
        lines = draft_text.strip().splitlines()
        for i, line in enumerate(lines):
            if line.startswith("Subject:"):
                subject = line.replace("Subject:", "").strip()
                body = "\n".join(lines[i + 1:]).strip()
                break

    return {
        "company": company,
        "website": website,
        "contact_name": contact_name,
        "contact_title": contact_title,
        "research": research_text,
        "email_subject": subject,
        "email_body": body,
        "drafted_at": datetime.now(UTC).isoformat(),
    }


def save_draft(result: dict[str, Any]) -> Path:
    slug = _slug(result["company"])
    out_path = DRAFTS_DIR / f"{slug}.md"
    content = f"""# Outbound Draft — {result['company']}
**Drafted:** {result['drafted_at']}
**Contact:** {result.get('contact_name', '')} {result.get('contact_title', '')}
**Website:** {result.get('website', '')}

---

## Research

{result['research']}

---

## Draft Email

**Subject:** {result['email_subject']}

{result['email_body']}

---

*Review before sending. Personalise further if needed.*
"""
    out_path.write_text(content, encoding="utf-8")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="EDON Outbound Agent")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", help="Path to JSON prospect list")
    group.add_argument("--company", help="Single company name")
    parser.add_argument("--website", default="", help="Company website (with --company)")
    parser.add_argument("--context", default="", help="Extra context about the company")
    parser.add_argument("--contact-name", default="", help="Contact name")
    parser.add_argument("--contact-title", default="", help="Contact title")
    args = parser.parse_args()

    if args.company:
        prospects = [{"company": args.company, "website": args.website,
                      "context": args.context, "contact_name": args.contact_name,
                      "contact_title": args.contact_title}]
    else:
        prospects = json.loads(Path(args.input).read_text(encoding="utf-8"))

    print(f"[outbound] Processing {len(prospects)} prospect(s)...\n")

    for p in prospects:
        try:
            result = research_and_draft(
                company=p["company"],
                website=p.get("website", ""),
                context=p.get("context", ""),
                contact_name=p.get("contact_name", ""),
                contact_title=p.get("contact_title", ""),
            )
            path = save_draft(result)
            print(f"  [outbound] Draft saved: {path}")
            print(f"    Subject: {result['email_subject']}\n")
        except Exception as exc:
            print(f"  [outbound] ERROR for {p.get('company', '?')}: {exc}\n")

    print(f"\n[outbound] All drafts in: {DRAFTS_DIR}")
    print("[outbound] Review each draft, personalise if needed, then send.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
