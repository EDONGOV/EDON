"""CORS setup for the EDON Gateway.

Two layers:
  1. CORSMiddleware (starlette) — handles preflight + normal response headers.
  2. CORSEnsureMiddleware — outermost fallback that injects CORS headers on
     error responses (4xx/5xx) that starlette's CORSMiddleware can miss,
     ensuring browser clients can read error bodies.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Dict, List

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from ..config import config
from ..logging_config import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger(__name__)

_PRODUCTION_ORIGINS = [
    "https://edoncore.com",
    "https://www.edoncore.com",
    "https://console.edoncore.com",
    "https://edon-gateway.fly.dev",
]
_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:5174",
    "http://[::1]:8080",
]
_CONSOLE_ORIGIN = "https://console.edoncore.com"


def _build_cors_origins() -> List[str]:
    origins = list(config.CORS_ORIGINS)
    if "*" in origins:
        if config.is_production():
            raise RuntimeError(
                "EDON_CORS_ORIGINS cannot include '*' in production. "
                "Set explicit origins for the agent UI and production domains."
            )
        origins = [
            "https://edoncore.com",
            "https://www.edoncore.com",
            "https://console.edoncore.com",
        ]
        if os.getenv("ENVIRONMENT") != "production" and os.getenv("EDON_ENV") != "production":
            origins.extend(_DEV_ORIGINS)
        logger.warning(
            "CORS wildcard detected - using default origins. Set EDON_CORS_ORIGINS for production."
        )
    if not origins:
        origins = list(_PRODUCTION_ORIGINS)
    if _CONSOLE_ORIGIN not in origins:
        origins.append(_CONSOLE_ORIGIN)
    return origins


def _cors_headers_for_request(request: Request, allowed_origins: List[str]) -> Dict[str, str]:
    origin = request.headers.get("origin")
    if not origin or origin not in allowed_origins:
        return {}
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
    }


class CORSEnsureMiddleware(BaseHTTPMiddleware):
    """Ensures every response carries CORS headers so browser-readable
    500/403 errors don't trigger opaque network failures."""

    def __init__(self, app, allowed_origins: List[str]):
        super().__init__(app)
        self.allowed_origins = allowed_origins

    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
        except Exception as exc:
            logger.exception("Unhandled exception in request: %s", exc)
            response = JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
            )
        origin_headers = _cors_headers_for_request(request, self.allowed_origins)
        for key, value in origin_headers.items():
            if key not in response.headers:
                response.headers[key] = value
        return response


def setup_cors(app: "FastAPI") -> None:
    """Add CORSMiddleware + CORSEnsureMiddleware to app."""
    origins = _build_cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # CORSEnsureMiddleware must be outermost (added last)
    app.add_middleware(CORSEnsureMiddleware, allowed_origins=origins)
