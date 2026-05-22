"""Canonical tenant knowledge plane for the Governance Assistant.

This module assembles the tenant snapshot that the assistant should use as its
source of truth: onboarding profile, market pack, deployment mode, signoff,
agents, policies, integrations, conversations, durable memories, and drift.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict, field
from datetime import UTC, datetime
from typing import Any

from .config import config
from .integration_catalog import get_enterprise_integration_catalog
from .logging_config import get_logger
from .market_packs import get_market_pack
from .onboarding.profile import get_onboarding_store
from .onboarding.signoff import get_signoff_store
from .persistence import get_db

logger = get_logger(__name__)


@dataclass
class TenantKnowledgeSnapshot:
    tenant_id: str
    generated_at: str
    deployment_mode: str | None
    market_pack: dict[str, Any] | None
    onboarding_profile: dict[str, Any] | None
    latest_signoff: dict[str, Any] | None
    active_policy_preset: dict[str, Any] | None
    agents: list[dict[str, Any]] = field(default_factory=list)
    policy_rules: list[dict[str, Any]] = field(default_factory=list)
    connected_services: list[str] = field(default_factory=list)
    enterprise_targets: list[dict[str, Any]] = field(default_factory=list)
    memories: list[dict[str, Any]] = field(default_factory=list)
    conversations: list[dict[str, Any]] = field(default_factory=list)
    preferences: dict[str, str] = field(default_factory=dict)
    review_queue: list[dict[str, Any]] = field(default_factory=list)
    compliance_health: dict[str, Any] = field(default_factory=dict)
    drift: dict[str, Any] = field(default_factory=dict)
    snapshot_hash: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _json_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _summarize_profile(profile: Any) -> dict[str, Any] | None:
    if profile is None:
        return None
    d = profile.as_dict() if hasattr(profile, "as_dict") else dict(profile)
    return {
        "profile_id": d.get("profile_id"),
        "tenant_id": d.get("tenant_id"),
        "org_name": d.get("org_name"),
        "stage": d.get("stage"),
        "deployment_mode": d.get("deployment_mode"),
        "market_pack": d.get("market_pack"),
        "market_pack_version": d.get("market_pack_version"),
        "identity_provider": d.get("identity_provider"),
        "risk_tier": d.get("risk_tier"),
        "risk_score": d.get("risk_score"),
        "environments": d.get("environments", []),
        "compliance_requirements": d.get("compliance_requirements", []),
        "all_data_classes": d.get("all_data_classes", []),
        "all_actions": d.get("all_actions", []),
        "external_sinks": d.get("external_sinks", []),
        "signed_off": bool(d.get("signed_off")),
        "signed_off_at": d.get("signed_off_at"),
        "signed_off_by": d.get("signed_off_by"),
    }


def _build_compliance_health(db, tenant_id: str) -> dict[str, Any]:
    try:
        rules = db.get_policy_rules(tenant_id, enabled_only=True) or []
        with db._get_connection() as conn:
            row = conn.execute(
                """
                SELECT
                  COUNT(*) as total,
                  SUM(CASE WHEN decision_verdict='BLOCK' THEN 1 ELSE 0 END) as blocks,
                  SUM(CASE WHEN decision_verdict='ESCALATE' THEN 1 ELSE 0 END) as escalations
                FROM audit_events
                WHERE customer_id = ? AND timestamp >= datetime('now','-7 days')
                """,
                (tenant_id,),
            ).fetchone()
        total = row["total"] if row else 0
        blocks = row["blocks"] if row else 0
        escalations = row["escalations"] if row else 0
        compliance_rate = round((total - blocks) / total * 100, 1) if total else 100.0
        return {
            "active_policy_rules": len(rules),
            "decisions_7d": total,
            "blocks_7d": blocks,
            "escalations_7d": escalations,
            "compliance_rate_pct": compliance_rate,
            "status": "healthy" if compliance_rate >= 90 and len(rules) >= 3 else "needs_attention",
        }
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)[:200]}


def _summarize_agents(agents: list[dict[str, Any]]) -> dict[str, Any]:
    vendors = sorted({str(a.get("vendor_id") or "").strip() for a in agents if a.get("vendor_id")})
    departments = sorted({str(a.get("department") or "").strip() for a in agents if a.get("department")})
    return {
        "count": len(agents),
        "vendors": vendors,
        "departments": departments,
        "vendor_count": len(vendors),
        "department_count": len(departments),
    }


def _build_drift_status(db, tenant_id: str) -> dict[str, Any]:
    try:
        catalog = get_enterprise_integration_catalog(approved_only=False)
        approved_targets = [t for t in catalog.get("targets", []) if t.get("enterprise_supported")]
        connector_version_drift = any(
            not t.get("last_verified") or t.get("certification_status") != "certified"
            for t in approved_targets
        )
        idp_claim_drift = not (config.ENTERPRISE_SSO_ONLY and bool(config.ENTERPRISE_IDENTITY_PROVIDERS))
        policy_pack_drift = not config.AUTH_ENABLED or not config.ENCRYPT_AUDIT_PAYLOAD
        permissions_drift = not (config.is_production() and config.ENTERPRISE_DEFAULT_USER_ROLE == "viewer")
        edge_config_drift = not (
            config.EDGE_REQUIRE_NODE_CERTIFICATE
            and config.EDGE_REQUIRE_ATTESTATION
            and bool(config.EDGE_BUNDLE_SIGNING_KEY)
        )
        memory_review_backlog = 0
        try:
            memory_review_backlog = len(
                [m for m in db.get_memories(tenant_id, limit=200, include_expired=True) if m.get("review_status") != "approved"]
            )
        except Exception:
            pass
        status = "healthy"
        if any([connector_version_drift, idp_claim_drift, policy_pack_drift, permissions_drift, edge_config_drift]):
            status = "degraded"
        return {
            "connector_version_drift": connector_version_drift,
            "idp_claim_drift": idp_claim_drift,
            "policy_pack_drift": policy_pack_drift,
            "permissions_drift": permissions_drift,
            "edge_config_drift": edge_config_drift,
            "memory_review_backlog": memory_review_backlog,
            "status": status,
        }
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)[:200]}


def build_tenant_knowledge_snapshot(tenant_id: str) -> TenantKnowledgeSnapshot:
    db = get_db()
    generated_at = datetime.now(UTC).isoformat()

    profile = None
    deployment_mode = None
    market_pack = None
    latest_signoff = None
    active_policy_preset = None

    try:
        profiles = get_onboarding_store().list_for_tenant(tenant_id)
        if profiles:
            profile = profiles[0]
            deployment_mode = (profile.get("deployment_mode") or "pilot").strip().lower()
            market_pack = get_market_pack(profile.get("market_pack"))
    except Exception as exc:
        logger.debug("tenant knowledge profile lookup failed for %s: %s", tenant_id, exc)

    try:
        latest_signoff = get_signoff_store().latest_approved(tenant_id)
    except Exception as exc:
        logger.debug("tenant knowledge signoff lookup failed for %s: %s", tenant_id, exc)

    try:
        active_policy_preset = db.get_active_policy_preset()
    except Exception as exc:
        logger.debug("tenant knowledge active preset lookup failed for %s: %s", tenant_id, exc)

    agents: list[dict[str, Any]] = []
    rules: list[dict[str, Any]] = []
    memories: list[dict[str, Any]] = []
    conversations: list[dict[str, Any]] = []
    connected_services: list[str] = []
    review_queue: list[dict[str, Any]] = []
    preferences: dict[str, str] = {}

    try:
        agents = db.list_agents(tenant_id) or []
    except Exception as exc:
        logger.debug("tenant knowledge agent lookup failed for %s: %s", tenant_id, exc)

    try:
        rules = db.get_policy_rules(tenant_id, enabled_only=False) or []
    except Exception as exc:
        logger.debug("tenant knowledge policy lookup failed for %s: %s", tenant_id, exc)

    try:
        memories = db.get_memories(tenant_id, limit=40, include_expired=False)
    except Exception as exc:
        logger.debug("tenant knowledge memory lookup failed for %s: %s", tenant_id, exc)

    try:
        conversations = db.get_conversations(tenant_id, limit=10) or []
    except Exception as exc:
        logger.debug("tenant knowledge conversation lookup failed for %s: %s", tenant_id, exc)

    try:
        connected_services = db.list_connected_services_for_tenant(tenant_id) or []
    except Exception as exc:
        logger.debug("tenant knowledge integration lookup failed for %s: %s", tenant_id, exc)

    try:
        review_queue = db.get_review_queue(tenant_id=tenant_id, status="pending", limit=10) or []
    except Exception as exc:
        logger.debug("tenant knowledge review queue lookup failed for %s: %s", tenant_id, exc)

    try:
        preferences = db.read_preferences(tenant_id) or {}
    except Exception as exc:
        logger.debug("tenant knowledge preference lookup failed for %s: %s", tenant_id, exc)

    try:
        catalog = get_enterprise_integration_catalog(approved_only=False)
        enterprise_targets = [
            {
                "identifier": t.get("identifier"),
                "title": t.get("title"),
                "category": t.get("category"),
                "status_tier": t.get("status_tier"),
                "certification_status": t.get("certification_status"),
                "last_verified": t.get("last_verified"),
                "connector_scope": t.get("connector_contract", {}).get("connector_scope"),
            }
            for t in catalog.get("targets", [])
            if t.get("enterprise_supported")
        ]
    except Exception as exc:
        logger.debug("tenant knowledge catalog lookup failed for %s: %s", tenant_id, exc)
        enterprise_targets = []

    compliance_health = _build_compliance_health(db, tenant_id)
    drift = _build_drift_status(db, tenant_id)
    agent_summary = _summarize_agents(agents)

    snapshot = TenantKnowledgeSnapshot(
        tenant_id=tenant_id,
        generated_at=generated_at,
        deployment_mode=deployment_mode,
        market_pack=market_pack,
        onboarding_profile=_summarize_profile(profile),
        latest_signoff=latest_signoff,
        active_policy_preset=active_policy_preset,
        agents=agents,
        policy_rules=rules,
        connected_services=connected_services,
        enterprise_targets=enterprise_targets,
        memories=memories,
        conversations=conversations,
        preferences=preferences,
        review_queue=review_queue,
        compliance_health=compliance_health,
        drift=drift,
    )
    snapshot.preferences = {
        **snapshot.preferences,
        "agent_count": str(agent_summary["count"]),
        "vendor_count": str(agent_summary["vendor_count"]),
        "department_count": str(agent_summary["department_count"]),
    }
    snapshot.snapshot_hash = _json_hash(snapshot.as_dict())
    return snapshot


def render_tenant_knowledge_snapshot(snapshot: TenantKnowledgeSnapshot) -> str:
    data = snapshot.as_dict()
    lines: list[str] = [f"TENANT KNOWLEDGE SNAPSHOT (tenant_id={snapshot.tenant_id}):"]

    profile = data.get("onboarding_profile") or {}
    if profile:
        lines.append(
            f"  Tenant: {profile.get('org_name')} | stage={profile.get('stage')} | "
            f"mode={profile.get('deployment_mode')} | market_pack={profile.get('market_pack')}@{profile.get('market_pack_version')}"
        )
        if profile.get("identity_provider"):
            lines.append(f"  Identity provider: {profile.get('identity_provider')}")
        if profile.get("risk_tier"):
            lines.append(f"  Risk: {profile.get('risk_tier')} ({profile.get('risk_score')}/10)")

    signoff = data.get("latest_signoff") or {}
    if signoff:
        lines.append(
            f"  Latest signoff: {signoff.get('status')} by {signoff.get('resolved_by') or signoff.get('requested_by')} "
            f"at {signoff.get('resolved_at') or signoff.get('requested_at')}"
        )
        if signoff.get("customer_signoff_artifacts"):
            lines.append(
                f"  Signoff artifacts: {', '.join(signoff.get('customer_signoff_artifacts')[:6])}"
            )

    lines.append(f"  Active policy rules: {len(data.get('policy_rules') or [])}")
    agents = data.get("agents") or []
    lines.append(f"  Registered agents: {len(agents)}")
    if agents:
        summary = _summarize_agents(agents)
        if summary.get("vendor_count"):
            lines.append(f"  Agent vendors: {summary.get('vendor_count')} ({', '.join(summary.get('vendors')[:8])})")
        if summary.get("department_count"):
            lines.append(f"  Agent departments: {summary.get('department_count')} ({', '.join(summary.get('departments')[:12])})")

    connected = data.get("connected_services") or []
    if connected:
        lines.append(f"  Connected services: {', '.join(connected)}")

    targets = data.get("enterprise_targets") or []
    if targets:
        lines.append(
            f"  Approved enterprise targets: {', '.join((t.get('identifier') or t.get('title') or 'unknown') for t in targets[:10])}"
        )

    memories = data.get("memories") or []
    if memories:
        lines.append("  Durable memories:")
        by_cat: dict[str, list[dict[str, Any]]] = {}
        for memory in memories:
            by_cat.setdefault(memory.get("category", "uncategorized"), []).append(memory)
        for cat, items in by_cat.items():
            lines.append(f"    {cat}:")
            for item in items[:5]:
                prefix = "[PINNED] " if item.get("pinned") else ""
                expiry = f" expires={item.get('expires_at')}" if item.get("expires_at") else ""
                lines.append(f"      - {prefix}{item.get('fact')}{expiry}")

    review_queue = data.get("review_queue") or []
    if review_queue:
        lines.append(f"  Pending memory reviews: {len(review_queue)}")

    compliance = data.get("compliance_health") or {}
    if compliance:
        lines.append(
            f"  Compliance health: {compliance.get('status')} | "
            f"rules={compliance.get('active_policy_rules')} | "
            f"blocks_7d={compliance.get('blocks_7d')} | "
            f"escalations_7d={compliance.get('escalations_7d')}"
        )

    drift = data.get("drift") or {}
    if drift:
        lines.append(f"  Drift: {drift.get('status')}")

    lines.append(f"  Snapshot hash: {snapshot.snapshot_hash}")
    return "\n".join(lines)
