"""Authentication middleware for EDON Gateway."""

import os
import logging
import json
import time
import random
import ipaddress
from typing import Optional, Dict, Any, Tuple, List
import uuid

import requests
import jwt

from fastapi import Request, status
from fastapi.security import HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from ..config import config

logger = logging.getLogger(__name__)

# Security scheme for OpenAPI docs
security = HTTPBearer(auto_error=False)


_JWKS_CACHE: Dict[str, Any] = {"keys": None, "fetched_at": 0}


def _get_clerk_jwks(force_refresh: bool = False) -> Optional[list]:
    ttl_seconds = int(os.getenv("CLERK_JWKS_CACHE_TTL", "3600"))
    now = time.time()

    if not force_refresh and _JWKS_CACHE.get("keys") and (now - _JWKS_CACHE.get("fetched_at", 0) < ttl_seconds):
        return _JWKS_CACHE["keys"]

    jwks_url = os.getenv("CLERK_JWKS_URL", "https://api.clerk.com/v1/jwks")
    headers = {}
    # Only send the secret key as auth for Clerk's private API endpoint.
    # Public /.well-known/jwks.json endpoints do NOT require (and may reject) an auth header.
    is_public_jwks = "/.well-known/" in jwks_url
    if config.CLERK_SECRET_KEY and not is_public_jwks:
        headers["Authorization"] = f"Bearer {config.CLERK_SECRET_KEY}"

    try:
        resp = requests.get(jwks_url, headers=headers, timeout=10)
        resp.raise_for_status()
        payload = resp.json()
        keys = payload.get("keys") if isinstance(payload, dict) else None
        if not keys:
            keys = payload if isinstance(payload, list) else None
        if not keys:
            return None
        _JWKS_CACHE["keys"] = keys
        _JWKS_CACHE["fetched_at"] = now
        return keys
    except Exception as exc:
        logger.warning(f"Failed to fetch Clerk JWKS from {jwks_url}: {exc}")
        return None


def _get_clerk_public_key_pem() -> Optional[bytes]:
    """Return the PEM-encoded RSA public key from CLERK_PUBLIC_KEY env var, or None."""
    pem = (os.getenv("CLERK_PUBLIC_KEY") or "").strip()
    if not pem:
        return None
    # Normalise: env vars with newlines stored as \n literal
    pem = pem.replace("\\n", "\n")
    if not pem.startswith("-----BEGIN"):
        return None
    return pem.encode()


def verify_clerk_token(token: str) -> Optional[Dict[str, Any]]:
    if not token or token.count(".") != 2:
        return None

    issuer = os.getenv("CLERK_ISSUER")
    audience = os.getenv("CLERK_AUDIENCE")
    options = {
        "verify_aud": bool(audience),
        "verify_iss": bool(issuer),
    }

    # Fast path: hardcoded PEM key bypasses JWKS fetch entirely.
    # Set CLERK_PUBLIC_KEY on the gateway to use this path.
    pem_key = _get_clerk_public_key_pem()
    if pem_key:
        try:
            claims = jwt.decode(
                token,
                pem_key,
                algorithms=["RS256"],
                audience=audience if audience else None,
                issuer=issuer if issuer else None,
                options=options,
            )
            return claims
        except Exception as exc:
            logger.debug(f"Clerk token verification (hardcoded key) failed: {exc}")
            return None

    if not config.CLERK_SECRET_KEY and not os.getenv("CLERK_JWKS_URL"):
        return None

    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if not kid:
            return None

        keys = _get_clerk_jwks() or []
        key = next((k for k in keys if k.get("kid") == kid), None)
        if not key:
            keys = _get_clerk_jwks(force_refresh=True) or []
            key = next((k for k in keys if k.get("kid") == kid), None)
        if not key:
            logger.warning(f"Clerk JWKS: no key matched kid={kid!r}. Keys available: {[k.get('kid') for k in keys]}")
            return None

        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=audience if audience else None,
            issuer=issuer if issuer else None,
            options=options,
        )
        return claims
    except Exception as exc:
        logger.debug(f"Clerk token verification failed: {exc}")
        return None


def _fetch_clerk_user_email(clerk_sub: str) -> Optional[str]:
    """Fetch the user's primary email from Clerk Backend API. Returns None on failure."""
    secret = (config.CLERK_SECRET_KEY or os.getenv("CLERK_SECRET_KEY") or "").strip()
    if not secret:
        return None
    url = f"https://api.clerk.com/v1/users/{clerk_sub}"
    try:
        resp = requests.get(url, headers={"Authorization": f"Bearer {secret}"}, timeout=5)
        resp.raise_for_status()
        data = resp.json() if resp.content else {}
        emails = data.get("email_addresses") or []
        for item in emails if isinstance(emails, list) else []:
            if isinstance(item, dict):
                addr = item.get("email_address") or item.get("email")
                if addr and "@" in str(addr):
                    return str(addr).strip()
        return None
    except Exception as e:
        logger.debug("Clerk API fetch email failed: %s", e)
        return None


def resolve_tenant_for_clerk(claims: Dict[str, Any], fallback_email: Optional[str] = None) -> Dict[str, Any]:
    from ..persistence import get_db

    db = get_db()
    clerk_sub = (claims or {}).get("sub")
    if not clerk_sub:
        raise ValueError("Missing Clerk subject")

    email = (
        claims.get("email")
        or claims.get("email_address")
        or claims.get("primary_email_address")
        or fallback_email
    )
    if not email or not str(email).strip() or str(email).strip() == "unknown@edoncore.com":
        clerk_email = _fetch_clerk_user_email(clerk_sub)
        if clerk_email:
            email = clerk_email
    if not email or not str(email).strip():
        email = "unknown@edoncore.com"

    user = db.get_user_by_auth("clerk", clerk_sub)
    if not user:
        user_id = str(uuid.uuid4())
        db.create_user(user_id=user_id, email=email, auth_provider="clerk", auth_subject=clerk_sub, role="user")
    else:
        user_id = user["id"]
        # Update stored email if we now have a real one (fixes unknown@edoncore.com)
        current = (user.get("email") or "").strip()
        if (not current or current == "unknown@edoncore.com") and email and str(email).strip() != "unknown@edoncore.com":
            db.update_user_email(user_id, email)

    tenant = db.get_tenant_by_user_id(user_id)
    if not tenant:
        tenant_id = f"tenant_{uuid.uuid4().hex[:12]}"
        db.create_tenant(tenant_id=tenant_id, user_id=user_id)
        tenant = db.get_tenant(tenant_id)

    return {
        "tenant_id": tenant["id"],
        "status": tenant["status"],
        "plan": tenant["plan"],
        "api_key_id": None,
        "user_id": user_id,
        "email": email,
    }


def verify_token(token: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Verify authentication token and return tenant info.

    Returns:
        (is_valid, tenant_info_dict)

    tenant_info_dict contains:
      - tenant_id
      - status
      - plan
      - api_key_id
    or None if legacy token/no tenant.
    """
    if not config.AUTH_ENABLED:
        return True, None  # Auth disabled

    token = (token or "").strip()
    if not token:
        return False, None

    # 1) DB lookup first (tenant-scoped API keys + channel tokens)
    try:
        from ..persistence import get_db
        from ..security.hashing import hash_api_key_fast

        key_hash = hash_api_key_fast(token)
        db = get_db()
        api_key = db.get_api_key_by_hash(key_hash)

        if api_key:
            db.update_api_key_last_used(api_key["id"])
            tenant = db.get_tenant(api_key["tenant_id"])
            if tenant:
                return True, {
                    "tenant_id": tenant["id"],
                    "status": tenant["status"],
                    "plan": tenant["plan"],
                    "api_key_id": api_key["id"],
                    "role": api_key.get("role", "user"),
                }
            # Orphaned key (no tenant): fall through to env token / Clerk

        channel_token = db.get_channel_token_by_hash(key_hash)
        if channel_token:
            db.update_channel_token_last_used(channel_token["id"])
            tenant = db.get_tenant(channel_token["tenant_id"])
            if tenant:
                return True, {
                    "tenant_id": tenant["id"],
                    "status": tenant["status"],
                    "plan": tenant["plan"],
                    "api_key_id": None,
                }
            # Orphaned channel token: fall through to env token / Clerk

    except Exception as e:
        logger.debug(f"Database token lookup failed: {e}")

    # 1b) Clerk session JWT fallback
    try:
        clerk_claims = verify_clerk_token(token)
        if clerk_claims:
            tenant_info = resolve_tenant_for_clerk(clerk_claims)
            return True, tenant_info
    except Exception as e:
        logger.debug(f"Clerk token resolution failed: {e}")

    # 2) Env token fallback (legacy)
    # Default behavior: disabled in production to enforce DB keys.
    # Can be explicitly enabled for bootstrap/admin via EDON_ALLOW_ENV_TOKEN_IN_PROD=true.
    if config.is_production() and not config.ALLOW_ENV_TOKEN_IN_PROD:
        logger.info("auth_fail: env_token_disabled_in_prod (set EDON_ALLOW_ENV_TOKEN_IN_PROD=true to allow)")
        return False, None

    api_token = (config.API_TOKEN or "").strip()
    if not api_token or api_token == "your-secret-token":
        logger.warning("EDON_AUTH_ENABLED is true but EDON_API_TOKEN is not set")
        return False, None

    if token == api_token:
        return True, None

    logger.info(
        "auth_fail: env_token_mismatch (token_len=%s, api_token_len=%s)",
        len(token),
        len(api_token),
    )
    return False, None


def get_token_from_header(request: Request) -> Optional[str]:
    """Extract token from headers.

    Primary: X-EDON-TOKEN
    Fallback: Authorization: Bearer <token>
    """
    token = request.headers.get("X-EDON-TOKEN")
    if token:
        token = token.strip()
        return token if token else None

    auth_header = (request.headers.get("Authorization", "") or "").strip()
    if auth_header.startswith("Bearer "):
        bearer = auth_header[7:].strip()
        return bearer if bearer else None

    return None


def _ip_in_allowlist(ip: str, cidrs: List[str]) -> bool:
    """Return True if the IP address is within any of the CIDR ranges.

    Fails open (returns True) for unparseable IP strings so that reverse-proxy
    or internal health-check addresses never get spuriously blocked.
    """
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in ipaddress.ip_network(c, strict=False) for c in cidrs)
    except ValueError:
        return True  # fail-open for unparseable IPs


_BRUTE_FORCE_MAX = int(os.getenv("EDON_BRUTE_FORCE_MAX", "10"))      # max failures per window
_BRUTE_FORCE_WINDOW_SEC = int(os.getenv("EDON_BRUTE_FORCE_WINDOW", "60"))  # lockout window in seconds
_STRICT_FAIL_CLOSED = (
    os.getenv(
        "EDON_STRICT_FAIL_CLOSED",
        "true" if (os.getenv("ENVIRONMENT") == "production" or os.getenv("EDON_ENV") == "production") else "false",
    ).strip().lower() == "true"
)


def _brute_force_key(ip: str) -> str:
    """Return the DB counter key for the current time window."""
    from datetime import datetime, UTC
    now = datetime.now(UTC)
    # 60-second bucket
    bucket = now.strftime("%Y%m%d%H%M")
    return f"brute_force:{ip}:{bucket}"


def _is_brute_force_locked(ip: str) -> bool:
    """Return True if the IP has exceeded the failure threshold."""
    try:
        from ..persistence import get_db
        db = get_db()
        count = db.get_counter(_brute_force_key(ip))
        return count >= _BRUTE_FORCE_MAX
    except Exception:
        return _STRICT_FAIL_CLOSED


def _record_failed_auth(ip: str):
    """Increment the failure counter for this IP."""
    try:
        from ..persistence import get_db
        db = get_db()
        db.increment_counter(_brute_force_key(ip), 1)
        # Probabilistic cleanup: 1% of failed-auth calls purge stale brute-force rows
        if random.random() < 0.01:
            try:
                with db._get_connection() as _conn:
                    _conn.execute(
                        "DELETE FROM counters WHERE key LIKE 'brute_force:%' AND updated_at < datetime('now', '-2 days')"
                    )
                    _conn.commit()
            except Exception:
                pass
    except Exception:
        pass


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to validate authentication token."""

    PUBLIC_ENDPOINTS = {
        "/health",
        "/healthz",
        "/health/dependencies",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/debug/auth-public",
        "/auth/signup",
        "/auth/session",
        "/auth/sync",
        "/billing/plans",
        "/billing/checkout",
        "/billing/webhook",
        "/integrations/telegram/verify-code",
        "/admin/bootstrap-api-key",
    }

    async def dispatch(self, request: Request, call_next):
        # Pass through CORS preflight requests — CORSMiddleware (outermost) handles them,
        # but this ensures auth never blocks a preflight if middleware order shifts.
        if request.method == "OPTIONS":
            return await call_next(request)

        # Normalize path for trailing slashes
        path = request.url.path.rstrip("/")
        if config.DEMO_MODE and path == "/integrations/telegram/connect-code":
            return await call_next(request)
        if path in self.PUBLIC_ENDPOINTS or request.url.path in self.PUBLIC_ENDPOINTS:
            return await call_next(request)

        if not config.AUTH_ENABLED:
            request.state.tenant_id = os.getenv("EDON_DEV_TENANT_ID", "tenant_dev")
            request.state.tenant_info = None
            return await call_next(request)

        # Extract client IP for brute-force tracking
        client_ip = (
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or request.headers.get("X-Real-IP", "").strip()
            or (request.client.host if request.client else "unknown")
        )

        # Brute-force lockout: block IP after too many failed attempts
        if _is_brute_force_locked(client_ip):
            logger.warning(f"brute_force_lockout: ip={client_ip}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Too many failed authentication attempts. Try again later."},
                headers={"Retry-After": str(_BRUTE_FORCE_WINDOW_SEC)},
            )

        token = get_token_from_header(request)

        if not token:
            _record_failed_auth(client_ip)
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "detail": "Missing authentication token. Provide X-EDON-TOKEN header or Authorization Bearer token."
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        is_valid, tenant_info = verify_token(token)

        if not is_valid:
            _record_failed_auth(client_ip)
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid authentication token"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Tenant-scoped behavior
        if tenant_info:
            tenant_status = tenant_info.get("status")
            tenant_plan = tenant_info.get("plan")

            # Demo mode bypass
            if config.DEMO_MODE:
                tenant_info["status"] = "active"
                tenant_info["plan"] = tenant_plan or "starter"
                tenant_status = "active"
            else:
                if tenant_status not in ["active", "trial"]:
                    return JSONResponse(
                        status_code=status.HTTP_402_PAYMENT_REQUIRED,
                        content={
                            "detail": f"Subscription inactive. Status: {tenant_status}",
                            "status": tenant_status,
                            "plan": tenant_plan,
                        },
                    )

            # Usage limits
            try:
                from ..billing.plans import check_usage_limit
                from ..persistence import get_db
                from datetime import date

                db = get_db()
                tenant_id = tenant_info["tenant_id"]

                monthly_usage = db.get_tenant_usage(tenant_id)
                if not check_usage_limit(tenant_plan or "free", monthly_usage, "month"):
                    return JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content={
                            "detail": f"Monthly usage limit exceeded for plan '{tenant_plan}'",
                            "plan": tenant_plan,
                            "usage": monthly_usage,
                        },
                    )

                daily_usage = db.get_tenant_usage(tenant_id, date.today().isoformat())
                if not check_usage_limit(tenant_plan or "free", daily_usage, "day"):
                    return JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content={
                            "detail": f"Daily usage limit exceeded for plan '{tenant_plan}'",
                            "plan": tenant_plan,
                            "usage": daily_usage,
                        },
                    )

                request.state.tenant_id = tenant_id
                request.state.tenant_plan = tenant_plan
                request.state.tenant_status = tenant_status

            except Exception as e:
                logger.error(f"Error checking tenant limits: {e}", exc_info=True)
                if _STRICT_FAIL_CLOSED:
                    return JSONResponse(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        content={"detail": "Unable to validate tenant limits in strict mode."},
                    )

        elif (
            (os.getenv("EDON_ENV") == "development" or os.getenv("ENVIRONMENT") == "development")
            and token == (config.API_TOKEN or "").strip()
            and not getattr(request.state, "tenant_id", None)
        ):
            request.state.tenant_id = os.getenv("EDON_DEV_TENANT_ID", "tenant_dev")

        # IP allowlist check (Phase 2.3) — runs after tenant is resolved
        _resolved_tenant_id = (
            (tenant_info or {}).get("tenant_id")
            or getattr(request.state, "tenant_id", None)
        )
        _ip_bypass_paths = {"/health", "/healthz", "/docs", "/openapi.json", "/redoc"}
        if _resolved_tenant_id and request.url.path not in _ip_bypass_paths:
            try:
                from ..persistence import get_db as _get_db
                _db = _get_db()
                _allowlist = _db.get_ip_allowlist(_resolved_tenant_id)
                if _allowlist:
                    _client_ip = (
                        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                        or request.headers.get("X-Real-IP", "").strip()
                        or (request.client.host if request.client else "unknown")
                    )
                    if not _ip_in_allowlist(_client_ip, _allowlist):
                        logger.warning(
                            "ip_allowlist_blocked: tenant=%s ip=%s",
                            _resolved_tenant_id,
                            _client_ip,
                        )
                        return JSONResponse(
                            status_code=403,
                            content={"detail": "IP address not in tenant allowlist"},
                        )
            except Exception:
                pass  # allowlist check is fail-open

        # Token → agent_id binding
        if config.TOKEN_BINDING_ENABLED:
            from ..persistence import get_db

            db = get_db()
            agent_id = request.query_params.get("agent_id") or request.headers.get("X-Agent-ID") or None

            if agent_id:
                db.bind_token_to_agent(token, agent_id)
                db.update_token_last_used(token)
            else:
                bound_agent_id = db.get_agent_id_for_token(token)
                if bound_agent_id:
                    request.state.bound_agent_id = bound_agent_id
                    db.update_token_last_used(token)

        request.state.auth_token = token
        request.state.tenant_info = tenant_info  # used by RBACMiddleware

        return await call_next(request)
