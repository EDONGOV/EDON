"""Stripe client for billing and subscriptions."""

import os
import logging
from typing import Optional, Dict, Any
import stripe

logger = logging.getLogger(__name__)

# Initialize Stripe
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY
else:
    logger.warning("STRIPE_SECRET_KEY not set - billing features disabled")


class StripeClient:
    """Stripe client for managing customers and subscriptions."""
    
    def __init__(self):
        """Initialize Stripe client."""
        if not STRIPE_SECRET_KEY:
            raise ValueError("STRIPE_SECRET_KEY not configured")
    
    def create_customer(self, email: str, metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Create a Stripe customer.
        
        Args:
            email: Customer email
            metadata: Optional metadata dictionary
            
        Returns:
            Stripe customer object
        """
        customer = stripe.Customer.create(
            email=email,
            metadata=metadata or {}
        )
        return customer
    
    def create_checkout_session(
        self,
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Create a Stripe checkout session.
        
        Args:
            customer_id: Stripe customer ID
            price_id: Stripe price ID for the plan
            success_url: URL to redirect on success
            cancel_url: URL to redirect on cancel
            metadata: Optional metadata dictionary
            
        Returns:
            Stripe checkout session object
        """
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{
                "price": price_id,
                "quantity": 1,
            }],
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=metadata or {}
        )
        return session
    
    def get_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """Get subscription details.
        
        Args:
            subscription_id: Stripe subscription ID
            
        Returns:
            Stripe subscription object
        """
        return stripe.Subscription.retrieve(subscription_id)
    
    def get_customer(self, customer_id: str) -> Dict[str, Any]:
        """Get customer details.
        
        Args:
            customer_id: Stripe customer ID
            
        Returns:
            Stripe customer object
        """
        return stripe.Customer.retrieve(customer_id)
    
    def cancel_subscription(self, subscription_id: str, at_period_end: bool = True) -> Dict[str, Any]:
        """Cancel a subscription.
        
        Args:
            subscription_id: Stripe subscription ID
            at_period_end: If True, cancel at period end; if False, cancel immediately
            
        Returns:
            Updated Stripe subscription object
        """
        if at_period_end:
            return stripe.Subscription.modify(
                subscription_id,
                cancel_at_period_end=True
            )
        else:
            return stripe.Subscription.delete(subscription_id)
    
    def report_usage(
        self,
        subscription_item_id: str,
        quantity: int,
        timestamp: Optional[int] = None,
        action: str = "increment",
    ) -> Dict[str, Any]:
        """Report metered usage to Stripe for per-decision billing.
        
        Use with a Stripe Price that has usage_type='metered'. Stripe bills at period end:
        quantity * unit_amount. To get $0.00001 per decision, create a price with
        unit_amount=1 (1 cent) and report quantity = decisions/1000 (so 1 unit = 1000 decisions).
        
        Args:
            subscription_item_id: Stripe subscription item ID (from subscription.items.data[].id)
            quantity: Number of units to report (e.g. decisions or blocks of decisions)
            timestamp: Unix timestamp; default now
            action: 'increment' (add to current) or 'set' (replace)
            
        Returns:
            Stripe usage record object
        """
        params = {"quantity": quantity, "action": action}
        if timestamp is not None:
            params["timestamp"] = timestamp
        return stripe.SubscriptionItem.create_usage_record(subscription_item_id, **params)

    def verify_webhook(self, payload: bytes, signature: str) -> Dict[str, Any]:
        """Verify Stripe webhook signature.
        
        Args:
            payload: Raw request body
            signature: Stripe signature header
            
        Returns:
            Parsed event object
            
        Raises:
            ValueError: If signature is invalid
        """
        if not STRIPE_WEBHOOK_SECRET:
            raise ValueError("STRIPE_WEBHOOK_SECRET not configured")
        
        try:
            event = stripe.Webhook.construct_event(
                payload, signature, STRIPE_WEBHOOK_SECRET
            )
            return event
        except ValueError as e:
            logger.error(f"Invalid webhook payload: {e}")
            raise
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Invalid webhook signature: {e}")
            raise
