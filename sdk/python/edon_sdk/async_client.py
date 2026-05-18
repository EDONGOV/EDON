"""EDON Python SDK — asynchronous client.

Drop-in async version of EdonClient. Uses ``httpx.AsyncClient`` under the hood.

Usage::

    import asyncio
    from edon_sdk import AsyncEdonClient

    async def main():
        async with AsyncEdonClient() as client:  # reads EDON_API_KEY from env
            result = await client.evaluate(
                action_type="database.query",
                payload={"query": "SELECT * FROM patients WHERE id = 42"},
            )
            if result["verdict"] == "ALLOW":
                ...

    asyncio.run(main())
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from ._base_client import (
    BaseClient,
    _DEFAULT_BASE_URL,
    _DEFAULT_MAX_RETRIES,
    _DEFAULT_TIMEOUT,
    _parse_api_error,
    _retry_delay,
    _RETRY_STATUSES,
)
from .client import _build_result, _fail_open, _now_iso
from .exceptions import APIConnectionError, APITimeoutError

logger = logging.getLogger(__name__)


class AsyncEdonClient(BaseClient):
    """Asynchronous EDON governance client.

    API is identical to :class:`EdonClient` — every method is a coroutine.

    Args:
        token:       Your EDON API key (starts with ``edon-``).
                     Falls back to ``EDON_API_KEY`` environment variable.
        base_url:    Gateway base URL. Falls back to ``EDON_GATEWAY_URL`` env
                     var, then production.
        timeout:     HTTP timeout in seconds. Default 10.
        max_retries: Automatic retries on 429 / 5xx. Default 2.
        agent_id:    Default agent identifier used when not passed per-call.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout: float = _DEFAULT_TIMEOUT,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        agent_id: str = "edon-agent",
    ) -> None:
        super().__init__(
            token=token or os.environ.get("EDON_API_KEY", ""),
            base_url=base_url or os.environ.get("EDON_GATEWAY_URL", _DEFAULT_BASE_URL),
            timeout=timeout,
            max_retries=max_retries,
            agent_id=agent_id,
        )
        self._http = httpx.AsyncClient(
            headers=self._build_headers(),
            timeout=timeout,
        )

    # ── Context manager ───────────────────────────────────────────────────────

    async def __aenter__(self) -> "AsyncEdonClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._http.aclose()

    # ── Internal HTTP ─────────────────────────────────────────────────────────

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        last_exc: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                delay = _retry_delay(attempt - 1)
                logger.debug("retry %d/%d — sleeping %.2fs", attempt, self.max_retries, delay)
                await asyncio.sleep(delay)

            try:
                resp = await self._http.request(method, url, **kwargs)
            except httpx.TimeoutException as exc:
                raise APITimeoutError(f"Request to {url} timed out") from exc
            except httpx.ConnectError as exc:
                raise APIConnectionError(
                    f"Could not connect to EDON gateway at {self.base_url}", cause=exc
                ) from exc
            except httpx.RequestError as exc:
                raise APIConnectionError(str(exc), cause=exc) from exc

            if resp.is_success:
                return resp.json()

            if attempt < self.max_retries and resp.status_code in _RETRY_STATUSES:
                retry_after: Optional[float] = None
                try:
                    retry_after = float(resp.headers.get("Retry-After", ""))
                except (ValueError, TypeError):
                    pass
                last_exc = _parse_api_error(resp)
                logger.debug("got %d — will retry (attempt %d)", resp.status_code, attempt + 1)
                if retry_after is not None:
                    await asyncio.sleep(min(retry_after, 60.0))
                continue

            raise _parse_api_error(resp)

        raise last_exc  # type: ignore[misc]

    # ── Intent contract ───────────────────────────────────────────────────────

    async def begin_intent(
        self,
        objective: str,
        allowed_tools: list[str],
        risk_ceiling: str = "MEDIUM",
        constraints: Optional[dict[str, Any]] = None,
        intent_id: Optional[str] = None,
        ttl_seconds: int = 3600,
    ) -> str:
        """Register an intent contract and return its intent_id."""
        iid = intent_id or f"intent_{uuid.uuid4().hex[:16]}"
        scope: dict[str, list[str]] = {}
        for entry in allowed_tools:
            parts = entry.split(".", 1)
            tool, op = parts[0], (parts[1] if len(parts) > 1 else "*")
            scope.setdefault(tool, []).append(op)

        payload = {
            "intent_id": iid,
            "objective": objective,
            "scope": scope,
            "constraints": {
                "max_risk_level": risk_ceiling.upper(),
                "ttl_seconds": ttl_seconds,
                **(constraints or {}),
            },
            "risk_level": risk_ceiling.lower(),
            "approved_by_user": False,
        }
        try:
            await self._request("POST", "/intent/set", json=payload)
        except Exception as exc:
            logger.warning("begin_intent failed (non-fatal): %s", exc)
        self._active_intent_id = iid
        return iid

    # ── Input governance ──────────────────────────────────────────────────────

    async def evaluate(
        self,
        action_type: str,
        payload: dict[str, Any],
        agent_id: Optional[str] = None,
        intent_id: Optional[str] = None,
        stated_intent: str = "",
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """Govern an action before executing it. See :meth:`EdonClient.evaluate`."""
        aid = agent_id or self.agent_id
        iid = intent_id or self._active_intent_id

        body: dict[str, Any] = {
            "agent_id": aid,
            "action_type": action_type,
            "action_payload": payload,
            "timestamp": _now_iso(),
            "context": {
                "stated_intent": stated_intent,
                **({"intent_id": iid} if iid else {}),
            },
        }

        for attempt in range(max_retries):
            try:
                resp = await self._request("POST", "/v1/action", json=body)
            except Exception as exc:
                logger.warning("evaluate: gateway error — fail-open: %s", exc)
                return _fail_open(exc)

            verdict = resp.get("decision") or resp.get("verdict") or "ALLOW"
            result = _build_result(resp, verdict)

            if verdict == "PAUSE":
                wait = 5 * (attempt + 1)
                logger.info(
                    "evaluate PAUSE — retrying in %ds (%d/%d)", wait, attempt + 1, max_retries
                )
                await asyncio.sleep(wait)
                continue

            return result

        return {
            "verdict": "BLOCK",
            "reason_code": "PAUSE_TIMEOUT",
            "explanation": f"Exhausted {max_retries} PAUSE retries.",
            "action_id": None,
            "safe_alternative": None,
            "escalation_question": None,
            "escalation_options": [],
            "fallback": False,
        }

    # ── Output governance ─────────────────────────────────────────────────────

    async def scan_output(
        self,
        response: Any,
        action_type: str,
        agent_id: Optional[str] = None,
        action_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Scan a tool response before the agent uses it. See :meth:`EdonClient.scan_output`."""
        body: dict[str, Any] = {
            "agent_id": agent_id or self.agent_id,
            "action_type": action_type,
            "action_id": action_id,
            "response": response,
        }
        try:
            resp = await self._request("POST", "/v1/output", json=body)
            return {
                "verdict": resp.get("verdict", "PASS"),
                "payload": resp.get("payload", response),
                "findings": resp.get("findings", []),
                "redacted": resp.get("redacted", False),
                "action_id": action_id,
                "fallback": False,
            }
        except Exception as exc:
            logger.warning("scan_output: gateway error — returning original: %s", exc)
            return {
                "verdict": "PASS",
                "payload": response,
                "findings": [],
                "redacted": False,
                "action_id": action_id,
                "fallback": True,
            }

    # ── Utility ───────────────────────────────────────────────────────────────

    async def health(self) -> dict[str, Any]:
        """Check gateway reachability."""
        try:
            return await self._request("GET", "/health")
        except Exception as exc:
            return {"status": "unreachable", "error": str(exc)}

    def end_intent(self) -> None:
        """Clear the active intent."""
        self._active_intent_id = None
