"""Shared HTTP transport, retry logic, and SDK headers."""
from __future__ import annotations

import logging
import random
from typing import Any, Optional

import httpx

from ._version import __version__
from .exceptions import APIConnectionError, APIError, APITimeoutError

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://edon-gateway-prod.fly.dev"
_DEFAULT_TIMEOUT = 10.0
_DEFAULT_MAX_RETRIES = 2
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_BASE_DELAY = 0.5
_MAX_DELAY = 8.0


def _sdk_headers() -> dict[str, str]:
    return {
        "User-Agent": f"edon-python/{__version__}",
        "X-EDON-SDK-Version": __version__,
        "X-EDON-SDK-Language": "python",
    }


def _retry_delay(attempt: int, retry_after: Optional[float] = None) -> float:
    if retry_after is not None:
        return min(retry_after, 60.0)
    base = _BASE_DELAY * (2 ** attempt)
    jitter = random.uniform(0, base * 0.25)
    return min(base + jitter, _MAX_DELAY)


def _parse_api_error(response: httpx.Response) -> APIError:
    try:
        body: dict[str, Any] = response.json()
    except Exception:
        body = {"error": response.text[:500]}
    request_id = response.headers.get("X-Request-ID") or response.headers.get("X-Request-Id")
    return APIError._from_response(response.status_code, body, request_id)


class BaseClient:
    """Shared config and headers for sync and async EDON clients."""

    def __init__(
        self,
        *,
        token: str,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = _DEFAULT_TIMEOUT,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        agent_id: str = "edon-agent",
    ) -> None:
        if not token:
            raise ValueError(
                "EDON API key is required. Pass token= or set the EDON_API_KEY environment variable."
            )
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.agent_id = agent_id
        self._active_intent_id: Optional[str] = None

    def _build_headers(self) -> dict[str, str]:
        return {
            "X-EDON-TOKEN": self.token,
            "Content-Type": "application/json",
            **_sdk_headers(),
        }
