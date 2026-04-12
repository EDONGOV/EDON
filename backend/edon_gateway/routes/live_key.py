"""Live key claim flow.

When an admin clicks "Go Live" for a tenant, a live key is created and a
pending_live_keys record is written. The client's console (authenticated with
their sandbox key) polls GET /live-key/pending to see if a key is waiting,
then POST /live-key/claim to reveal it once and delete the record.
"""

import uuid
from datetime import datetime, UTC, timedelta
from fastapi import APIRouter, Request, HTTPException

from ..persistence import get_db
from ..tenancy import get_request_tenant_id
from ..logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/live-key", tags=["live-key"])


@router.get("/pending")
async def check_pending(request: Request):
    """Check if this tenant has an unclaimed live key waiting."""
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    db = get_db()
    now = datetime.now(UTC).isoformat()
    try:
        with db._get_connection() as conn:
            row = conn.execute(
                "SELECT id, created_at FROM pending_live_keys WHERE tenant_id = ? AND expires_at > ? LIMIT 1",
                (tenant_id, now),
            ).fetchone()
    except Exception:
        return {"pending": False}

    if row:
        return {"pending": True, "created_at": row["created_at"]}
    return {"pending": False}


@router.post("/claim")
async def claim_live_key(request: Request):
    """Claim the pending live key. Returns the raw key once, then deletes the record."""
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    db = get_db()
    now = datetime.now(UTC).isoformat()
    try:
        with db._get_connection() as conn:
            row = conn.execute(
                "SELECT id, raw_key, key_id FROM pending_live_keys WHERE tenant_id = ? AND expires_at > ? LIMIT 1",
                (tenant_id, now),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="No pending live key found for this tenant")

            raw_key = row["raw_key"]
            key_id = row["key_id"]
            record_id = row["id"]

            # Delete immediately — shown once only
            conn.execute("DELETE FROM pending_live_keys WHERE id = ?", (record_id,))
            conn.commit()

    except HTTPException:
        raise
    except Exception as e:
        logger.error("live_key.claim failed: tenant=%s err=%s", tenant_id, e)
        raise HTTPException(status_code=500, detail="Failed to claim key")

    logger.info("live_key.claimed: tenant=%s key_id=%s", tenant_id, key_id)
    return {
        "key": raw_key,
        "key_id": key_id,
        "message": "Your live key — copy it now. This is the only time it will be shown.",
    }
