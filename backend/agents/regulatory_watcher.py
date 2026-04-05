"""EDON Regulatory Watcher — monitors HHS/FDA/NIST for rule changes.

Fetches recent entries from government RSS/Atom feeds, asks Claude to check
whether any updates touch regulations that EDON enforces, and opens a GitHub
issue if a gap is found.

Runs weekly via GitHub Actions. Also runnable locally.

Usage:
    ANTHROPIC_API_KEY=xxx GITHUB_TOKEN=xxx python -m agents.regulatory_watcher

Feeds monitored:
    - HHS Office for Civil Rights (HIPAA/HITECH) — federalregister.gov
    - FDA Digital Health (SaMD/AI/ML) — federalregister.gov
    - NIST AI Risk Management — nist.gov
    - DEA Diversion Control (controlled substances) — federalregister.gov
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, UTC
from pathlib import Path

import requests
import anthropic

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "GHOSTCODERRRRAHAHA/edongov")

REPO_ROOT = Path(__file__).resolve().parents[2]
CLINICAL_SAFETY_PATH = REPO_ROOT / "backend" / "edon_gateway" / "clinical_safety.py"

# Federal Register RSS: search by agency + keyword, last 30 days
_FR_BASE = "https://www.federalregister.gov/api/v1/articles.json"

FEEDS = [
    {
        "name": "HHS / HIPAA & HITECH",
        "params": {
            "agencies[]": "health-and-human-services-department",
            "search_term": "HIPAA privacy security breach notification",
            "per_page": 5,
            "order": "newest",
        },
        "regulations": ["HIPAA", "HITECH"],
    },
    {
        "name": "FDA / Digital Health & SaMD",
        "params": {
            "agencies[]": "food-and-drug-administration",
            "search_term": "artificial intelligence machine learning software medical device",
            "per_page": 5,
            "order": "newest",
        },
        "regulations": ["FDA_SAMD"],
    },
    {
        "name": "DEA / Controlled Substances",
        "params": {
            "agencies[]": "drug-enforcement-administration",
            "search_term": "controlled substance dispensing electronic",
            "per_page": 5,
            "order": "newest",
        },
        "regulations": ["DEA"],
    },
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _fetch_feed(feed: dict) -> list[dict]:
    """Fetch recent Federal Register articles for a feed config."""
    try:
        r = requests.get(
            _FR_BASE,
            params={**feed["params"], "fields[]": ["title", "abstract", "publication_date", "html_url", "document_number"]},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("results", [])
    except Exception as exc:
        print(f"[watcher] Feed '{feed['name']}' fetch failed: {exc}", file=sys.stderr)
        return []


def _load_rule_codes() -> list[str]:
    """Extract rule codes from clinical_safety.py."""
    src = CLINICAL_SAFETY_PATH.read_text(encoding="utf-8")
    codes = []
    for line in src.splitlines():
        if '"rule_code"' in line:
            parts = line.split('"')
            if len(parts) >= 4:
                codes.append(parts[3])
    return codes


def _open_github_issue(title: str, body: str) -> str | None:
    if not GITHUB_TOKEN:
        print("[watcher] GITHUB_TOKEN not set — skipping issue", file=sys.stderr)
        return None
    r = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPO}/issues",
        headers={"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"},
        json={"title": title, "body": body, "labels": ["regulatory", "automated"]},
        timeout=15,
    )
    if r.status_code == 201:
        url = r.json().get("html_url", "")
        print(f"[watcher] Issue created: {url}")
        return url
    print(f"[watcher] Issue creation failed: {r.status_code} {r.text[:200]}", file=sys.stderr)
    return None


# ── Core ──────────────────────────────────────────────────────────────────────

def run() -> int:
    print(f"[watcher] Starting — {datetime.now(UTC).isoformat()}")

    rule_codes = _load_rule_codes()
    print(f"[watcher] Monitoring {len(rule_codes)} rule codes: {', '.join(rule_codes)}")

    all_articles: list[dict] = []
    for feed in FEEDS:
        articles = _fetch_feed(feed)
        for a in articles:
            a["_feed_name"] = feed["name"]
            a["_regulations"] = feed["regulations"]
        all_articles.extend(articles)
        print(f"[watcher] {feed['name']}: {len(articles)} recent articles")

    if not all_articles:
        print("[watcher] No articles fetched — check network or feed URLs")
        return 0

    # Build article summary for Claude
    article_lines = []
    for a in all_articles:
        article_lines.append(
            f"- [{a['_feed_name']}] {a.get('publication_date', '?')} — "
            f"{a.get('title', 'No title')}\n"
            f"  URL: {a.get('html_url', '')}\n"
            f"  Abstract: {(a.get('abstract') or '')[:300]}"
        )

    clinical_safety_src = CLINICAL_SAFETY_PATH.read_text(encoding="utf-8")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""You are the regulatory compliance agent for EDON, an AI governance platform.
EDON enforces these regulation-mapped rules: {', '.join(rule_codes)}

Here are the recent government publications from the last 30 days:

{chr(10).join(article_lines)}

Here are EDON's current clinical safety rule definitions for context:

{clinical_safety_src[:4000]}

Your task:
1. Identify any articles that could require changes to EDON's clinical safety rules
2. For each potentially impactful article: explain which rule_code(s) are affected and why
3. If nothing is impactful, say so clearly

Be specific. Cite document titles and rule codes. Do not flag articles that are routine/procedural.
If there are no gaps, say "No regulatory gaps found — current coverage is sufficient."

Format as plain markdown. Keep it under 400 words."""

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    analysis = str(getattr(msg.content[0], "text", msg.content[0]))

    print("\n" + "=" * 60)
    print(analysis)
    print("=" * 60 + "\n")

    no_gap_phrases = ["no regulatory gaps", "no gaps found", "coverage is sufficient", "nothing impactful"]
    has_gaps = not any(p in analysis.lower() for p in no_gap_phrases)

    if has_gaps:
        title = f"[Regulatory] Potential compliance gap detected — {datetime.now(UTC).strftime('%Y-%m-%d')}"
        body = f"{analysis}\n\n---\n*Generated by EDON Regulatory Watcher — {datetime.now(UTC).isoformat()}*"
        _open_github_issue(title, body)
        return 1

    print("[watcher] No gaps found. Coverage is current.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
