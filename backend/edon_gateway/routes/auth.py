"""Authentication routes for EDON Gateway (Clerk-backed)."""

import secrets
import logging
import uuid as _uuid

from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, EmailStr, field_validator

logger = logging.getLogger(__name__)

from ..middleware.auth import get_token_from_header, verify_token, verify_clerk_token, resolve_tenant_for_clerk
from ..middleware.rate_limit import check_rate_limit, increment_rate_limit
from ..config import config
from ..persistence import get_db
from ..security.hashing import hash_api_key_fast

# Strict per-IP limits for the signup endpoint to prevent account-creation abuse
_SIGNUP_LIMITS = {
    "per_minute": 2,    # max 2 signup attempts per IP per minute
    "per_hour": 5,      # max 5 signup attempts per IP per hour
}

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Self-serve registration (no Clerk required) ────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str

    @field_validator('email')
    @classmethod
    def email_must_have_at(cls, v: str) -> str:
        v = v.strip().lower()
        if '@' not in v or '.' not in v.split('@')[-1]:
            raise ValueError('Invalid email address')
        return v

    @field_validator('password')
    @classmethod
    def password_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v


def _hash_password(password: str) -> str:
    try:
        import bcrypt
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode()
    except ImportError:
        import hashlib, os
        salt = os.urandom(16).hex()
        h = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
        return f"sha256:{salt}:{h}"


def _verify_password(password: str, hashed: str) -> bool:
    try:
        import bcrypt
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ImportError:
        logger.warning(
            "bcrypt not available — falling back to SHA-256 password verification. "
            "Install bcrypt for production-grade hashing."
        )
        if hashed.startswith("sha256:"):
            _, salt, h = hashed.split(":", 2)
            import hashlib
            candidate = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
            return secrets.compare_digest(candidate, h)
        return False


@router.post("/register", status_code=201)
async def register(request: Request, body: RegisterRequest):
    """Self-serve registration — no Clerk required.

    Creates a user, tenant, and API key in one step.
    The API key is returned once and must be stored immediately.
    """
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"register_ip:{client_ip}"
    allowed, rate_err = check_rate_limit(rate_key, _SIGNUP_LIMITS)
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Too many attempts. {rate_err}", headers={"Retry-After": "3600"})
    increment_rate_limit(rate_key)

    if config.ENTERPRISE_MODE or config.ENTERPRISE_SSO_ONLY:
        raise HTTPException(
            status_code=403,
            detail="Password registration is disabled in enterprise SSO-only mode.",
        )

    db = get_db()

    # Reject duplicate emails
    existing = db.get_user_by_auth("email", body.email)
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user_id = str(_uuid.uuid4())
    tenant_id = f"tenant_{_uuid.uuid4().hex[:16]}"
    pw_hash = _hash_password(body.password)

    # Store password hash in auth_subject field (provider = "email")
    db.create_user(
        user_id=user_id,
        email=body.email,
        auth_provider="email",
        auth_subject=pw_hash,
        role="viewer" if config.ENTERPRISE_MODE else "admin",
    )
    db.create_tenant(tenant_id=tenant_id, user_id=user_id)

    raw_key = f"edon-{secrets.token_urlsafe(32)}"
    key_hash = hash_api_key_fast(raw_key)
    key_id = db.create_api_key(
        tenant_id=tenant_id,
        key_hash=key_hash,
        name="Default Key",
        role="operator" if config.ENTERPRISE_MODE else "admin",
    )

    return {
        "tenant_id": tenant_id,
        "api_key": raw_key,
        "api_key_id": key_id,
        "api_key_notice": "This is the only time your API key will be shown. Copy it now.",
        "user": {"id": user_id, "email": body.email, "tenant_id": tenant_id},
    }


@router.post("/login")
async def login(request: Request, body: RegisterRequest):
    """Email + password login — returns the tenant's active API key metadata.

    Does NOT re-issue the plaintext key (already shown at registration).
    Use /api-keys to create a new key if the original was lost.
    """
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"login_ip:{client_ip}"
    allowed, rate_err = check_rate_limit(rate_key, {"per_minute": 10, "per_hour": 60})
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Too many login attempts. {rate_err}")
    increment_rate_limit(rate_key)

    if config.ENTERPRISE_MODE or config.ENTERPRISE_SSO_ONLY:
        raise HTTPException(
            status_code=403,
            detail="Password login is disabled in enterprise SSO-only mode.",
        )

    db = get_db()
    user = db.get_user_by_auth("email", body.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    if not _verify_password(body.password, user["auth_subject"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    tenant = db.get_tenant_by_user(user["id"]) if hasattr(db, "get_tenant_by_user") else None
    if not tenant:
        # fallback: find tenant via list
        for t in (db.list_tenants() or []):
            if t.get("user_id") == user["id"]:
                tenant = t
                break
    if not tenant:
        raise HTTPException(status_code=404, detail="No tenant found for this account.")

    tenant_id = tenant["id"] if "id" in tenant else tenant.get("tenant_id", "")
    keys = db.list_api_keys(tenant_id) if hasattr(db, "list_api_keys") else []
    active_keys = [k for k in keys if k.get("status") == "active"]

    # If no key exists, provision a fresh one
    raw_key = None
    key_id = None
    if not active_keys:
        raw_key = f"edon-{secrets.token_urlsafe(32)}"
        key_hash = hash_api_key_fast(raw_key)
        key_id = db.create_api_key(
            tenant_id=tenant_id,
            key_hash=key_hash,
            name="Default Key",
            role="operator" if config.ENTERPRISE_MODE else "admin",
        )

    response: dict = {
        "tenant_id": tenant_id,
        "user": {"id": user["id"], "email": user["email"], "tenant_id": tenant_id},
    }
    if raw_key:
        response["api_key"] = raw_key
        response["api_key_id"] = key_id
        response["api_key_notice"] = "This is the only time your API key will be shown. Copy it now."
    else:
        response["message"] = "Logged in. Use your existing API key to authenticate SDK calls."
        response["key_count"] = len(active_keys)
    return response


class SignupRequest(BaseModel):
    auth_provider: str = "clerk"
    auth_subject: Optional[str] = None  # Optional: use Clerk token "sub" when missing
    email: str


def _provision_api_key_if_missing(db, tenant_id: str):
    """Return (raw_key, key_id) if a new key was created, or (None, None) if one already exists.

    The raw key is returned ONCE and must be shown to the user immediately.
    After this function returns the plaintext key is no longer recoverable.
    """
    existing = db.list_api_keys(tenant_id)
    active_keys = [k for k in existing if k.get("status") == "active"]
    if active_keys:
        return None, None

    raw_key = f"edon-{secrets.token_urlsafe(32)}"
    key_hash = hash_api_key_fast(raw_key)
    key_id = db.create_api_key(
        tenant_id=tenant_id,
        key_hash=key_hash,
        name="Default Key",
        role="operator" if config.ENTERPRISE_MODE else "admin",
    )
    return raw_key, key_id


@router.post("/signup")
async def signup(request: Request, body: SignupRequest):
    """
    Create (or fetch) a user + tenant for a Clerk user.
    Requires a valid Clerk session token in Authorization or X-EDON-TOKEN.

    On the first call for a new user an API key is automatically provisioned
    and returned as ``api_key`` in the response.  This is the ONLY time the
    plaintext key is available — the user must copy it immediately.
    """
    # Rate limit: max 5 signup attempts per IP per hour (2/min burst)
    client_ip = request.client.host if request.client else "unknown"
    signup_rate_key = f"signup_ip:{client_ip}"
    allowed, rate_err = check_rate_limit(signup_rate_key, _SIGNUP_LIMITS)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Too many signup attempts from this IP. {rate_err}",
            headers={"Retry-After": "3600"},
        )
    increment_rate_limit(signup_rate_key)

    token = get_token_from_header(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing Clerk session token. Send Authorization: Bearer <clerk_jwt>.")

    clerk_claims = verify_clerk_token(token)
    if not clerk_claims:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired Clerk token. Ensure CLERK_SECRET_KEY on the gateway matches your Clerk app (test vs live).",
        )

    if body.auth_provider != "clerk":
        raise HTTPException(status_code=400, detail="Unsupported auth provider")

    clerk_sub = (clerk_claims or {}).get("sub")
    if not clerk_sub:
        raise HTTPException(status_code=401, detail="Clerk token missing subject (sub)")
    # Only reject when frontend explicitly sends a different auth_subject (prevent spoofing)
    if body.auth_subject and body.auth_subject.strip() and clerk_sub != body.auth_subject.strip():
        raise HTTPException(status_code=403, detail="Clerk subject mismatch")

    tenant_info = resolve_tenant_for_clerk(clerk_claims, fallback_email=body.email)
    tenant_id = tenant_info["tenant_id"]

    db = get_db()
    raw_key, key_id = _provision_api_key_if_missing(db, tenant_id)

    response: dict = {
        "tenant_id": tenant_id,
        "session_token": token,
        "user": {
            "id": tenant_info.get("user_id"),
            "email": tenant_info.get("email"),
            "tenant_id": tenant_id,
            "plan": tenant_info.get("plan"),
            "status": tenant_info.get("status"),
        },
    }

    if raw_key:
        response["api_key"] = raw_key
        response["api_key_id"] = key_id
        response["api_key_notice"] = (
            "This is the only time your API key will be shown. Copy it now."
        )

    return response


@router.get("/session")
async def session(request: Request):
    """
    Validate a session token and return user + tenant context.
    Accepts either an EDON API key or a Clerk session token.

    When a Clerk JWT is used and the tenant has no API key yet, one is
    auto-provisioned and returned as ``api_key`` in the response (shown once).
    """
    token = get_token_from_header(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")

    is_valid, tenant_info = verify_token(token)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    if not tenant_info:
        return {
            "id": None,
            "email": None,
            "tenant_id": None,
            "plan": None,
            "status": None,
        }

    db = get_db()
    tenant = db.get_tenant(tenant_info["tenant_id"])
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Email: tenant may have it (SQLite join) or not (Postgres); fallback to user row
    email = tenant.get("email")
    if not email and tenant.get("user_id"):
        user = db.get_user(tenant["user_id"])
        email = (user or {}).get("email") if user else None
    response: dict = {
        "id": tenant.get("user_id"),
        "email": email,
        "tenant_id": tenant.get("id"),
        "plan": tenant.get("plan"),
        "status": tenant.get("status"),
    }

    # When authenticated via a Clerk JWT (api_key_id is None), check whether
    # the tenant already has an API key.  If not, provision one now so the
    # user can immediately start making authenticated requests.
    if tenant_info.get("api_key_id") is None:
        raw_key, key_id = _provision_api_key_if_missing(db, tenant.get("id"))
        if raw_key:
            response["api_key"] = raw_key
            response["api_key_id"] = key_id
            response["api_key_notice"] = (
                "This is the only time your API key will be shown. Copy it now."
            )

    return response


@router.post("/sync")
async def sync_session(request: Request):
    """
    Sync session from Clerk: validate Clerk JWT and refresh stored user email from Clerk.
    Call this from the marketing site (with Bearer Clerk token) so the gateway DB
    has the correct email for GET /auth/session (used by the console).
    """
    token = get_token_from_header(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing Authorization: Bearer <clerk_jwt>")

    clerk_claims = verify_clerk_token(token)
    if not clerk_claims:
        raise HTTPException(status_code=401, detail="Invalid or expired Clerk token")

    tenant_info = resolve_tenant_for_clerk(clerk_claims)
    db = get_db()
    tenant = db.get_tenant(tenant_info["tenant_id"])
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    user = db.get_user(tenant["user_id"]) if tenant.get("user_id") else None
    email = (user or {}).get("email") if user else tenant_info.get("email")

    return {
        "id": tenant.get("user_id"),
        "email": email,
        "tenant_id": tenant.get("id"),
        "plan": tenant.get("plan"),
        "status": tenant.get("status"),
    }
