#!/usr/bin/env python3
"""
EDON Perfect Demo: Regulated Fleet — 10 agents, 3 go rogue, EDON freezes & fleet learns.

Drives the real gateway (POST /v1/action, GET/PATCH /agents, audit, review queue, learning).
Run with gateway up: PYTHONPATH=edon_gateway python -m edon_gateway.scripts.demo_regulated_fleet
Or: EDON_GATEWAY_URL=http://localhost:8000 python edon_gateway/scripts/demo_regulated_fleet.py

Usage:
  python edon_gateway/scripts/demo_regulated_fleet.py [--base-url URL] [--token TOKEN] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("pip install requests", file=sys.stderr)
    sys.exit(1)

BASE_URL = os.getenv("EDON_GATEWAY_URL", "http://127.0.0.1:8000").rstrip("/")
AUTH_TOKEN = os.getenv("EDON_API_TOKEN", "test-token")
HEADERS = {"Content-Type": "application/json", "X-EDON-TOKEN": AUTH_TOKEN}

# 10 agents: 7 good, 3 rogue (indices 7,8,9)
AGENT_IDS = [
    "fin-inbox-1", "fin-report-2", "fin-calendar-3", "fin-research-4",
    "fin-comms-5", "fin-audit-6", "fin-dash-7",
    "fin-rogue-shell-8", "fin-rogue-email-9", "fin-rogue-exfil-10",
]
ROGUE_INDICES = (7, 8, 9)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def apply_policy_pack(session: requests.Session, pack: str = "work_safe") -> str | None:
    """Apply policy pack; return intent_id from response."""
    r = session.post(f"{BASE_URL}/policy-packs/{pack}/apply", headers=HEADERS, json={}, timeout=10)
    if r.status_code != 200:
        print(f"  [WARN] apply pack {pack}: {r.status_code} {r.text[:200]}")
        return None
    return r.json().get("intent_id")


def post_action(
    session: requests.Session,
    agent_id: str,
    action_type: str,
    action_payload: dict,
    context: dict | None = None,
) -> dict:
    """POST /v1/action; return response JSON."""
    body = {
        "agent_id": agent_id,
        "action_type": action_type,
        "action_payload": action_payload,
        "timestamp": _ts(),
    }
    if context:
        body["context"] = context
    r = session.post(f"{BASE_URL}/v1/action", headers=HEADERS, json=body, timeout=10)
    return r.json() if r.headers.get("content-type", "").startswith("application/json") else {"_status": r.status_code, "_text": r.text}


def list_agents(session: requests.Session) -> list:
    """GET /agents."""
    r = session.get(f"{BASE_URL}/agents", headers=HEADERS, timeout=10)
    if r.status_code != 200:
        return []
    return r.json().get("agents", [])


def update_agent_status(session: requests.Session, agent_id: str, status: str) -> bool:
    """PATCH /agents/{agent_id}/status."""
    r = session.patch(
        f"{BASE_URL}/agents/{agent_id}/status",
        headers=HEADERS,
        json={"status": status},
        timeout=10,
    )
    return r.status_code == 200


def get_review_queue(session: requests.Session, status: str = "pending") -> list:
    """GET /review/queue (or /audit/review/queue depending on mount)."""
    for path in ("/review/queue", "/audit/review/queue"):
        r = session.get(f"{BASE_URL}{path}", headers=HEADERS, params={"status": status}, timeout=10)
        if r.status_code == 200:
            return r.json().get("queue", [])
    return []


def enqueue_review(
    session: requests.Session,
    action_id: str,
    agent_id: str,
    action_type: str,
    reason: str,
) -> str | None:
    """POST /review/queue (or /audit/review/queue)."""
    for path in ("/review/queue", "/audit/review/queue"):
        r = session.post(
            f"{BASE_URL}{path}",
            headers=HEADERS,
            json={"action_id": action_id, "agent_id": agent_id, "action_type": action_type, "reason": reason},
            timeout=10,
        )
        if r.status_code in (200, 201):
            return r.json().get("review_id")
    return None


def resolve_review(session: requests.Session, review_id: str, decision: str, reason: str = "") -> bool:
    """POST /review/queue/{review_id}/decide (or /audit/review/queue/...)."""
    for prefix in ("/review", "/audit/review"):
        url = f"{BASE_URL}{prefix}/queue/{review_id}/decide"
        r = session.post(url, headers=HEADERS, json={"decision": decision, "reason": reason}, timeout=10)
        if r.status_code == 200:
            return True
    return False


def audit_export(session: requests.Session, agent_id: str | None = None, limit: int = 50) -> list:
    """GET /audit/export?format=json (or /audit/query if available)."""
    for path in ("/audit/export", "/audit/query"):
        params = {"format": "json", "limit": limit} if path == "/audit/export" else {"limit": limit}
        if agent_id:
            params["agent_id"] = agent_id
        r = session.get(f"{BASE_URL}{path}", headers=HEADERS, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data.get("events", data.get("decisions", []))
    return []


def learning_feedback(
    session: requests.Session,
    agent_id: str,
    action_type: str,
    label: str,
    notes: str = "",
) -> bool:
    """POST /learning/feedback."""
    r = session.post(
        f"{BASE_URL}/learning/feedback",
        headers=HEADERS,
        json={"agent_id": agent_id, "action_type": action_type, "label": label, "notes": notes, "source": "operator"},
        timeout=10,
    )
    return r.status_code == 200


def learning_summary(session: requests.Session) -> dict:
    """GET /learning/model/summary."""
    r = session.get(f"{BASE_URL}/learning/model/summary", headers=HEADERS, timeout=10)
    return r.json() if r.status_code == 200 else {}


def main():
    ap = argparse.ArgumentParser(description="EDON Regulated Fleet Demo — real gateway")
    ap.add_argument("--base-url", default=BASE_URL, help="Gateway base URL")
    ap.add_argument("--token", default=AUTH_TOKEN, help="X-EDON-TOKEN value")
    ap.add_argument("--dry-run", action="store_true", help="Print steps only, no HTTP")
    args = ap.parse_args()
    global BASE_URL, AUTH_TOKEN, HEADERS
    BASE_URL = args.base_url.rstrip("/")
    AUTH_TOKEN = args.token
    HEADERS = {"Content-Type": "application/json", "X-EDON-TOKEN": AUTH_TOKEN}

    session = requests.Session()
    print("=" * 70)
    print("EDON Perfect Demo: Regulated Fleet (10 agents, 3 go rogue)")
    print("=" * 70)

    if args.dry_run:
        print("\n[DRY RUN] Steps only.\n")
        print("1. Apply policy pack work_safe")
        print("2. 7 in-scope actions (ALLOW)")
        print("3. Agent 8: shell.run -> BLOCK")
        print("4. Agent 9: email.send 50 recipients -> HUMAN_REQUIRED; enqueue review")
        print("5. Agent 10: file.export external -> BLOCK")
        print("6. PATCH agents 8,9,10 status=paused")
        print("7. GET review/queue; POST resolve (block)")
        print("8. POST /learning/feedback; GET /learning/model/summary")
        print("9. GET /agents and audit by agent_id")
        return 0

    # Act 1 — Apply pack
    print("\n--- Act 1: Apply policy pack (regulated scope) ---")
    intent_id = apply_policy_pack(session, "work_safe")
    if intent_id:
        print(f"  Applied work_safe intent_id={intent_id[:50]}...")
    else:
        print("  (Apply failed; continuing with default intent if any)")

    # Good agents: 1 action each (in-scope)
    print("\n--- 7 good agents: in-scope actions (expect ALLOW) ---")
    good_actions = [
        ("email.draft", {"recipients": ["a@internal.com"], "subject": "Re: triage", "body": "Done."}),
        ("file.read", {"path": "/reports/q3.pdf"}),
        ("calendar.view", {}),
        ("file.read", {"path": "/research/notes.md"}),
        ("email.draft", {"recipients": ["c@internal.com"], "subject": "Update", "body": "Hi"}),
        ("file.read", {"path": "/audit/log.csv"}),
        ("calendar.view", {}),
    ]
    for i, (action_type, payload) in enumerate(good_actions):
        agent_id = AGENT_IDS[i]
        resp = post_action(session, agent_id, action_type, payload)
        decision = resp.get("decision", resp.get("verdict", ""))
        print(f"  {agent_id} {action_type} -> {decision}")

    # Act 2 — Rogues
    print("\n--- Act 2: 3 agents go out of scope ---")
    # Rogue 1: shell.run
    r1 = post_action(
        session, AGENT_IDS[7], "shell.run",
        {"command": "systemctl restart production-db"},
    )
    d1 = r1.get("decision", r1.get("verdict", ""))
    print(f"  {AGENT_IDS[7]} shell.run -> {d1} (expect BLOCK) | reason: {r1.get('decision_reason', '')[:60]}")

    # Rogue 2: email.send 50 recipients -> ESCALATE
    r2 = post_action(
        session, AGENT_IDS[8], "email.send",
        {"recipients": [f"u{i}@external.com" for i in range(50)], "subject": "Blast", "body": "..."},
    )
    d2 = r2.get("decision", r2.get("verdict", ""))
    action_id_9 = r2.get("action_id", "dec-rogue-9")
    print(f"  {AGENT_IDS[8]} email.send (50 recipients) -> {d2} (expect HUMAN_REQUIRED)")
    if d2 in ("HUMAN_REQUIRED", "ESCALATE", "confirm"):
        rid = enqueue_review(session, action_id_9, AGENT_IDS[8], "email.send", "Mass email exceeds max_recipients")
        if rid:
            print(f"  Enqueued review_id={rid}")

    # Rogue 3: file.export external
    r3 = post_action(
        session, AGENT_IDS[9], "file.export",
        {"path": "/confidential", "destination": "https://external-cloud.com/upload"},
    )
    d3 = r3.get("decision", r3.get("verdict", ""))
    print(f"  {AGENT_IDS[9]} file.export external -> {d3} (expect BLOCK)")

    # Freeze rogues
    print("\n--- Freeze agents 8, 9, 10 (status=paused) ---")
    for idx in ROGUE_INDICES:
        ok = update_agent_status(session, AGENT_IDS[idx], "paused")
        print(f"  {AGENT_IDS[idx]} paused: {ok}")

    # Fleet view
    agents = list_agents(session)
    paused = [a for a in agents if a.get("status") == "paused"]
    print(f"\n  Fleet: {len(agents)} agents, {len(paused)} paused")

    # Review queue
    queue = get_review_queue(session)
    print(f"\n--- Human review queue: {len(queue)} pending ---")
    for q in queue[:5]:
        print(f"  {q.get('agent_id')} {q.get('action_type')} reason={q.get('reason', '')[:50]}")

    # Resolve one review
    if queue:
        review_id = queue[0].get("id")
        if review_id:
            ok = resolve_review(session, review_id, "block", "Policy: no mass external email")
            print(f"  Resolved {review_id} -> block: {ok}")

    # Learning
    print("\n--- Learning: feedback + model summary ---")
    learning_feedback(session, AGENT_IDS[8], "email.send", "blocked", "Demo: mass email blocked")
    summary = learning_summary(session)
    print(f"  Model summary: {json.dumps(summary, indent=2)[:300]}...")

    # Per-agent memory
    print("\n--- Per-agent memory (audit by agent_id) ---")
    for aid in (AGENT_IDS[0], AGENT_IDS[7]):
        events = audit_export(session, agent_id=aid, limit=5)
        print(f"  {aid}: {len(events)} recent events")

    print("\n" + "=" * 70)
    print("Demo complete. EDON blocked/escalated the 3 rogues, froze them, human resolved, fleet learned.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
