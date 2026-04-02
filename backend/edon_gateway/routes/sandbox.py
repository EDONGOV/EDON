"""Sandbox environment routes for developer testing.

The sandbox gives developers a pre-seeded tenant and a known API key so they
can explore the governance API without setting up billing.  All sandbox events
are written to `sandbox_audit_events` — never to the production audit trail.
"""

import uuid
from datetime import datetime, UTC, timedelta
from fastapi import APIRouter, Request
from ..persistence import get_db
from ..logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/sandbox", tags=["sandbox"])

# ── Hostpals demo data ────────────────────────────────────────────────────────

_HOSTPALS_AGENTS = [
    {"agent_id": "hp_booking_agent",     "name": "Booking Agent",       "description": "Manages room reservations and calendar availability"},
    {"agent_id": "hp_concierge_agent",   "name": "Concierge Agent",     "description": "Handles guest requests, drafts emails, reads internal docs"},
    {"agent_id": "hp_housekeeping_agent","name": "Housekeeping Dispatch","description": "Dispatches housekeeping tasks, reads property calendar"},
    {"agent_id": "hp_billing_agent",     "name": "Billing Agent",       "description": "Reads invoices and drafts billing communications"},
    {"agent_id": "hp_frontdesk_agent",   "name": "Front-Desk Agent",    "description": "Views bookings and calendar; guest check-in support"},
]

def _hostpals_events(base_ts: datetime) -> list[dict]:
    """Return the Hostpals demo audit event dataset."""
    def _ts(minutes_ago: int) -> str:
        return (base_ts - timedelta(minutes=minutes_ago)).isoformat()

    TENANT = "tenant_sandbox_edon"
    V = "hostpals-policy-v1.0"

    return [
        # ── Happy-path ALLOW events ───────────────────────────────────────────
        {
            "action_id": f"act_{uuid.uuid4().hex[:12]}",
            "timestamp": _ts(58),
            "agent_id": "hp_booking_agent",
            "customer_id": TENANT,
            "action_tool": "calendar",
            "action_op": "view",
            "action_params": {"resource": "room_availability", "date_range": "7d"},
            "action_source": "agent",
            "action_estimated_risk": "low",
            "action_computed_risk": "low",
            "decision_verdict": "ALLOW",
            "decision_reason_code": "POLICY_PASS",
            "decision_explanation": "calendar.view is in-scope for booking_agent; no PII accessed.",
            "decision_policy_version": V,
            "action_summary": "Viewed room availability calendar",
            "stated_intent": "Check availability before creating reservation",
            "processing_latency_ms": 18.4,
        },
        {
            "action_id": f"act_{uuid.uuid4().hex[:12]}",
            "timestamp": _ts(55),
            "agent_id": "hp_booking_agent",
            "customer_id": TENANT,
            "action_tool": "booking",
            "action_op": "create",
            "action_params": {"system": "internal_pms", "room": "204", "guest": "redacted"},
            "action_source": "agent",
            "action_estimated_risk": "low",
            "action_computed_risk": "low",
            "decision_verdict": "ALLOW",
            "decision_reason_code": "POLICY_PASS",
            "decision_explanation": "booking.create targeting internal PMS is in-scope.",
            "decision_policy_version": V,
            "action_summary": "Created internal room reservation (room 204)",
            "stated_intent": "Complete guest check-in reservation",
            "processing_latency_ms": 22.1,
        },
        {
            "action_id": f"act_{uuid.uuid4().hex[:12]}",
            "timestamp": _ts(50),
            "agent_id": "hp_concierge_agent",
            "customer_id": TENANT,
            "action_tool": "email",
            "action_op": "draft",
            "action_params": {"to": "guest@example.com", "subject": "Welcome to Hostpals"},
            "action_source": "agent",
            "action_estimated_risk": "low",
            "action_computed_risk": "low",
            "decision_verdict": "ALLOW",
            "decision_reason_code": "POLICY_PASS",
            "decision_explanation": "email.draft (not send) is permitted; single recipient.",
            "decision_policy_version": V,
            "action_summary": "Drafted welcome email to guest",
            "stated_intent": "Send personalised welcome message",
            "processing_latency_ms": 14.7,
        },
        {
            "action_id": f"act_{uuid.uuid4().hex[:12]}",
            "timestamp": _ts(48),
            "agent_id": "hp_concierge_agent",
            "customer_id": TENANT,
            "action_tool": "file",
            "action_op": "read",
            "action_params": {"path": "/internal/hotel_policies.pdf"},
            "action_source": "agent",
            "action_estimated_risk": "low",
            "action_computed_risk": "low",
            "decision_verdict": "ALLOW",
            "decision_reason_code": "POLICY_PASS",
            "decision_explanation": "file.read on internal docs is in-scope for concierge_agent.",
            "decision_policy_version": V,
            "action_summary": "Read internal hotel policy document",
            "stated_intent": "Look up late check-out policy to answer guest query",
            "processing_latency_ms": 11.2,
        },
        {
            "action_id": f"act_{uuid.uuid4().hex[:12]}",
            "timestamp": _ts(43),
            "agent_id": "hp_housekeeping_agent",
            "customer_id": TENANT,
            "action_tool": "calendar",
            "action_op": "view",
            "action_params": {"resource": "housekeeping_schedule", "date": "today"},
            "action_source": "agent",
            "action_estimated_risk": "low",
            "action_computed_risk": "low",
            "decision_verdict": "ALLOW",
            "decision_reason_code": "POLICY_PASS",
            "decision_explanation": "calendar.view on housekeeping schedule is in-scope.",
            "decision_policy_version": V,
            "action_summary": "Viewed today's housekeeping task calendar",
            "stated_intent": "Plan room-turn schedule for the morning shift",
            "processing_latency_ms": 9.8,
        },
        {
            "action_id": f"act_{uuid.uuid4().hex[:12]}",
            "timestamp": _ts(38),
            "agent_id": "hp_billing_agent",
            "customer_id": TENANT,
            "action_tool": "file",
            "action_op": "read",
            "action_params": {"path": "/invoices/INV-2026-0314.pdf"},
            "action_source": "agent",
            "action_estimated_risk": "low",
            "action_computed_risk": "low",
            "decision_verdict": "ALLOW",
            "decision_reason_code": "POLICY_PASS",
            "decision_explanation": "file.read on invoice is in-scope for billing_agent.",
            "decision_policy_version": V,
            "action_summary": "Read invoice INV-2026-0314",
            "stated_intent": "Verify charges before drafting folio summary",
            "processing_latency_ms": 12.3,
        },
        {
            "action_id": f"act_{uuid.uuid4().hex[:12]}",
            "timestamp": _ts(35),
            "agent_id": "hp_billing_agent",
            "customer_id": TENANT,
            "action_tool": "email",
            "action_op": "draft",
            "action_params": {"to": "accounts@hostpals.internal", "subject": "Folio summary #0314"},
            "action_source": "agent",
            "action_estimated_risk": "low",
            "action_computed_risk": "low",
            "decision_verdict": "ALLOW",
            "decision_reason_code": "POLICY_PASS",
            "decision_explanation": "email.draft to internal accounts is in-scope.",
            "decision_policy_version": V,
            "action_summary": "Drafted folio summary email to internal accounts",
            "stated_intent": "Send folio draft for review before posting",
            "processing_latency_ms": 15.0,
        },
        {
            "action_id": f"act_{uuid.uuid4().hex[:12]}",
            "timestamp": _ts(30),
            "agent_id": "hp_frontdesk_agent",
            "customer_id": TENANT,
            "action_tool": "booking",
            "action_op": "view",
            "action_params": {"reservation_id": "RES-20260322-088"},
            "action_source": "agent",
            "action_estimated_risk": "low",
            "action_computed_risk": "low",
            "decision_verdict": "ALLOW",
            "decision_reason_code": "POLICY_PASS",
            "decision_explanation": "booking.view is in-scope for front-desk agent.",
            "decision_policy_version": V,
            "action_summary": "Viewed reservation RES-20260322-088",
            "stated_intent": "Confirm arrival details for incoming guest",
            "processing_latency_ms": 8.6,
        },
        # ── Out-of-scope / rogue BLOCK events ─────────────────────────────────
        {
            "action_id": f"act_{uuid.uuid4().hex[:12]}",
            "timestamp": _ts(25),
            "agent_id": "hp_concierge_agent",
            "customer_id": TENANT,
            "action_tool": "email",
            "action_op": "send",
            "action_params": {"to": "guest_list_all", "recipient_count": 847, "subject": "Special offer"},
            "action_source": "agent",
            "action_estimated_risk": "high",
            "action_computed_risk": "critical",
            "decision_verdict": "BLOCK",
            "decision_reason_code": "MAX_RECIPIENTS_EXCEEDED",
            "decision_explanation": "email.send to 847 recipients violates max_recipients=1 policy. Bulk guest PII transmission blocked.",
            "decision_policy_version": V,
            "policy_rule_id": "hp-rule-max-recipients",
            "action_summary": "BLOCKED: bulk email to 847 guests (all guest list)",
            "stated_intent": "Send promotional offer to all hotel guests",
            "anomaly_score": 0.91,
            "processing_latency_ms": 6.2,
        },
        {
            "action_id": f"act_{uuid.uuid4().hex[:12]}",
            "timestamp": _ts(22),
            "agent_id": "hp_concierge_agent",
            "customer_id": TENANT,
            "action_tool": "file",
            "action_op": "export",
            "action_params": {"path": "/guests/pii_full_export.csv", "destination": "s3://external-bucket"},
            "action_source": "agent",
            "action_estimated_risk": "critical",
            "action_computed_risk": "critical",
            "decision_verdict": "BLOCK",
            "decision_reason_code": "PII_EXPORT_DENIED",
            "decision_explanation": "file.export of guest PII to external cloud storage is prohibited. Concierge agents may not export data outside the property system.",
            "decision_policy_version": V,
            "policy_rule_id": "hp-rule-no-pii-export",
            "action_summary": "BLOCKED: guest PII export to external S3 bucket",
            "stated_intent": "Export guest contact list for marketing partner",
            "anomaly_score": 0.97,
            "processing_latency_ms": 5.9,
        },
        {
            "action_id": f"act_{uuid.uuid4().hex[:12]}",
            "timestamp": _ts(18),
            "agent_id": "hp_housekeeping_agent",
            "customer_id": TENANT,
            "action_tool": "shell",
            "action_op": "run",
            "action_params": {"command": "systemctl restart property-mgmt-service"},
            "action_source": "agent",
            "action_estimated_risk": "critical",
            "action_computed_risk": "critical",
            "decision_verdict": "BLOCK",
            "decision_reason_code": "TOOL_NOT_PERMITTED",
            "decision_explanation": "shell.run is not in the permitted tool set for housekeeping_agent. System restart commands require operator approval.",
            "decision_policy_version": V,
            "policy_rule_id": "hp-rule-no-shell",
            "action_summary": "BLOCKED: attempted shell command to restart property management service",
            "stated_intent": "Restart stuck check-in kiosk service",
            "anomaly_score": 0.88,
            "processing_latency_ms": 4.1,
        },
        {
            "action_id": f"act_{uuid.uuid4().hex[:12]}",
            "timestamp": _ts(14),
            "agent_id": "hp_billing_agent",
            "customer_id": TENANT,
            "action_tool": "payment",
            "action_op": "run",
            "action_params": {"amount": 1250.00, "currency": "USD", "guest_card": "****4242", "authorization": "none"},
            "action_source": "agent",
            "action_estimated_risk": "critical",
            "action_computed_risk": "critical",
            "decision_verdict": "BLOCK",
            "decision_reason_code": "UNAUTHORIZED_PAYMENT",
            "decision_explanation": "payment.run requires explicit human approval. billing_agent may only draft; it cannot execute charges.",
            "decision_policy_version": V,
            "policy_rule_id": "hp-rule-no-payment-exec",
            "action_summary": "BLOCKED: attempted unauthorised card charge of $1,250.00",
            "stated_intent": "Charge guest card for extended stay",
            "anomaly_score": 0.94,
            "processing_latency_ms": 3.8,
        },
        {
            "action_id": f"act_{uuid.uuid4().hex[:12]}",
            "timestamp": _ts(10),
            "agent_id": "hp_booking_agent",
            "customer_id": TENANT,
            "action_tool": "booking",
            "action_op": "create",
            "action_params": {"system": "external_ota", "bulk": True, "count": 120},
            "action_source": "agent",
            "action_estimated_risk": "high",
            "action_computed_risk": "high",
            "decision_verdict": "BLOCK",
            "decision_reason_code": "EXTERNAL_SYSTEM_DENIED",
            "decision_explanation": "booking.create targeting external OTA systems is out-of-scope. Agent is restricted to the internal PMS.",
            "decision_policy_version": V,
            "policy_rule_id": "hp-rule-internal-only",
            "action_summary": "BLOCKED: bulk booking creation on external OTA (120 reservations)",
            "stated_intent": "Mirror inventory to external booking channel",
            "anomaly_score": 0.79,
            "processing_latency_ms": 7.3,
        },
        {
            "action_id": f"act_{uuid.uuid4().hex[:12]}",
            "timestamp": _ts(6),
            "agent_id": "hp_frontdesk_agent",
            "customer_id": TENANT,
            "action_tool": "booking",
            "action_op": "delete",
            "action_params": {"reservation_id": "RES-20260310-022", "reason": "retroactive_correction"},
            "action_source": "agent",
            "action_estimated_risk": "high",
            "action_computed_risk": "high",
            "decision_verdict": "ESCALATE",
            "decision_reason_code": "DESTRUCTIVE_ACTION_REQUIRES_REVIEW",
            "decision_explanation": "booking.delete on a past reservation requires human manager review before proceeding.",
            "decision_policy_version": V,
            "policy_rule_id": "hp-rule-no-delete-past",
            "action_summary": "ESCALATED: attempted deletion of past reservation RES-20260310-022",
            "stated_intent": "Remove erroneous reservation from records",
            "anomaly_score": 0.72,
            "processing_latency_ms": 8.9,
        },
    ]


@router.post("/seed/hostpals")
async def seed_hostpals():
    """Seed the sandbox with the Hostpals (hospitality) demo scenario.

    Creates the sandbox tenant + API key if they don't exist, registers the
    five Hostpals agent roles, and inserts a realistic set of audit events
    (8 ALLOW + 5 BLOCK/ESCALATE) so you can immediately explore governance
    decisions, audit chains, and compliance reports without writing any code.

    Safe to call multiple times — each call resets sandbox events first.
    """
    db = get_db()
    try:
        # Ensure sandbox tenant/key exist
        tenant = db.get_or_create_sandbox_tenant()

        # Register Hostpals agents in tenant_agents
        for agent in _HOSTPALS_AGENTS:
            db.register_agent_full(
                agent_id=agent["agent_id"],
                tenant_id=tenant["tenant_id"],
                name=agent["name"],
                agent_type="software",
                description=agent["description"],
                capabilities=[],
                policy_pack="hostpals-policy-v1.0",
            )

        # Reset and re-seed sandbox events
        deleted = db.reset_sandbox()
        events = _hostpals_events(datetime.now(UTC))
        for event in events:
            db.insert_sandbox_event(event)

        logger.info(
            "Hostpals sandbox seeded: tenant=%s agents=%d events=%d (replaced %d)",
            tenant["tenant_id"], len(_HOSTPALS_AGENTS), len(events), deleted,
        )
        return {
            "status": "seeded",
            "tenant_id": tenant["tenant_id"],
            "sandbox_api_key": "edon_sandbox_key_dev_only",
            "agents_registered": [a["agent_id"] for a in _HOSTPALS_AGENTS],
            "events_inserted": len(events),
            "events_replaced": deleted,
            "scenario": "Hostpals — Hotel & Property Management",
            "summary": {
                "allow": sum(1 for e in events if e["decision_verdict"] == "ALLOW"),
                "block": sum(1 for e in events if e["decision_verdict"] == "BLOCK"),
                "escalate": sum(1 for e in events if e["decision_verdict"] == "ESCALATE"),
            },
            "next_steps": {
                "view_audit_events": "GET /audit/events  (X-EDON-TOKEN: edon_sandbox_key_dev_only)",
                "compliance_report": "GET /compliance/report?standard=eu_ai_act",
                "review_queue": "GET /review-queue",
                "reset": "GET /sandbox/reset",
                "docs": "https://edon-gateway.fly.dev/docs",
            },
        }
    except Exception as exc:
        logger.error("Hostpals sandbox seed failed: %s", exc)
        return {"status": "error", "detail": str(exc)}


@router.get("/info")
async def sandbox_info():
    """Return sandbox tenant credentials and usage hints.

    This endpoint is intentionally unauthenticated so that new developers can
    discover the sandbox without any prior setup.
    """
    return {
        "sandbox_api_key": "edon_sandbox_key_dev_only",
        "sandbox_tenant_id": "tenant_sandbox_edon",
        "note": (
            "The sandbox key is for development and exploration only. "
            "Decisions are logged to sandbox_audit_events, not the production audit trail. "
            "Use X-EDON-TOKEN: edon_sandbox_key_dev_only in your requests."
        ),
        "endpoints": {
            "govern_action": "POST /v1/action",
            "audit_events": "GET /audit/events",
            "policy_packs": "GET /policy-packs",
            "reset_sandbox": "GET /sandbox/reset",
        },
        "gateway_url": "https://edon-gateway.fly.dev",
        "docs_url": "https://edon-gateway.fly.dev/docs",
    }


@router.get("/reset")
async def reset_sandbox(request: Request):
    """Flush all sandbox audit data.

    Deletes every row from `sandbox_audit_events`.  Safe to call repeatedly
    during development to start from a clean state.

    Returns:
        JSON with `deleted_events` count and `status`.
    """
    db = get_db()
    try:
        deleted = db.reset_sandbox()
        logger.info("Sandbox reset: %d events deleted", deleted)
        return {"deleted_events": deleted, "status": "reset"}
    except Exception as exc:
        logger.error("Sandbox reset failed: %s", exc)
        return {"deleted_events": 0, "status": "error", "detail": str(exc)}


@router.get("/status")
async def sandbox_status():
    """Return current sandbox event count and tenant health."""
    db = get_db()
    try:
        with db._get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM sandbox_audit_events"
            ).fetchone()
            event_count = row["cnt"] if row else 0

        tenant = db.get_or_create_sandbox_tenant()
        return {
            "status": "active",
            "tenant_id": tenant["tenant_id"],
            "event_count": event_count,
            "is_sandbox": True,
        }
    except Exception as exc:
        logger.error("Sandbox status check failed: %s", exc)
        return {"status": "error", "detail": str(exc)}
