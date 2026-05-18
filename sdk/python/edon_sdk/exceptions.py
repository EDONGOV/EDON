"""EDON SDK exception hierarchy.

Every error the SDK can raise is a subclass of EdonError.
Catch the specific type you care about, or EdonError for everything.

    from edon_sdk import (
        AuthenticationError,
        RateLimitError,
        APITimeoutError,
        APIConnectionError,
        EdonError,
    )

    try:
        result = client.evaluate(...)
    except AuthenticationError:
        # Bad API key — check EDON_API_KEY
    except RateLimitError as e:
        # Back off and retry after e.retry_after seconds
        time.sleep(e.retry_after or 5)
    except APITimeoutError:
        # Gateway took too long — transient, safe to retry
    except APIConnectionError:
        # Could not reach gateway — check network / EDON_GATEWAY_URL
    except EdonError:
        # Catch-all for anything else
"""
from __future__ import annotations

from typing import Any, Optional


class EdonError(Exception):
    """Base class for all EDON SDK errors."""


class APIError(EdonError):
    """An error response returned by the EDON API (4xx / 5xx)."""

    status_code: int
    message: str
    request_id: Optional[str]
    body: dict[str, Any]

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        request_id: Optional[str] = None,
        body: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.request_id = request_id
        self.body = body or {}

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}("
            f"message={self.message!r}, "
            f"status_code={self.status_code}, "
            f"request_id={self.request_id!r})"
        )

    @classmethod
    def _from_response(
        cls,
        status_code: int,
        body: dict[str, Any],
        request_id: Optional[str],
    ) -> "APIError":
        message = (
            body.get("detail")
            or body.get("message")
            or body.get("error")
            or f"HTTP {status_code}"
        )
        if isinstance(message, dict):
            message = str(message)

        if status_code == 401:
            return AuthenticationError(message, status_code=status_code, request_id=request_id, body=body)
        if status_code == 403:
            return PermissionDeniedError(message, status_code=status_code, request_id=request_id, body=body)
        if status_code == 404:
            return NotFoundError(message, status_code=status_code, request_id=request_id, body=body)
        if status_code == 422:
            return UnprocessableEntityError(message, status_code=status_code, request_id=request_id, body=body)
        if status_code == 429:
            retry_after = None
            if isinstance(body.get("retry_after"), (int, float)):
                retry_after = float(body["retry_after"])
            return RateLimitError(message, status_code=status_code, request_id=request_id, body=body, retry_after=retry_after)
        if status_code >= 500:
            return GatewayError(message, status_code=status_code, request_id=request_id, body=body)
        return cls(message, status_code=status_code, request_id=request_id, body=body)


class AuthenticationError(APIError):
    """401 — invalid or missing API key.

    Check that EDON_API_KEY is set correctly and starts with 'edon-'.
    """


class PermissionDeniedError(APIError):
    """403 — your API key does not have permission for this operation."""


class NotFoundError(APIError):
    """404 — the requested resource does not exist."""


class UnprocessableEntityError(APIError):
    """422 — the request was well-formed but failed validation."""


class RateLimitError(APIError):
    """429 — you have sent too many requests. Back off before retrying."""

    retry_after: Optional[float]

    def __init__(self, message: str, *, retry_after: Optional[float] = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class GatewayError(APIError):
    """5xx — the EDON gateway returned a server-side error. Usually transient."""


class APIConnectionError(EdonError):
    """Could not reach the EDON gateway at all (DNS failure, refused connection, etc.)."""

    def __init__(self, message: str, *, cause: Optional[BaseException] = None) -> None:
        super().__init__(message)
        if cause is not None:
            self.__cause__ = cause


class APITimeoutError(APIConnectionError):
    """The request to the EDON gateway timed out.

    The action may or may not have been received. Safe to retry evaluate()
    because governance is idempotent for the same action payload.
    """
