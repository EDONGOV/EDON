"""Tenant self-service settings — IP allowlist management."""

import ipaddress
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

from ..persistence import get_db
from ..tenancy import get_request_tenant_id
from ..logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


class CIDRRequest(BaseModel):
    cidr: str = Field(..., description="IPv4/IPv6 CIDR block, e.g. '203.0.113.0/24' or single IP '1.2.3.4'")


def _normalize_cidr(cidr: str) -> str:
    cidr = cidr.strip()
    # Accept bare IPs — convert to /32 or /128
    try:
        addr = ipaddress.ip_address(cidr)
        return str(ipaddress.ip_network(addr))
    except ValueError:
        pass
    try:
        network = ipaddress.ip_network(cidr, strict=False)
        return str(network)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid CIDR: {cidr!r}")


@router.get("/ip-allowlist")
async def get_ip_allowlist(request: Request):
    """Return the tenant's current IP allowlist."""
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    db = get_db()
    cidrs = db.get_ip_allowlist(tenant_id) if hasattr(db, "get_ip_allowlist") else []
    return {"cidrs": cidrs, "enabled": len(cidrs) > 0}


@router.post("/ip-allowlist", status_code=201)
async def add_ip_allowlist(request: Request, body: CIDRRequest):
    """Add a CIDR block to the tenant's IP allowlist.

    Once any entry is added, ALL requests from IPs outside the allowlist
    will be rejected with 403. Add your own IP before enabling.
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    cidr = _normalize_cidr(body.cidr)
    db = get_db()

    existing = db.get_ip_allowlist(tenant_id) if hasattr(db, "get_ip_allowlist") else []
    if cidr in existing:
        return {"ok": True, "cidr": cidr, "message": "Already in allowlist"}

    if hasattr(db, "add_ip_to_allowlist"):
        db.add_ip_to_allowlist(tenant_id, cidr)
    else:
        raise HTTPException(status_code=501, detail="IP allowlist not supported by this backend")

    logger.info("settings.ip_allowlist_add: tenant=%s cidr=%s", tenant_id, cidr)
    return {"ok": True, "cidr": cidr, "message": "CIDR added to allowlist"}


@router.delete("/ip-allowlist", status_code=200)
async def remove_ip_allowlist(request: Request, body: CIDRRequest):
    """Remove a CIDR block from the tenant's IP allowlist."""
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")

    cidr = _normalize_cidr(body.cidr)
    db = get_db()

    if hasattr(db, "remove_ip_from_allowlist"):
        removed = db.remove_ip_from_allowlist(tenant_id, cidr)
    else:
        raise HTTPException(status_code=501, detail="IP allowlist not supported by this backend")

    logger.info("settings.ip_allowlist_remove: tenant=%s cidr=%s removed=%s", tenant_id, cidr, removed)
    return {"ok": removed, "cidr": cidr}
