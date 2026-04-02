"""MAG client helpers for gateway enforcement."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, TYPE_CHECKING

import requests

from .config import config
from .persistence import get_db

if TYPE_CHECKING:
    from .schemas import Action, IntentContract

LOGGER = logging.getLogger(__name__)

_IS_PRODUCTION = (os.getenv("ENVIRONMENT") == "production" or os.getenv("EDON_ENV") == "production")
_STRICT_FAIL_CLOSED = (os.getenv("EDON_STRICT_FAIL_CLOSED", "true" if _IS_PRODUCTION else "false").strip().lower() == "true")


def mag_enabled_for_tenant(tenant_id: Optional[str]) -> bool:
    if config.MAG_ENABLED:
        return True
    if not tenant_id:
        return False
    try:
        db = get_db()
        return db.is_mag_enabled(tenant_id)
    except Exception:
        return False


def authorize_action(
    action: "Action",
    intent: Optional["IntentContract"],
    tenant_id: Optional[str],
    context: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Send action to MAG /mag/authorize and return the authorization result.

    Maps EDON Action + IntentContract to MAG UniversalIntent format.

    Returns dict with: verdict (allow/deny/degrade), reason, constraints,
    risk_level, matched_rules.
    Returns None on error or if MAG is unreachable (fail-open: governance
    continues without MAG).
    """
    url = f"{config.MAG_URL}/mag/authorize"
    timeout_s = config.MAG_TIMEOUT_S

    # Build the MAG UniversalIntent payload
    action_str = f"{action.tool.value}.{action.op}"
    objective = intent.objective if intent else ""
    risk_val = action.computed_risk.value if action.computed_risk else "low"

    mag_context: Dict[str, Any] = {
        "mission_mode": "standard",
        "tenant_id": tenant_id,
        "risk_level": risk_val,
    }
    if context:
        # Merge caller-supplied context keys (do not override the three core keys)
        for k, v in context.items():
            if k not in mag_context:
                mag_context[k] = v

    payload = {
        "structured_intent": {
            "action": action_str,
            "parameters": action.params,
            "objective": objective,
        },
        "context": mag_context,
    }

    def _deny(reason: str) -> Dict[str, Any]:
        return {
            "verdict": "deny",
            "reason": reason,
            "constraints": [],
            "risk_level": "unknown",
            "matched_rules": ["MAG_UNREACHABLE_FAIL_CLOSED"],
        }

    try:
        resp = requests.post(url, json=payload, timeout=timeout_s)
    except Exception as exc:
        LOGGER.warning("MAG authorize unreachable — fail-open (continuing governance): %s", exc)
        return _deny("MAG unreachable in strict fail-closed mode") if _STRICT_FAIL_CLOSED else None

    if not resp.ok:
        LOGGER.warning(
            "MAG authorize returned non-OK status (%s) — fail-open: %s",
            resp.status_code,
            resp.text[:200],
        )
        return _deny(f"MAG non-OK status ({resp.status_code}) in strict fail-closed mode") if _STRICT_FAIL_CLOSED else None

    try:
        data = resp.json()
    except Exception as exc:
        LOGGER.warning("MAG authorize response not JSON — fail-open: %s", exc)
        return _deny("MAG invalid response in strict fail-closed mode") if _STRICT_FAIL_CLOSED else None

    # Normalize: MAG may wrap the result in an outer envelope
    decision: Dict[str, Any] = data
    if isinstance(data.get("result"), dict):
        decision = data["result"]
    elif isinstance(data.get("authorization"), dict):
        decision = data["authorization"]

    return {
        "verdict": decision.get("decision") or decision.get("verdict"),
        "reason": decision.get("rationale") or decision.get("reason"),
        "constraints": decision.get("constraints", []),
        "risk_level": decision.get("risk_level"),
        "matched_rules": decision.get("matched_rules", []),
    }


def fetch_decision_bundle(decision_id: str) -> Optional[Dict[str, Any]]:
    if not decision_id:
        return None
    url = f"{config.MAG_URL}/mag/ledger/decisions/{decision_id}"
    timeout_s = float("5")
    try:
        resp = requests.get(url, timeout=timeout_s)
    except Exception as exc:
        LOGGER.warning("MAG decision lookup failed: %s", exc)
        return None
    if resp.status_code == 404:
        return None
    if not resp.ok:
        LOGGER.warning("MAG decision lookup error (%s): %s", resp.status_code, resp.text)
        return None
    try:
        payload = resp.json()
    except Exception:
        return None
    if isinstance(payload, dict) and payload.get("ok") and payload.get("decision"):
        return payload.get("decision")
    return payload if isinstance(payload, dict) else None


def extract_decision_verdict(decision_bundle: Dict[str, Any]) -> Optional[str]:
    if not decision_bundle:
        return None
    if isinstance(decision_bundle.get("decision"), dict):
        decision = decision_bundle.get("decision") or {}
        verdict = decision.get("decision") or decision.get("verdict")
        return verdict.lower() if isinstance(verdict, str) else None
    verdict = decision_bundle.get("decision") or decision_bundle.get("verdict")
    return verdict.lower() if isinstance(verdict, str) else None

