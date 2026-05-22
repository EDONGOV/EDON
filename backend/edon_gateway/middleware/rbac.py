"""Role-Based Access Control (RBAC) middleware for EDON Gateway."""

import logging
from typing import Optional, Dict, List
from fastapi import status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Permissions granted per role
ROLE_PERMISSIONS: Dict[str, List[str]] = {
    'super_admin':     ['*'],  # Full tenant control
    'admin':           ['*'],  # Backward-compatible alias for legacy bootstrap flows
    'governance_admin': ['read', 'write', 'action', 'audit', 'export', 'approvals', 'api_keys'],
    'security_admin':   ['read', 'audit', 'export', 'api_keys', 'incidents'],
    'operator':         ['read', 'write', 'action', 'audit'],
    'developer':        ['read', 'action', 'sandbox'],
    'auditor':          ['read', 'audit', 'export'],
    'viewer':           ['read'],
    'read_only':        ['read', 'audit'],
    'user':             ['read'],  # Legacy alias kept narrow for compatibility
    'agent':            ['read', 'action'],  # Legacy alias kept narrow for compatibility
}

# Permission required per endpoint (None = public)
ENDPOINT_PERMISSIONS: Dict[str, Optional[str]] = {
    'POST /v1/action':               'action',
    'GET /audit/query':              'audit',
    'POST /decisions/query':         'audit',
    'GET /decisions/{decision_id}':  'read',
    'GET /settings/kill-switch':     'read',
    'POST /settings/kill-switch':    'admin',
    'DELETE /settings/kill-switch':  'admin',
    'POST /auth/signup':             None,
    'POST /auth/session':            None,
    'POST /auth/sync':               None,
    'POST /access/user-invites/accept': None,
    'GET /health':                   None,
    'GET /healthz':                  None,
    'GET /health/dependencies':      None,
    'GET /version':                  None,
    'GET /docs':                     None,
    'GET /openapi.json':             None,
}


def required_permission_for(method: str, path: str) -> Optional[str]:
    """Resolve the RBAC permission for a route.

    Keep high-risk console and runtime mutations explicit. The fallback exists
    for legacy surfaces, but production-sensitive paths should be declared here
    so broad "write" roles do not accidentally inherit admin operations.
    """
    method = method.upper()
    path = path.rstrip("/") or "/"
    endpoint_key = f"{method} {path}"
    required = ENDPOINT_PERMISSIONS.get(endpoint_key)

    if required is None and path.startswith("/billing/api-keys") and method in ("GET", "POST", "DELETE"):
        return "api_keys"

    if path.startswith("/admin"):
        return None if path == "/admin/bootstrap-api-key" else "admin"

    if path.startswith("/api-keys"):
        if method in ("POST", "PATCH", "DELETE"):
            return "admin"
        if method == "GET":
            return "api_keys"

    if path.startswith("/access/user-invites") and method in ("GET", "POST", "DELETE"):
        if path == "/access/user-invites/accept" and method == "POST":
            return None
        return "admin"

    if path.startswith("/access/department-owners") and method in ("GET", "PUT", "DELETE"):
        return "admin"

    if path.startswith("/v1/onboarding"):
        if method == "POST" and (
            "/review" in path
            or "/promote" in path
            or "/signoffs/" in path
            or path.endswith("/bootstrap")
            or path.endswith("/shadow")
            or path.endswith("/signoff/request")
        ):
            return "admin"
        if method == "POST":
            return "write"
        if method == "GET":
            return "read"

    if path.startswith("/v1/operations/reconciliation"):
        if method == "POST" and (
            path.endswith("/promote")
            or path.endswith("/hold")
            or path.endswith("/merge")
            or "/rows/" in path
        ):
            return "admin"
        if method == "POST":
            return "write"
        if method == "GET":
            return "read"

    if path.startswith("/v1/assistant"):
        if method == "POST" and (
            path == "/v1/assistant/apply"
            or "/memories/" in path
        ):
            return "admin"
        if method == "POST":
            return "read"
        if method == "GET":
            return "read"

    if path.startswith("/v1/jarvis") or path.startswith("/v1/voice") or path.startswith("/v1/autonomous") or path.startswith("/v1/codex"):
        return "admin" if method in ("POST", "PUT", "PATCH", "DELETE") else "read"

    if path in ("/audit/export", "/audit/evidence-package") and method == "GET":
        return "export"

    if path.startswith("/policy-packs") and path.endswith("/apply") and method == "POST":
        return "admin"

    if path == "/settings/shadow-mode" and method == "POST":
        return "admin"

    if method == "GET":
        return "read"
    if method in ("POST", "PUT", "PATCH", "DELETE"):
        return "write"
    return required


def check_permission(tenant_info: Optional[Dict], required_permission: str) -> bool:
    """Check if tenant has the required permission.

    Args:
        tenant_info: Dict with at least 'role' key. None means unauthenticated
                     (auth middleware already validated before this runs).
        required_permission: Permission string to check.

    Returns:
        True if permitted, False otherwise.
    """
    if not tenant_info:
        # No tenant context — auth middleware handles authentication separately;
        # this shouldn't happen for protected routes
        return False
    role = tenant_info.get('role', 'user')
    allowed = ROLE_PERMISSIONS.get(role, [])
    return '*' in allowed or required_permission in allowed


class RBACMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces role-based access control after authentication."""

    async def dispatch(self, request: Request, call_next):
        from ..config import config as _cfg
        if not _cfg.AUTH_ENABLED:
            return await call_next(request)

        method = request.method
        path = request.url.path.rstrip('/')

        endpoint_key = f"{method} {path}"
        required = required_permission_for(method, path)

        # Public endpoints pass through
        if required is None:
            return await call_next(request)

        tenant_info = getattr(request.state, 'tenant_info', None)

        # If no auth context is present, only allow known public/health endpoints.
        # All other routes require an authenticated tenant context.
        if tenant_info is None:
            # Only allow public/health endpoints without auth context
            public_paths = {
                "/health", "/healthz", "/", "/docs", "/redoc", "/openapi.json",
                "/health/dependencies",
                "/auth/signup",      # Public: create tenant from Clerk (no tenant yet)
                "/auth/session",     # Public: validate Clerk session / get tenant
                "/billing/webhook",
                "/billing/plans",   # Public: list plans for pricing page / console
                "/billing/checkout",  # Public: start checkout (session created server-side)
                "/admin/bootstrap-api-key",  # Protected by X-Bootstrap-Secret, not tenant auth
                "/telegram/bot-webhook",     # Protected by X-Telegram-Bot-Api-Secret-Token
            }
            path = request.url.path.rstrip("/")
            # All /admin/* routes are protected by X-Bootstrap-Secret, not tenant auth
            if path.startswith("/admin/") or path == "/admin":
                return await call_next(request)
            if path not in public_paths:
                return JSONResponse(status_code=403, content={"detail": "Authentication required"})
            return await call_next(request)

        if not check_permission(tenant_info, required):
            role = tenant_info.get('role', 'unknown')
            logger.warning(
                "RBAC denied: role=%s required=%s endpoint=%s",
                role, required, endpoint_key,
            )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "detail": (
                        f"Insufficient permissions. "
                        f"Role '{role}' cannot perform '{required}' on this endpoint."
                    )
                },
            )

        return await call_next(request)
