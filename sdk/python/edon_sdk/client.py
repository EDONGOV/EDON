"""EDON Python SDK — synchronous client.

Three methods cover the full governed agent loop:

    begin_intent()   — register a session intent contract upfront
    evaluate()       — govern an action before executing it
    scan_output()    — scan a tool response before the agent uses it

Usage::

    import os
    from edon_sdk import EdonClient

    client = EdonClient()                            # reads EDON_API_KEY from env
    # or: EdonClient(token="edon-...")

    intent_id = client.begin_intent(
        objective="Summarise patient records",
        allowed_tools=["database.query", "llm.complete"],
    )

    result = client.evaluate(
        action_type="database.query",
        payload={"query": "SELECT * FROM patients WHERE id = 42"},
    )

    if result["verdict"] == "ALLOW":
        raw = run_query(...)
        scan = client.scan_output(raw, action_type="database.query", action_id=result["action_id"])
        if scan["verdict"] != "BLOCK":
            use(scan["payload"])
"""
from __future__ import annotations

import logging
import os
import time
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
from .exceptions import APIConnectionError, APITimeoutError

logger = logging.getLogger(__name__)


class EdonClient(BaseClient):
    """Synchronous EDON governance client.

    Args:
        token:       Your EDON API key (starts with ``edon-``).
                     Falls back to ``EDON_API_KEY`` environment variable.
        base_url:    Gateway base URL. Falls back to ``EDON_GATEWAY_URL`` env var,
                     then production.
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
        self._http = httpx.Client(
            headers=self._build_headers(),
            timeout=timeout,
        )

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> "EdonClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._http.close()

    # ── Internal HTTP ─────────────────────────────────────────────────────────

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        last_exc: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                delay = _retry_delay(attempt - 1)
                logger.debug("retry %d/%d — sleeping %.2fs", attempt, self.max_retries, delay)
                time.sleep(delay)

            try:
                resp = self._http.request(method, url, **kwargs)
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
                    time.sleep(min(retry_after, 60.0))
                continue

            raise _parse_api_error(resp)

        raise last_exc  # type: ignore[misc]

    # ── Intent contract ───────────────────────────────────────────────────────

    def begin_intent(
        self,
        objective: str,
        allowed_tools: list[str],
        risk_ceiling: str = "MEDIUM",
        constraints: Optional[dict[str, Any]] = None,
        intent_id: Optional[str] = None,
        ttl_seconds: int = 3600,
    ) -> str:
        """Register an intent contract and return its intent_id.

        Call once at the start of an agent session. All subsequent
        ``evaluate()`` calls will be scoped to this intent, enabling sequence
        drift detection, intent alignment checks, and shared rate budgets.

        Args:
            objective:     Plain-English description of what the agent will do.
            allowed_tools: ``"tool.op"`` strings the agent needs
                           (e.g. ``["database.query", "email.send"]``).
            risk_ceiling:  Max acceptable risk: ``"LOW"``, ``"MEDIUM"``,
                           ``"HIGH"``, or ``"CRITICAL"``.
            constraints:   Optional extra constraints forwarded to the policy
                           engine.
            intent_id:     Supply your own ID, or let EDON generate one.
            ttl_seconds:   Intent expiry in seconds. Default 3600.

        Returns:
            ``intent_id`` string — store and pass to ``evaluate()`` calls.
        """
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
            self._request("POST", "/intent/set", json=payload)
        except Exception as exc:
            logger.warning("begin_intent failed (non-fatal): %s", exc)
        self._active_intent_id = iid
        return iid

    # ── Input governance ──────────────────────────────────────────────────────

    def evaluate(
        self,
        action_type: str,
        payload: dict[str, Any],
        agent_id: Optional[str] = None,
        intent_id: Optional[str] = None,
        stated_intent: str = "",
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """Govern an action before executing it.

        Submit the action to EDON and get a verdict. Only proceed when the
        verdict is ``"ALLOW"`` or ``"DEGRADE"``.

        Args:
            action_type:   ``tool.operation`` string, e.g. ``"database.query"``.
            payload:       Action parameters (tool-specific).
            agent_id:      Agent identifier. Defaults to client-level
                           ``agent_id``.
            intent_id:     Intent to scope this action under. Defaults to the
                           active intent set by ``begin_intent()``.
            stated_intent: Why the agent is taking this action — improves
                           alignment scoring.
            max_retries:   Max retries on ``PAUSE`` verdict. Default 3.

        Returns:
            dict with keys:

            * ``verdict`` — ``"ALLOW"`` | ``"BLOCK"`` | ``"ESCALATE"`` |
              ``"DEGRADE"`` | ``"PAUSE"`` | ``"ERROR"``
            * ``reason_code`` — machine-readable reason
            * ``explanation`` — human-readable explanation
            * ``action_id`` — audit trail ID; pass to ``scan_output()``
            * ``safe_alternative`` — (*DEGRADE only*) modified params to use
            * ``escalation_question`` — (*ESCALATE only*) question for a human
            * ``fallback`` — ``True`` if the gateway was unreachable and
              fail-open was applied
        """
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
                resp = self._request("POST", "/v1/action", json=body)
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
                time.sleep(wait)
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

    def scan_output(
        self,
        response: Any,
        action_type: str,
        agent_id: Optional[str] = None,
        action_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Scan a tool response before the agent uses it.

        Detects PHI/PII, credential leakage, bulk data, and sensitive paths.
        Always call this after executing a tool and before passing the result
        to your LLM or downstream logic.

        Args:
            response:    Raw tool response (any JSON-serialisable value).
            action_type: Same ``action_type`` used in ``evaluate()`` — for
                         audit linking.
            agent_id:    Agent identifier. Defaults to client-level
                         ``agent_id``.
            action_id:   ``action_id`` from the ``evaluate()`` response —
                         links audit records.

        Returns:
            dict with keys:

            * ``verdict`` — ``"PASS"`` | ``"REDACT"`` | ``"BLOCK"``
            * ``payload`` — safe payload (redacted if ``REDACT``, ``None``
              if ``BLOCK``)
            * ``findings`` — list of ``{category, pattern, count}`` dicts
            * ``redacted`` — ``True`` if content was modified
            * ``fallback`` — ``True`` if the gateway was unreachable
        """
        body: dict[str, Any] = {
            "agent_id": agent_id or self.agent_id,
            "action_type": action_type,
            "action_id": action_id,
            "response": response,
        }
        try:
            resp = self._request("POST", "/v1/output", json=body)
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

    def health(self) -> dict[str, Any]:
        """Check gateway reachability. Returns the health response dict."""
        try:
            return self._request("GET", "/health")
        except Exception as exc:
            return {"status": "unreachable", "error": str(exc)}

    def end_intent(self) -> None:
        """Clear the active intent (call at end of agent session)."""
        self._active_intent_id = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fail_open(exc: Exception) -> dict[str, Any]:
    return {
        "verdict": "ALLOW",
        "reason_code": "GATEWAY_UNREACHABLE",
        "explanation": f"EDON gateway unreachable — fail-open applied: {exc}",
        "action_id": None,
        "safe_alternative": None,
        "escalation_question": None,
        "escalation_options": [],
        "fallback": True,
    }


def _build_result(resp: dict[str, Any], verdict: str) -> dict[str, Any]:
    return {
        "verdict": verdict,
        "reason_code": resp.get("reason_code") or resp.get("decision_reason", ""),
        "explanation": resp.get("explanation", ""),
        "action_id": resp.get("action_id"),
        "safe_alternative": resp.get("safe_alternative"),
        "escalation_question": resp.get("escalation_question"),
        "escalation_options": resp.get("escalation_options", []),
        "fallback": False,
    }
