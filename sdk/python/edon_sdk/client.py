"""EDON Python SDK — EdonClient.

Three methods cover the full governed agent loop:

    begin_intent()   — register a session intent contract upfront
    evaluate()       — govern an action before executing it
    scan_output()    — scan a tool response before the agent uses it
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://edon-gateway-prod.fly.dev"
_DEFAULT_TIMEOUT = 10


class EdonClient:
    """Client for the EDON governance gateway.

    Args:
        token:    Your EDON API key (starts with eak_).
        base_url: Gateway base URL. Defaults to production.
        timeout:  HTTP timeout in seconds.
        agent_id: Default agent_id used when not passed per-call.
    """

    def __init__(
        self,
        token: str,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: int = _DEFAULT_TIMEOUT,
        agent_id: str = "edon-agent",
    ) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.agent_id = agent_id
        self._active_intent_id: Optional[str] = None
        self._session = requests.Session()
        self._session.headers.update({
            "X-EDON-TOKEN": token,
            "Content-Type": "application/json",
        })

    # ── Intent contract ───────────────────────────────────────────────────────

    def begin_intent(
        self,
        objective: str,
        allowed_tools: list[str],
        risk_ceiling: str = "MEDIUM",
        constraints: Optional[dict] = None,
        intent_id: Optional[str] = None,
        ttl_seconds: int = 3600,
    ) -> str:
        """Register an intent contract and return its intent_id.

        Call once at the start of an agent session. All subsequent evaluate()
        calls will be scoped to this intent, enabling sequence drift detection,
        intent alignment checks, and shared rate budgets.

        Args:
            objective:     Plain-English description of what the agent will do.
            allowed_tools: List of "tool.op" strings the agent needs (e.g. ["database.query", "email.send"]).
            risk_ceiling:  Max acceptable risk: "LOW", "MEDIUM", "HIGH", "CRITICAL".
            constraints:   Optional extra constraints dict forwarded to the policy engine.
            intent_id:     Supply your own ID, or let EDON generate one.
            ttl_seconds:   Intent expiry in seconds (default 1 hour).

        Returns:
            intent_id string — store and pass to evaluate() calls.
        """
        iid = intent_id or f"intent_{uuid.uuid4().hex[:16]}"

        # Build scope dict: {"tool": ["op1", "op2"], ...}
        scope: dict[str, list[str]] = {}
        for entry in allowed_tools:
            parts = entry.split(".", 1)
            tool = parts[0]
            op = parts[1] if len(parts) > 1 else "*"
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
            r = self._session.post(
                f"{self.base_url}/intent/set",
                json=payload,
                timeout=self.timeout,
            )
            r.raise_for_status()
            self._active_intent_id = iid
            logger.debug("begin_intent: registered intent_id=%s", iid)
            return iid
        except Exception as exc:
            logger.warning("begin_intent failed (non-fatal): %s", exc)
            self._active_intent_id = iid  # use it anyway; governance will fall back gracefully
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

        Submit the action to EDON and get a verdict. Handle the verdict before
        proceeding — only execute when verdict is "ALLOW" or "DEGRADE".

        Args:
            action_type:   tool.operation string, e.g. "database.query", "email.send".
            payload:       Action parameters (tool-specific).
            agent_id:      Agent identifier. Defaults to client-level agent_id.
            intent_id:     Intent to scope this action under. Defaults to active intent.
            stated_intent: Why the agent is taking this action (improves alignment scoring).
            max_retries:   Max retries on PAUSE verdict.

        Returns:
            dict with keys:
                verdict        — "ALLOW" | "BLOCK" | "ESCALATE" | "DEGRADE" | "PAUSE" | "ERROR"
                reason_code    — machine-readable reason (e.g. "SCOPE_VIOLATION")
                explanation    — human-readable explanation
                action_id      — audit trail ID, pass to scan_output()
                safe_alternative — (DEGRADE only) modified params to use instead
                escalation_question — (ESCALATE only) question for the human reviewer
        """
        aid = agent_id or self.agent_id
        iid = intent_id or self._active_intent_id

        request_payload = {
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
                r = self._session.post(
                    f"{self.base_url}/v1/action",
                    json=request_payload,
                    timeout=self.timeout,
                )
                r.raise_for_status()
                resp = r.json()
            except Exception as exc:
                logger.warning("evaluate: gateway unreachable — fail-open: %s", exc)
                return {
                    "verdict": "ALLOW",
                    "reason_code": "GATEWAY_UNREACHABLE",
                    "explanation": f"EDON gateway unreachable — fail-open applied: {exc}",
                    "action_id": None,
                    "fallback": True,
                }

            verdict = resp.get("decision", resp.get("verdict", "ALLOW"))
            result = {
                "verdict": verdict,
                "reason_code": resp.get("reason_code") or resp.get("decision_reason", ""),
                "explanation": resp.get("explanation", ""),
                "action_id": resp.get("action_id"),
                "safe_alternative": resp.get("safe_alternative"),
                "escalation_question": resp.get("escalation_question"),
                "escalation_options": resp.get("escalation_options", []),
                "fallback": False,
            }

            if verdict == "PAUSE":
                wait = 5 * (attempt + 1)
                logger.info("evaluate: PAUSE — retrying in %ds (attempt %d/%d)", wait, attempt + 1, max_retries)
                time.sleep(wait)
                continue

            return result

        return {
            "verdict": "BLOCK",
            "reason_code": "PAUSE_TIMEOUT",
            "explanation": f"Exhausted {max_retries} PAUSE retries.",
            "action_id": None,
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
            action_type: Same action_type used in evaluate() — for audit linking.
            agent_id:    Agent identifier. Defaults to client-level agent_id.
            action_id:   action_id from the evaluate() response — links audit records.

        Returns:
            dict with keys:
                verdict   — "PASS" | "REDACT" | "BLOCK"
                payload   — safe payload to use (redacted if REDACT, None if BLOCK)
                findings  — list of {category, pattern, count} dicts
                redacted  — True if content was modified
        """
        aid = agent_id or self.agent_id

        request_payload = {
            "agent_id": aid,
            "action_type": action_type,
            "action_id": action_id,
            "response": response,
        }

        try:
            r = self._session.post(
                f"{self.base_url}/v1/output",
                json=request_payload,
                timeout=self.timeout,
            )
            r.raise_for_status()
            resp = r.json()
            return {
                "verdict": resp.get("verdict", "PASS"),
                "payload": resp.get("payload", response),
                "findings": resp.get("findings", []),
                "redacted": resp.get("redacted", False),
                "action_id": action_id,
            }
        except Exception as exc:
            logger.warning("scan_output: gateway unreachable — returning original: %s", exc)
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
        """Check gateway reachability."""
        try:
            r = self._session.get(f"{self.base_url}/health", timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            return {"status": "unreachable", "error": str(exc)}

    def end_intent(self) -> None:
        """Clear the active intent (call at end of agent session)."""
        self._active_intent_id = None


def _now_iso() -> str:
    from datetime import datetime, UTC
    return datetime.now(UTC).isoformat()
