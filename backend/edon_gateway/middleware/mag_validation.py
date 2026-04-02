"""MAG enforcement middleware."""

from __future__ import annotations

import json
from typing import Optional

from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from ..config import config
from ..mag_client import mag_enabled_for_tenant, fetch_decision_bundle, extract_decision_verdict
from ..tenancy import get_request_tenant_id


class MagValidationMiddleware(BaseHTTPMiddleware):
    """Require MAG decision_id/decision_bundle for configured endpoints."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path.rstrip("/") or "/"
        enforce_paths = {p.rstrip("/") or "/" for p in config.MAG_ENFORCE_PATHS}

        if request.method not in {"POST", "PUT"} or path not in enforce_paths:
            return await call_next(request)

        tenant_id = get_request_tenant_id(request)
        if not mag_enabled_for_tenant(tenant_id):
            return await call_next(request)

        decision_id: Optional[str] = request.headers.get("X-Decision-ID")
        decision_bundle = None

        body_bytes = await request.body()
        if body_bytes:
            try:
                body = json.loads(body_bytes)
            except Exception:
                body = {}
            request._body = body_bytes
            if isinstance(body, dict):
                decision_id = decision_id or body.get("decision_id")
                decision_bundle = body.get("decision_bundle")

        if not decision_bundle and decision_id:
            decision_bundle = fetch_decision_bundle(decision_id)
            if not decision_bundle:
                return JSONResponse(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content={"detail": "decision_id not found in MAG ledger"},
                )

        if not decision_bundle:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "decision_id or decision_bundle required when MAG enabled"},
            )

        verdict = extract_decision_verdict(decision_bundle)
        if not verdict:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "decision_bundle missing decision verdict"},
            )
        if verdict != "allow":
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "MAG decision denied"},
            )

        request.state.mag_decision_id = decision_id or decision_bundle.get("decision_id")
        request.state.mag_decision_bundle = decision_bundle
        return await call_next(request)
