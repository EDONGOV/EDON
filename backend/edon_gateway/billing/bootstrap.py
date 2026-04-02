import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request, HTTPException
import secrets

from ..security.hashing import hash_api_key_fast
from ..persistence import get_db
from ..config import config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


# ---------------------------------------------------------------------------
# Public pricing data (no auth required)
# ---------------------------------------------------------------------------

def _build_price_plan_map() -> Dict[str, str]:
    """Build a mapping from Stripe Price ID → plan slug using config values.

    Only includes entries where the Price ID is actually configured (non-empty).
    """
    mapping: Dict[str, str] = {}
    pairs = [
        (config.STRIPE_PRICE_SCALE, "scale"),
        (config.STRIPE_PRICE_PRO, "pro"),
    ]
    for price_id, plan_slug in pairs:
        if price_id:
            mapping[price_id] = plan_slug
    return mapping


def _plan_to_price_id(plan: str) -> Optional[str]:
    """Return the Stripe Price ID for a given plan slug, or None if not configured."""
    lookup = {
        "scale": config.STRIPE_PRICE_SCALE,
        "pro": config.STRIPE_PRICE_PRO,
    }
    return lookup.get(plan.lower())


def _plan_to_payment_link(plan: str) -> Optional[str]:
    """Return the Stripe Payment Link URL for a plan if set (instant redirect, no Stripe API call)."""
    lookup = {
        "scale": config.STRIPE_PAYMENT_LINK_SCALE,
        "pro": config.STRIPE_PAYMENT_LINK_PRO,
    }
    return lookup.get(plan.lower())


# ---------------------------------------------------------------------------
# GET /billing/plans  — PUBLIC, no auth required
# ---------------------------------------------------------------------------

@router.get("/plans")
async def get_pricing_plans():
    """Public endpoint — returns pricing tiers for the consumer dashboard and pricing page.
    No authentication required.
    """
    from .plans import PLANS, ENTERPRISE_VOLUME_PRICING, ENTERPRISE_PLATFORM_FEE_USD, ENTERPRISE_COMPLIANCE_FEE_USD

    plan_list = []
    for slug, p in PLANS.items():
        plan_list.append({
            "name": p.name,
            "slug": slug,
            "price_usd": p.monthly_price_usd if p.monthly_price_usd > 0 else (0 if slug == "free" else None),
            "decisions_per_month": p.requests_per_month if p.requests_per_month != -1 else None,
            "max_agents": p.max_agents if p.max_agents != -1 else None,
            "audit_retention_days": p.audit_retention_days if p.audit_retention_days != -1 else None,
            "compliance_suite": p.compliance_suite,
            "contact_us": slug == "enterprise",
        })

    return {
        "plans": plan_list,
        "enterprise_volume_pricing": [
            {"up_to_decisions": t["up_to"], "price_per_decision": t["price_per_decision"]}
            for t in ENTERPRISE_VOLUME_PRICING
        ],
        "enterprise_platform_fee_usd": ENTERPRISE_PLATFORM_FEE_USD,
        "enterprise_compliance_fee_usd": ENTERPRISE_COMPLIANCE_FEE_USD,
    }


# ---------------------------------------------------------------------------
# GET /billing/status  — requires auth
# ---------------------------------------------------------------------------

@router.get("/status")
async def billing_status(request: Request):
    """Return billing status for the current tenant."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        if not config.DEMO_MODE:
            raise HTTPException(
                status_code=401,
                detail="No tenant context for billing status"
            )
        tenant_id = config.DEMO_TENANT_ID

    db = get_db()
    tenant = db.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    from .plans import get_plan_limits
    limits = get_plan_limits(tenant["plan"])
    usage_today = db.get_tenant_usage(tenant_id)

    return {
        "tenant_id": tenant_id,
        "status": tenant["status"],
        "plan": tenant["plan"],
        "usage": {
            "today": usage_today
        },
        "limits": {
            "requests_per_month": limits.requests_per_month,
            "requests_per_day": limits.requests_per_day,
            "requests_per_minute": limits.requests_per_minute
        }
    }


# ---------------------------------------------------------------------------
# POST /billing/checkout  — requires auth or body tenant_id + valid token
# ---------------------------------------------------------------------------

def _get_tenant_id_for_checkout(request: Request, body: Optional[Dict[str, Any]]) -> str:
    """Resolve tenant_id from request.state (set by auth middleware) or from body when token is valid."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id:
        return tenant_id
    if config.DEMO_MODE:
        return config.DEMO_TENANT_ID

    # Public path: no middleware ran. Allow tenant_id from body when Bearer/EDON token is valid for that tenant.
    body = body or {}
    body_tenant_id = (body.get("tenant_id") or "").strip()
    if not body_tenant_id:
        raise HTTPException(status_code=401, detail="No tenant context for checkout. Send tenant_id in body or authenticate with X-EDON-TOKEN / Authorization Bearer.")

    from ..middleware.auth import get_token_from_header, verify_token
    token = get_token_from_header(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token. Send Authorization: Bearer <token> or X-EDON-TOKEN.")
    is_valid, tenant_info = verify_token(token)
    if not is_valid or not tenant_info:
        raise HTTPException(status_code=401, detail="Invalid or expired token. Use the session token from signup or your EDON API key.")
    resolved_id = (tenant_info.get("tenant_id") or "").strip()
    if resolved_id != body_tenant_id:
        raise HTTPException(status_code=403, detail="Token does not match tenant_id.")
    return body_tenant_id


@router.post("/checkout")
async def create_checkout_session(request: Request, body: Optional[Dict[str, Any]] = None):
    """Create a Stripe Checkout session for the given plan.

    Request body: {"plan": "scale" | "pro", "tenant_id": "..." (required when not from auth middleware)}

    Returns:
        {"checkout_url": "https://checkout.stripe.com/..."} when Stripe is
        configured, or {"checkout_url": null, "message": "..."} when it is not.
    """
    tenant_id = _get_tenant_id_for_checkout(request, body)

    plan = (body or {}).get("plan", "scale").lower()
    if plan not in ("scale", "pro"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid plan '{plan}'. Must be one of: scale, pro"
        )

    # Fast path: Payment Link configured — no Stripe API call needed, no secret key required
    payment_link = _plan_to_payment_link(plan)
    if payment_link:
        return {"checkout_url": f"{payment_link}?client_reference_id={tenant_id}"}

    # Graceful degradation when Stripe is not configured
    if not config.STRIPE_SECRET_KEY:
        return {
            "checkout_url": None,
            "message": "Contact sales@edoncore.com to upgrade",
        }

    price_id = _plan_to_price_id(plan)
    if not price_id:
        return {
            "checkout_url": None,
            "message": (
                f"Stripe Price ID for plan '{plan}' is not configured. "
                "Contact sales@edoncore.com to upgrade."
            ),
        }

    try:
        import stripe
        stripe.api_key = config.STRIPE_SECRET_KEY

        db = get_db()
        tenant = db.get_tenant(tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        # Build customer params — reuse existing Stripe customer if we have one
        customer_params: dict = {}
        stripe_customer_id = tenant.get("stripe_customer_id")
        if stripe_customer_id:
            customer_params["customer"] = stripe_customer_id
        elif tenant.get("email"):
            customer_params["customer_email"] = tenant["email"]

        app_url = config.EDON_APP_URL
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{app_url}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{app_url}/billing/cancel",
            metadata={"tenant_id": tenant_id, "plan": plan},
            **customer_params,
        )

        return {"checkout_url": session.url}

    except Exception as exc:
        logger.error(f"Stripe checkout session creation failed: {exc}")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to create checkout session: {exc}"
        )


# ---------------------------------------------------------------------------
# POST /billing/api-keys  — bootstrap key creation
# ---------------------------------------------------------------------------

@router.post("/api-keys")
async def create_api_key(request: Request, body: Optional[Dict[str, Any]] = None):
    """Create a new API key for the authenticated tenant.

    Requires X-EDON-TOKEN (or Clerk session). Allowed in production so users can
    create and rotate keys from the dashboard.
    """
    tenant_id = getattr(request.state, "tenant_id", None)

    if not tenant_id:
        if config.DEMO_MODE:
            tenant_id = config.DEMO_TENANT_ID
        else:
            raise HTTPException(
                status_code=401,
                detail="Authentication required. Send X-EDON-TOKEN or sign in."
            )

    name = (body or {}).get("name", "bootstrap-key")

    raw_key = secrets.token_hex(32)
    key_hash = hash_api_key_fast(raw_key)

    db = get_db()
    api_key_id = db.create_api_key(
        tenant_id=tenant_id,
        key_hash=key_hash,
        name=name
    )

    return {
        "api_key": raw_key,
        "api_key_id": api_key_id,
        "tenant_id": tenant_id,
        "warning": "Store this key now. It will not be shown again."
    }


# ---------------------------------------------------------------------------
# GET /billing/api-keys  — list keys for tenant
# ---------------------------------------------------------------------------

@router.get("/api-keys")
async def list_api_keys(request: Request):
    """List API keys for the current tenant. Requires auth."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        if config.DEMO_MODE:
            tenant_id = config.DEMO_TENANT_ID
        else:
            raise HTTPException(status_code=401, detail="Authentication required")

    db = get_db()
    keys = db.list_api_keys(tenant_id)
    return {
        "keys": keys,
        "total": len(keys),
    }


# ---------------------------------------------------------------------------
# DELETE /billing/api-keys/{api_key_id}  — revoke key (used by deployed app)
# ---------------------------------------------------------------------------

@router.delete("/api-keys/{api_key_id}")
async def revoke_api_key(api_key_id: str, request: Request):
    """Revoke an API key. Requires auth; key must belong to current tenant."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        if config.DEMO_MODE:
            tenant_id = config.DEMO_TENANT_ID
        else:
            raise HTTPException(status_code=401, detail="Authentication required")

    db = get_db()
    api_key_id = api_key_id.strip()
    keys = db.list_api_keys(tenant_id)
    key_match = next((k for k in keys if str(k.get("id") or "") == str(api_key_id)), None)
    if not key_match:
        logger.warning("API key revoke: not found tenant_id=%s api_key_id=%s", tenant_id, api_key_id)
        raise HTTPException(status_code=404, detail="API key not found")
    if (key_match.get("status") or "").lower() == "revoked":
        return {"status": "revoked", "api_key_id": api_key_id}

    revoked = db.revoke_api_key(api_key_id)
    if not revoked:
        logger.warning("API key revoke: DB update failed tenant_id=%s api_key_id=%s", tenant_id, api_key_id)
        raise HTTPException(status_code=404, detail="API key not found")
    logger.info("API key revoked tenant_id=%s api_key_id=%s name=%s", tenant_id, api_key_id, key_match.get("name") or "")
    return {"status": "revoked", "api_key_id": api_key_id}


# ---------------------------------------------------------------------------
# POST /billing/webhook  — Stripe webhook handler
# ---------------------------------------------------------------------------

@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    webhook_secret = config.STRIPE_WEBHOOK_SECRET
    if not webhook_secret:
        logger.warning("STRIPE_WEBHOOK_SECRET not set — webhook processing skipped")
        return {"received": True}

    try:
        import stripe
        stripe.api_key = config.STRIPE_SECRET_KEY or ""
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception:
        raise HTTPException(status_code=400, detail="Webhook signature verification failed.")

    db = get_db()
    event_type = event.get("type", "")
    data_object = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        _handle_checkout_completed(db, data_object)
    elif event_type in ("customer.subscription.created", "customer.subscription.updated"):
        _handle_subscription_updated(db, data_object)
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(db, data_object)
    elif event_type == "invoice.payment_succeeded":
        _handle_payment_succeeded(db, data_object)
    elif event_type == "invoice.payment_failed":
        _handle_payment_failed(db, data_object)
    else:
        logger.debug(f"Unhandled Stripe event type: {event_type}")

    return {"received": True}


# ---------------------------------------------------------------------------
# Internal webhook helpers
# ---------------------------------------------------------------------------

def _handle_subscription_updated(db, subscription: dict):
    """Update tenant subscription status and plan from a Stripe subscription object."""
    stripe_customer_id = subscription.get("customer")
    if not stripe_customer_id:
        return

    status_map = {
        "active": "active",
        "trialing": "trial",
        "past_due": "past_due",
        "canceled": "canceled",
        "incomplete": "inactive",
        "incomplete_expired": "inactive",
        "unpaid": "past_due",
    }
    stripe_status = subscription.get("status", "")
    tenant_status = status_map.get(stripe_status, "inactive")

    # Derive plan from subscription items using config-backed Price ID map
    plan = "free"
    items = subscription.get("items", {}).get("data", [])
    if items:
        price_id = items[0].get("price", {}).get("id", "")
        price_plan_map = _build_price_plan_map()
        plan = price_plan_map.get(price_id, "starter")

    sub_id = subscription.get("id")
    period_start = subscription.get("current_period_start")
    period_end = subscription.get("current_period_end")
    cancel_at_period_end = subscription.get("cancel_at_period_end", False)

    try:
        tenant = db.get_tenant_by_stripe_customer(stripe_customer_id)
        if tenant:
            db.update_tenant_subscription(
                tenant_id=tenant["id"],
                status=tenant_status,
                plan=plan,
                stripe_subscription_id=sub_id,
                current_period_start=str(period_start) if period_start else None,
                current_period_end=str(period_end) if period_end else None,
                cancel_at_period_end=bool(cancel_at_period_end),
            )
            logger.info(
                f"Updated tenant {tenant['id']} subscription: "
                f"status={tenant_status} plan={plan}"
            )
        else:
            logger.warning(f"No tenant found for stripe_customer_id={stripe_customer_id}")
    except Exception as exc:
        logger.error(f"Failed to update tenant subscription: {exc}")


def _handle_subscription_deleted(db, subscription: dict):
    """Downgrade tenant to free plan when subscription is fully canceled."""
    stripe_customer_id = subscription.get("customer")
    if not stripe_customer_id:
        return
    try:
        tenant = db.get_tenant_by_stripe_customer(stripe_customer_id)
        if tenant:
            db.update_tenant_subscription(
                tenant_id=tenant["id"],
                status="canceled",
                plan="free",
                stripe_subscription_id=None,
            )
            logger.info(f"Tenant {tenant['id']} subscription canceled — downgraded to free")
    except Exception as exc:
        logger.error(f"Failed to cancel tenant subscription: {exc}")


def _handle_payment_succeeded(db, invoice: dict):
    """Ensure tenant is active after a successful payment."""
    stripe_customer_id = invoice.get("customer")
    if not stripe_customer_id:
        return
    try:
        tenant = db.get_tenant_by_stripe_customer(stripe_customer_id)
        if tenant and tenant.get("status") in ("past_due", "inactive"):
            db.update_tenant_subscription(
                tenant_id=tenant["id"],
                status="active",
            )
            logger.info(f"Tenant {tenant['id']} reactivated after successful payment")
    except Exception as exc:
        logger.error(f"Failed to reactivate tenant after payment: {exc}")


def _handle_payment_failed(db, invoice: dict):
    """Mark tenant as past_due after a failed payment."""
    stripe_customer_id = invoice.get("customer")
    if not stripe_customer_id:
        return
    try:
        tenant = db.get_tenant_by_stripe_customer(stripe_customer_id)
        if tenant:
            db.update_tenant_subscription(
                tenant_id=tenant["id"],
                status="past_due",
            )
            logger.info(f"Tenant {tenant['id']} marked past_due after payment failure")
    except Exception as exc:
        logger.error(f"Failed to mark tenant past_due: {exc}")


def _handle_checkout_completed(db, session: dict):
    """Handle checkout.session.completed — fired by both Payment Links and programmatic checkout.

    Links the Stripe customer to our tenant (via client_reference_id) so that
    subsequent subscription events can find the tenant by stripe_customer_id.
    """
    tenant_id = session.get("client_reference_id") or (session.get("metadata") or {}).get("tenant_id")
    stripe_customer_id = session.get("customer")
    plan_from_metadata = (session.get("metadata") or {}).get("plan")

    if not tenant_id or not stripe_customer_id:
        logger.warning(
            f"checkout.session.completed missing tenant_id or customer: "
            f"client_reference_id={session.get('client_reference_id')} "
            f"customer={stripe_customer_id}"
        )
        return

    try:
        # Save the Stripe customer ID to the tenant record so future subscription
        # events can look up the tenant by stripe_customer_id
        with db._get_connection() as conn:
            conn.execute(
                "UPDATE tenants SET stripe_customer_id = ?, updated_at = ? WHERE id = ?",
                (stripe_customer_id, __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(), tenant_id)
            )
            conn.commit()
        logger.info(
            f"checkout.session.completed: tenant={tenant_id} "
            f"stripe_customer={stripe_customer_id}"
        )

        # Also activate the tenant immediately if we know the plan
        # (subscription events will follow and confirm this)
        if plan_from_metadata and plan_from_metadata in ("scale", "pro"):
            db.update_tenant_subscription(
                tenant_id=tenant_id,
                status="active",
                plan=plan_from_metadata,
            )
    except Exception as exc:
        logger.error(f"Failed to handle checkout.session.completed: {exc}")
