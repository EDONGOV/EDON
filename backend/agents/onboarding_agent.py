"""EDON Onboarding Agent — provisions a new tenant end-to-end.

Given a customer's name, email, declared regulations, and use case,
this agent:
  1. Provisions the tenant via POST /admin/provision
  2. Creates an API key
  3. Activates clinical safety mode with regulation-specific rules
  4. Runs a compliance health check
  5. Uses Claude to write a personalised welcome brief

You review the output and send it. Nothing is sent automatically.

Usage:
    echo '{
      "name": "Acme Health",
      "email": "cto@acme.com",
      "regulations": ["HIPAA", "HITECH"],
      "use_case": "Clinical AI assistant for EHR workflows",
      "plan": "enterprise"
    }' | ANTHROPIC_API_KEY=xxx EDON_API_TOKEN=xxx \\
        EDON_BOOTSTRAP_SECRET=xxx python -m agents.onboarding_agent

    # Or from file:
    ANTHROPIC_API_KEY=xxx ... python -m agents.onboarding_agent --input customer.json
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
API_TOKEN = os.environ["EDON_API_TOKEN"]
BOOTSTRAP_SECRET = os.environ.get("EDON_BOOTSTRAP_SECRET", "")

REPO_ROOT = Path(__file__).resolve().parents[2]
ONBOARDING_DOC = REPO_ROOT / "backend" / "docs" / "ONBOARDING.md"


# ── Gateway calls ─────────────────────────────────────────────────────────────

def _admin_headers() -> dict[str, str]:
    return {
        "X-EDON-TOKEN": API_TOKEN,
        "X-Bootstrap-Secret": BOOTSTRAP_SECRET,
        "Content-Type": "application/json",
    }


def _tenant_headers(tenant_id: str) -> dict[str, str]:
    return {
        "X-EDON-TOKEN": API_TOKEN,
        "X-Tenant-ID": tenant_id,
        "Content-Type": "application/json",
    }


def provision_tenant(name: str, plan: str) -> dict[str, Any]:
    """Call POST /admin/provision to create tenant + initial API key."""
    if not BOOTSTRAP_SECRET:
        raise RuntimeError("EDON_BOOTSTRAP_SECRET is required to provision tenants")
    r = requests.post(
        f"{GATEWAY_URL}/admin/provision",
        headers=_admin_headers(),
        json={"tenant_name": name, "plan": plan, "key_name": f"{name} - Initial Key"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def activate_clinical_safety(tenant_id: str, activated_by: str) -> dict[str, Any]:
    r = requests.post(
        f"{GATEWAY_URL}/compliance/clinical-safety/activate",
        headers=_tenant_headers(tenant_id),
        json={"activated_by": activated_by},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def compliance_health(tenant_id: str) -> dict[str, Any]:
    r = requests.get(
        f"{GATEWAY_URL}/compliance/health",
        headers=_tenant_headers(tenant_id),
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


# ── Welcome brief ──────────────────────────────��──────────────────────────────

def generate_welcome_brief(
    customer: dict[str, Any],
    tenant_id: str,
    api_key: str,
    clinical_safety_result: dict[str, Any],
    health: dict[str, Any],
) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    onboarding_doc = ""
    try:
        onboarding_doc = ONBOARDING_DOC.read_text(encoding="utf-8")[:3000]
    except FileNotFoundError:
        pass

    activated_rules = clinical_safety_result.get("total_rules", 0)
    regs = customer.get("regulations", [])
    use_case = customer.get("use_case", "")

    prompt = f"""You are writing a technical welcome brief for a new EDON customer.
Customer: {customer['name']}
Contact: {customer['email']}
Use case: {use_case}
Declared regulations: {', '.join(regs)}

Their EDON account is now live:
- Tenant ID: {tenant_id}
- API Key: {api_key}  (this is shown once — they must store it securely)
- Clinical safety rules activated: {activated_rules} rules seeded and protected
- Compliance health: {json.dumps(health, indent=2)[:500]}

Here is the standard onboarding guide for reference:
{onboarding_doc}

Write a concise, technical welcome brief (plain markdown) that:
1. Confirms their account is live and what was configured
2. Lists their API key and tenant ID (they need these)
3. Explains the 2-3 most important first steps tailored to their use case and regulations
4. Points to the right docs for their specific situation (e.g. if HIPAA is declared, point to clinical safety docs)
5. Tells them how to reach you if they hit an issue

Tone: direct, technical, confident. No fluff. Under 400 words."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    return str(getattr(msg.content[0], "text", msg.content[0]))


# ── Main ──────────────────────────────────────────────────────────────────────

def onboard(customer: dict[str, Any]) -> int:
    name = customer["name"]
    email = customer.get("email", "")
    plan = customer.get("plan", "starter")

    print(f"[onboarding] Starting onboarding for: {name}")

    # Step 1 — Provision tenant
    print("[onboarding] Provisioning tenant...")
    try:
        prov = provision_tenant(name, plan)
    except Exception as exc:
        print(f"[onboarding] Provision failed: {exc}")
        print("[onboarding] Tip: set EDON_BOOTSTRAP_SECRET and ensure the gateway supports /admin/provision")
        return 1

    tenant_id = prov.get("tenant_id", "")
    api_key = prov.get("api_key", "")
    print(f"[onboarding] Tenant created: {tenant_id}")
    print(f"[onboarding] API key: {api_key}")

    # Step 2 — Activate clinical safety
    print("[onboarding] Activating clinical safety mode...")
    try:
        cs_result = activate_clinical_safety(tenant_id, activated_by=f"onboarding-agent:{email}")
        print(f"[onboarding] {cs_result.get('message', 'clinical safety activated')}")
    except Exception as exc:
        print(f"[onboarding] Clinical safety activation failed: {exc}")
        cs_result = {}

    # Step 3 — Compliance health check
    print("[onboarding] Running compliance health check...")
    try:
        health = compliance_health(tenant_id)
        status = health.get("status", "unknown")
        print(f"[onboarding] Compliance health: {status}")
    except Exception as exc:
        print(f"[onboarding] Health check failed: {exc}")
        health = {}

    # Step 4 — Generate welcome brief
    print("[onboarding] Generating welcome brief with Claude...")
    brief = generate_welcome_brief(customer, tenant_id, api_key, cs_result, health)

    output = {
        "run_at": datetime.now(UTC).isoformat(),
        "tenant_id": tenant_id,
        "api_key": api_key,
        "clinical_safety": cs_result,
        "compliance_health": health,
        "welcome_brief": brief,
    }

    print("\n" + "=" * 60)
    print("WELCOME BRIEF (review and send to customer)")
    print("=" * 60)
    print(brief)
    print("=" * 60 + "\n")

    # Write full output to file for reference
    out_path = Path(__file__).parent / f"onboarding_{tenant_id}.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"[onboarding] Full output saved to {out_path}")
    print("[onboarding] Done. Review the brief above, then send it to the customer.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="EDON Onboarding Agent")
    parser.add_argument("--input", help="Path to JSON file with customer details")
    args = parser.parse_args()

    if args.input:
        with open(args.input) as f:
            customer = json.load(f)
    elif not sys.stdin.isatty():
        customer = json.load(sys.stdin)
    else:
        parser.print_help()
        print("\nExpected JSON fields: name, email, regulations (list), use_case, plan")
        return 1

    return onboard(customer)


if __name__ == "__main__":
    sys.exit(main())
