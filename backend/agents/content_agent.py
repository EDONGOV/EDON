"""EDON Content Agent — writes technical blog posts for inbound SEO.

Picks the next topic from a curated list, researches using web search,
and writes a 1000-1500 word technical post targeting healthtech AI compliance
keywords. Opens a PR to add it to content/blog/.

Topics are tracked in agents/content_topics.json — mark them done so you
don't repeat. Add new topics to the queue anytime.

Usage:
    # Write next post in queue
    ANTHROPIC_API_KEY=xxx python -m agents.content_agent

    # Write post on a specific topic
    ANTHROPIC_API_KEY=xxx python -m agents.content_agent \\
      --topic "How HIPAA-001 protects against bulk PHI export by AI agents"

    # Add topics to the queue
    ANTHROPIC_API_KEY=xxx python -m agents.content_agent --add-topic "your topic here"

GitHub Actions: see .github/workflows/content_agent.yml — runs weekly, opens a PR.
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

from .self_govern import gov_check

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
REPO_ROOT = Path(__file__).resolve().parents[2]
CONTENT_DIR = REPO_ROOT / "content" / "blog"
TOPICS_FILE = Path(__file__).parent / "content_topics.json"

# Seed topics if none exist — high-value SEO targets for EDON
DEFAULT_TOPICS = [
    "What is AI governance and why every health system deploying AI agents needs it",
    "HIPAA compliance for AI agents: the 7 rules that actually matter in 2026",
    "How to comply with FDA SaMD guidance when your AI agent controls medical devices",
    "AI agent audit trails: why SHA-256 chain hashing beats a database log",
    "HITECH breach notification for AI systems: when your agent causes a reportable incident",
    "The difference between AI safety and AI governance in clinical settings",
    "How to implement human-in-the-loop for AI agents under Joint Commission standards",
    "DEA compliance for AI agents dispensing controlled substances",
    "What happens when an AI agent violates HIPAA: liability, fines, and how governance prevents it",
    "Building a zero-trust AI agent architecture for hospital deployments",
]

EDON_CONTEXT = """EDON is an AI governance platform — a compliance and policy layer that sits between
AI agents and the real world. Every action (email, file export, device command, database query)
passes through EDON, which evaluates it against regulatory rules and returns a verdict in <100ms.

Key capabilities: HIPAA/HITECH/FDA SaMD/DEA/Joint Commission rule packs, tamper-proof audit logs,
human-in-the-loop escalation, policy-as-code, multi-agent fleet management.

Author voice: Technical, direct, no fluff. Cite real regulation section numbers. Use concrete examples.
The audience is CTOs and engineering leads at health systems and clinical SaaS companies."""


def load_topics() -> list[dict[str, Any]]:
    if TOPICS_FILE.exists():
        return json.loads(TOPICS_FILE.read_text(encoding="utf-8"))
    topics = [{"topic": t, "status": "pending", "added_at": datetime.now(UTC).isoformat()}
               for t in DEFAULT_TOPICS]
    save_topics(topics)
    return topics


def save_topics(topics: list[dict[str, Any]]) -> None:
    TOPICS_FILE.write_text(json.dumps(topics, indent=2), encoding="utf-8")


def next_topic(topics: list[dict[str, Any]]) -> dict[str, Any] | None:
    pending = [t for t in topics if t.get("status") == "pending"]
    return pending[0] if pending else None


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower())[:60].strip("-")


def write_post(topic: str) -> dict[str, Any]:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    print(f"  [content] Researching: {topic[:70]}...")

    # Step 1: Research the topic
    research_msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],  # type: ignore[list-item]
        messages=[{"role": "user", "content": f"""Research this topic for a technical blog post:

"{topic}"

Find:
1. Recent (2025-2026) regulatory guidance, enforcement actions, or rule changes relevant to this topic
2. Real-world incidents or case studies where this problem caused harm or fines
3. Current industry statistics or benchmarks
4. What competitors or similar tools are saying about this topic

Summarise key findings in 5-8 bullet points with specifics (dates, dollar amounts, regulation section numbers)."""}],
    )

    research_text = ""
    for block in research_msg.content:
        research_text += str(getattr(block, "text", ""))

    print(f"  [content] Writing post...")

    # Step 2: Write the full post
    write_msg = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=3000,
        messages=[{"role": "user", "content": f"""Write a technical blog post for EDON on this topic:

"{topic}"

## Author context
{EDON_CONTEXT}

## Research findings
{research_text or 'Use your knowledge of the topic.'}

## Requirements
- Length: 1000-1500 words
- Format: Markdown with H2/H3 headers
- Cite real regulation section numbers (e.g. 45 CFR §164.312(b))
- Include at least one concrete code example or API call showing EDON in action
- End with a clear CTA (link to demo or contact)
- SEO: naturally include the main keyword 3-4 times
- No fluff. No "In today's rapidly evolving landscape..." openers.
- Don't mention EDON in every paragraph — make it a useful post first, a pitch second

Start directly with the title as an H1."""}],
    )

    post_content = str(getattr(write_msg.content[0], "text", write_msg.content[0]))

    # Extract title from first H1
    title = topic
    for line in post_content.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break

    slug = _slug(title)
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    filename = f"{date_str}-{slug}.md"

    # Add frontmatter
    frontmatter = f"""---
title: "{title}"
date: {date_str}
topic: {topic}
status: draft
---

"""
    full_post = frontmatter + post_content

    return {
        "topic": topic,
        "title": title,
        "slug": slug,
        "filename": filename,
        "content": full_post,
        "word_count": len(post_content.split()),
        "written_at": datetime.now(UTC).isoformat(),
    }


def save_post(post: dict[str, Any]) -> Path | None:
    decision = gov_check(
        agent_id="content_agent",
        action_type="file.write",
        parameters={"path": f"content/blog/{post['filename']}", "topic": post.get("topic", "")},
        stated_intent="publish auto-written SEO blog post to content pipeline for human review",
    )
    if not decision:
        print(f"[self_govern] Blog post write blocked: {decision.reason}")
        return None
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CONTENT_DIR / post["filename"]
    out_path.write_text(post["content"], encoding="utf-8")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="EDON Content Agent")
    parser.add_argument("--topic", help="Write a post on this specific topic (skips queue)")
    parser.add_argument("--add-topic", metavar="TOPIC", help="Add a topic to the queue")
    parser.add_argument("--list", action="store_true", help="List topics in queue")
    args = parser.parse_args()

    topics = load_topics()

    if args.list:
        pending = [t for t in topics if t.get("status") == "pending"]
        done = [t for t in topics if t.get("status") == "done"]
        print(f"Pending ({len(pending)}):")
        for t in pending:
            print(f"  - {t['topic']}")
        print(f"\nDone ({len(done)}):")
        for t in done:
            print(f"  ✓ {t['topic']}")
        return 0

    if args.add_topic:
        topics.append({"topic": args.add_topic, "status": "pending",
                        "added_at": datetime.now(UTC).isoformat()})
        save_topics(topics)
        print(f"[content] Added topic: {args.add_topic}")
        return 0

    if args.topic:
        topic_str = args.topic
    else:
        topic_entry = next_topic(topics)
        if not topic_entry:
            print("[content] No pending topics. Add some with --add-topic.")
            return 0
        topic_str = topic_entry["topic"]

    print(f"[content] Writing post: {topic_str[:70]}...\n")
    post = write_post(topic_str)
    out_path = save_post(post)

    # Mark topic as done
    for t in topics:
        if t["topic"] == topic_str:
            t["status"] = "done"
            t["filename"] = post["filename"]
            t["completed_at"] = post["written_at"]
    save_topics(topics)

    if out_path is None:
        print("[content] Post blocked by governance — not saved.")
        return 1
    print(f"\n[content] Post written: {out_path}")
    print(f"[content] Title: {post['title']}")
    print(f"[content] Word count: {post['word_count']}")
    print("[content] Review before publishing. Check all regulation citations are accurate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
