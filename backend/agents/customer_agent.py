"""EDON Customer Agent — drafts answers to technical prospect/customer questions.

Loads your full API reference, clinical safety rules, governance model, and
onboarding guide as context, then drafts a precise answer you can review and send.

Usage:
    # From stdin (pipe a JSON object with "question" and optional "context")
    echo '{"question": "Does EDON cover 21 CFR Part 11?", "context": "We build LIMS software"}' \\
      | ANTHROPIC_API_KEY=xxx python -m agents.customer_agent

    # From a file
    ANTHROPIC_API_KEY=xxx python -m agents.customer_agent --input question.json

    # Interactive
    ANTHROPIC_API_KEY=xxx python -m agents.customer_agent --ask "How does HIPAA-001 work?"

Output is written to stdout (the draft) and optionally to --output file.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import anthropic

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

REPO_ROOT = Path(__file__).resolve().parents[2]

# Context files loaded for every question
CONTEXT_FILES = {
    "API Reference": REPO_ROOT / "docs" / "api-reference.md",
    "Architecture": REPO_ROOT / "docs" / "architecture.md",
    "Governance Model": REPO_ROOT / "docs" / "governance-model.md",
    "Onboarding Guide": REPO_ROOT / "backend" / "docs" / "ONBOARDING.md",
    "Clinical Safety Rules": REPO_ROOT / "backend" / "edon_gateway" / "clinical_safety.py",
    "RBAC Roles": REPO_ROOT / "backend" / "docs" / "RBAC_PRODUCT_ROLES.md",
    "Enterprise Safety": REPO_ROOT / "backend" / "docs" / "ENTERPRISE_SAFETY.md",
}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _build_context() -> str:
    parts = []
    for name, path in CONTEXT_FILES.items():
        content = _read(path)
        if content:
            parts.append(f"=== {name} ===\n{content[:3000]}")
    return "\n\n".join(parts)


def draft_answer(question: str, customer_context: str = "") -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    knowledge = _build_context()

    system = """You are the technical sales engineer for EDON, an AI governance platform.
EDON is the safety and compliance layer that sits between AI agents and the real world —
every action an agent wants to take passes through EDON first for policy evaluation.

Your job is to answer technical questions from prospects and customers with precision.
Rules:
- Answer from the actual product capabilities, not aspirations
- Cite specific endpoints, rule codes, or config options when relevant (e.g. HIPAA-001, /v1/action, /compliance/clinical-safety/activate)
- Be honest about limitations — don't oversell
- Keep it under 300 words unless the question needs more depth
- Write in plain English — no jargon unless the customer used it first
- Format as a ready-to-send email reply (no "Dear Customer" opener needed, just the answer)"""

    user_msg = f"""Customer context: {customer_context or "Not provided"}

Their question:
{question}

Draft a precise, helpful answer."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=system,
        messages=[
            {"role": "user", "content": f"Here is the EDON product knowledge base:\n\n{knowledge}"},
            {"role": "assistant", "content": "I've reviewed the EDON documentation. Ready to answer customer questions."},
            {"role": "user", "content": user_msg},
        ],
    )
    return str(getattr(msg.content[0], "text", msg.content[0]))


def main() -> int:
    parser = argparse.ArgumentParser(description="EDON Customer Agent")
    parser.add_argument("--ask", help="Question to answer directly")
    parser.add_argument("--input", help="Path to JSON file with question and context")
    parser.add_argument("--output", help="Write draft to this file instead of stdout")
    args = parser.parse_args()

    if args.ask:
        question = args.ask
        context = ""
    elif args.input:
        with open(args.input) as f:
            data = json.load(f)
        question = data["question"]
        context = data.get("context", "")
    elif not sys.stdin.isatty():
        data = json.load(sys.stdin)
        question = data["question"]
        context = data.get("context", "")
    else:
        parser.print_help()
        return 1

    print(f"[customer] Drafting answer for: {question[:80]}...", file=sys.stderr)
    draft = draft_answer(question, context)

    if args.output:
        Path(args.output).write_text(draft, encoding="utf-8")
        print(f"[customer] Draft written to {args.output}", file=sys.stderr)
    else:
        print("\n" + "=" * 60)
        print("DRAFT ANSWER")
        print("=" * 60)
        print(draft)
        print("=" * 60 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
