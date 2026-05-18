"""EDON Healthcare — Governance Quickstart

EDON is a pure governance layer. You already have an AI agent.
This script shows the two calls you add around every action it takes:

    client.evaluate()    — ask EDON before your agent acts
    client.scan_output() — ask EDON before your agent uses the result

EDON never executes anything. You own the agent and the execution.
EDON owns the decision of whether it should happen.

Requirements:
    pip install edon-sdk httpx
    export EDON_API_KEY="edon-..."

Run:
    python sdk/examples/healthcare_quickstart.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import httpx
from edon_sdk import EdonClient, AuthenticationError, APIConnectionError

GATEWAY = os.environ.get("EDON_GATEWAY_URL", "https://edon-gateway-prod.fly.dev")
API_KEY = os.environ.get("EDON_API_KEY", "")
SEP = "─" * 60

if not API_KEY:
    print("\n⛔  Set EDON_API_KEY first.")
    print("    Sign up: POST https://edon-gateway-prod.fly.dev/auth/register")
    sys.exit(1)

try:
    client = EdonClient(token=API_KEY, base_url=GATEWAY, agent_id="clinical-ai-agent")
    health = client.health()
except (APIConnectionError, AuthenticationError) as e:
    print(f"\n⛔  {e}")
    sys.exit(1)

print(f"\n{SEP}")
print(f"  EDON Healthcare Governance Quickstart")
print(f"  Gateway: {health.get('status', 'unknown')}")
print(SEP)


# ── Step 1: Apply HIPAA + Clinical Governance templates ───────────────────────
# One-time setup. Creates the policy rules that govern your tenant.
# Do this once when onboarding; skip on subsequent runs (rules are preserved).

print("\nApplying compliance templates…")
headers = {"X-EDON-TOKEN": API_KEY}
for tid in ("hipaa", "clinical_governance"):
    r = httpx.post(f"{GATEWAY}/policy/templates/{tid}/apply", headers=headers, timeout=10)
    if r.is_success:
        d = r.json()
        print(f"  ✅ {d['template_name']}: {d['rules_created']} rules created")
    else:
        print(f"  ⚠️  {tid}: {r.status_code}")


# ── The two calls you add to your existing agent ──────────────────────────────

def governed(action_type: str, payload: dict, stated_intent: str = "") -> dict | None:
    """
    Wrap any action your clinical AI agent is about to take.

    1. evaluate()    — EDON decides: ALLOW / BLOCK / ESCALATE / DEGRADE
    2. your code     — runs the actual action (not shown here — that's your system)
    3. scan_output() — EDON scans the result for PHI before your agent uses it

    Returns the safe result payload, or None if blocked.
    """
    # ── Before acting ─────────────────────────────────────────────────────────
    decision = client.evaluate(
        action_type=action_type,
        payload=payload,
        stated_intent=stated_intent,
    )

    verdict = decision["verdict"]
    print(f"\n  action:    {action_type}")
    print(f"  verdict:   {verdict}  {decision.get('reason_code', '')}")
    if decision.get("explanation"):
        print(f"  detail:    {decision['explanation'][:80]}")

    if verdict == "BLOCK":
        print("  → Your agent should NOT execute this action.")
        return None

    if verdict == "ESCALATE":
        print(f"  → Queue for human review: {decision.get('escalation_question', 'review required')}")
        print("    See console.edoncore.com → Review Queue")
        return None

    if verdict == "DEGRADE":
        print("  → Use safe_alternative params instead of original.")
        payload = decision.get("safe_alternative") or payload

    # ── Your agent executes here (EDON does not do this) ──────────────────────
    # result = your_ehr_system.call(action_type, payload)
    # We use a mock result below to demonstrate scan_output.
    result = _mock_result(action_type)

    # ── After getting a result ────────────────────────────────────────────────
    scan = client.scan_output(
        response=result,
        action_type=action_type,
        action_id=decision.get("action_id"),
    )

    print(f"  scan:      {scan['verdict']}  ({len(scan['findings'])} findings)")
    for f in scan["findings"]:
        print(f"             PHI detected — {f['pattern']} ×{f['count']} (redacted)")

    if scan["verdict"] == "BLOCK":
        print("  → Output blocked. Do not pass this to your LLM.")
        return None

    # scan["payload"] is the safe version — redacted if PHI was found
    return scan["payload"]


def _mock_result(action_type: str) -> dict:
    """Simulates the raw response your existing system would return."""
    if "read" in action_type or "query" in action_type:
        return {
            "patient_id": "P001",
            "name": "Jane Smith",
            "ssn": "123-45-6789",       # PHI — EDON will catch this
            "dob": "DOB: 03/14/1965",   # PHI — EDON will catch this
            "mrn": "MRN: 00847291",     # PHI — EDON will catch this
            "ward": "cardiology",
        }
    return {"status": "ok"}


# ── Scenario 1: Normal read — your agent reads a patient record ───────────────
print(f"\n{SEP}")
print("Scenario 1 — Read patient record (normal clinical workflow)")
print(SEP)
safe_result = governed(
    action_type="ehr.read",
    payload={"patient_id": "P001", "fields": ["name", "ward", "diagnosis"]},
    stated_intent="Summarise patient status for morning huddle",
)
if safe_result:
    print("  → Safe to pass to your LLM. ✅")


# ── Scenario 2: Bulk export — your agent tries to export all patient records ──
print(f"\n{SEP}")
print("Scenario 2 — Bulk patient record export (potential HIPAA breach)")
print(SEP)
governed(
    action_type="shell.execute",
    payload={"command": "mysqldump ehr_prod patients", "server": "db-prod-01"},
    stated_intent="Export patient records for analysis",
)


# ── Scenario 3: Schema destruction ───────────────────────────────────────────
print(f"\n{SEP}")
print("Scenario 3 — Destructive operation (always blocked)")
print(SEP)
governed(
    action_type="database.truncate",
    payload={"table": "patients"},
    stated_intent="Clear test data",
)


# ── Done ──────────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("Next steps:")
print("  1. console.edoncore.com → Audit  — every decision logged above is here")
print("  2. console.edoncore.com → Review — escalations wait here for human approval")
print("  3. console.edoncore.com → Policies — add rules specific to your action types")
print("  4. Replace _mock_result() with your real EHR/system calls")
print(SEP)

client.end_intent()
