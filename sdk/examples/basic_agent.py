"""Basic EDON governance example — the full three-step governed agent loop.

Run:
    EDON_API_KEY=eak_... python sdk/examples/basic_agent.py
"""
import os
import sys
sys.path.insert(0, "sdk/python")

from edon_sdk import EdonClient

client = EdonClient(
    token=os.environ.get("EDON_API_KEY", "dev-token"),
    base_url=os.environ.get("EDON_GATEWAY_URL", "https://edon-gateway-prod.fly.dev"),
    agent_id="example-agent-1",
)

# ── Step 0: Check gateway ─────────────────────────────────────────────────────
health = client.health()
print(f"Gateway status: {health.get('status', 'unknown')}")

# ── Step 1: Declare intent upfront ────────────────────────────────────────────
# Every evaluate() and scan_output() call is now scoped to this intent.
# The sequence scorer tracks all actions under this session.
intent_id = client.begin_intent(
    objective="Query patient database and email daily summary to care team",
    allowed_tools=["database.query", "email.send"],
    risk_ceiling="MEDIUM",
)
print(f"Intent registered: {intent_id}")

# ── Step 2: Govern the action before executing ────────────────────────────────
result = client.evaluate(
    action_type="database.query",
    payload={"table": "patients", "filter": {"ward": "cardiology"}, "limit": 10},
    stated_intent="fetch today's cardiology patients for daily summary",
)

print(f"\nVerdict: {result['verdict']}")
print(f"Reason:  {result.get('reason_code', 'N/A')}")

if result["verdict"] == "ALLOW":
    # Simulate tool execution
    raw_db_response = {
        "rows": [
            {"patient_id": "P001", "name": "John Doe", "ward": "cardiology"},
            {"patient_id": "P002", "name": "Jane Smith", "ward": "cardiology"},
        ],
        "count": 2,
    }

    # ── Step 3: Scan the response before using it ─────────────────────────────
    output = client.scan_output(
        response=raw_db_response,
        action_type="database.query",
        action_id=result.get("action_id"),
    )

    if output["verdict"] == "PASS":
        print(f"\nOutput clean — {len(output['payload'].get('rows', []))} rows safe to use")
    elif output["verdict"] == "REDACT":
        print(f"\nOutput redacted — {len(output['findings'])} findings. Using cleaned payload.")
        print(f"Findings: {output['findings']}")
    else:
        print(f"\nOutput BLOCKED — cannot use this response: {output['findings']}")

elif result["verdict"] == "BLOCK":
    print(f"Action blocked: {result.get('explanation', '')}")

elif result["verdict"] == "ESCALATE":
    print(f"Human review required: {result.get('escalation_question', '')}")

# ── Clean up intent at end of session ─────────────────────────────────────────
client.end_intent()
