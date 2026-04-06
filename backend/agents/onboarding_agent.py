"""EDON Onboarding Agent — end-to-end client provisioning in one command.

Does everything:
  1. Generates a secure API token
  2. Provisions the tenant via /admin/bootstrap-api-key
  3. Applies the correct policy pack (hospital/clinical_saas/medical_device)
  4. Activates clinical safety mode (16 regulation-mapped rules)
  5. Runs compliance health check
  6. Generates personalised welcome email with Claude
  7. Sends the email to the client (via SMTP/Gmail)
  8. Notifies you on Telegram with the client's credentials

Usage:
    python -m agents.onboarding_agent \\
        --name "Acme Hospital" \\
        --email cto@acmehospital.com \\
        --tenant acme-hospital \\
        --plan hospital \\
        --use-case "Clinical AI for radiology and pharmacy workflows"

Required env vars:
    ANTHROPIC_API_KEY, EDON_API_TOKEN, EDON_BOOTSTRAP_SECRET, EDON_GATEWAY_URL
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (for founder notification)
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD (for email delivery)
    FOUNDER_EMAIL (shown as reply-to in welcome email)
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import smtplib
import sys
from datetime import datetime, UTC
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import requests
import anthropic

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GATEWAY_URL = os.environ.get("EDON_GATEWAY_URL", "https://edon-gateway-prod.fly.dev").rstrip("/")
API_TOKEN = os.environ["EDON_API_TOKEN"]
BOOTSTRAP_SECRET = os.environ.get("EDON_BOOTSTRAP_SECRET", "edon-bootstrap-2026")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
FOUNDER_EMAIL = os.environ.get("FOUNDER_EMAIL", "charliebiggins.edon@gmail.com")
FOUNDER_NAME = os.environ.get("FOUNDER_NAME", "Charlie")

AGENTS_DIR = Path(__file__).parent

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

PLAN_TO_POLICY_PACK = {
    "hospital":       "hospital",
    "hipaa":          "hospital",
    "clinical_saas":  "ops_commander",
    "medical_device": "autonomy_mode",
    "pro":            "ops_commander",
    "scale":          "ops_commander",
    "free":           "ops_commander",
    "enterprise":     "hospital",
}


# ── Gateway calls ─────────────────────────────────────────────────────────────

def _headers(token: str | None = None) -> dict[str, str]:
    return {
        "X-EDON-TOKEN": token or API_TOKEN,
        "Content-Type": "application/json",
    }


def provision_tenant(
    tenant_id: str,
    name: str,
    plan: str,
    email: str,
    token: str,
) -> dict[str, Any]:
    r = requests.post(
        f"{GATEWAY_URL}/admin/bootstrap-api-key",
        headers={"X-Bootstrap-Secret": BOOTSTRAP_SECRET, "Content-Type": "application/json"},
        json={
            "token": token,
            "tenant_id": tenant_id,
            "name": f"{name} — Admin Key",
            "role": "admin",
            "plan": plan,
            "email": email,
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def apply_policy_pack(tenant_token: str, pack_name: str, objective: str) -> dict[str, Any]:
    r = requests.post(
        f"{GATEWAY_URL}/policy-packs/{pack_name}/apply",
        headers=_headers(tenant_token),
        json={"objective": objective},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def activate_clinical_safety(tenant_token: str, email: str) -> dict[str, Any]:
    r = requests.post(
        f"{GATEWAY_URL}/compliance/clinical-safety/activate",
        headers=_headers(tenant_token),
        json={"activated_by": f"onboarding:{email}"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def compliance_health(tenant_token: str) -> dict[str, Any]:
    r = requests.get(
        f"{GATEWAY_URL}/compliance/health",
        headers=_headers(tenant_token),
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


# ── Email generation ──────────────────────────────────────────────────────────

def generate_welcome_email(
    name: str,
    contact_email: str,
    tenant_id: str,
    token: str,
    plan: str,
    use_case: str,
    rules_activated: int,
    health: dict[str, Any],
) -> dict[str, str]:
    """Generate personalised welcome email using Claude."""

    passing = [k for k, v in health.get("regulations", {}).items() if v.get("status") == "pass"]
    failing = [k for k, v in health.get("regulations", {}).items() if v.get("status") != "pass"]

    prompt = f"""You are writing a welcome email on behalf of {FOUNDER_NAME} at EDON (edoncore.com).
EDON is an AI governance platform built for healthtech — it governs every AI agent action in real time.

New client details:
- Organisation: {name}
- Contact: {contact_email}
- Plan: {plan}
- Use case: {use_case}
- Tenant ID: {tenant_id}
- API Token: {token}
- Clinical safety rules activated: {rules_activated}
- Compliant regulations: {', '.join(passing) if passing else 'none yet'}
- Regulations needing attention: {', '.join(failing) if failing else 'none'}
- Console URL: https://console.edoncore.com
- Gateway URL: {GATEWAY_URL}

Write a professional, warm but direct welcome email. Sections:
1. Brief welcome (1-2 sentences, specific to their use case)
2. What's been set up (tenant ID, rules, compliance status)
3. Credentials block (clearly formatted — token, gateway URL, console URL)
4. First 3 steps to get their first AI agent governed
5. Direct contact info ({FOUNDER_EMAIL})

Rules:
- Keep it under 350 words
- The credentials must be clearly visible, not buried
- Tone: confident, technical, founder-to-founder
- No generic filler like "We're thrilled to have you"
- Sign off as {FOUNDER_NAME}, EDON

Return JSON:
{{
  "subject": "Your EDON account is live — credentials inside",
  "plain_text": "full plain text email",
  "html": "full HTML email with basic styling (inline CSS, clean font, credential box highlighted)"
}}"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = str(getattr(msg.content[0], "text", msg.content[0]))
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1:
        return {
            "subject": f"Your EDON account is live — {name}",
            "plain_text": raw,
            "html": f"<pre>{raw}</pre>",
        }
    try:
        return json.loads(raw[start:end])
    except json.JSONDecodeError:
        return {"subject": f"Your EDON account is live — {name}", "plain_text": raw, "html": f"<pre>{raw}</pre>"}


# ── Email delivery ────────────────────────────────────────────────────────────

def send_email(to_email: str, subject: str, plain_text: str, html: str) -> bool:
    if not SMTP_USER or not SMTP_PASSWORD:
        print("No SMTP credentials — email not sent. Set SMTP_USER and SMTP_PASSWORD.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{FOUNDER_NAME} at EDON <{SMTP_USER}>"
        msg["To"] = to_email
        msg["Reply-To"] = FOUNDER_EMAIL
        msg.attach(MIMEText(plain_text, "plain"))
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, to_email, msg.as_string())

        print(f"✓ Welcome email sent to {to_email}")
        return True
    except Exception as exc:
        print(f"Email delivery failed: {exc}")
        return False


# ── Telegram notification ─────────────────────────────────────────────────────

def notify_telegram(
    name: str,
    tenant_id: str,
    token: str,
    email: str,
    plan: str,
    rules: int,
    email_sent: bool,
) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    msg = (
        f"🎉 *New client onboarded!*\n\n"
        f"*{name}*\n"
        f"📧 {email}\n"
        f"📋 Plan: `{plan}`\n"
        f"🏥 Rules activated: {rules}\n\n"
        f"*Credentials:*\n"
        f"Tenant: `{tenant_id}`\n"
        f"Token: `{token[:16]}...` _(truncated)_\n\n"
        f"{'✅ Welcome email sent' if email_sent else '⚠️ Email not sent — check SMTP config'}\n"
        f"Console: https://console.edoncore.com"
    )
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"},
            timeout=10,
        ).raise_for_status()
    except Exception as exc:
        print(f"Telegram notification failed: {exc}")


# ── Main ──────────────────────────────────────────────────────────────────────

def onboard(
    name: str,
    email: str,
    tenant_id: str,
    plan: str,
    use_case: str,
) -> int:
    print(f"\n{'='*60}")
    print(f"EDON Onboarding — {name}")
    print(f"{'='*60}\n")

    # Generate secure token
    token = secrets.token_hex(32)
    print(f"Generated token: {token[:16]}...")

    # Step 1 — Provision
    print("1. Provisioning tenant…")
    try:
        prov = provision_tenant(tenant_id, name, plan, email, token)
        print(f"   ✓ Tenant '{tenant_id}' created — key_id: {prov.get('key_id', '?')}")
    except Exception as exc:
        print(f"   ✗ Provisioning failed: {exc}")
        return 1

    # Step 2 — Policy pack
    pack = PLAN_TO_POLICY_PACK.get(plan.lower(), "ops_commander")
    print(f"2. Applying policy pack '{pack}'…")
    try:
        apply_policy_pack(token, pack, f"AI governance for {name} — {use_case}")
        print(f"   ✓ Policy pack applied")
    except Exception as exc:
        print(f"   ⚠ Policy pack failed (non-fatal): {exc}")

    # Step 3 — Clinical safety
    print("3. Activating clinical safety mode…")
    try:
        cs = activate_clinical_safety(token, email)
        rules_count = cs.get("total_rules", 0)
        print(f"   ✓ {rules_count} clinical safety rules activated")
    except Exception as exc:
        print(f"   ⚠ Clinical safety failed (non-fatal): {exc}")
        cs = {}
        rules_count = 0

    # Step 4 — Compliance check
    print("4. Running compliance health check…")
    try:
        health = compliance_health(token)
        overall = health.get("overall", "unknown")
        print(f"   ✓ Compliance: {overall}")
    except Exception as exc:
        print(f"   ⚠ Health check failed (non-fatal): {exc}")
        health = {}

    # Step 5 — Generate welcome email
    print("5. Generating welcome email…")
    email_content = generate_welcome_email(
        name=name,
        contact_email=email,
        tenant_id=tenant_id,
        token=token,
        plan=plan,
        use_case=use_case,
        rules_activated=rules_count,
        health=health,
    )
    print("   ✓ Email generated")

    # Step 6 — Send email
    print(f"6. Sending welcome email to {email}…")
    email_sent = send_email(
        to_email=email,
        subject=email_content.get("subject", f"Your EDON account is live — {name}"),
        plain_text=email_content.get("plain_text", ""),
        html=email_content.get("html", ""),
    )

    # Step 7 — Telegram notification
    notify_telegram(name, tenant_id, token, email, plan, rules_count, email_sent)

    # Save full record
    record = {
        "onboarded_at": datetime.now(UTC).isoformat(),
        "name": name,
        "email": email,
        "tenant_id": tenant_id,
        "token": token,
        "plan": plan,
        "policy_pack": pack,
        "rules_activated": rules_count,
        "compliance_health": health,
        "email_sent": email_sent,
        "welcome_email_subject": email_content.get("subject", ""),
        "welcome_email_plain": email_content.get("plain_text", ""),
    }
    out_path = AGENTS_DIR / f"onboarding_{tenant_id}.json"
    out_path.write_text(json.dumps(record, indent=2))

    print(f"\n{'='*60}")
    print("WELCOME EMAIL PREVIEW")
    print(f"{'='*60}")
    print(f"To: {email}")
    print(f"Subject: {email_content.get('subject', '')}")
    print(f"\n{email_content.get('plain_text', '')}")
    print(f"{'='*60}")
    print(f"\n✓ Onboarding complete — saved to {out_path}")
    print(f"  Tenant: {tenant_id}")
    print(f"  Token:  {token}")
    print(f"  Email:  {'sent' if email_sent else 'not sent (configure SMTP)'}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="EDON Onboarding Agent")
    parser.add_argument("--name",      required=True, help="Organisation name")
    parser.add_argument("--email",     required=True, help="Client contact email")
    parser.add_argument("--tenant",    required=True, help="Tenant ID (slug, e.g. acme-hospital)")
    parser.add_argument("--plan",      default="hospital", help="Plan: hospital | pro | scale | free")
    parser.add_argument("--use-case",  default="AI governance for healthcare workflows",
                        help="Client's use case (used to personalise the welcome email)")
    args = parser.parse_args()

    return onboard(
        name=args.name,
        email=args.email,
        tenant_id=args.tenant,
        plan=args.plan,
        use_case=args.use_case,
    )


if __name__ == "__main__":
    sys.exit(main())
