"""EDON Demo Environment Agent — spins up a configured demo for a prospect.

Given a prospect's use case, this agent:
  1. Provisions a demo tenant (time-limited, clearly marked as demo)
  2. Applies the right policy pack based on their industry/use case
  3. Activates clinical safety mode with their relevant regulations
  4. Fires realistic sample decisions so the dashboard has live data to show
  5. Generates a personalised demo guide tailored to their use case

Turns "we'll set up a POC next week" into same-day demo credentials.

Usage:
    echo '{
      "company": "Acme Health",
      "contact_email": "cto@acme.com",
      "use_case": "Clinical AI assistant reviewing EHR notes before physician sign-off",
      "regulations": ["HIPAA", "HITECH"],
      "industry": "hospital"
    }' | ANTHROPIC_API_KEY=xxx EDON_API_TOKEN=xxx \\
        EDON_BOOTSTRAP_SECRET=xxx python -m agents.demo_agent

    # Or from file:
    ANTHROPIC_API_KEY=xxx ... python -m agents.demo_agent --input prospect.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import requests
import anthropic

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GATEWAY_URL = os.environ.get("EDON_GATEWAY_URL", "https://edon-gateway.fly.dev").rstrip("/")
API_TOKEN = os.environ["EDON_API_TOKEN"]
BOOTSTRAP_SECRET = os.environ.get("EDON_BOOTSTRAP_SECRET", "")
FRONTEND_URL = os.environ.get("EDON_FRONTEND_URL", "https://agent.edoncore.com")

REPO_ROOT = Path(__file__).resolve().parents[2]

# Sample action payloads by industry — generates realistic demo data
SAMPLE_ACTIONS: dict[str, list[dict[str, Any]]] = {
    "hospital": [
        {"action_type": "file.export", "action_payload": {"file": "patient_records_bulk.csv", "tags": ["phi", "bulk_export"]}, "context": {"risk_estimate": "high"}},
        {"action_type": "email.send", "action_payload": {"to": "external@lab.com", "subject": "Patient Lab Results"}, "context": {"risk_estimate": "high"}},
        {"action_type": "robot.configure", "action_payload": {"device": "infusion_pump_01", "setting": "dosage_rate"}},
        {"action_type": "file.read", "action_payload": {"file": "ehr_notes_2026.db"}, "context": {"risk_estimate": "low"}},
        {"action_type": "email.send", "action_payload": {"to": "dr.smith@hospital.com", "subject": "Appointment reminder"}, "context": {"risk_estimate": "low"}},
        {"action_type": "shell.execute", "action_payload": {"cmd": "export_patient_db.sh"}, "context": {"risk_estimate": "high"}},
        {"action_type": "robot.dispense", "action_payload": {"medication": "morphine_5mg", "patient": "P-00142"}},
        {"action_type": "database.query", "action_payload": {"query": "SELECT * FROM patients WHERE diagnosis='cancer'"}, "context": {"risk_estimate": "low"}},
    ],
    "clinical_saas": [
        {"action_type": "file.export", "action_payload": {"file": "clinical_trial_data.csv", "tags": ["phi"]},"context": {"risk_estimate": "high"}},
        {"action_type": "http.request", "action_payload": {"url": "https://api.partner.com/patients", "method": "POST"}, "context": {"risk_estimate": "medium"}},
        {"action_type": "email.send", "action_payload": {"to": "researcher@uni.edu", "subject": "De-identified dataset"}, "context": {"risk_estimate": "low"}},
        {"action_type": "database.query", "action_payload": {"query": "SELECT patient_id, diagnosis FROM records LIMIT 1000"}, "context": {"risk_estimate": "medium"}},
        {"action_type": "shell.execute", "action_payload": {"cmd": "run_model_inference.py --input patients.csv"}, "context": {"risk_estimate": "low"}},
    ],
    "medical_device": [
        {"action_type": "robot.firmware_update", "action_payload": {"device": "ventilator_v2", "version": "2.1.4"}},
        {"action_type": "robot.calibrate", "action_payload": {"device": "mri_scanner_01", "mode": "auto"}},
        {"action_type": "robot.configure", "action_payload": {"device": "drug_dispenser", "setting": "max_dose"}},
        {"action_type": "robot.execute", "action_payload": {"device": "surgical_robot", "procedure": "assist"}, "context": {"risk_estimate": "critical"}},
        {"action_type": "file.export", "action_payload": {"file": "device_logs.bin"}, "context": {"risk_estimate": "low"}},
    ],
    "default": [
        {"action_type": "email.send", "action_payload": {"to": "user@example.com", "subject": "Weekly report"}, "context": {"risk_estimate": "low"}},
        {"action_type": "file.export", "action_payload": {"file": "report.csv", "tags": ["phi"]}, "context": {"risk_estimate": "high"}},
        {"action_type": "shell.execute", "action_payload": {"cmd": "backup.sh"}, "context": {"risk_estimate": "medium"}},
        {"action_type": "database.query", "action_payload": {"query": "SELECT * FROM users"}, "context": {"risk_estimate": "low"}},
    ],
}

INDUSTRY_TO_PACK = {
    "hospital": "hospital",
    "clinical_saas": "ops_commander",
    "medical_device": "autonomy_mode",
    "default": "casual_user",
}


def _admin_headers() -> dict[str, str]:
    return {"X-EDON-TOKEN": API_TOKEN, "X-Bootstrap-Secret": BOOTSTRAP_SECRET, "Content-Type": "application/json"}


def _tenant_headers(tenant_id: str) -> dict[str, str]:
    return {"X-EDON-TOKEN": API_TOKEN, "X-Tenant-ID": tenant_id, "Content-Type": "application/json"}


def provision_demo_tenant(company: str) -> tuple[str, str]:
    if not BOOTSTRAP_SECRET:
        raise RuntimeError("EDON_BOOTSTRAP_SECRET required")
    demo_name = f"DEMO — {company}"
    r = requests.post(
        f"{GATEWAY_URL}/admin/provision",
        headers=_admin_headers(),
        json={"tenant_name": demo_name, "plan": "starter", "key_name": f"{company} Demo Key"},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    return data["tenant_id"], data["api_key"]


def apply_pack(tenant_id: str, pack: str) -> None:
    requests.post(
        f"{GATEWAY_URL}/policy-packs/{pack}/apply",
        headers=_tenant_headers(tenant_id),
        json={},
        timeout=15,
    )


def activate_clinical_safety(tenant_id: str) -> dict[str, Any]:
    r = requests.post(
        f"{GATEWAY_URL}/compliance/clinical-safety/activate",
        headers=_tenant_headers(tenant_id),
        json={"activated_by": "demo-agent"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def seed_demo_decisions(tenant_id: str, industry: str, demo_agent_id: str) -> list[dict[str, Any]]:
    actions = SAMPLE_ACTIONS.get(industry, SAMPLE_ACTIONS["default"])
    results = []
    for action in actions:
        payload = {
            "agent_id": demo_agent_id,
            "action_type": action["action_type"],
            "action_payload": action.get("action_payload", {}),
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "context": action.get("context", {}),
        }
        try:
            r = requests.post(
                f"{GATEWAY_URL}/v1/action",
                headers=_tenant_headers(tenant_id),
                json=payload,
                timeout=10,
            )
            if r.status_code == 200:
                verdict = r.json().get("verdict", "?")
                results.append({"action": action["action_type"], "verdict": verdict})
                print(f"    {action['action_type']} → {verdict}")
            time.sleep(0.3)  # avoid rate limiting
        except Exception as exc:
            print(f"    {action['action_type']} → ERROR: {exc}")
    return results


def generate_demo_guide(
    prospect: dict[str, Any],
    tenant_id: str,
    api_key: str,
    decisions: list[dict[str, Any]],
    pack: str,
) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    allow_count = sum(1 for d in decisions if d.get("verdict") == "ALLOW")
    block_count = sum(1 for d in decisions if d.get("verdict") in ("BLOCK", "HUMAN_REQUIRED"))

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": f"""Write a personalised demo guide for {prospect['company']}.

Context:
- Use case: {prospect.get('use_case', '')}
- Regulations: {', '.join(prospect.get('regulations', []))}
- Industry: {prospect.get('industry', 'healthcare')}
- Policy pack applied: {pack}
- Demo tenant ID: {tenant_id}
- Demo API key: {api_key}
- Frontend URL: {FRONTEND_URL}/#token={api_key}
- Sample decisions seeded: {len(decisions)} ({allow_count} ALLOW, {block_count} BLOCK/ESCALATE)

Write a concise demo guide (plain markdown) that:
1. Gives them their credentials (tenant ID + API key + dashboard URL)
2. Explains what to look at first in the dashboard (where the seeded decisions are)
3. Shows them 2-3 specific things that are relevant to their use case
4. Gives them a simple cURL command to fire their first real action
5. Tells them what to do next (next steps to evaluate or sign)

Tone: direct, technical. Under 400 words."""}],
    )
    return str(getattr(msg.content[0], "text", msg.content[0]))


def run(prospect: dict[str, Any]) -> int:
    company = prospect["company"]
    industry = prospect.get("industry", "default")
    pack = INDUSTRY_TO_PACK.get(industry, "casual_user")
    demo_agent_id = f"demo-agent-{company.lower().replace(' ', '-')[:20]}"

    print(f"[demo] Setting up demo for: {company}")
    print(f"[demo] Industry: {industry} | Policy pack: {pack}")

    print("[demo] Provisioning demo tenant...")
    tenant_id, api_key = provision_demo_tenant(company)
    print(f"[demo] Tenant: {tenant_id}")

    print("[demo] Applying policy pack...")
    apply_pack(tenant_id, pack)

    if prospect.get("regulations"):
        print("[demo] Activating clinical safety mode...")
        cs = activate_clinical_safety(tenant_id)
        print(f"[demo] {cs.get('total_rules', 0)} clinical safety rules active")

    print(f"[demo] Seeding {len(SAMPLE_ACTIONS.get(industry, SAMPLE_ACTIONS['default']))} demo decisions...")
    decisions = seed_demo_decisions(tenant_id, industry, demo_agent_id)

    print("[demo] Generating personalised demo guide...")
    guide = generate_demo_guide(prospect, tenant_id, api_key, decisions, pack)

    result = {
        "company": company,
        "tenant_id": tenant_id,
        "api_key": api_key,
        "dashboard_url": f"{FRONTEND_URL}/#token={api_key}",
        "policy_pack": pack,
        "decisions_seeded": len(decisions),
        "guide": guide,
        "created_at": datetime.now(UTC).isoformat(),
    }

    out_path = Path(__file__).parent / f"demo_{tenant_id}.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print("DEMO GUIDE (send to prospect)")
    print("=" * 60)
    print(guide)
    print("=" * 60)
    print(f"\n[demo] Dashboard: {result['dashboard_url']}")
    print(f"[demo] Full output saved to {out_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="EDON Demo Environment Agent")
    parser.add_argument("--input", help="Path to JSON prospect profile")
    args = parser.parse_args()

    if args.input:
        prospect = json.loads(Path(args.input).read_text(encoding="utf-8"))
    elif not sys.stdin.isatty():
        prospect = json.load(sys.stdin)
    else:
        parser.print_help()
        print("\nExpected JSON fields: company, contact_email, use_case, regulations (list), industry")
        print("Industry values: hospital | clinical_saas | medical_device | default")
        return 1

    return run(prospect)


if __name__ == "__main__":
    sys.exit(main())
