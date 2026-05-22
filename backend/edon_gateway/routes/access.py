"""Console human access management routes."""

import hashlib
import os
import secrets
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..logging_config import get_logger
from ..persistence import get_db
from ..tenancy import get_request_tenant_id

logger = get_logger(__name__)

router = APIRouter(prefix="/access", tags=["access"])

HUMAN_ROLES = {"viewer", "operator", "governance_admin", "security_admin", "auditor"}
GLOBAL_ROLES = {"governance_admin", "security_admin"}
ADMIN_ROLES = {"admin", "super_admin", "governance_admin", "security_admin"}
MAX_INVITE_HOURS = 24 * 30


class CreateUserInviteRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    role: str = Field("viewer", max_length=80)
    department: Optional[str] = Field(None, max_length=120)
    scope: Optional[str] = Field(None, max_length=160)
    expires_in_hours: int = Field(168, ge=1, le=MAX_INVITE_HOURS)


class AcceptInviteRequest(BaseModel):
    token: str = Field(..., min_length=16)


class DepartmentOwnerRequest(BaseModel):
    owner_email: str = Field(..., min_length=3, max_length=254)


def _require_admin(request: Request) -> dict:
    tenant_info = getattr(request.state, "tenant_info", None) or {}
    if tenant_info.get("role") not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required")
    return tenant_info


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _public_invite_url(request: Request, token: str) -> str:
    # In production this can be replaced with the hospital SSO invite landing URL.
    base = str(request.base_url).rstrip("/")
    return f"{base}/console/invite?token={token}"


def _deliver_invite_email(*, email: str, invite_url: str, role: str, department: Optional[str]) -> dict:
    """Send an invite email when SMTP is configured.

    Invite creation must not depend on email provider availability. If SMTP is
    not configured, the caller still gets the one-time URL for Entra/Okta/email
    delivery outside EDON.
    """
    enabled = (os.getenv("EDON_INVITE_EMAIL_ENABLED") or "").strip().lower() in {"1", "true", "yes"}
    host = (os.getenv("EDON_SMTP_HOST") or os.getenv("SMTP_HOST") or "").strip()
    if not enabled or not host:
        return {
            "status": "ready",
            "channel": "identity_provider_or_email",
            "message": "Send invite_url through the hospital SSO or email delivery connector.",
        }

    port = int((os.getenv("EDON_SMTP_PORT") or os.getenv("SMTP_PORT") or "587").strip())
    username = (os.getenv("EDON_SMTP_USERNAME") or os.getenv("SMTP_USER") or "").strip()
    password = os.getenv("EDON_SMTP_PASSWORD") or os.getenv("SMTP_PASSWORD") or ""
    sender = (os.getenv("EDON_SMTP_FROM") or os.getenv("SMTP_FROM") or username or "no-reply@edon.ai").strip()
    starttls = (os.getenv("EDON_SMTP_STARTTLS") or "true").strip().lower() not in {"0", "false", "no"}

    message = EmailMessage()
    message["Subject"] = "Your EDON console invite"
    message["From"] = sender
    message["To"] = email
    message.set_content(
        "\n".join([
            "You were invited to the EDON governance console.",
            "",
            f"Role: {role}",
            f"Department: {department or 'cross-department'}",
            "",
            f"Open this one-time invite link: {invite_url}",
            "",
            "If your hospital uses SSO, complete identity verification before accepting the invite.",
        ])
    )

    try:
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            if starttls:
                smtp.starttls()
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
        return {"status": "sent", "channel": "smtp", "message": "Invite email sent."}
    except Exception as exc:
        logger.warning("[access] invite email delivery failed for %s: %s", email, exc)
        return {"status": "failed", "channel": "smtp", "message": "Invite was created, but SMTP delivery failed."}


def _safe_invite(invite: dict, *, include_url: bool = False) -> dict:
    safe = {
        "invite_id": invite.get("invite_id"),
        "tenant_id": invite.get("tenant_id"),
        "email": invite.get("email"),
        "role": invite.get("role"),
        "department": invite.get("department"),
        "scope": invite.get("scope"),
        "status": invite.get("status"),
        "invited_by": invite.get("invited_by"),
        "expires_at": invite.get("expires_at"),
        "accepted_at": invite.get("accepted_at"),
        "revoked_at": invite.get("revoked_at"),
        "created_at": invite.get("created_at"),
        "updated_at": invite.get("updated_at"),
    }
    if include_url:
        safe["invite_url"] = invite.get("invite_url")
    return safe


def _safe_owner(owner: dict) -> dict:
    return {
        "id": owner.get("id"),
        "tenant_id": owner.get("tenant_id"),
        "department": owner.get("department"),
        "owner_email": owner.get("owner_email"),
        "updated_by": owner.get("updated_by"),
        "created_at": owner.get("created_at"),
        "updated_at": owner.get("updated_at"),
    }


def _audit_access_event(tenant_id: str, *, actor: str, op: str, invite: dict, verdict: str = "ALLOW") -> None:
    try:
        db = get_db()
        db.save_audit_event(
            action={
                "action_id": f"access_{op}_{invite.get('invite_id')}",
                "tool": "console_access",
                "op": op,
                "params": {
                    "invite_id": invite.get("invite_id"),
                    "email": invite.get("email"),
                    "role": invite.get("role"),
                    "department": invite.get("department"),
                    "scope": invite.get("scope"),
                    "status": invite.get("status"),
                },
                "source": "console",
                "estimated_risk": "medium",
            },
            decision={
                "verdict": verdict,
                "reason_code": "HUMAN_ACCESS_MANAGEMENT",
                "explanation": f"Console access invite {op} recorded for {invite.get('email')}",
                "policy_version": "access-management-v1",
            },
            intent_id=None,
            agent_id="console_access",
            context={"actor": actor, "tenant_id": tenant_id},
            customer_id=tenant_id,
            user_message=f"{actor} performed {op} for {invite.get('email')}",
        )
    except Exception as exc:
        logger.warning("[access] could not persist audit event: %s", exc)


@router.get("/user-invites")
async def list_user_invites(request: Request):
    """List human console user invites for the current tenant. Requires admin."""
    _require_admin(request)
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    db = get_db()
    invites = [_safe_invite(invite, include_url=True) for invite in db.list_console_user_invites(tenant_id)]
    now = datetime.now(UTC).isoformat()
    for invite in invites:
        invite["expired"] = bool(invite.get("expires_at") and invite["expires_at"] < now and invite.get("status") == "pending")
    return {"invites": invites, "count": len(invites)}


@router.post("/user-invites", status_code=201)
async def create_user_invite(request: Request, body: CreateUserInviteRequest):
    """Create a backend-tracked invite for a human console user.

    The returned invite_url is what an email/SSO connector should deliver.
    EDON stores only a token hash; the raw token is returned once for delivery.
    """
    tenant_info = _require_admin(request)
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    role = body.role.strip()
    if role not in HUMAN_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role '{role}'. Valid: {sorted(HUMAN_ROLES)}")
    email = body.email.strip().lower()
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        raise HTTPException(status_code=400, detail="Valid email is required")
    department = (body.department or "").strip() or None
    if role not in GLOBAL_ROLES and not department:
        raise HTTPException(status_code=400, detail="Department is required for department-scoped roles")

    scope = (body.scope or "").strip()
    if not scope:
        scope = "Cross-department" if role in GLOBAL_ROLES else f"{department} only"

    token = f"edon_inv_{secrets.token_urlsafe(32)}"
    token_hash = _hash_token(token)
    expires_at = (datetime.now(UTC) + timedelta(hours=min(body.expires_in_hours, MAX_INVITE_HOURS))).isoformat()
    invite_url = _public_invite_url(request, token)
    invited_by = tenant_info.get("key_name") or tenant_info.get("api_key_id") or tenant_info.get("role") or "admin"

    db = get_db()
    invite = db.create_console_user_invite(
        tenant_id=tenant_id,
        email=email,
        role=role,
        department=department,
        scope=scope,
        invited_by=invited_by,
        invite_token_hash=token_hash,
        invite_url=invite_url,
        expires_at=expires_at,
    )
    _audit_access_event(tenant_id, actor=invited_by, op="invite_user", invite=invite)
    logger.info("[access] user invite created tenant=%s email=%s role=%s department=%s", tenant_id, email, role, department)
    delivery = _deliver_invite_email(email=email, invite_url=invite_url, role=role, department=department)
    return {
        "invite": _safe_invite(invite, include_url=True),
        "invite_token": token,
        "delivery": delivery,
    }


@router.delete("/user-invites/{invite_id}")
async def revoke_user_invite(invite_id: str, request: Request):
    """Revoke a pending human console invite. Requires admin."""
    tenant_info = _require_admin(request)
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    db = get_db()
    invite = db.revoke_console_user_invite(invite_id=invite_id, tenant_id=tenant_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found or already accepted")
    actor = tenant_info.get("key_name") or tenant_info.get("api_key_id") or tenant_info.get("role") or "admin"
    _audit_access_event(tenant_id, actor=actor, op="revoke_user_invite", invite=invite, verdict="BLOCK")
    return {"invite": _safe_invite(invite, include_url=True), "status": "revoked"}


@router.post("/user-invites/accept")
async def accept_user_invite(body: AcceptInviteRequest):
    """Accept an invite token.

    In production, the SSO callback should call this after identity verification.
    """
    db = get_db()
    invite = db.accept_console_user_invite(token_hash=_hash_token(body.token))
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found, expired, revoked, or already used")
    _audit_access_event(invite["tenant_id"], actor=invite["email"], op="accept_user_invite", invite=invite)
    return {"invite": _safe_invite(invite), "status": "accepted"}


@router.get("/department-owners")
async def list_department_owners(request: Request):
    """List department owner mappings for the current tenant. Requires admin."""
    _require_admin(request)
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    db = get_db()
    owners = [_safe_owner(owner) for owner in db.list_console_department_owners(tenant_id)]
    return {"owners": owners, "count": len(owners)}


@router.put("/department-owners/{department}")
async def set_department_owner(department: str, request: Request, body: DepartmentOwnerRequest):
    """Create or update the owner for one department. Requires admin."""
    tenant_info = _require_admin(request)
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    clean_department = department.strip()
    clean_owner = body.owner_email.strip().lower()
    if not clean_department:
        raise HTTPException(status_code=400, detail="Department is required")
    if "@" not in clean_owner or "." not in clean_owner.rsplit("@", 1)[-1]:
        raise HTTPException(status_code=400, detail="Valid owner email is required")
    actor = tenant_info.get("key_name") or tenant_info.get("api_key_id") or tenant_info.get("role") or "admin"
    db = get_db()
    owner = db.upsert_console_department_owner(
        tenant_id=tenant_id,
        department=clean_department,
        owner_email=clean_owner,
        updated_by=actor,
    )
    _audit_access_event(
        tenant_id,
        actor=actor,
        op="set_department_owner",
        invite={
            "invite_id": f"department_owner_{clean_department}",
            "email": clean_owner,
            "role": "department_owner",
            "department": clean_department,
            "scope": f"{clean_department} only",
            "status": "active",
        },
    )
    return {"owner": _safe_owner(owner), "status": "saved"}


@router.delete("/department-owners/{department}")
async def delete_department_owner(department: str, request: Request):
    """Remove the owner mapping for one department. Requires admin."""
    tenant_info = _require_admin(request)
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    clean_department = department.strip()
    db = get_db()
    deleted = db.delete_console_department_owner(tenant_id=tenant_id, department=clean_department)
    if not deleted:
        raise HTTPException(status_code=404, detail="Department owner not found")
    actor = tenant_info.get("key_name") or tenant_info.get("api_key_id") or tenant_info.get("role") or "admin"
    _audit_access_event(
        tenant_id,
        actor=actor,
        op="delete_department_owner",
        verdict="BLOCK",
        invite={
            "invite_id": f"department_owner_{clean_department}",
            "email": "",
            "role": "department_owner",
            "department": clean_department,
            "scope": f"{clean_department} only",
            "status": "deleted",
        },
    )
    return {"department": clean_department, "status": "deleted"}
