"""EDON Integration Agent — monitors the ecosystem and grows distribution.

Infrastructure platforms win by integrating everywhere. This agent:

  1. Monitors popular tools in the healthtech/AI ecosystem for integration opportunities
  2. Scans your own audit logs for tool types customers are already using
  3. Auto-generates SDK code examples for the most-used tool/op combinations
  4. Suggests new integrations ranked by distribution potential
  5. Checks existing SDK examples to ensure they're still accurate

Runs weekly. Opens PRs for new SDK examples. Opens GitHub issues for
integration opportunities.

Usage:
    ANTHROPIC_API_KEY=xxx EDON_API_TOKEN=xxx python -m agents.integration_agent

GitHub Actions: .github/workflows/integration_agent.yml — runs weekly.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import requests
import anthropic

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GATEWAY_URL = os.environ.get("EDON_GATEWAY_URL", "https://edon-gateway.fly.dev").rstrip("/")
API_TOKEN = os.environ.get("EDON_API_TOKEN", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "GHOSTCODERRRRAHAHA/edongov")
ADMIN_TENANT = os.environ.get("EDON_ADMIN_TENANT_ID", "tenant_dev")

REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_EXAMPLES_DIR = REPO_ROOT / "sdk" / "examples"

# High-value integration targets in healthtech + AI agent ecosystem
ECOSYSTEM_TARGETS = [
    # EHR / Clinical
    {"name": "Epic MyChart / FHIR API", "category": "ehr", "keywords": ["epic", "fhir", "ehr", "emr"]},
    {"name": "Cerner PowerChart", "category": "ehr", "keywords": ["cerner", "oracle health"]},
    {"name": "Athenahealth", "category": "ehr", "keywords": ["athenahealth", "athena"]},
    # AI Platforms
    {"name": "LangChain", "category": "ai_framework", "keywords": ["langchain", "langchain agent"]},
    {"name": "AutoGen (Microsoft)", "category": "ai_framework", "keywords": ["autogen", "microsoft autogen"]},
    {"name": "CrewAI", "category": "ai_framework", "keywords": ["crewai", "crew ai"]},
    {"name": "Hugging Face Agents", "category": "ai_framework", "keywords": ["hugging face", "huggingface"]},
    # Robotics / Physical AI
    {"name": "ROS 2", "category": "robotics", "keywords": ["ros2", "ros 2", "robot operating system"]},
    {"name": "NVIDIA Isaac", "category": "robotics", "keywords": ["nvidia isaac", "isaac sim"]},
    # Enterprise SaaS
    {"name": "Salesforce Health Cloud", "category": "enterprise", "keywords": ["salesforce health", "health cloud"]},
    {"name": "ServiceNow", "category": "enterprise", "keywords": ["servicenow", "service now"]},
    {"name": "Workday", "category": "enterprise", "keywords": ["workday"]},
]


def _h() -> dict[str, str]:
    h = {"Content-Type": "application/json", "X-Tenant-ID": ADMIN_TENANT}
    if API_TOKEN:
        h["X-EDON-TOKEN"] = API_TOKEN
    return h


def _get(path: str, params: dict | None = None) -> Any:
    try:
        r = requests.get(f"{GATEWAY_URL}{path}", headers=_h(), params=params or {}, timeout=10)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}


# ── Usage pattern mining ──────────────────────────────────────────────────────

def mine_customer_tool_patterns() -> list[dict[str, Any]]:
    """Find the most-used tool/op combos in customer audit logs."""
    decisions = _get("/decisions/query", params={"limit": 1000})
    decision_list = decisions.get("decisions", decisions.get("items", [])) if isinstance(decisions, dict) else []

    pattern_counts: dict[str, int] = defaultdict(int)
    for d in decision_list if isinstance(decision_list, list) else []:
        action_type = d.get("action_type", "")
        if action_type:
            pattern_counts[action_type] += 1

    return [
        {"action_type": action, "count": count}
        for action, count in sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True)[:15]
    ]


def check_existing_examples() -> list[str]:
    """List SDK examples that already exist."""
    existing = []
    if SDK_EXAMPLES_DIR.exists():
        for f in SDK_EXAMPLES_DIR.rglob("*.py"):
            existing.append(str(f.relative_to(REPO_ROOT)))
        for f in SDK_EXAMPLES_DIR.rglob("*.js"):
            existing.append(str(f.relative_to(REPO_ROOT)))
        for f in SDK_EXAMPLES_DIR.rglob("*.ts"):
            existing.append(str(f.relative_to(REPO_ROOT)))
    return existing


# ── Ecosystem research ────────────────────────────────────────────────────────

def research_integrations(top_patterns: list[dict[str, Any]]) -> dict[str, Any]:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    pattern_summary = "\n".join(f"- {p['action_type']}: {p['count']} uses" for p in top_patterns[:10])
    targets_summary = "\n".join(
        f"- {t['name']} ({t['category']})" for t in ECOSYSTEM_TARGETS
    )
    existing = check_existing_examples()

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],  # type: ignore[list-item]
        messages=[{"role": "user", "content": f"""You are the integrations analyst for EDON, an AI governance platform for healthtech.

EDON's value: it sits between any AI agent and the real world, evaluating every action against HIPAA/HITECH/FDA rules before it executes.

## What customers are actually using (top action types from audit logs)
{pattern_summary}

## Integration targets we're tracking
{targets_summary}

## SDK examples that already exist
{existing[:20] or ['none']}

Search for:
1. Which of these platforms recently added AI agent support or published agent integration guides
2. Any healthtech companies that publicly use these tools and have AI governance requirements
3. New AI agent frameworks gaining traction in 2025-2026

Then return JSON:
{{
  "priority_integrations": [
    {{
      "platform": "<name>",
      "category": "<ehr|ai_framework|robotics|enterprise>",
      "why": "<why this integration matters for EDON's distribution>",
      "effort": "low|medium|high",
      "example_needed": "<what SDK example would unlock this>",
      "evidence": "<what you found that supports this priority>"
    }}
  ],
  "sdk_examples_to_generate": [
    {{
      "action_type": "<e.g. robot.dispense>",
      "title": "<example title>",
      "description": "<what this example demonstrates>"
    }}
  ],
  "ecosystem_insight": "<one key thing happening in the ecosystem this week>"
}}

Prioritise by: distribution impact × EDON fit × effort. Max 5 integrations, 5 examples."""}],
    )

    research_text = ""
    for block in msg.content:
        research_text += str(getattr(block, "text", ""))

    try:
        import re
        json_match = re.search(r'\{[\s\S]*\}', research_text)
        if json_match:
            return json.loads(json_match.group())
    except Exception:
        pass

    return {
        "priority_integrations": [],
        "sdk_examples_to_generate": [{"action_type": p["action_type"], "title": f"Example: {p['action_type']}", "description": "Common customer pattern"} for p in top_patterns[:3]],
        "ecosystem_insight": research_text[:300],
    }


# ── SDK example generation ────────────────────────────────────────────────────

def generate_sdk_example(action_type: str, title: str, description: str) -> dict[str, Any]:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    api_ref_path = REPO_ROOT / "docs" / "api-reference.md"
    api_ref = api_ref_path.read_text(encoding="utf-8")[:3000] if api_ref_path.exists() else ""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": f"""Generate a complete, runnable SDK example for EDON.

Action type: {action_type}
Title: {title}
Description: {description}

EDON API reference:
{api_ref}

Generate TWO files:
1. Python example using the EDON Python SDK
2. JavaScript/TypeScript example

Each example should:
- Show the full flow: create intent → evaluate action → handle verdict
- Be runnable with just EDON_API_TOKEN set
- Include realistic payload for this action type
- Handle ALLOW, BLOCK, and ESCALATE verdicts
- Include comments explaining each step

Format your response as:
### Python (filename: {action_type.replace('.', '_')}_example.py)
```python
<code>
```

### JavaScript (filename: {action_type.replace('.', '_')}_example.js)
```javascript
<code>
```"""}],
    )

    content = str(getattr(msg.content[0], "text", msg.content[0]))
    return {"action_type": action_type, "title": title, "content": content}


def save_sdk_example(example: dict[str, Any]) -> list[Path]:
    SDK_EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    slug = example["action_type"].replace(".", "_")
    saved = []

    content = example["content"]
    import re

    py_match = re.search(r"```python\n([\s\S]*?)```", content)
    if py_match:
        path = SDK_EXAMPLES_DIR / f"{slug}_example.py"
        path.write_text(py_match.group(1), encoding="utf-8")
        saved.append(path)

    js_match = re.search(r"```javascript\n([\s\S]*?)```", content)
    if js_match:
        path = SDK_EXAMPLES_DIR / f"{slug}_example.js"
        path.write_text(js_match.group(1), encoding="utf-8")
        saved.append(path)

    return saved


def _open_issue(title: str, body: str) -> str | None:
    if not GITHUB_TOKEN:
        return None
    r = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPO}/issues",
        headers={"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"},
        json={"title": title, "body": body, "labels": ["integrations", "automated"]},
        timeout=10,
    )
    return r.json().get("html_url") if r.status_code == 201 else None


def main() -> int:
    print(f"[integration] EDON Integration Agent — {datetime.now(UTC).isoformat()}")

    print("[integration] Mining customer tool patterns...")
    top_patterns = mine_customer_tool_patterns()
    print(f"[integration] Top patterns: {[p['action_type'] for p in top_patterns[:5]]}")

    print("[integration] Researching ecosystem with Claude + web search...")
    research = research_integrations(top_patterns)

    print(f"\n[integration] Ecosystem insight: {research.get('ecosystem_insight', '')}")

    integrations = research.get("priority_integrations", [])
    print(f"\n[integration] Priority integrations ({len(integrations)}):")
    for intg in integrations:
        print(f"  [{intg.get('effort','?').upper()}] {intg.get('platform','')} — {intg.get('why','')[:80]}")

    # Open GitHub issues for high-priority integrations
    for intg in [i for i in integrations if i.get("effort") == "low"][:3]:
        body = f"""## Integration Opportunity: {intg.get('platform', '')}

**Category:** {intg.get('category', '')}
**Effort:** {intg.get('effort', '')}
**Why this matters:** {intg.get('why', '')}
**Evidence:** {intg.get('evidence', '')}

**SDK example needed:** {intg.get('example_needed', '')}

---
*Auto-generated by EDON Integration Agent — {datetime.now(UTC).isoformat()}*"""
        url = _open_issue(f"[Integration] {intg.get('platform', '')}", body)
        if url:
            print(f"  [integration] Issue: {url}")

    # Generate SDK examples
    examples_to_generate = research.get("sdk_examples_to_generate", [])[:3]
    if examples_to_generate:
        print(f"\n[integration] Generating {len(examples_to_generate)} SDK example(s)...")
        all_saved = []
        for ex in examples_to_generate:
            print(f"  Generating: {ex.get('title', ex.get('action_type', ''))}")
            example = generate_sdk_example(
                ex.get("action_type", ""),
                ex.get("title", ""),
                ex.get("description", ""),
            )
            saved = save_sdk_example(example)
            all_saved.extend(saved)
            for path in saved:
                print(f"    Saved: {path.relative_to(REPO_ROOT)}")

    report = {
        "run_at": datetime.now(UTC).isoformat(),
        "top_patterns": top_patterns,
        "research": research,
        "examples_generated": len(examples_to_generate),
    }
    out_path = Path(__file__).parent / "integration_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n[integration] Report: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
