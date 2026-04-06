"""EDON Code Agent — reads agent outputs and writes code improvements as PRs.

This agent closes the feedback loop: data → insight → code → better product.

It collects signals from all other agents, identifies the highest-impact lowest-risk
code changes, writes them using Claude Opus, runs the test suite to verify, and
opens a GitHub PR for human review. It never pushes directly to master.

What it can improve:
  - Clinical safety rules (new regulations, updated rule codes)
  - Policy rule thresholds (incident detection, rate limits)
  - Compliance mappings (new regulations mapped to rules)
  - Agent configurations (follow-up schedules, competitor list, monitoring thresholds)
  - Test coverage gaps (adds tests for uncovered edge cases from QA findings)

What it will NOT touch (safety rails):
  - Authentication / auth middleware
  - Billing / Stripe integration
  - Database schema / migrations
  - Security hashing / encryption
  - Anything outside the allowed paths list

Usage:
    ANTHROPIC_API_KEY=xxx GITHUB_TOKEN=xxx python -m agents.code_agent

    # Dry run — shows proposed changes without creating PR
    python -m agents.code_agent --dry-run

GitHub Actions: .github/workflows/code_agent.yml — runs weekly Sunday 6am UTC.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import requests
import anthropic

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "EDONGOV/EDON")
EDON_GATEWAY_URL = os.environ.get("EDON_GATEWAY_URL", "https://edon-gateway-prod.fly.dev")
EDON_API_TOKEN = os.environ.get("EDON_API_TOKEN", "")

AGENTS_DIR = Path(__file__).parent
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"

# ── Safety: only these paths may be modified ─────────────────────────────────
ALLOWED_PATHS = [
    "backend/edon_gateway/clinical_safety.py",
    "backend/edon_gateway/policies.py",
    "backend/agents/incident_agent.py",   # threshold tuning only
    "backend/tests/",
]

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ── Signal collection ─────────────────────────────────────────────────────────

def _load_json(path: Path) -> Any:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return None
    return None


def _gh_get(path: str) -> Any:
    if not GITHUB_TOKEN:
        return {"error": "No GITHUB_TOKEN"}
    try:
        r = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}{path}",
            headers={"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        return {"error": str(exc)}


def _gw_get(path: str) -> Any:
    if not EDON_API_TOKEN:
        return {"error": "No EDON_API_TOKEN"}
    try:
        r = requests.get(
            f"{EDON_GATEWAY_URL}{path}",
            headers={"X-EDON-TOKEN": EDON_API_TOKEN},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        return {"error": str(exc)}


def collect_signals() -> dict[str, Any]:
    print("Collecting signals from all agents…")
    signals: dict[str, Any] = {}

    # Agent outputs
    signals["product_intelligence"] = _load_json(AGENTS_DIR / "product_intelligence_report.json")
    signals["competitor_report"] = _load_json(AGENTS_DIR / "competitor_report_latest.json")
    signals["daily_brief"] = _load_json(AGENTS_DIR / "daily_brief_latest.json")
    signals["incident_baseline"] = _load_json(AGENTS_DIR / "incident_baseline.json")

    # Live gateway compliance
    signals["compliance_health"] = _gw_get("/compliance/health")

    # GitHub issues labelled code-agent or auto-fix or regression
    issues_data = _gh_get("/issues?state=open&labels=code-agent,regression&per_page=20")
    if isinstance(issues_data, list):
        signals["flagged_issues"] = [
            {"number": i.get("number"), "title": i.get("title"), "body": (i.get("body") or "")[:500]}
            for i in issues_data
        ]
    else:
        signals["flagged_issues"] = []

    # Read current clinical safety rules for context
    cs_path = BACKEND_DIR / "edon_gateway" / "clinical_safety.py"
    if cs_path.exists():
        signals["current_clinical_safety"] = cs_path.read_text(encoding="utf-8")[:3000]

    # Read incident thresholds
    incident_path = AGENTS_DIR / "incident_agent.py"
    if incident_path.exists():
        content = incident_path.read_text(encoding="utf-8")
        # Extract just the THRESHOLDS block
        start = content.find("THRESHOLDS")
        end = content.find("}", start) + 1
        signals["incident_thresholds"] = content[start:end] if start != -1 else ""

    return signals


# ── Change identification ─────────────────────────────────────────────────────

def identify_best_change(signals: dict[str, Any]) -> dict[str, Any]:
    print("Asking Claude Opus to identify the best code improvement…")

    prompt = f"""You are the Code Agent for EDON, an AI governance SaaS for healthtech.
You have read-only access to signals from all 15 AI agents.
Your job: identify ONE high-impact, low-risk code change that will improve EDON.

SIGNALS FROM ALL AGENTS:
{json.dumps({k: v for k, v in signals.items() if k != "current_clinical_safety"}, indent=2, default=str)[:4000]}

CURRENT CLINICAL SAFETY RULES (first 3000 chars):
{signals.get("current_clinical_safety", "Not available")[:2000]}

ALLOWED FILE PATHS YOU MAY MODIFY:
{json.dumps(ALLOWED_PATHS, indent=2)}

STRICT RULES:
- You may ONLY modify files in the allowed paths list
- Never touch: auth, billing, encryption, database schema, middleware
- The change must be self-contained and testable
- If no clear improvement is warranted, return {{"action": "none", "reason": "..."}}

Identify the single best improvement. Return ONLY valid JSON:
{{
  "action": "modify_file | add_rule | tune_threshold | none",
  "reason": "Why this change matters and what signal triggered it",
  "file_path": "relative path from repo root",
  "change_type": "add | modify | append",
  "description": "One sentence describing the change",
  "pr_title": "feat/fix/chore: concise PR title",
  "pr_body": "Markdown PR description explaining what changed, why, and what to review",
  "search_string": "Exact string to find in the file (for modify/append)",
  "new_content": "The complete new content or replacement",
  "test_command": "pytest command to verify (e.g. pytest tests/ -q -k test_name)",
  "risk_level": "low | medium",
  "confidence": "high | medium | low"
}}"""

    msg = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = str(getattr(msg.content[0], "text", msg.content[0]))
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1:
        return {"action": "none", "reason": "Could not parse response"}
    try:
        return json.loads(raw[start:end])
    except json.JSONDecodeError:
        return {"action": "none", "reason": "Invalid JSON response"}


# ── Change execution ──────────────────────────────────────────────────────────

def is_path_allowed(file_path: str) -> bool:
    for allowed in ALLOWED_PATHS:
        if file_path.startswith(allowed):
            return True
    return False


def apply_change(change: dict[str, Any]) -> tuple[bool, str]:
    """Apply the proposed change to the file. Returns (success, message)."""
    file_path = change.get("file_path", "")
    if not file_path:
        return False, "No file_path specified"

    if not is_path_allowed(file_path):
        return False, f"BLOCKED: {file_path} is not in allowed paths"

    full_path = REPO_ROOT / file_path
    if not full_path.exists():
        return False, f"File not found: {full_path}"

    change_type = change.get("change_type", "modify")
    new_content = change.get("new_content", "")
    search_string = change.get("search_string", "")

    try:
        original = full_path.read_text(encoding="utf-8")

        if change_type == "append":
            updated = original.rstrip() + "\n\n" + new_content + "\n"
        elif change_type == "modify" and search_string:
            if search_string not in original:
                return False, f"Search string not found in {file_path}"
            updated = original.replace(search_string, new_content, 1)
        elif change_type == "add":
            updated = new_content
        else:
            return False, f"Unknown change_type: {change_type}"

        full_path.write_text(updated, encoding="utf-8")
        return True, f"Applied {change_type} to {file_path}"

    except Exception as exc:
        return False, f"Failed to apply change: {exc}"


def run_tests(test_command: str) -> tuple[bool, str]:
    """Run the test suite. Returns (passed, output)."""
    print(f"Running tests: {test_command}")
    try:
        result = subprocess.run(
            test_command.split(),
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "PYTHONPATH": str(BACKEND_DIR), "EDON_ENV": "development",
                 "EDON_AUTH_ENABLED": "false", "EDON_CREDENTIALS_STRICT": "false"},
        )
        output = result.stdout + result.stderr
        passed = result.returncode == 0
        return passed, output
    except subprocess.TimeoutExpired:
        return False, "Tests timed out after 120s"
    except Exception as exc:
        return False, f"Failed to run tests: {exc}"


# ── GitHub PR ─────────────────────────────────────────────────────────────────

def create_pr(change: dict[str, Any], test_output: str, test_passed: bool) -> str | None:
    if not GITHUB_TOKEN:
        print("No GITHUB_TOKEN — cannot create PR")
        return None

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    branch = f"code-agent/auto-fix-{today}-{change.get('change_type', 'change')}"

    gh_headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    # Get default branch SHA
    try:
        ref_data = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/git/ref/heads/master",
            headers=gh_headers, timeout=10,
        ).json()
        sha = ref_data["object"]["sha"]
    except Exception as exc:
        print(f"Failed to get master SHA: {exc}")
        return None

    # Create branch
    try:
        requests.post(
            f"https://api.github.com/repos/{GITHUB_REPO}/git/refs",
            headers=gh_headers,
            json={"ref": f"refs/heads/{branch}", "sha": sha},
            timeout=10,
        ).raise_for_status()
    except Exception as exc:
        print(f"Failed to create branch: {exc}")
        return None

    # Push file change
    file_path = change.get("file_path", "")
    full_path = REPO_ROOT / file_path
    try:
        import base64
        content_b64 = base64.b64encode(full_path.read_bytes()).decode()

        # Get current file SHA for update
        file_info = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}?ref=master",
            headers=gh_headers, timeout=10,
        ).json()
        file_sha = file_info.get("sha", "")

        requests.put(
            f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}",
            headers=gh_headers,
            json={
                "message": f"{change.get('pr_title', 'code-agent: auto-improvement')}\n\nCo-Authored-By: EDON Code Agent <noreply@edoncore.com>",
                "content": content_b64,
                "branch": branch,
                "sha": file_sha,
            },
            timeout=10,
        ).raise_for_status()
    except Exception as exc:
        print(f"Failed to push file: {exc}")
        return None

    # Create PR
    test_status = "✅ Tests passed" if test_passed else "⚠️ Tests failed — review required"
    pr_body = f"""{change.get('pr_body', '')}

---

## Triggered by
{change.get('reason', 'Automatic improvement detected by Code Agent')}

## Test results
{test_status}

```
{test_output[:2000]}
```

## Safety
- Risk level: `{change.get('risk_level', 'low')}`
- Confidence: `{change.get('confidence', 'medium')}`
- File modified: `{file_path}`

> 🤖 Auto-generated by EDON Code Agent. Review carefully before merging.
"""
    try:
        pr = requests.post(
            f"https://api.github.com/repos/{GITHUB_REPO}/pulls",
            headers=gh_headers,
            json={
                "title": change.get("pr_title", "code-agent: auto-improvement"),
                "body": pr_body,
                "head": branch,
                "base": "master",
            },
            timeout=10,
        ).json()
        url = pr.get("html_url", "")
        print(f"PR created: {url}")
        return url
    except Exception as exc:
        print(f"Failed to create PR: {exc}")
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main(dry_run: bool = False) -> None:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"EDON Code Agent — {today}")
    if dry_run:
        print("DRY RUN — no changes will be made")
    print(f"{'='*60}\n")

    # Step 1: Collect signals
    signals = collect_signals()
    print(f"Signals collected: {list(signals.keys())}")

    # Step 2: Identify best change
    change = identify_best_change(signals)
    print(f"\nProposed action: {change.get('action')}")
    print(f"Description: {change.get('description', '')}")
    print(f"Reason: {change.get('reason', '')}")
    print(f"Risk: {change.get('risk_level', 'unknown')} | Confidence: {change.get('confidence', 'unknown')}")

    if change.get("action") == "none":
        print(f"\nNo changes needed: {change.get('reason')}")
        return

    if dry_run:
        print("\n[DRY RUN] Proposed change:")
        print(json.dumps(change, indent=2))
        return

    # Step 3: Validate path
    file_path = change.get("file_path", "")
    if not is_path_allowed(file_path):
        print(f"\nBLOCKED: {file_path} is not in allowed paths. Aborting.")
        sys.exit(1)

    if change.get("risk_level") == "high":
        print("\nBLOCKED: High-risk change requires manual review. Aborting.")
        sys.exit(1)

    # Step 4: Apply change
    success, msg = apply_change(change)
    if not success:
        print(f"\nFailed to apply change: {msg}")
        sys.exit(1)
    print(f"\n✓ {msg}")

    # Step 5: Run tests
    test_cmd = change.get("test_command", "pytest -q -W ignore::DeprecationWarning")
    test_passed, test_output = run_tests(test_cmd)
    print(f"Tests: {'✓ passed' if test_passed else '✗ failed'}")

    if not test_passed and change.get("risk_level") != "low":
        print("Tests failed and risk is not low — reverting change")
        # Revert by restoring from git
        subprocess.run(["git", "checkout", "--", file_path], cwd=REPO_ROOT)
        sys.exit(1)

    # Step 6: Open PR
    pr_url = create_pr(change, test_output, test_passed)
    if pr_url:
        print(f"\n✓ PR ready for review: {pr_url}")
    else:
        print("\nPR creation failed — change is applied locally but not pushed")

    print(f"\n{'='*60}")
    print(f"Code Agent complete — {change.get('description', '')}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EDON Code Agent")
    parser.add_argument("--dry-run", action="store_true", help="Show proposed changes without applying")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
