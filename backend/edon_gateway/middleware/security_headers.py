"""Security header + request-ID middleware for the EDON Gateway."""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI


def add_security_headers_middleware(app: "FastAPI") -> None:
    """Register request-ID propagation and defensive security headers on every response."""
    from starlette.requests import Request

    @app.middleware("http")
    async def request_id_and_security_headers(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or os.urandom(8).hex()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-XSS-Protection"] = "0"
        return response
