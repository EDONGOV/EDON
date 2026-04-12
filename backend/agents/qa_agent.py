"""EDON QA Agent — nightly clinical safety regression runner.

Activates clinical safety mode on the QA tenant, fires a test payload for
every rule in CLINICAL_SAFETY_RULES, verifies the expected verdict comes back,
then uses the Claude API to write a plain-English analysis.

If any rules fail, creates a GitHub issue automatically.

Usage (local):
    EDON_API_TOKEN=xxx EDON_GATEWAY_URL=https://edon-gateway.fly.dev \\
    ANTHROPIC_API_KEY=xxx GITHUB_TOKEN=xxx \\
    python -m agents.qa_agent

GitHub Actions: see .github/workflows/nightly_qa.yml
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, UTC
from typing import Any

import requests
import anthropic

# ── Config ────────────────────────────────────────────────────────────────────

GATEWAY_URL = os.environ.get("EDON_GATEWAY_URL", "https://edon-gateway.fly.dev").rstrip("/")
API_TOKEN = os.environ["EDON_API_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "EDONGOV/EDON")
QA_AGENT_ID = "edon-qa-agent-nightly"
QA_TENANT_ID = os.environ.get("EDON_QA_TENANT_ID", "tenant_dev")

# Default op to use when a rule's condition_op is None
_DEFAULT_OPS: dict[str, str] = {
    "email":   "send",
    "file":    "write",
    "shell":   "execute",
    "robot":   "execute",
    "vehicle": "move",
    "scanner": "scan",
    "drone":   "fly",
    "browser": "navigate",
    "database":"query",
    "http":    "request",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _headers() -> dict[str, str]:
    return {
        "X-EDON-TOKEN": API_TOKEN,
        "X-Tenant-ID": QA_TENANT_ID,
        "Content-Type": "application/json",
    }


def _action_type(rule: dict[str, Any]) -> str:
    tool = rule.get("condition_tool") or "file"
    op = rule.get("condition_op") or _DEFAULT_OPS.get(tool, "execute")
    return f"{tool}.{op}"


def _build_payload(rule: dict[str, Any]) -> dict[str, Any]:
    """Build a /v1/action request that should trigger this rule."""
    risk = rule.get("condition_risk_level") or "low"
    tags = rule.get("condition_tags") or []
    return {
        "agent_id": QA_AGENT_ID,
        "action_type": _action_type(rule),
        "action_payload": {
            "qa_test": True,
            "rule_code": rule["rule_code"],
            "tags": tags,
        },
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "context": {
            "risk_estimate": risk,
            "tags": tags,
            "qa_mode": True,
        },
    }


def activate_clinical_safety() -> dict[str, Any]:
    r = requests.post(
        f"{GATEWAY_URL}/compliance/clinical-safety/activate",
        headers=_headers(),
        json={"activated_by": QA_AGENT_ID},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def evaluate_action(payload: dict[str, Any]) -> dict[str, Any]:
    r = requests.post(
        f"{GATEWAY_URL}/v1/action",
        headers=_headers(),
        json=payload,
        timeout=15,
    )
    # Return raw response so we can inspect non-200s too
    try:
        return {"status": r.status_code, **r.json()}
    except Exception:
        return {"status": r.status_code, "raw": r.text}


# ── Core test runner ──────────────────────────────────────────────────────────

def run_tests() -> dict[str, Any]:
    # Import rules from the live module — always tests current code
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from edon_gateway.clinical_safety import CLINICAL_SAFETY_RULES

    print(f"[qa] Activating clinical safety mode for tenant={QA_TENANT_ID}...")
    activation = activate_clinical_safety()
    print(f"[qa] {activation.get('message', 'activated')}")

    results: list[dict[str, Any]] = []

    for rule in CLINICAL_SAFETY_RULES:
        rule_code = rule["rule_code"]
        expected_verdict = rule["action"]  # "BLOCK" or "ESCALATE"
        payload = _build_payload(rule)

        try:
            resp = evaluate_action(payload)
            # v1 API maps ESCALATE → HUMAN_REQUIRED
            actual = resp.get("verdict") or resp.get("decision", {}).get("verdict", "UNKNOWN")
            # Normalise: HUMAN_REQUIRED is ESCALATE for our purposes
            if actual == "HUMAN_REQUIRED":
                actual = "ESCALATE"

            passed = actual == expected_verdict
            results.append({
                "rule_code": rule_code,
                "regulation": rule["regulation"],
                "name": rule["name"],
                "expected": expected_verdict,
                "actual": actual,
                "passed": passed,
                "http_status": resp.get("status"),
                "reason": resp.get("reason_code", ""),
            })
            icon = "PASS" if passed else "FAIL"
            print(f"  [{icon}] {rule_code}: expected={expected_verdict} actual={actual}")

        except Exception as exc:
            results.append({
                "rule_code": rule_code,
                "regulation": rule["regulation"],
                "name": rule["name"],
                "expected": expected_verdict,
                "actual": "ERROR",
                "passed": False,
                "error": str(exc),
            })
            print(f"  [ERROR] {rule_code}: {exc}")

    passed_count = sum(1 for r in results if r["passed"])
    failed_count = len(results) - passed_count

    return {
        "run_at": datetime.now(UTC).isoformat(),
        "gateway": GATEWAY_URL,
        "total": len(results),
        "passed": passed_count,
        "failed": failed_count,
        "results": results,
    }


# ── Claude analysis ───────────────────────────────────────────────────────────

def generate_analysis(report: dict[str, Any]) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    summary_lines = []
    for r in report["results"]:
        status = "PASS" if r["passed"] else "FAIL"
        summary_lines.append(
            f"- [{status}] {r['rule_code']} ({r['regulation']}): "
            f"expected={r['expected']} actual={r['actual']}"
            + (f" error={r.get('error', '')}" if r.get("error") else "")
        )

    prompt = f"""You are the QA agent for EDON, an AI governance platform.
You just ran a nightly regression test against the live gateway at {report['gateway']}.
The test fires a payload for every clinical safety rule and checks the expected verdict fires.

Results: {report['passed']}/{report['total']} passed, {report['failed']} failed.
Run at: {report['run_at']}

Full results:
{chr(10).join(summary_lines)}

Write a concise report (plain markdown, no fluff) with:
1. A one-line status summary
2. If there are failures: what broke, which regulations are affected, and a suggested fix
3. If all passed: confirmation that coverage is clean

Keep it under 300 words. This will be posted as a GitHub issue or Slack message."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return str(getattr(msg.content[0], "text", msg.content[0]))


# ── GitHub issue ──────────────────────────────────────────────────────────────

def open_github_issue(title: str, body: str) -> str | None:
    if not GITHUB_TOKEN:
        print("[qa] GITHUB_TOKEN not set — skipping issue creation")
        return None

    url = f"https://api.github.com/repos/{GITHUB_REPO}/issues"
    r = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
        json={
            "title": title,
            "body": body,
            "labels": ["qa-regression", "automated"],
        },
        timeout=15,
    )
    if r.status_code == 201:
        issue_url = r.json().get("html_url", "")
        print(f"[qa] Issue created: {issue_url}")
        return issue_url
    else:
        print(f"[qa] Failed to create issue: {r.status_code} {r.text[:200]}")
        return None


# ── Entrypoint ────────────────────────────────────────────────────────────────

def main() -> int:
    print(f"[qa] EDON QA Agent starting — {datetime.now(UTC).isoformat()}")
    print(f"[qa] Gateway: {GATEWAY_URL}")

    report = run_tests()

    print(f"\n[qa] Results: {report['passed']}/{report['total']} passed")

    print("[qa] Generating analysis with Claude...")
    analysis = generate_analysis(report)

    print("\n" + "=" * 60)
    print(analysis)
    print("=" * 60 + "\n")

    # Write report artifact
    report_path = os.path.join(os.path.dirname(__file__), "qa_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"[qa] Full report written to {report_path}")

    if report["failed"] > 0:
        failures = [r for r in report["results"] if not r["passed"]]
        affected_regs = sorted({r["regulation"] for r in failures})
        title = (
            f"[QA REGRESSION] {report['failed']} clinical safety rule(s) failing "
            f"— {', '.join(affected_regs)}"
        )
        body = f"{analysis}\n\n---\n<details><summary>Raw results</summary>\n\n```json\n{json.dumps(report, indent=2)}\n```\n</details>"
        open_github_issue(title, body)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
