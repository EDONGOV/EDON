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
    'admin':     ['*'],                              # All permissions
    'operator':  ['read', 'write', 'action', 'audit', 'api_keys'],
    'user':      ['action', 'read', 'audit', 'write'],  # Product default (console + governed actions)
    'agent':     ['action', 'read', 'audit', 'write'],  # Backward-compatible alias
    'read_only': ['read', 'audit'],
    'auditor':   ['read', 'audit', 'export'],        # External auditor: read + export evidence, no writes
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
    'GET /health':                   None,
    'GET /healthz':                  None,
    'GET /health/dependencies':      None,
    'GET /version':                  None,
    'GET /docs':                     None,
    'GET /openapi.json':             None,
}


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

        # Find the required permission for this endpoint
        endpoint_key = f"{method} {path}"
        required = ENDPOINT_PERMISSIONS.get(endpoint_key)

        # Path-prefix: /billing/api-keys (list, create, delete by id) require api_keys
        if required is None and path.startswith("/billing/api-keys") and method in ("GET", "POST", "DELETE"):
            required = "api_keys"

        # Admin-only routes: /admin/* mutations, API key management, policy-pack application,
        # and audit export all require the 'admin' role (which has '*' permissions).
        if required is None:
            if path.startswith("/admin") and method in ("POST", "PUT", "PATCH", "DELETE"):
                required = "admin"
            elif path.startswith("/api-keys") and method in ("POST", "DELETE"):
                required = "admin"
            elif path.startswith("/policy-packs") and path.endswith("/apply") and method == "POST":
                required = "admin"
            elif path in ("/audit/export", "/audit/evidence-package") and method == "GET":
                required = "export"
            elif path == "/settings/shadow-mode" and method == "POST":
                required = "admin"

        # Default: unspecified endpoints require 'read' for GET, 'write' for mutations
        if required is None:
            if method == 'GET':
                required = 'read'
            elif method in ('POST', 'PUT', 'PATCH', 'DELETE'):
                required = 'write'

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
                "/v1/jarvis/ask",
                "/v1/voice/ask",
                "/v1/voice/stream",
                "/v1/autonomous/status",
                "/v1/autonomous/run",
                "/v1/autonomous/start",
                "/v1/autonomous/stop",
                "/v1/codex/task",
                "/v1/codex/tasks",
            }
            path = request.url.path.rstrip("/")
            if any(path == prefix or path.startswith(f"{prefix}/") for prefix in ("/v1/jarvis", "/v1/voice", "/v1/autonomous", "/v1/codex")):
                return await call_next(request)
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
