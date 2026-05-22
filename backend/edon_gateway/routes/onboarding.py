"""EDON Onboarding Copilot — HTTP API routes.

Drives the 10-step client onboarding flow end-to-end.

Endpoints:
    POST /v1/onboarding/intake               — Step 1: submit intake questionnaire
    GET  /v1/onboarding/profiles             — list profiles for tenant
    GET  /v1/onboarding/profiles/{id}        — get a specific profile
    POST /v1/onboarding/profiles/{id}/topology       — Step 2: generate enforcement topology
    POST /v1/onboarding/profiles/{id}/bootstrap      — Step 3: generate policy bootstrap
    GET  /v1/onboarding/profiles/{id}/deployment     — Step 4: get deployment package
    POST /v1/onboarding/profiles/{id}/shadow         — Step 6: enable/disable shadow mode
    POST /v1/onboarding/profiles/{id}/signoff/request — Step 7: request go-live signoff
    POST /v1/onboarding/signoffs/{id}/approve         — Step 7: approve go-live
    POST /v1/onboarding/signoffs/{id}/reject          — Step 7: reject go-live
    GET  /v1/onboarding/profiles/{id}/expansion       — Step 10: check expansion signals
    GET  /v1/onboarding/profiles/{id}/status          — full pipeline status summary
"""
from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..tenancy import get_request_tenant_id
from ..logging_config import get_logger
from ..market_packs import get_market_pack, normalize_market_pack_slug
from ..onboarding.profile import get_onboarding_store, normalize_deployment_mode
from ..onboarding.topology import generate_topology
from ..onboarding.policy_bootstrap import bootstrap_policies
from ..onboarding.deployment_package import generate_deployment_package
from ..onboarding.repeatable_architecture import build_repeatable_architecture_standard
from ..onboarding.signoff import get_signoff_store
from ..onboarding.expansion import check_expansion_signals
from ..persistence import get_db

logger = get_logger(__name__)
router = APIRouter(prefix="/v1/onboarding", tags=["onboarding"])


def _require_request_tenant(request: Request, purpose: str) -> str:
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(400, f"Tenant context is required to {purpose}.")
    return tenant_id


def _assert_owns_profile(profile, tenant_id: str) -> None:
    """Raise 404 (not 403) if profile doesn't belong to this tenant — avoids leaking existence."""
    if profile is None or not tenant_id or profile.tenant_id != tenant_id:
        raise HTTPException(404, f"Profile not found")


# ── Request models ─────────────────────────────────────────────────────────────

def _classify_action_risk(action_name: str, data_classes: list[str]) -> str:
    text = action_name.lower()
    if any(keyword in text for keyword in ("writeback", "medication", "admin", "delete", "destroy")):
        return "critical"
    if any(keyword in text for keyword in ("write", "update", "submit", "approve", "execute")):
        return "high"
    if any(keyword in text for keyword in ("notify", "message", "ticket", "draft")):
        return "medium"
    if data_classes and any(
        label.upper() in {"PHI", "FINANCIAL", "CREDENTIAL", "SAFETY-CRITICAL"}
        for label in data_classes
    ):
        return "high"
    return "low"


def _build_governed_action_matrix(profile, bundle) -> list[dict]:
    matrix: list[dict] = []
    for agent in profile.agent_systems:
        for action in agent.actions or []:
            risk = _classify_action_risk(action, agent.data_classes or [])
            matrix.append({
                "system": agent.name,
                "action": action,
                "risk": risk,
                "approval": "required" if risk in ("high", "critical") else "optional",
                "rollback": "partial" if risk in ("high", "critical") else "full",
                "logged": True,
                "data_classes": agent.data_classes or [],
            })
    if not matrix:
        matrix.append({
            "system": profile.org_name,
            "action": "governed.action",
            "risk": "medium",
            "approval": "optional",
            "rollback": "full",
            "logged": True,
            "data_classes": profile.all_data_classes,
        })
    return matrix


def _deployment_mode_label(profile) -> str:
    return normalize_deployment_mode(getattr(profile, "deployment_mode", "pilot"))


def _market_pack_label(profile) -> str:
    return normalize_market_pack_slug(getattr(profile, "market_pack", "healthcare"))


class AgentSystemInput(BaseModel):
    name: str
    agent_type: str = "llm_agent"
    actions: list[str] = []
    data_classes: list[str] = []
    external_sinks: list[str] = []
    description: str = ""
    vendor_name: Optional[str] = None
    department: Optional[str] = None


class IntakeRequest(BaseModel):
    org_name: str
    agent_systems: list[AgentSystemInput]
    identity_provider: str = "none"
    environments: list[str] = ["saas"]
    compliance_requirements: list[str] = []
    deployment_mode: str = "pilot"
    market_pack: str = "healthcare"
    policy_pack: str = "hospital"


class OnboardingManifest(BaseModel):
    tenant_id: str
    org_name: str
    deployment_mode: str = "pilot"
    market_pack: str = "healthcare"
    policy_pack: str = "hospital"
    identity_provider: str = "none"
    environments: list[str] = ["saas"]
    compliance_requirements: list[str] = []
    agent_systems: list[AgentSystemInput] = []
    support_contact: str = ""
    support_webhook_url: str = ""
    support_diagnostics_enabled: bool = True
    production_promotion_requires_approval: bool = True
    connector_writeback_requires_approval: bool = True
    agent_inventory: list[dict] = []
    notes: str = ""


class ShadowModeRequest(BaseModel):
    enabled: bool


class SignoffCreateRequest(BaseModel):
    requested_by: str
    enforcement_scope: list[str]
    escalation_rules_accepted: bool = True
    kill_switch_authority: str = "admin"
    data_classes_governed: list[str] = []
    governed_action_matrix: list[dict] = []
    risk_tier_definitions: list[dict] = []
    fail_open_exceptions: list[dict] = []
    rollback_limits: list[str] = []
    escalation_paths: list[str] = []
    customer_signoff_artifacts: list[str] = []


class SignoffResolveRequest(BaseModel):
    resolved_by: str
    rejection_reason: Optional[str] = None


class RuntimeRegistrationRequest(BaseModel):
    runtime_name: str
    vendor_name: str = ""
    vendor_id: str = ""
    source_type: str = "Existing system"
    agent_count: int = 1
    department: str = ""
    purpose: str = ""
    runtime_type: str = "Service"
    requested_access: list[str] = []
    connectors: list[str] = []


class RuntimeReviewRequest(BaseModel):
    reviewed_by: str
    approved: bool = True
    notes: Optional[str] = None


class RuntimePromoteRequest(BaseModel):
    promoted_by: str
    agent_id: Optional[str] = None


def _audit_runtime_event(runtime, tenant_id: str, *, action_op: str, verdict: str, actor: str, notes: str = "") -> None:
    action = {
        "id": f"{action_op}-{runtime.runtime_id}",
        "tool": "onboarding",
        "op": action_op,
        "params": runtime.as_dict(),
        "source": "onboarding",
        "estimated_risk": runtime.risk_tier,
        "computed_risk": runtime.risk_score,
        "requested_at": runtime.updated_at or runtime.created_at,
    }
    decision = {
        "verdict": verdict,
        "reason_code": "ONBOARDING",
        "explanation": notes or runtime.policy_simulation.get("summary", "Shadow Governance active."),
        "policy_version": runtime.governance_mode,
        "action_summary": f"{action_op}: {runtime.runtime_name}",
    }
    context = {
        "tenant_id": tenant_id,
        "runtime_id": runtime.runtime_id,
        "runtime_name": runtime.runtime_name,
        "vendor_name": runtime.vendor_name,
        "vendor_id": runtime.vendor_id,
        "source_type": runtime.source_type,
        "agent_count": runtime.agent_count,
        "department": runtime.department,
        "purpose": runtime.purpose,
        "runtime_type": runtime.runtime_type,
        "requested_access": runtime.requested_access,
        "connectors": runtime.connectors,
        "governance_mode": runtime.governance_mode,
        "status": runtime.status,
        "review_status": runtime.review_status,
        "risk_score": runtime.risk_score,
        "risk_tier": runtime.risk_tier,
        "actor": actor,
        "notes": notes,
    }
    try:
        db = get_db()
        db.save_audit_event(
            action,
            decision,
            intent_id=runtime.runtime_id,
            agent_id=runtime.promoted_agent_id or runtime.runtime_id,
            context=context,
            customer_id=tenant_id,
            action_summary=decision["action_summary"],
            stated_intent="runtime onboarding",
            user_message=notes or None,
        )
    except Exception as e:
        logger.warning(f"[onboarding/runtime] could not persist audit event: {e}")


# ── Step 1: Intake ────────────────────────────────────────────────────────────

@router.post("/intake")
async def submit_intake(request: Request, body: IntakeRequest):
    """Submit the onboarding intake questionnaire. Returns GovernanceDeploymentProfile v1."""
    tenant_id = _require_request_tenant(request, "submit onboarding intake")
    store = get_onboarding_store()
    deployment_mode = normalize_deployment_mode(body.deployment_mode)
    market_pack = normalize_market_pack_slug(body.market_pack)

    profile = store.create(
        tenant_id=tenant_id,
        org_name=body.org_name,
        agent_systems=[a.model_dump() for a in body.agent_systems],
        identity_provider=body.identity_provider,
        environments=body.environments,
        compliance_requirements=body.compliance_requirements,
        deployment_mode=deployment_mode,
        market_pack=market_pack,
        policy_pack=body.policy_pack,
    )
    logger.info(f"[onboarding/intake] profile={profile.profile_id} tenant={tenant_id}")
    return {
        "profile": profile.as_dict(),
        "deployment_mode": deployment_mode,
        "market_pack": get_market_pack(market_pack),
        "next_step": {
            "action": f"POST /v1/onboarding/profiles/{profile.profile_id}/topology",
            "description": "Generate EDON Enforcement Topology",
        },
    }


@router.post("/manifest")
async def apply_onboarding_manifest(request: Request, body: OnboardingManifest):
    """Apply a tenant onboarding manifest and create the initial profile."""
    tenant_id = _require_request_tenant(request, "apply an onboarding manifest")
    if tenant_id != body.tenant_id:
        raise HTTPException(400, "Manifest tenant_id must match request tenant context.")

    store = get_onboarding_store()
    profile = store.create(
        tenant_id=body.tenant_id,
        org_name=body.org_name,
        agent_systems=[a.model_dump() for a in body.agent_systems],
        identity_provider=body.identity_provider,
        environments=body.environments,
        compliance_requirements=body.compliance_requirements,
        deployment_mode=body.deployment_mode,
        market_pack=body.market_pack,
        policy_pack=body.policy_pack,
    )
    store.update_stage(profile.profile_id, "intake")
    manifest = {
        "tenant_id": body.tenant_id,
        "org_name": body.org_name,
        "deployment_mode": profile.deployment_mode,
        "market_pack": profile.market_pack,
        "market_pack_version": profile.market_pack_version,
        "policy_pack": profile.policy_pack,
        "support_contact": body.support_contact,
        "support_webhook_url_set": bool(body.support_webhook_url.strip()),
        "support_diagnostics_enabled": body.support_diagnostics_enabled,
        "production_promotion_requires_approval": body.production_promotion_requires_approval,
        "connector_writeback_requires_approval": body.connector_writeback_requires_approval,
        "agent_inventory": body.agent_inventory,
        "notes": body.notes,
    }
    return {
        "manifest": manifest,
        "profile": profile.as_dict(),
        "next_step": {
            "action": f"POST /v1/onboarding/profiles/{profile.profile_id}/topology",
            "description": "Generate enforcement topology from the manifest-driven profile",
        },
    }


# ── Profile CRUD ──────────────────────────────────────────────────────────────

@router.get("/profiles")
async def list_profiles(request: Request):
    tenant_id = _require_request_tenant(request, "list onboarding profiles")
    store = get_onboarding_store()
    profiles = store.list_for_tenant(tenant_id)
    return {"profiles": profiles, "count": len(profiles)}


@router.get("/profiles/{profile_id}")
async def get_profile(profile_id: str, request: Request):
    tenant_id = _require_request_tenant(request, "view an onboarding profile")
    store = get_onboarding_store()
    profile = store.get(profile_id)
    _assert_owns_profile(profile, tenant_id)
    return {"profile": profile.as_dict()}


@router.post("/runtimes")
async def register_runtime(request: Request, body: RuntimeRegistrationRequest):
    tenant_id = _require_request_tenant(request, "register a governed runtime")
    store = get_onboarding_store()
    runtime = store.register_runtime(
        tenant_id=tenant_id,
        runtime_name=body.runtime_name,
        vendor_name=body.vendor_name,
        vendor_id=body.vendor_id,
        source_type=body.source_type,
        agent_count=body.agent_count,
        department=body.department,
        purpose=body.purpose,
        runtime_type=body.runtime_type,
        requested_access=body.requested_access,
        connectors=body.connectors,
    )
    _audit_runtime_event(runtime, tenant_id, action_op="register_runtime", verdict="ALLOW", actor="system")
    return {
        "runtime": runtime.as_dict(),
        "message": "Runtime registered in shadow governance.",
        "next_step": {
            "action": f"POST /v1/onboarding/runtimes/{runtime.runtime_id}/review",
            "description": "Review the runtime before promotion",
        },
    }


@router.get("/runtimes")
async def list_runtimes(request: Request):
    tenant_id = _require_request_tenant(request, "list governed runtimes")
    store = get_onboarding_store()
    runtimes = store.list_runtimes_for_tenant(tenant_id)
    return {"runtimes": runtimes, "count": len(runtimes)}


@router.get("/runtimes/{runtime_id}")
async def get_runtime(runtime_id: str, request: Request):
    tenant_id = _require_request_tenant(request, "view a governed runtime")
    store = get_onboarding_store()
    runtime = store.get_runtime(runtime_id)
    if runtime is None or runtime.tenant_id != tenant_id:
        raise HTTPException(404, "Runtime not found")
    return {"runtime": runtime.as_dict()}


@router.post("/runtimes/{runtime_id}/review")
async def review_runtime(runtime_id: str, request: Request, body: RuntimeReviewRequest):
    tenant_id = _require_request_tenant(request, "review a governed runtime")
    store = get_onboarding_store()
    runtime = store.get_runtime(runtime_id)
    if runtime is None or runtime.tenant_id != tenant_id:
        raise HTTPException(404, "Runtime not found")
    reviewed = store.review_runtime(runtime_id, body.reviewed_by, body.approved, body.notes or "")
    if reviewed is None:
        raise HTTPException(404, "Runtime not found")
    _audit_runtime_event(reviewed, tenant_id, action_op="review_runtime", verdict="ALLOW" if body.approved else "BLOCK", actor=body.reviewed_by, notes=body.notes or "")
    return {
        "runtime": reviewed.as_dict(),
        "message": "Runtime review recorded.",
    }


@router.post("/runtimes/{runtime_id}/promote")
async def promote_runtime(runtime_id: str, request: Request, body: RuntimePromoteRequest):
    tenant_id = _require_request_tenant(request, "promote a governed runtime")
    store = get_onboarding_store()
    runtime = store.get_runtime(runtime_id)
    if runtime is None or runtime.tenant_id != tenant_id:
        raise HTTPException(404, "Runtime not found")
    if runtime.review_status != "approved":
        raise HTTPException(409, "Runtime must be approved before promotion")

    promoted = store.promote_runtime(runtime_id, body.promoted_by, agent_id=body.agent_id)
    if promoted is None:
        raise HTTPException(404, "Runtime not found")

    db = get_db()
    try:
        db.register_agent_full(
            agent_id=promoted.promoted_agent_id or promoted.runtime_id,
            tenant_id=tenant_id,
            name=promoted.runtime_name,
            agent_type=promoted.runtime_type.lower(),
            description=promoted.purpose,
            capabilities=promoted.requested_access,
            policy_pack="hospital",
            mag_enabled=False,
            metadata={
                "runtime_id": promoted.runtime_id,
                "vendor_name": promoted.vendor_name,
                "vendor_id": promoted.vendor_id,
                "source_type": promoted.source_type,
                "agent_count": promoted.agent_count,
                "department": promoted.department,
                "purpose": promoted.purpose,
                "runtime_type": promoted.runtime_type,
                "requested_access": promoted.requested_access,
                "connectors": promoted.connectors,
                "governance_mode": promoted.governance_mode,
                "risk_score": promoted.risk_score,
                "risk_tier": promoted.risk_tier,
                "policy_simulation": promoted.policy_simulation,
            },
            vendor_id=promoted.vendor_id or None,
            department=promoted.department or None,
        )
        try:
            db.register_agent(tenant_id, promoted.promoted_agent_id or promoted.runtime_id)
        except Exception:
            pass
    except Exception as e:
        logger.exception("[onboarding/runtime] failed to promote runtime into agent registry: %s", e)
        raise HTTPException(500, f"Failed to promote runtime: {e}")

    _audit_runtime_event(promoted, tenant_id, action_op="promote_runtime", verdict="ALLOW", actor=body.promoted_by)
    return {
        "runtime": promoted.as_dict(),
        "agent": db.get_agent(promoted.promoted_agent_id or promoted.runtime_id, tenant_id=tenant_id),
        "message": "Runtime promoted into governed agent fleet.",
    }


# ── Step 2: Topology ──────────────────────────────────────────────────────────

@router.post("/profiles/{profile_id}/topology")
async def generate_enforcement_topology(profile_id: str, request: Request):
    """Generate the EDON Enforcement Topology — exactly where EDON plugs in."""
    tenant_id = _require_request_tenant(request, "generate an onboarding topology")
    store = get_onboarding_store()
    profile = store.get(profile_id)
    _assert_owns_profile(profile, tenant_id)

    topology = generate_topology(profile)
    store.update_stage(profile_id, "topology")

    return {
        "topology": topology.as_dict(),
        "next_step": {
            "action": f"POST /v1/onboarding/profiles/{profile_id}/bootstrap",
            "description": "Generate 3-layer policy bootstrap",
        },
    }


# ── Step 3: Policy Bootstrap ──────────────────────────────────────────────────

@router.post("/profiles/{profile_id}/bootstrap")
async def run_policy_bootstrap(profile_id: str, request: Request):
    """Generate the 3-layer initial policy set (hard safety, operational, intent contracts)."""
    tenant_id = _require_request_tenant(request, "bootstrap onboarding policies")
    store = get_onboarding_store()
    profile = store.get(profile_id)
    _assert_owns_profile(profile, tenant_id)

    bundle = bootstrap_policies(profile)
    store.update_stage(profile_id, "bootstrap")

    return {
        "policy_bundle": bundle.as_dict(),
        "next_step": {
            "action": f"GET /v1/onboarding/profiles/{profile_id}/deployment",
            "description": "Get deployment package for IT review",
        },
    }


# ── Step 4: Deployment Package ────────────────────────────────────────────────

@router.get("/profiles/{profile_id}/deployment")
async def get_deployment_package(profile_id: str, request: Request):
    """Get the IT-approvable deployment package (Helm values, env vars, network rules)."""
    tenant_id = _require_request_tenant(request, "view an onboarding deployment package")
    store = get_onboarding_store()
    profile = store.get(profile_id)
    _assert_owns_profile(profile, tenant_id)

    topology = generate_topology(profile)
    package = generate_deployment_package(profile, topology)
    store.update_stage(profile_id, "deployment")

    return {
        "deployment_package": package.as_dict(),
        "next_step": {
            "action": f"POST /v1/onboarding/profiles/{profile_id}/shadow",
            "description": "Enable shadow mode to begin observing agent traffic",
        },
    }


@router.get("/profiles/{profile_id}/architecture-standard")
async def get_repeatable_architecture_standard(profile_id: str, request: Request):
    """Get the repeatable architecture contract for this tenant."""
    tenant_id = _require_request_tenant(request, "view the repeatable architecture standard")
    store = get_onboarding_store()
    profile = store.get(profile_id)
    _assert_owns_profile(profile, tenant_id)

    topology = generate_topology(profile)
    bundle = bootstrap_policies(profile)
    package = generate_deployment_package(profile, topology)
    standard = build_repeatable_architecture_standard(profile, topology, package, bundle)

    return {
        "architecture_standard": standard.as_dict(),
        "next_step": {
            "action": f"POST /v1/onboarding/profiles/{profile_id}/shadow",
            "description": "Exercise the standard in shadow mode before signoff",
        },
    }


# ── Step 6: Shadow Mode ───────────────────────────────────────────────────────

@router.post("/profiles/{profile_id}/shadow")
async def set_shadow_mode(profile_id: str, request: Request, body: ShadowModeRequest):
    """Enable or disable shadow mode for this profile's tenant."""
    tenant_id = _require_request_tenant(request, "change shadow mode")
    store = get_onboarding_store()
    profile = store.get(profile_id)
    _assert_owns_profile(profile, tenant_id)

    # Flip the actual gateway shadow mode setting
    try:
        from ..persistence import get_db
        db = get_db()
        if hasattr(db, "set_shadow_mode"):
            db.set_shadow_mode(profile.tenant_id, body.enabled)
    except Exception as e:
        logger.warning(f"[onboarding/shadow] could not persist setting: {e}")

    store.set_shadow_mode(profile_id, body.enabled)

    return {
        "shadow_mode": body.enabled,
        "profile_id": profile_id,
        "message": (
            "Shadow mode enabled — EDON is observing all agent actions and logging what it would block. "
            "No enforcement yet. Review findings in /v1/shadow-findings."
            if body.enabled else
            "Shadow mode disabled."
        ),
        "next_step": {
            "action": f"POST /v1/onboarding/profiles/{profile_id}/signoff/request",
            "description": "When ready, request go-live signoff to activate enforcement",
        } if body.enabled else None,
    }


# ── Step 7: Signoff ───────────────────────────────────────────────────────────

@router.post("/profiles/{profile_id}/signoff/request")
async def request_signoff(profile_id: str, request: Request, body: SignoffCreateRequest):
    """Request go-live signoff. Presents scope for explicit human approval."""
    tenant_id = _require_request_tenant(request, "request go-live signoff")
    profile_store = get_onboarding_store()
    profile = profile_store.get(profile_id)
    _assert_owns_profile(profile, tenant_id)

    bundle = bootstrap_policies(profile)
    signoff_store = get_signoff_store()
    governed_action_matrix = body.governed_action_matrix or _build_governed_action_matrix(profile, bundle)
    risk_tier_definitions = body.risk_tier_definitions or [
        {"tier": "low", "approval": "optional", "rollback": "full"},
        {"tier": "medium", "approval": "optional", "rollback": "full"},
        {"tier": "high", "approval": "required", "rollback": "partial"},
        {"tier": "critical", "approval": "required", "rollback": "limited"},
    ]
    fail_open_exceptions = body.fail_open_exceptions or [
        {
            "scope": "break_glass",
            "requirement": "explicit reason, time-boxed approval, post-event review",
        }
    ]
    rollback_limits = body.rollback_limits or [
        "High-risk writebacks may only partially rollback if the downstream system is non-transactional.",
    ]
    escalation_paths = body.escalation_paths or [
        "agent -> governance admin -> security admin -> tenant super admin",
    ]
    customer_signoff_artifacts = body.customer_signoff_artifacts or [
        "governed_action_matrix",
        "risk_tier_definitions",
        "fail_open_exceptions",
        "rollback_limits",
        "escalation_paths",
    ]
    sr = signoff_store.create(
        profile_id=profile_id,
        tenant_id=profile.tenant_id,
        requested_by=body.requested_by,
        enforcement_scope=body.enforcement_scope or [a.name for a in profile.agent_systems],
        escalation_rules_accepted=body.escalation_rules_accepted,
        kill_switch_authority=body.kill_switch_authority,
        data_classes_governed=body.data_classes_governed or profile.all_data_classes,
        policy_count_hard_safety=len(bundle.hard_safety),
        policy_count_operational=len(bundle.operational),
        policy_count_intent_contracts=len(bundle.intent_contracts),
        governed_action_matrix=governed_action_matrix,
        risk_tier_definitions=risk_tier_definitions,
        fail_open_exceptions=fail_open_exceptions,
        rollback_limits=rollback_limits,
        escalation_paths=escalation_paths,
        customer_signoff_artifacts=customer_signoff_artifacts,
    )
    profile_store.update_stage(profile_id, "signoff_pending")

    return {
        "signoff": sr.as_dict(),
        "instructions": (
            "Review the signoff scope above. When approved, call "
            f"POST /v1/onboarding/signoffs/{sr.signoff_id}/approve. "
            "After approval, EDON switches from shadow to active enforcement."
        ),
    }


@router.post("/signoffs/{signoff_id}/approve")
async def approve_signoff(signoff_id: str, request: Request, body: SignoffResolveRequest):
    """Approve go-live signoff — activates enforcement for this tenant."""
    tenant_id = _require_request_tenant(request, "approve a go-live signoff")
    signoff_store = get_signoff_store()
    sr_pre = signoff_store.get(signoff_id)
    if sr_pre is None or sr_pre.tenant_id != tenant_id:
        raise HTTPException(404, f"Signoff not found")
    sr = signoff_store.approve(signoff_id, body.resolved_by)
    if sr is None:
        raise HTTPException(404, f"Signoff '{signoff_id}' not found")

    profile_store = get_onboarding_store()
    profile = profile_store.sign_off(sr.profile_id, body.resolved_by)

    # Disable shadow mode — switch to active enforcement
    try:
        from ..persistence import get_db
        _db = get_db()
        if hasattr(_db, "set_shadow_mode"):
            _db.set_shadow_mode(sr.tenant_id, False)  # type: ignore[union-attr]
    except Exception as e:
        logger.warning(f"[onboarding/signoff] could not disable shadow mode: {e}")

    return {
        "signoff": sr.as_dict(),
        "profile": profile.as_dict() if profile else None,
        "deployment_mode": _deployment_mode_label(profile) if profile else None,
        "message": (
            "EDON is now LIVE. Active enforcement is enabled. "
            "Shadow mode has been disabled. All agent actions are now governed."
        ),
    }


@router.post("/signoffs/{signoff_id}/reject")
async def reject_signoff(signoff_id: str, request: Request, body: SignoffResolveRequest):
    """Reject go-live signoff — stays in shadow mode."""
    tenant_id = _require_request_tenant(request, "reject a go-live signoff")
    signoff_store = get_signoff_store()
    sr_pre = signoff_store.get(signoff_id)
    if sr_pre is None or sr_pre.tenant_id != tenant_id:
        raise HTTPException(404, f"Signoff not found")
    sr = signoff_store.reject(signoff_id, body.resolved_by, body.rejection_reason or "Rejected")
    if sr is None:
        raise HTTPException(404, f"Signoff '{signoff_id}' not found")

    profile_store = get_onboarding_store()
    profile_store.update_stage(sr.profile_id, "shadow")

    return {
        "signoff": sr.as_dict(),
        "message": "Signoff rejected. Profile remains in shadow mode.",
    }


# ── Step 10: Expansion Signals ────────────────────────────────────────────────

@router.get("/profiles/{profile_id}/expansion")
async def get_expansion_signals(profile_id: str, request: Request):
    """Check live telemetry for expansion trigger signals (new agents, sinks, stress points)."""
    tenant_id = _require_request_tenant(request, "view expansion signals")
    store = get_onboarding_store()
    profile = store.get(profile_id)
    _assert_owns_profile(profile, tenant_id)
    signals = check_expansion_signals(tenant_id, profile)
    high = [s for s in signals if s.severity == "high"]

    return {
        "signals": [s.as_dict() for s in signals],
        "count": len(signals),
        "high_severity_count": len(high),
        "expansion_recommended": len(high) >= 2,
    }


# ── Full pipeline status ──────────────────────────────────────────────────────

@router.get("/profiles/{profile_id}/status")
async def get_onboarding_status(profile_id: str, request: Request):
    """Full pipeline status — where this client is in the 10-step onboarding flow."""
    tenant_id = _require_request_tenant(request, "view onboarding status")
    store = get_onboarding_store()
    profile = store.get(profile_id)
    _assert_owns_profile(profile, tenant_id)

    signoff_store = get_signoff_store()
    signoffs = signoff_store.list_for_profile(profile_id)

    stage_labels = {
        "intake":          "1/7 — Intake complete",
        "topology":        "2/7 — Enforcement topology generated",
        "bootstrap":       "3/7 — Policy bootstrap complete",
        "deployment":      "4/7 — Deployment package ready",
        "shadow":          "5/7 — Shadow mode active",
        "signoff_pending": "6/7 — Awaiting go-live signoff",
        "live":            "7/7 — LIVE — Active enforcement",
        "expanding":       "Ongoing — Expansion monitoring active",
    }

    steps = [
        {"step": 1, "name": "Intake",            "done": True},
        {"step": 2, "name": "Topology",          "done": profile.stage not in ("intake",)},
        {"step": 3, "name": "Policy Bootstrap",  "done": profile.stage not in ("intake", "topology")},
        {"step": 4, "name": "Deployment Package","done": profile.stage not in ("intake", "topology", "bootstrap")},
        {"step": 5, "name": "Shadow Mode",       "done": profile.shadow_mode_enabled or profile.signed_off},
        {"step": 6, "name": "Go-Live Signoff",   "done": profile.signed_off},
        {"step": 7, "name": "Live Enforcement",  "done": profile.stage == "live"},
    ]

    return {
        "profile_id": profile_id,
        "stage": profile.stage,
        "stage_label": stage_labels.get(profile.stage, profile.stage),
        "deployment_mode": _deployment_mode_label(profile),
        "market_pack": _market_pack_label(profile),
        "risk_tier": profile.risk_tier,
        "shadow_mode": profile.shadow_mode_enabled,
        "signed_off": profile.signed_off,
        "signed_off_at": profile.signed_off_at,
        "steps": steps,
        "signoffs": signoffs,
    }
