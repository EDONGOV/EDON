"""EDON Account Manager Agent — one per client, runs weekly.

Each client gets their own AM that knows their history, monitors their health,
and drafts proactive outreach when something needs attention.

Memory is stored in agents/am_memory/{tenant_id}.json — this is what makes
each AM feel like a dedicated person who knows the client, not a generic check-in.

Usage:
    # Run for a specific tenant
    ANTHROPIC_API_KEY=xxx EDON_API_TOKEN=xxx \\
      python -m agents.account_manager --tenant tenant_acme

    # Run for ALL tenants with a memory file (weekly batch)
    ANTHROPIC_API_KEY=xxx EDON_API_TOKEN=xxx \\
      python -m agents.account_manager --all

    # Create a new client memory file (do this after onboarding)
    python -m agents.account_manager --new '{
      "tenant_id": "tenant_acme",
      "company_name": "Acme Health",
      "contact_name": "John Smith",
      "contact_email": "cto@acme.com",
      "regulations": ["HIPAA", "HITECH"],
      "use_case": "Clinical AI assistant for EHR workflows"
    }'

GitHub Actions: see .github/workflows/account_manager.yml
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import requests
import anthropic

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GATEWAY_URL = os.environ.get("EDON_GATEWAY_URL", "https://edon-gateway.fly.dev").rstrip("/")
API_TOKEN = os.environ.get("EDON_API_TOKEN", "")

MEMORY_DIR = Path(__file__).parent / "am_memory"
MEMORY_DIR.mkdir(exist_ok=True)


# ── Memory ────────────────────────────────────────────────────────────────────

def _memory_path(tenant_id: str) -> Path:
    return MEMORY_DIR / f"{tenant_id}.json"


def load_memory(tenant_id: str) -> dict[str, Any]:
    path = _memory_path(tenant_id)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "tenant_id": tenant_id,
        "company_name": tenant_id,
        "contact_name": "",
        "contact_email": "",
        "plan": "unknown",
        "regulations": [],
        "use_case": "",
        "relationship_notes": "",
        "health_score": None,
        "last_contact_date": None,
        "observations": [],
        "open_items": [],
    }


def save_memory(memory: dict[str, Any]) -> None:
    path = _memory_path(memory["tenant_id"])
    path.write_text(json.dumps(memory, indent=2), encoding="utf-8")


def create_client(profile: dict[str, Any]) -> None:
    """Initialise a new client memory file from an onboarding profile."""
    tenant_id = profile["tenant_id"]
    memory = load_memory(tenant_id)
    memory.update({
        "company_name": profile.get("company_name", tenant_id),
        "contact_name": profile.get("contact_name", ""),
        "contact_email": profile.get("contact_email", ""),
        "plan": profile.get("plan", "starter"),
        "regulations": profile.get("regulations", []),
        "use_case": profile.get("use_case", ""),
        "relationship_notes": profile.get("relationship_notes", ""),
        "created_at": datetime.now(UTC).isoformat(),
    })
    save_memory(memory)
    print(f"[am] Client profile created: {_memory_path(tenant_id)}")


# ── Live data from gateway ────────────────────────────────────────────────────

def _headers(tenant_id: str) -> dict[str, str]:
    h = {"Content-Type": "application/json", "X-Tenant-ID": tenant_id}
    if API_TOKEN:
        h["X-EDON-TOKEN"] = API_TOKEN
    return h


def _get(path: str, tenant_id: str, params: dict | None = None) -> dict[str, Any]:
    try:
        r = requests.get(
            f"{GATEWAY_URL}{path}",
            headers=_headers(tenant_id),
            params=params or {},
            timeout=15,
        )
        if r.status_code == 200:
            return r.json()
        return {"_error": f"{r.status_code}", "_text": r.text[:200]}
    except Exception as exc:
        return {"_error": str(exc)}


def pull_client_data(tenant_id: str) -> dict[str, Any]:
    """Pull all live data we care about for this tenant."""
    print(f"  [am] Pulling live data for {tenant_id}...")

    timeseries = _get("/timeseries", tenant_id, {"days": 14})
    compliance = _get("/compliance/health", tenant_id)
    agents_data = _get("/agents", tenant_id)
    recent_decisions = _get("/decisions/query", tenant_id, {"limit": 20})
    stats = _get("/stats", tenant_id)

    # Compute decision volume trend from timeseries
    volume_trend = None
    if isinstance(timeseries, list) and len(timeseries) >= 2:
        ts_list: list[Any] = list(timeseries)
        first_half = ts_list[:7]
        second_half = ts_list[7:]
        week1 = sum(
            (p.get("allowed", 0) + p.get("blocked", 0) + p.get("confirm", 0))
            for p in first_half
        )
        week2 = sum(
            (p.get("allowed", 0) + p.get("blocked", 0) + p.get("confirm", 0))
            for p in second_half
        )
        volume_trend = {"week_prior": week1, "this_week": week2}

    return {
        "pulled_at": datetime.now(UTC).isoformat(),
        "timeseries": timeseries if isinstance(timeseries, list) else [],
        "compliance_health": compliance,
        "agents": agents_data,
        "recent_decisions": recent_decisions,
        "stats": stats,
        "volume_trend": volume_trend,
    }


# ── AM analysis ───────────────────────────────────────────────────────────────

def _summarise_timeseries(ts: list[dict]) -> str:
    if not ts:
        return "No timeseries data."
    lines = []
    for p in ts[-7:]:
        total = p.get("allowed", 0) + p.get("blocked", 0) + p.get("confirm", 0)
        lines.append(f"  {p.get('label', '?')}: {total} decisions "
                     f"(allow={p.get('allowed',0)} block={p.get('blocked',0)} escalate={p.get('confirm',0)})")
    return "\n".join(lines)


def run_account_review(tenant_id: str) -> dict[str, Any]:
    memory = load_memory(tenant_id)
    company = memory.get("company_name", tenant_id)
    print(f"[am] Running review for: {company} ({tenant_id})")

    live = pull_client_data(tenant_id)

    # Build observation for this week
    vt = live.get("volume_trend") or {}
    this_week = vt.get("this_week", 0)
    last_week = vt.get("week_prior", 0)
    compliance_status = (live.get("compliance_health") or {}).get("status", "unknown")

    observation = {
        "date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "this_week_volume": this_week,
        "last_week_volume": last_week,
        "compliance_status": compliance_status,
    }

    # Build context for Claude
    past_observations = memory.get("observations", [])[-4:]  # last 4 weeks
    open_items = memory.get("open_items", [])

    timeseries_summary = _summarise_timeseries(live.get("timeseries", []))
    agents_raw = live.get("agents", {})
    agents_summary = json.dumps(agents_raw, indent=2)[:600] if agents_raw else "No agent data."
    compliance_raw = live.get("compliance_health", {})
    compliance_summary = json.dumps(compliance_raw, indent=2)[:400] if compliance_raw else "No compliance data."

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""You are the dedicated account manager for {company}, a customer of EDON (AI governance platform).

## Client Profile
- Tenant ID: {tenant_id}
- Regulations: {', '.join(memory.get('regulations', []) or ['unknown'])}
- Use case: {memory.get('use_case', 'not specified')}
- Plan: {memory.get('plan', 'unknown')}
- Contact: {memory.get('contact_name', '')} <{memory.get('contact_email', '')}>
- Relationship notes: {memory.get('relationship_notes', 'none')}
- Last contact: {memory.get('last_contact_date', 'never')}

## Open items from previous reviews
{json.dumps(open_items, indent=2) if open_items else 'None'}

## Past 4 weeks of observations
{json.dumps(past_observations, indent=2) if past_observations else 'No history yet'}

## This week's live data

Decision volume (last 7 days):
{timeseries_summary}

Volume trend: last week={last_week} this week={this_week}

Compliance health: {compliance_summary}

Agent fleet: {agents_summary}

---

Your tasks:
1. **Health score** (0-100): assess the client's health based on usage trend, compliance status, and agent activity
2. **Observations**: note anything significant (volume drop >20%, compliance gap, no agent activity, escalation spike)
3. **Action required?**: decide YES or NO — does something need a proactive email to the client this week?
4. **Draft email** (only if action required): write a short, specific, helpful email. Subject line + body. Reference their actual data. No fluff.
5. **Open items**: list any items that need follow-up next week

Respond as JSON with this exact structure:
{{
  "health_score": <0-100>,
  "summary": "<one sentence>",
  "observations": ["<obs1>", "<obs2>"],
  "action_required": true/false,
  "action_reason": "<why action is needed, or null>",
  "email_subject": "<subject or null>",
  "email_body": "<body or null>",
  "open_items": ["<item1>"]
}}"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = str(getattr(msg.content[0], "text", msg.content[0]))

    # Parse JSON from Claude's response
    try:
        # Strip markdown code fences if present
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        result = json.loads(clean.strip())
    except Exception:
        result = {
            "health_score": None,
            "summary": "Parse error — see raw output",
            "observations": [raw[:500]],
            "action_required": False,
            "action_reason": None,
            "email_subject": None,
            "email_body": None,
            "open_items": [],
        }

    # Update memory
    observation["health_score"] = result.get("health_score")
    observation["summary"] = result.get("summary", "")
    memory["observations"] = (memory.get("observations") or []) + [observation]
    memory["health_score"] = result.get("health_score")
    memory["open_items"] = result.get("open_items", [])
    save_memory(memory)

    return {
        "tenant_id": tenant_id,
        "company_name": company,
        "contact_email": memory.get("contact_email", ""),
        **result,
    }


# ── Batch runner ──────────────────────────────────────────────────────────────

def run_all() -> list[dict[str, Any]]:
    """Run AM review for every client that has a memory file."""
    memory_files = sorted(MEMORY_DIR.glob("*.json"))
    if not memory_files:
        print("[am] No client memory files found. Create one with --new first.")
        return []

    print(f"[am] Running reviews for {len(memory_files)} client(s)...\n")
    results = []
    for mf in memory_files:
        tenant_id = mf.stem
        try:
            review = run_account_review(tenant_id)
            results.append(review)
            icon = "ACTION" if review.get("action_required") else "OK"
            score = review.get("health_score", "?")
            print(f"  [{icon}] {review['company_name']} — health={score} — {review.get('summary', '')}\n")
        except Exception as exc:
            print(f"  [ERROR] {tenant_id}: {exc}\n")
            results.append({"tenant_id": tenant_id, "error": str(exc)})

    return results


def print_weekly_report(results: list[dict[str, Any]]) -> None:
    print("\n" + "=" * 60)
    print(f"WEEKLY AM REPORT — {datetime.now(UTC).strftime('%Y-%m-%d')}")
    print("=" * 60)

    action_items = [r for r in results if r.get("action_required")]
    healthy = [r for r in results if not r.get("action_required") and not r.get("error")]
    errors = [r for r in results if r.get("error")]

    if action_items:
        print(f"\n{len(action_items)} client(s) need attention:\n")
        for r in action_items:
            print(f"  {r['company_name']} ({r['tenant_id']}) — health={r.get('health_score', '?')}")
            print(f"  Reason: {r.get('action_reason', '')}")
            print(f"\n  --- EMAIL TO {r.get('contact_email', '(no email)')} ---")
            print(f"  Subject: {r.get('email_subject', '')}")
            print(f"\n{r.get('email_body', '')}\n")
            print("  " + "-" * 50 + "\n")

    print(f"{len(healthy)} client(s) healthy — no action needed")
    if errors:
        print(f"{len(errors)} error(s): {[e['tenant_id'] for e in errors]}")
    print("=" * 60)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="EDON Account Manager Agent")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tenant", help="Run review for a specific tenant ID")
    group.add_argument("--all", action="store_true", help="Run review for all clients")
    group.add_argument("--new", metavar="JSON", help="Create new client memory from JSON string")
    group.add_argument("--list", action="store_true", help="List all client memory files")
    args = parser.parse_args()

    if args.list:
        files = sorted(MEMORY_DIR.glob("*.json"))
        if not files:
            print("No clients yet. Use --new to add one.")
        for f in files:
            m = json.loads(f.read_text())
            score = m.get("health_score", "?")
            last = m.get("last_contact_date", "never")
            print(f"  {m.get('company_name', f.stem)} ({f.stem}) — health={score} last_contact={last}")
        return 0

    if args.new:
        profile = json.loads(args.new)
        create_client(profile)
        return 0

    if args.tenant:
        review = run_account_review(args.tenant)
        print("\n" + "=" * 60)
        print(f"Review: {review['company_name']}")
        print("=" * 60)
        print(f"Health score: {review.get('health_score', '?')}")
        print(f"Summary: {review.get('summary', '')}")
        if review.get("action_required"):
            print(f"\nACTION REQUIRED: {review.get('action_reason', '')}")
            print(f"\n--- EMAIL TO {review.get('contact_email', '(no email)')} ---")
            print(f"Subject: {review.get('email_subject', '')}\n")
            print(review.get("email_body", ""))
        else:
            print("\nNo action needed this week.")
        print("=" * 60)
        return 0

    if args.all:
        results = run_all()
        print_weekly_report(results)
        # Write report artifact for CI
        report_path = Path(__file__).parent / "am_weekly_report.json"
        report_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\n[am] Full report saved to {report_path}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
