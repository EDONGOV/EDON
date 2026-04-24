"""EDON Self-Governance — policy check client for internal autonomous agents.

Every consequential action taken by an EDON operational agent (file writes,
GitHub issue creation, PRs, Slack/Telegram messages, webhooks) flows through
this client before execution.

What this gives you:
  - Shadow trace in the audit log for every internal agent action
  - Kill switch: if active, all internal agents stop taking actions immediately
  - RBAC: per-agent rules (e.g. code_agent may only write allowed paths)
  - Intent normalization: misalignment between stated_intent and action is flagged
  - Impact graph: EDON's own agents appear as nodes — execution graph of the company
  - Fail-open: if the gateway is unreachable, action proceeds with a warning logged

Usage:
    from agents.self_govern import gov_check

    decision = gov_check(
        agent_id="code_agent",
        action_type="file.write",
        parameters={"path": "backend/policies.py", "change_type": "modify"},
        stated_intent="apply approved code improvement from product signals",
    )
    if not decision.allowed:
        print(f"[self_govern] blocked — {decision.reason}")
        return
    # proceed with action

Environment variables:
    EDON_GATEWAY_URL              Gateway base URL (default: http://localhost:8000)
    EDON_API_TOKEN                Auth token for the gateway
    EDON_SELF_GOVERN_TENANT_ID    Internal tenant ID (default: tenant_edon_internal)
    EDON_SELF_GOVERN_TIMEOUT_SEC  Request timeout in seconds (default: 5)
    EDON_SELF_GOVERN_ENABLED      Set to "false" to disable all governance checks (default: true)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Any, Optional

import requests

_log = logging.getLogger(__name__)

_GATEWAY_URL = os.environ.get("EDON_GATEWAY_URL", "http://localhost:8000").rstrip("/")
_API_TOKEN = os.environ.get("EDON_API_TOKEN", "")
_TENANT_ID = os.environ.get("EDON_SELF_GOVERN_TENANT_ID", "tenant_edon_internal")
_TIMEOUT = float(os.environ.get("EDON_SELF_GOVERN_TIMEOUT_SEC", "5"))
_ENABLED = os.environ.get("EDON_SELF_GOVERN_ENABLED", "true").lower() == "true"


@dataclass
class GovDecision:
    """Result of a governance check.

    Truthy (``if decision:``) means the action is allowed to proceed.
    Falsy means it was blocked or requires human review.
    """
    allowed: bool
    decision: str       # ALLOW | BLOCK | DEGRADE | HUMAN_REQUIRED | ESCALATE | PAUSE
    reason: str
    action_id: str
    fallback: bool = False  # True when gateway was unreachable — fail-open applied

    def __bool__(self) -> bool:
        return self.allowed


# ── Sentinel responses ─────────────────────────────────────────────────────────

_FALLBACK = GovDecision(
    allowed=True,
    decision="ALLOW",
    reason="governance gateway unreachable — fail-open applied",
    action_id="fallback",
    fallback=True,
)

_DISABLED = GovDecision(
    allowed=True,
    decision="ALLOW",
    reason="self-governance disabled via EDON_SELF_GOVERN_ENABLED=false",
    action_id="disabled",
    fallback=False,
)


# ── Public API ─────────────────────────────────────────────────────────────────

def gov_check(
    agent_id: str,
    action_type: str,
    parameters: dict[str, Any],
    stated_intent: str = "",
    context: Optional[dict[str, Any]] = None,
) -> GovDecision:
    """Submit an action for governance evaluation before executing it.

    This is the primary entry point. Call it before every consequential action
    an internal agent takes (file write, GitHub issue, PR, Slack/Telegram send).

    Args:
        agent_id:       Internal agent name (e.g. "code_agent", "incident_agent").
        action_type:    tool.operation string (e.g. "file.write", "github.issue_create",
                        "github.pr_create", "message.send", "webhook.fire").
        parameters:     Action-specific payload passed into governance engine.
        stated_intent:  Why the agent is taking this action — feeds intent normalization.
        context:        Extra context merged into req_context (optional).

    Returns:
        GovDecision — truthy = proceed, falsy = blocked.
        Always fail-open: unreachable gateway returns truthy with fallback=True.
    """
    if not _ENABLED:
        return _DISABLED

    payload = {
        "agent_id": agent_id,
        "action_type": action_type,
        "action_payload": parameters,
        "timestamp": datetime.now(UTC).isoformat(),
        "context": {
            "stated_intent": stated_intent,
            "triggered_by": "internal_agent",
            "source": "self_govern",
            **(context or {}),
        },
    }

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "X-Tenant-ID": _TENANT_ID,
    }
    if _API_TOKEN:
        headers["X-EDON-TOKEN"] = _API_TOKEN

    try:
        r = requests.post(
            f"{_GATEWAY_URL}/v1/action",
            json=payload,
            headers=headers,
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        resp = r.json()
        decision = resp.get("decision", "ALLOW")
        # ALLOW and DEGRADE both proceed (DEGRADE = proceed with caution, logged)
        allowed = decision in ("ALLOW", "DEGRADE")
        result = GovDecision(
            allowed=allowed,
            decision=decision,
            reason=resp.get("decision_reason", ""),
            action_id=resp.get("action_id", ""),
        )

        if not allowed:
            _log.warning(
                "[self_govern] BLOCKED agent=%s action=%s reason=%s action_id=%s",
                agent_id, action_type, result.reason, result.action_id,
            )
        else:
            _log.debug(
                "[self_govern] ALLOWED agent=%s action=%s action_id=%s fallback=%s",
                agent_id, action_type, result.action_id, result.fallback,
            )

        return result

    except Exception as exc:
        _log.warning(
            "[self_govern] gateway unreachable for agent=%s action=%s — fail-open: %s",
            agent_id, action_type, exc,
        )
        return _FALLBACK
