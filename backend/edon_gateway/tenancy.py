"""Single source of truth for tenant scoping."""

from typing import Optional
from starlette.requests import Request


def get_request_tenant_id(request: Request) -> Optional[str]:
    """
    Single source of truth for tenant scoping.

    Tenant ID is ONLY sourced from request.state.tenant_id, which is set
    exclusively by the auth middleware after validating the caller's token.
    Client-supplied headers (e.g. X-Tenant-ID) are never trusted.
    """
    tid = getattr(request.state, "tenant_id", None)
    if tid:
        return tid

    return None
