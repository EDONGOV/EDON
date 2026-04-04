"""Basic EDON governance example — minimal working agent.

Run:
    EDON_API_KEY=eak_... python sdk/examples/basic_agent.py
"""
import os
import sys
sys.path.insert(0, "sdk/python")

from edon_sdk import EdonClient

client = EdonClient(
    token=os.environ.get("EDON_API_KEY", "dev-token"),
    base_url=os.environ.get("EDON_GATEWAY_URL", "https://edon-gateway.fly.dev"),
)

# Check gateway is reachable
health = client.health()
print(f"Gateway status: {health.get('status', 'unknown')}")

# Evaluate a low-risk action
result = client.evaluate(
    action_type="email.send",
    agent_id="example-agent-1",
    payload={
        "recipients": ["user@example.com"],
        "subject": "Daily summary",
        "body": "Here is today's summary.",
    },
)

print(f"Verdict: {result['verdict']}")
print(f"Reason:  {result.get('reason_code', 'N/A')}")
print(f"Explain: {result.get('explanation', '')[:100]}")

if result["verdict"] == "ALLOW":
    print("✓ Action approved — would send email now")
elif result["verdict"] == "BLOCK":
    print(f"✗ Action blocked: {result.get('explanation', '')}")
elif result["verdict"] == "ESCALATE":
    print(f"⚠ Escalation needed: {result.get('escalation_question', '')}")
else:
    print(f"? Unexpected verdict: {result['verdict']}")
