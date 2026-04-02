"""Subscription plan definitions and limits."""

import os
from typing import Dict, List, Optional
from dataclasses import dataclass


# Per-decision pricing (e.g. FedEx-style: $0.000001 or $0.00001 per governed decision)
# Used for usage-based billing; set in env or override per plan.
def get_price_per_decision_usd() -> float:
    """Price in USD per single governed decision. Default 1e-5 ($0.00001 = one thousandth of a cent)."""
    return float(os.getenv("EDON_PRICE_PER_DECISION_USD", "0.00001"))


@dataclass
class PlanLimits:
    """Plan limits for a subscription tier."""
    name: str
    requests_per_month: int
    requests_per_day: Optional[int] = None
    requests_per_minute: Optional[int] = None
    max_agents: int = 1                  # -1 = unlimited
    audit_retention_days: int = 7        # -1 = unlimited
    compliance_suite: bool = False
    monthly_price_usd: float = 0.0       # 0.0 = free or custom pricing


# Plan definitions — Free, Scale, Pro
PLANS: Dict[str, PlanLimits] = {
    "free": PlanLimits(
        name="Free",
        requests_per_month=50_000,
        requests_per_day=5_000,
        requests_per_minute=100,
        max_agents=3,
        audit_retention_days=7,
        compliance_suite=False,
        monthly_price_usd=0.0,
    ),
    "scale": PlanLimits(
        name="Scale",
        requests_per_month=5_000_000,
        requests_per_day=200_000,
        requests_per_minute=2_000,
        max_agents=100,
        audit_retention_days=90,
        compliance_suite=False,
        monthly_price_usd=150.0,
    ),
    "pro": PlanLimits(
        name="Pro",
        requests_per_month=25_000_000,
        requests_per_day=2_000_000,
        requests_per_minute=5_000,
        max_agents=1_000,
        audit_retention_days=365,
        compliance_suite=True,
        monthly_price_usd=600.0,
    ),
    # HIPAA-compliant plan for hospital deployments.
    # Audit retention is 2555 days (7 years) to exceed the HIPAA minimum of 6 years.
    # Custom pricing — contact sales. Requires signed BAA before provisioning.
    "hospital": PlanLimits(
        name="Hospital",
        requests_per_month=-1,          # unlimited
        requests_per_day=-1,            # unlimited
        requests_per_minute=10_000,
        max_agents=-1,                  # unlimited
        audit_retention_days=2555,      # 7 years (HIPAA minimum = 6 years / 2190 days)
        compliance_suite=True,
        monthly_price_usd=0.0,          # custom — quoted per engagement
    ),
}


# ---------------------------------------------------------------------------
# Enterprise volume pricing
# ---------------------------------------------------------------------------

ENTERPRISE_VOLUME_PRICING: List[dict] = [
    {"up_to": 1_000_000_000,       "price_per_decision": 0.0001},
    {"up_to": 10_000_000_000,      "price_per_decision": 0.000075},
    {"up_to": 100_000_000_000,     "price_per_decision": 0.00005},
    {"up_to": 1_000_000_000_000,   "price_per_decision": 0.000025},
    {"up_to": None,                 "price_per_decision": 0.00001},  # 1T+
]

ENTERPRISE_PLATFORM_FEE_USD: float = 15_000.0        # per month
ENTERPRISE_COMPLIANCE_FEE_USD: float = 10_000.0      # per month
ENTERPRISE_INTELLIGENCE_PREMIUM_USD: float = 0.0     # custom — EDON Core predictive features (quoted per engagement)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_plan_limits(plan_name: str) -> PlanLimits:
    """Get plan limits for a plan name.

    Aliases are provided for backward compatibility so that callers using the
    old plan names ("pro", "pro_plus", "pro+", "proplus") are silently mapped
    to the current equivalent names ("growth" and "business").

    Args:
        plan_name: Plan name (free, scale, pro, or legacy aliases starter/growth/business/enterprise)

    Returns:
        PlanLimits object

    Raises:
        ValueError: If plan name is not recognised
    """
    plan_name_lower = (plan_name or "").strip().lower().replace(" ", "")

    # Backward-compatibility aliases (old tier names → current)
    _ALIASES: Dict[str, str] = {
        "starter":    "scale",
        "growth":     "scale",
        "business":   "pro",
        "enterprise": "pro",
        "pro_plus":   "pro",
        "pro+":       "pro",
        "proplus":    "pro",
        "healthcare": "hospital",
        "hipaa":      "hospital",
        "clinical":   "hospital",
    }
    plan_name_lower = _ALIASES.get(plan_name_lower, plan_name_lower)

    if plan_name_lower not in PLANS:
        raise ValueError(f"Unknown plan: {plan_name!r}")

    return PLANS[plan_name_lower]


def check_usage_limit(
    plan_name: str,
    current_usage: int,
    period: str = "month",
    current_agents: Optional[int] = None,
) -> bool:
    """Check if usage (and optionally agent count) is within plan limits.

    Args:
        plan_name: Plan name
        current_usage: Current request/decision count for the given period
        period: Period to check — one of "month", "day", or "minute"
        current_agents: Optional current number of active agents.  When
            provided the agent cap is also enforced.

    Returns:
        True if all checked limits are within bounds, False if any is exceeded
    """
    limits = get_plan_limits(plan_name)

    # --- Request-volume check ---
    if period == "month":
        limit = limits.requests_per_month
    elif period == "day":
        limit = limits.requests_per_day if limits.requests_per_day is not None \
            else limits.requests_per_month // 30
    elif period == "minute":
        limit = limits.requests_per_minute if limits.requests_per_minute is not None \
            else limits.requests_per_month // (30 * 24 * 60)
    else:
        limit = -1  # Unknown period — treat as unlimited

    # -1 means unlimited
    if limit != -1 and current_usage >= limit:
        return False

    # --- Agent-count check (optional) ---
    if current_agents is not None:
        agent_limit = limits.max_agents
        if agent_limit != -1 and current_agents > agent_limit:
            return False

    return True


def get_enterprise_price(decisions_per_month: int) -> dict:
    """Calculate enterprise pricing for a given monthly decision volume.

    Applies the ENTERPRISE_VOLUME_PRICING tiered rate table, then adds the
    fixed platform and compliance fees.

    Args:
        decisions_per_month: Expected number of governed decisions per month.

    Returns:
        A dict with keys:
            decisions_per_month     (int)
            price_per_decision      (float)  — effective blended rate
            decision_cost_usd       (float)
            platform_fee_usd        (float)
            compliance_fee_usd      (float)
            total_usd               (float)
    """
    if decisions_per_month < 0:
        raise ValueError("decisions_per_month must be >= 0")

    # Find the applicable tier (first tier whose "up_to" >= decisions_per_month,
    # or the catch-all tier where up_to is None).
    price_per_decision: float = ENTERPRISE_VOLUME_PRICING[-1]["price_per_decision"]
    for tier in ENTERPRISE_VOLUME_PRICING:
        if tier["up_to"] is None or decisions_per_month <= tier["up_to"]:
            price_per_decision = tier["price_per_decision"]
            break

    decision_cost = decisions_per_month * price_per_decision
    platform_fee = ENTERPRISE_PLATFORM_FEE_USD
    compliance_fee = ENTERPRISE_COMPLIANCE_FEE_USD
    total = decision_cost + platform_fee + compliance_fee

    return {
        "decisions_per_month": decisions_per_month,
        "price_per_decision": price_per_decision,
        "decision_cost_usd": round(decision_cost, 6),
        "platform_fee_usd": platform_fee,
        "compliance_fee_usd": compliance_fee,
        "total_usd": round(total, 6),
    }
