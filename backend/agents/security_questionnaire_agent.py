"""EDON Security Questionnaire Agent — answers vendor security assessments.

Enterprise health systems send 150-300 question security/vendor assessments before
signing. Each one takes 8-40 hours manually. This agent loads your full security
posture and answers every question with Claude Opus.

Handles common formats: plain text (one question per line), JSON array, CSV.

Usage:
    # From a text file (one question per line)
    ANTHROPIC_API_KEY=xxx python -m agents.security_questionnaire_agent \\
      --input questionnaire.txt --output completed_questionnaire.md

    # From JSON array of questions
    ANTHROPIC_API_KEY=xxx python -m agents.security_questionnaire_agent \\
      --input questionnaire.json --company "Acme Health" --output answers.md

    # Pipe questions in
    cat questions.txt | ANTHROPIC_API_KEY=xxx \\
      python -m agents.security_questionnaire_agent --output answers.md
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import anthropic

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
REPO_ROOT = Path(__file__).resolve().parents[2]

# Every security doc we have — all loaded as context
SECURITY_CONTEXT_FILES = {
    "Threat Model": REPO_ROOT / "backend" / "docs" / "THREAT_MODEL.md",
    "Enterprise Safety": REPO_ROOT / "backend" / "docs" / "ENTERPRISE_SAFETY.md",
    "Authentication Methods": REPO_ROOT / "backend" / "docs" / "AUTHENTICATION_METHODS.md",
    "Architecture": REPO_ROOT / "docs" / "architecture.md",
    "Network Isolation": REPO_ROOT / "backend" / "docs" / "NETWORK_ISOLATION_GUIDE.md",
    "Network Gating": REPO_ROOT / "backend" / "docs" / "NETWORK_GATING_IMPLEMENTATION.md",
    "Configuration": REPO_ROOT / "backend" / "docs" / "CONFIGURATION.md",
    "Backup Procedures": REPO_ROOT / "backend" / "docs" / "BACKUP_PROCEDURES.md",
    "Backup Recovery": REPO_ROOT / "backend" / "docs" / "BACKUP_RECOVERY.md",
    "Deployment Readiness": REPO_ROOT / "backend" / "docs" / "DEPLOYMENT_READINESS.md",
    "Clinical Safety Rules": REPO_ROOT / "backend" / "edon_gateway" / "clinical_safety.py",
    "RBAC Roles": REPO_ROOT / "backend" / "docs" / "RBAC_PRODUCT_ROLES.md",
    "Governance Model": REPO_ROOT / "docs" / "governance-model.md",
    "API Reference": REPO_ROOT / "docs" / "api-reference.md",
}

# Boilerplate facts not in docs — edit these to match your actuals
COMPANY_FACTS = """
Company: EDON (edoncore.com)
Product: EDON Gateway — AI governance and compliance platform
Deployment: Cloud-hosted SaaS (Fly.io, iad region) + self-hosted option
Database: SQLite (single-tenant) / PostgreSQL (enterprise)
Encryption at rest: AES-256 (Fly.io volume encryption)
Encryption in transit: TLS 1.2+ enforced
Authentication: API key (bcrypt hashed, cost factor 12+) + Clerk JWT
MFA: Supported via Clerk (TOTP, SMS)
SOC2: In progress
HIPAA: BAA available for enterprise customers
Penetration testing: Annual (results available under NDA)
Vulnerability disclosure: security@edoncore.com
Data residency: US (iad) by default; EU region available on request
Audit log retention: 6 years minimum for HIPAA tenants (45 CFR §164.312)
Incident response SLA: P0 = 1 hour, P1 = 4 hours, P2 = 24 hours
Subprocessors: Fly.io (hosting), Clerk (auth), Stripe (billing), Anthropic (AI analysis)
"""


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _build_security_context() -> str:
    parts = [f"## Company Facts\n{COMPANY_FACTS}"]
    for name, path in SECURITY_CONTEXT_FILES.items():
        content = _read(path)
        if content:
            parts.append(f"## {name}\n{content[:3000]}")
    return "\n\n---\n\n".join(parts)


def parse_questions(raw: str, filename: str = "") -> list[str]:
    """Parse questions from various formats."""
    raw = raw.strip()

    # JSON array
    if raw.startswith("["):
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(q) for q in data if q]
        except json.JSONDecodeError:
            pass

    # JSON object with "questions" key
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
            questions_raw = data.get("questions", [])
            if isinstance(questions_raw, list):
                return [str(q) for q in questions_raw if q]
        except json.JSONDecodeError:
            pass

    # CSV: first column is the question
    if filename.endswith(".csv") or "," in raw[:200]:
        try:
            reader = csv.reader(raw.splitlines())
            questions = []
            for row in reader:
                if row and row[0].strip() and not row[0].strip().startswith("#"):
                    questions.append(row[0].strip())
            if len(questions) > 2:
                return questions
        except Exception:
            pass

    # Plain text: one question per non-empty line, or numbered list
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    questions = []
    for line in lines:
        # Strip leading numbers/bullets: "1.", "1)", "•", "-", "*"
        for prefix in ["• ", "- ", "* "]:
            if line.startswith(prefix):
                line = line[len(prefix):]
                break
        if len(line) > 1 and line[0].isdigit():
            dot = line.find(".")
            paren = line.find(")")
            cut = min(x for x in [dot, paren] if x > 0) if any(x > 0 for x in [dot, paren]) else -1
            if 0 < cut <= 4:
                line = line[cut + 1:].strip()
        if line:
            questions.append(line)
    return questions


def answer_questions(questions: list[str], company_name: str = "") -> list[dict[str, Any]]:
    context = _build_security_context()
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    system = f"""You are the security team for EDON, an AI governance platform.
You are answering a vendor security questionnaire{f' for {company_name}' if company_name else ''}.

Answer each question accurately and completely based on the security documentation provided.
Rules:
- Answer directly — no "Based on our documentation..." preamble
- If something is in progress (e.g. SOC2), say "In progress — expected Q[X] 202X"
- If something is not applicable, say "N/A — [brief reason]"
- If you genuinely don't know, say "Please contact security@edoncore.com for details"
- Keep answers concise but complete — 1-3 sentences unless the question needs more
- Never make up certifications, audits, or capabilities we don't have

Here is EDON's full security documentation:

{context[:12000]}"""

    results = []
    total = len(questions)

    # Process in batches of 20 to stay within token limits
    batch_size = 20
    for batch_start in range(0, total, batch_size):
        batch = questions[batch_start:batch_start + batch_size]
        batch_num = batch_start // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size
        print(f"  [secq] Answering questions {batch_start+1}-{batch_start+len(batch)}/{total} "
              f"(batch {batch_num}/{total_batches})...")

        numbered = "\n".join(f"{i+1}. {q}" for i, q in enumerate(batch))
        prompt = f"""Answer each of these {len(batch)} security questionnaire questions.
Return a JSON array with one object per question in order:
[{{"question": "...", "answer": "..."}}]

Questions:
{numbered}"""

        msg = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=3000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = str(getattr(msg.content[0], "text", msg.content[0]))

        try:
            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            batch_results = json.loads(clean.strip())
            results.extend(batch_results)
        except Exception:
            # Fallback: pair questions with raw output
            for q in batch:
                results.append({"question": q, "answer": raw[:200]})

    return results


def render_markdown(results: list[dict[str, Any]], company_name: str = "") -> str:
    lines = [
        f"# Security Questionnaire — EDON",
        f"{'**Prepared for:** ' + company_name if company_name else ''}",
        f"**Date:** {datetime.now(UTC).strftime('%Y-%m-%d')}",
        f"**Contact:** security@edoncore.com",
        "",
        "---",
        "",
    ]
    for i, r in enumerate(results, 1):
        lines.append(f"## Q{i}. {r.get('question', '')}")
        lines.append("")
        lines.append(r.get("answer", ""))
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="EDON Security Questionnaire Agent")
    parser.add_argument("--input", help="Path to questionnaire file (.txt, .json, .csv)")
    parser.add_argument("--output", required=True, help="Output path for completed questionnaire (.md or .json)")
    parser.add_argument("--company", default="", help="Prospect/customer company name")
    args = parser.parse_args()

    if args.input:
        raw = Path(args.input).read_text(encoding="utf-8")
        filename = args.input
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
        filename = ""
    else:
        parser.print_help()
        return 1

    print(f"[secq] Parsing questionnaire...")
    questions = parse_questions(raw, filename)
    if not questions:
        print("[secq] No questions found. Check your input format.")
        return 1
    print(f"[secq] Found {len(questions)} questions. Starting with Claude Opus...")

    results = answer_questions(questions, args.company)

    out_path = Path(args.output)
    if args.output.endswith(".json"):
        out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    else:
        out_path.write_text(render_markdown(results, args.company), encoding="utf-8")

    print(f"\n[secq] Done. {len(results)} answers written to {out_path}")
    print("[secq] Review carefully before sending — verify any 'In progress' items are accurate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
