"""Comprehensive verdict handling — all 6 EDON verdict types with correct responses.

Run:
    EDON_API_KEY=eak_... python sdk/examples/handle_verdicts.py
"""
import os
import sys
import time
sys.path.insert(0, "sdk/python")

from edon_sdk import EdonClient

client = EdonClient(
    token=os.environ.get("EDON_API_KEY", "dev-token"),
    base_url=os.environ.get("EDON_GATEWAY_URL", "https://edon-gateway-prod.fly.dev"),
)


def execute_with_governance(
    action_type: str,
    payload: dict,
    agent_id: str = "example-agent",
    max_retries: int = 3,
) -> dict:
    """Execute an action with full EDON governance handling."""
    for attempt in range(max_retries):
        result = client.evaluate(
            action_type=action_type,
            agent_id=agent_id,
            payload=payload,
        )
        verdict = result["verdict"]

        if verdict == "ALLOW":
            # ✓ Safe to proceed
            print(f"[ALLOW] Executing {action_type}")
            return {"executed": True, "action": action_type, "payload": payload}

        elif verdict == "BLOCK":
            # ✗ Hard stop — do not execute under any circumstances
            reason = result.get("reason_code", "unknown")
            explanation = result.get("explanation", "")
            print(f"[BLOCK] {action_type} denied — {reason}: {explanation}")
            return {"executed": False, "blocked": True, "reason": reason}

        elif verdict == "ESCALATE":
            # ⚠ Human review required before proceeding
            question = result.get("escalation_question", "Please review this action.")
            options = result.get("escalation_options", [])
            print(f"[ESCALATE] {action_type} requires human review")
            print(f"  Question: {question}")
            print(f"  Options:  {[o.get('label') for o in options]}")
            # In production: create a review ticket and wait
            return {"executed": False, "escalated": True, "question": question}

        elif verdict == "DEGRADE":
            # ⚡ Proceed but use the safe alternative parameters
            safe_alt = result.get("safe_alternative") or payload
            print(f"[DEGRADE] {action_type} executing with safe parameters")
            return {"executed": True, "degraded": True, "used_params": safe_alt}

        elif verdict == "PAUSE":
            # ⏸ Temporary hold — retry after a short delay
            wait_seconds = 5 * (attempt + 1)
            print(f"[PAUSE] {action_type} — retrying in {wait_seconds}s (attempt {attempt+1}/{max_retries})")
            time.sleep(wait_seconds)
            continue  # retry

        elif verdict == "ERROR":
            # 🔴 Governance error — fail closed (do not execute)
            print(f"[ERROR] Governance error for {action_type} — failing closed")
            return {"executed": False, "governance_error": True}

        else:
            print(f"[UNKNOWN] Unexpected verdict: {verdict}")
            return {"executed": False, "unexpected_verdict": verdict}

    # Exhausted retries (only happens after repeated PAUSE verdicts)
    print(f"[TIMEOUT] {action_type} gave up after {max_retries} PAUSE retries")
    return {"executed": False, "timeout": True}


if __name__ == "__main__":
    # Test each scenario
    scenarios = [
        ("email.send", {"recipients": ["ceo@company.com"], "subject": "Q1 Results", "body": "Great quarter!"}),
        ("filesystem.write", {"path": "/etc/passwd", "content": "malicious"}),  # Should block
        ("http.request", {"url": "https://api.partner.com/data", "method": "GET"}),
    ]

    for action_type, payload in scenarios:
        print(f"\n--- Testing: {action_type} ---")
        outcome = execute_with_governance(action_type, payload)
        print(f"Outcome: {outcome}")
