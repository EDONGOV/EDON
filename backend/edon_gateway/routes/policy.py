"""Per-tenant custom policy rules CRUD API, plus policy-pack management."""

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List

from ..persistence import get_db
from ..tenancy import get_request_tenant_id
from ..logging_config import get_logger
from ..middleware.rbac import check_permission
from .audit import record_policy_change

logger = get_logger(__name__)

router = APIRouter(prefix="/policy", tags=["policy"])


# ── Policy Pack routes (/policy-packs) ─────────────────────────────────────────

router_packs = APIRouter(prefix="/policy-packs", tags=["policy-packs"])


class PolicyPackApplyRequest(BaseModel):
    objective: Optional[str] = Field(
        None,
        description="Override the pack's default objective string",
    )
    set_as_active: bool = Field(
        True,
        description="Persist the pack as the tenant's active preset (default true)",
    )


@router_packs.get("")
async def list_packs():
    """List all available policy packs."""
    from ..policy_packs import list_policy_packs
    packs = list_policy_packs()
    return {"packs": packs, "count": len(packs)}


@router_packs.post("/{pack_name}/apply")
async def apply_pack(pack_name: str, request: Request, body: Optional[PolicyPackApplyRequest] = None):
    """Apply a named policy pack to this tenant.

    The pack's scope, constraints, and risk level are returned as an intent
    contract dictionary. When `set_as_active=true` (default) the pack is also
    saved as the tenant's active preset so that /v1/action uses it immediately.

    Available packs: casual_user, market_analyst, ops_commander, founder_mode,
    helpdesk, autonomy_mode.
    """
    from ..policy_packs import apply_policy_pack
    if body is None:
        body = PolicyPackApplyRequest()
    db = get_db()
    tenant_id = get_request_tenant_id(request)

    try:
        intent_dict = apply_policy_pack(pack_name, objective=body.objective or None)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    if body.set_as_active:
        try:
            db.set_active_policy_preset(
                preset_name=pack_name,
                applied_by=tenant_id or "api",
            )
        except Exception as exc:
            logger.warning("set_active_policy_preset failed: %s", exc)

    record_policy_change(
        tenant_id=tenant_id or "unknown",
        change_type="apply_pack",
        entity_type="policy_pack",
        entity_name=pack_name,
        diff_json={"pack": pack_name, "set_as_active": body.set_as_active},
        changed_by=tenant_id,
    )
    logger.info("[policy-packs/apply] tenant=%s pack=%s", tenant_id, pack_name)
    return {
        "pack": pack_name,
        "applied": True,
        "set_as_active": body.set_as_active,
        "intent": intent_dict,
    }

# ── HIPAA / Compliance Policy Templates ───────────────────────────────────────

COMPLIANCE_TEMPLATES = [
    {
        "id": "hipaa",
        "name": "HIPAA",
        "description": "HIPAA-compliant AI governance baseline",
        "rules": [
            "phi_access_control",
            "audit_logging",
            "minimum_necessary",
            "breach_detection",
            "access_timeout",
        ],
    },
    {
        "id": "hitrust",
        "name": "HITRUST CSF",
        "description": "HITRUST Common Security Framework",
        "rules": [
            "access_control",
            "audit_logging",
            "risk_management",
            "incident_response",
            "configuration_management",
        ],
    },
    {
        "id": "soc2",
        "name": "SOC 2 Type II",
        "description": "SOC 2 security and availability controls",
        "rules": [
            "access_control",
            "audit_logging",
            "change_management",
            "risk_assessment",
            "monitoring",
        ],
    },
]

# Map rule names in templates to policy rule definitions
_TEMPLATE_RULE_DEFS = {
    "phi_access_control": {
        "name": "PHI Access Control",
        "description": "Block access to protected health information by unauthorized agents",
        "action": "BLOCK",
        "condition_tags": ["phi", "pii"],
        "priority": 900,
    },
    "audit_logging": {
        "name": "Audit Logging Required",
        "description": "Escalate actions that attempt to disable or bypass audit logging",
        "action": "ESCALATE",
        "condition_tags": ["audit", "logging"],
        "priority": 850,
    },
    "minimum_necessary": {
        "name": "Minimum Necessary Access",
        "description": "Escalate file and data access requests for human review",
        "action": "ESCALATE",
        "condition_tool": "file",
        "priority": 800,
    },
    "breach_detection": {
        "name": "Breach Detection",
        "description": "Block bulk data export operations that may indicate a breach",
        "action": "BLOCK",
        "condition_tags": ["bulk_export", "data_export"],
        "priority": 950,
    },
    "access_timeout": {
        "name": "Access Timeout Enforcement",
        "description": "Escalate requests that appear to exceed authorized session duration",
        "action": "ESCALATE",
        "condition_tags": ["session", "timeout"],
        "priority": 700,
    },
    "access_control": {
        "name": "Access Control",
        "description": "Escalate privileged access requests for human review",
        "action": "ESCALATE",
        "condition_tags": ["admin", "privileged"],
        "priority": 900,
    },
    "risk_management": {
        "name": "Risk Management",
        "description": "Block high-risk actions without explicit approval",
        "action": "BLOCK",
        "condition_risk_level": "critical",
        "priority": 950,
    },
    "incident_response": {
        "name": "Incident Response",
        "description": "Escalate actions flagged as potential incidents",
        "action": "ESCALATE",
        "condition_tags": ["incident", "alert"],
        "priority": 920,
    },
    "configuration_management": {
        "name": "Configuration Management",
        "description": "Escalate configuration changes for human review",
        "action": "ESCALATE",
        "condition_tags": ["config", "settings"],
        "priority": 800,
    },
    "change_management": {
        "name": "Change Management",
        "description": "Escalate system change operations for human review",
        "action": "ESCALATE",
        "condition_tags": ["change", "deploy"],
        "priority": 800,
    },
    "risk_assessment": {
        "name": "Risk Assessment",
        "description": "Block critical-risk actions pending assessment",
        "action": "BLOCK",
        "condition_risk_level": "critical",
        "priority": 960,
    },
    "monitoring": {
        "name": "Continuous Monitoring",
        "description": "Escalate actions that attempt to disable monitoring",
        "action": "ESCALATE",
        "condition_tags": ["monitoring", "telemetry"],
        "priority": 850,
    },
}


@router.get("/templates")
async def list_policy_templates():
    """List all available compliance policy template packs (HIPAA, HITRUST, SOC 2)."""
    return COMPLIANCE_TEMPLATES


@router.post("/templates/{template_id}/apply", status_code=201)
async def apply_policy_template(template_id: str, request: Request):
    """Apply a compliance policy template to the current tenant.

    Creates enabled policy rules for every rule in the template pack.
    Existing rules with the same name are skipped (not duplicated).

    Available templates: hipaa, hitrust, soc2
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    # Find template
    template = next((t for t in COMPLIANCE_TEMPLATES if t["id"] == template_id), None)
    if not template:
        raise HTTPException(
            status_code=404,
            detail=f"Template '{template_id}' not found. Available: {[t['id'] for t in COMPLIANCE_TEMPLATES]}"
        )

    db = get_db()
    existing_rules = db.get_policy_rules(tenant_id, enabled_only=False)
    existing_names = {r["name"].lower() for r in existing_rules}

    created_rules = []
    skipped_rules = []

    for rule_name in template["rules"]:
        rule_def = _TEMPLATE_RULE_DEFS.get(rule_name, {})
        display_name = rule_def.get("name", rule_name.replace("_", " ").title())

        if display_name.lower() in existing_names:
            skipped_rules.append(rule_name)
            continue

        rule_id = db.create_policy_rule(
            tenant_id=tenant_id,
            name=display_name,
            action=rule_def.get("action", "ESCALATE"),
            priority=rule_def.get("priority", 500),
            description=rule_def.get("description"),
            condition_tool=rule_def.get("condition_tool"),
            condition_op=rule_def.get("condition_op"),
            condition_risk_level=rule_def.get("condition_risk_level"),
            condition_tags=rule_def.get("condition_tags"),
            enabled=True,
        )
        created_rules.append({"rule_name": rule_name, "rule_id": rule_id})

    record_policy_change(
        tenant_id=tenant_id,
        change_type="apply_pack",
        entity_type="compliance_template",
        entity_name=template["name"],
        diff_json={
            "template_id": template_id,
            "created": created_rules,
            "skipped": skipped_rules,
        },
        changed_by=tenant_id,
    )
    logger.info("[policy/templates] tenant=%s template=%s created=%d skipped=%d",
                tenant_id, template_id, len(created_rules), len(skipped_rules))

    return {
        "template_id": template_id,
        "template_name": template["name"],
        "applied": True,
        "rules_created": len(created_rules),
        "rules_skipped": len(skipped_rules),
        "created": created_rules,
        "skipped": skipped_rules,
    }


VALID_ACTIONS = {"ALLOW", "BLOCK", "ESCALATE"}
VALID_TOOLS = {
    "email", "shell", "calendar", "file", "clawdbot",
    "brave_search", "gmail", "google_calendar", "elevenlabs",
    "github", "gemini", "polygon", "fmp", "newsapi",
    "home_assistant", "memory", "agent",
    "robot", "vehicle", "conveyor", "forklift", "drone",
    "scanner", "sorter", "dock", "gate", "sensor",
}
VALID_RISK_LEVELS = {"low", "medium", "high", "critical"}


class PolicyRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    condition_tool: Optional[str] = None
    condition_op: Optional[str] = Field(None, max_length=100)
    condition_risk_level: Optional[str] = None
    condition_tags: Optional[List[str]] = None
    action: str = Field(..., description="ALLOW, BLOCK, or ESCALATE")
    priority: int = Field(0, ge=0, le=1000)
    enabled: bool = True


class PolicyRuleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    condition_tool: Optional[str] = None
    condition_op: Optional[str] = Field(None, max_length=100)
    condition_risk_level: Optional[str] = None
    condition_tags: Optional[List[str]] = None
    action: Optional[str] = None
    priority: Optional[int] = Field(None, ge=0, le=1000)
    enabled: Optional[bool] = None
    justification: Optional[str] = Field(
        None,
        description="Required when mutating a protected (clinical safety) rule. Admin role only.",
    )


def _validate_rule(data: dict):
    """Validate rule fields."""
    action = data.get("action")
    if action and action not in VALID_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action '{action}'. Must be one of: {sorted(VALID_ACTIONS)}"
        )
    tool = data.get("condition_tool")
    if tool and tool not in VALID_TOOLS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid condition_tool '{tool}'. Must be one of: {sorted(VALID_TOOLS)}"
        )
    risk = data.get("condition_risk_level")
    if risk and risk not in VALID_RISK_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid condition_risk_level '{risk}'. Must be one of: {sorted(VALID_RISK_LEVELS)}"
        )


@router.get("/rules")
async def list_rules(request: Request, include_disabled: bool = False):
    """List all policy rules for the current tenant.

    Rules are ordered by priority (highest first).
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    db = get_db()
    rules = db.get_policy_rules(tenant_id, enabled_only=not include_disabled)
    return {"tenant_id": tenant_id, "rules": rules, "count": len(rules)}


@router.post("/rules", status_code=201)
async def create_rule(request: Request, body: PolicyRuleCreate):
    """Create a new custom policy rule for the current tenant.

    Rules are evaluated before the standard governance policy.
    The first matching rule (by priority, highest first) wins.

    **Conditions** (all are optional; omitting means "match any"):
    - `condition_tool`: e.g. `robot`, `email`, `shell`
    - `condition_op`: e.g. `move`, `send`, `exec`
    - `condition_risk_level`: `low`, `medium`, `high`, `critical`
    - `condition_tags`: list of tags that must ALL be present

    **Actions**: `ALLOW`, `BLOCK`, `ESCALATE`
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    data = body.model_dump()
    _validate_rule(data)

    db = get_db()
    rule_id = db.create_policy_rule(
        tenant_id=tenant_id,
        name=data["name"],
        action=data["action"],
        priority=data["priority"],
        description=data.get("description"),
        condition_tool=data.get("condition_tool"),
        condition_op=data.get("condition_op"),
        condition_risk_level=data.get("condition_risk_level"),
        condition_tags=data.get("condition_tags"),
        enabled=data["enabled"],
    )

    rule = db.get_policy_rule(rule_id, tenant_id)
    record_policy_change(
        tenant_id=tenant_id,
        change_type="create",
        entity_type="policy_rule",
        entity_id=rule_id,
        entity_name=data["name"],
        diff_json={"after": rule},
        changed_by=tenant_id,
    )
    logger.info(f"[policy] Created rule {rule_id} for tenant {tenant_id}: {data['name']}")
    return {"rule_id": rule_id, "rule": rule}


@router.get("/rules/{rule_id}")
async def get_rule(rule_id: str, request: Request):
    """Get a specific policy rule."""
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    db = get_db()
    rule = db.get_policy_rule(rule_id, tenant_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Policy rule not found")
    return rule


def _enforce_protected_mutation(existing: dict, request: Request, justification: Optional[str]):
    """Raise 403 if rule is protected and caller is not admin with justification."""
    if not existing.get("protected"):
        return
    tenant_info = getattr(request.state, "tenant_info", None)
    if not check_permission(tenant_info, "*"):
        raise HTTPException(
            status_code=403,
            detail=(
                "Rule is protected by Clinical Safety Mode. "
                "Only admin role may mutate it."
            ),
        )
    if not justification or not justification.strip():
        raise HTTPException(
            status_code=422,
            detail=(
                "A non-empty 'justification' is required when mutating a "
                "protected Clinical Safety rule."
            ),
        )


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: str, request: Request, body: PolicyRuleUpdate):
    """Update a policy rule.

    If the rule is protected (seeded by Clinical Safety Mode), the caller must
    have **admin** role and supply a non-empty `justification` field.
    The justification is appended to the policy-change audit log.
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    db = get_db()
    existing = db.get_policy_rule(rule_id, tenant_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Policy rule not found")

    _enforce_protected_mutation(existing, request, body.justification)

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    updates.pop("justification", None)  # not a DB column
    _validate_rule(updates)

    if not updates:
        return existing

    updated = db.update_policy_rule(rule_id, tenant_id, **updates)
    if not updated:
        raise HTTPException(status_code=500, detail="Update failed")

    rule = db.get_policy_rule(rule_id, tenant_id)
    record_policy_change(
        tenant_id=tenant_id,
        change_type="update",
        entity_type="policy_rule",
        entity_id=rule_id,
        entity_name=rule.get("name") if rule else rule_id,
        diff_json={"before": existing, "changes": updates,
                   **({"justification": body.justification} if body.justification else {})},
        changed_by=tenant_id,
    )
    logger.info(f"[policy] Updated rule {rule_id} for tenant {tenant_id}")
    return rule


class PolicyRuleDeleteRequest(BaseModel):
    justification: Optional[str] = Field(
        None,
        description="Required when deleting a protected (clinical safety) rule. Admin role only.",
    )


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(rule_id: str, request: Request, body: Optional[PolicyRuleDeleteRequest] = None):
    """Delete a policy rule.

    If the rule is protected (seeded by Clinical Safety Mode), the caller must
    have **admin** role and supply a non-empty `justification` in the request body.
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    db = get_db()
    existing = db.get_policy_rule(rule_id, tenant_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Policy rule not found")

    justification = (body.justification if body else None)
    _enforce_protected_mutation(existing, request, justification)

    deleted = db.delete_policy_rule(rule_id, tenant_id)
    if not deleted:
        raise HTTPException(status_code=500, detail="Delete failed")

    record_policy_change(
        tenant_id=tenant_id,
        change_type="delete",
        entity_type="policy_rule",
        entity_id=rule_id,
        entity_name=existing.get("name") if existing else rule_id,
        diff_json={"before": existing,
                   **({"justification": justification} if justification else {})},
        changed_by=tenant_id,
    )
    logger.info(f"[policy] Deleted rule {rule_id} for tenant {tenant_id}")


@router.post("/rules/{rule_id}/enable")
async def enable_rule(rule_id: str, request: Request):
    """Enable a policy rule."""
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    db = get_db()
    existing = db.get_policy_rule(rule_id, tenant_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Policy rule not found")

    db.update_policy_rule(rule_id, tenant_id, enabled=True)
    record_policy_change(
        tenant_id=tenant_id,
        change_type="enable",
        entity_type="policy_rule",
        entity_id=rule_id,
        entity_name=existing.get("name") if existing else rule_id,
        changed_by=tenant_id,
    )
    return {"rule_id": rule_id, "enabled": True}


class PolicyRuleDisableRequest(BaseModel):
    justification: Optional[str] = Field(
        None,
        description="Required when disabling a protected (clinical safety) rule. Admin role only.",
    )


@router.post("/rules/{rule_id}/disable")
async def disable_rule(rule_id: str, request: Request, body: Optional[PolicyRuleDisableRequest] = None):
    """Disable a policy rule without deleting it.

    If the rule is protected (seeded by Clinical Safety Mode), the caller must
    have **admin** role and supply a non-empty `justification` in the request body.
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    db = get_db()
    existing = db.get_policy_rule(rule_id, tenant_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Policy rule not found")

    justification = (body.justification if body else None)
    _enforce_protected_mutation(existing, request, justification)

    db.update_policy_rule(rule_id, tenant_id, enabled=False)
    record_policy_change(
        tenant_id=tenant_id,
        change_type="disable",
        entity_type="policy_rule",
        entity_id=rule_id,
        entity_name=existing.get("name") if existing else rule_id,
        diff_json={**({"justification": justification} if justification else {})},
        changed_by=tenant_id,
    )
    return {"rule_id": rule_id, "enabled": False}
