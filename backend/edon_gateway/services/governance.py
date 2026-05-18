"""Shared governance helpers used by multiple route handlers.

Centralises the three places that independently implement intent-loading:
  - routes/v1_action.py
  - routes/execute.py
  - routes/clawdbot_proxy.py

Any change to intent-resolution logic (e.g. new fallback tier, new preset
format) now only needs to happen here.
"""
from __future__ import annotations

from typing import Any, Optional, Tuple

from ..logging_config import get_logger

logger = get_logger(__name__)


def load_intent(
    db: Any,
    intent_id: Optional[str],
    tenant_id: Optional[str],
) -> Tuple[Any, Optional[str]]:
    """Return the best available IntentContract for a governance decision.

    Priority:
      1. Explicit intent_id  → DB lookup scoped to tenant
      2. Tenant active preset → IntentContract built from the pack definition;
         intent_id auto-resolved from DB for audit completeness
      3. Default             → MEDIUM risk, empty scope, approved_by_user=False

    Returns (intent_contract, resolved_intent_id).
    The resolved_intent_id may differ from the input intent_id when it has
    been auto-resolved from the active preset name.
    """
    from ..schemas import IntentContract, RiskLevel

    # ── 1. Explicit intent ────────────────────────────────────────────────────
    if intent_id:
        try:
            intent_data = db.get_intent(intent_id, customer_id=tenant_id)
            if intent_data:
                return (
                    IntentContract(
                        objective=intent_data["objective"],
                        scope=intent_data["scope"],
                        constraints=intent_data.get("constraints", {}),
                        risk_level=RiskLevel(intent_data.get("risk_level", "MEDIUM")),
                        approved_by_user=bool(intent_data.get("approved_by_user", False)),
                    ),
                    intent_id,
                )
        except Exception as exc:
            logger.warning("Failed to load intent %s: %s", intent_id, exc)

    # ── 2. Active policy preset ───────────────────────────────────────────────
    try:
        active_preset = db.get_active_policy_preset()
        if active_preset and active_preset.get("preset_name"):
            from ..policy_packs import get_policy_pack

            preset_name = active_preset["preset_name"]
            pack = get_policy_pack(preset_name)
            intent_dict = pack.to_intent_dict()

            # Auto-resolve intent_id so audit records always carry one even
            # when the caller passed nothing.
            resolved_id = intent_id
            if not resolved_id:
                try:
                    all_intents = db.list_intents(customer_id=tenant_id)
                    matching = [
                        i for i in all_intents
                        if preset_name.lower() in i.get("intent_id", "").lower()
                    ]
                    if matching:
                        resolved_id = matching[0]["intent_id"]
                except Exception:
                    pass

            return (
                IntentContract(
                    objective=intent_dict["objective"],
                    scope=intent_dict["scope"],
                    constraints=intent_dict.get("constraints", {}),
                    risk_level=RiskLevel(intent_dict.get("risk_level", "LOW")),
                    approved_by_user=bool(intent_dict.get("approved_by_user", False)),
                ),
                resolved_id,
            )
    except Exception as exc:
        logger.warning("Failed to load active policy preset: %s", exc)

    # ── 3. Default ────────────────────────────────────────────────────────────
    from ..schemas import IntentContract, RiskLevel  # re-import safe (cached)

    return (
        IntentContract(
            objective="Default intent",
            scope={},
            constraints={},
            risk_level=RiskLevel.MEDIUM,
            approved_by_user=False,
        ),
        None,
    )
