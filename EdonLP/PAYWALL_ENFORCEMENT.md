# Paywall Enforcement Architecture

## The 3 Requirements for a Real Paywall

### 1. Server-Side Enforcement (Not Just UI)

**Rule:** UI paywall is convenience. API paywall is the actual wall.

Even if someone bypasses the UI and hits your gateway directly, these endpoints must require:
- Valid token
- Token maps to tenant
- Tenant has active Stripe subscription

**Protected Endpoints:**
```
POST /clawdbot/invoke
POST /execute
GET  /audit/*
GET  /decisions/*
GET  /metrics
GET  /stats
```

**Gateway Middleware Flow:**
```
1. Extract X-EDON-TOKEN header
2. Lookup token_hash in api_tokens table
3. Get tenant_id from token
4. Check tenant.status in tenants table
5. If status != "active" && status != "trial":
   → Return 402 Payment Required
6. If token not found or inactive:
   → Return 401 Unauthorized
```

**Response Format (Inactive Subscription):**
```json
{
  "detail": "Subscription inactive. Status: canceled",
  "status": "canceled",
  "plan": "starter",
  "checkout_url": "https://checkout.stripe.com/..."
}
```

---

### 2. Tokens Must Be Per-Tenant (Per Customer)

**Database Schema:**
```sql
-- Tenants table
CREATE TABLE tenants (
  id TEXT PRIMARY KEY,  -- tenant_id
  email TEXT NOT NULL,
  status TEXT NOT NULL,  -- "active", "trial", "past_due", "canceled", "inactive", "pending"
  plan TEXT NOT NULL,    -- "starter", "pro", "enterprise"
  stripe_customer_id TEXT,
  stripe_subscription_id TEXT,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

-- API Tokens table (per-tenant)
CREATE TABLE api_tokens (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  token_hash TEXT NOT NULL UNIQUE,  -- SHA-256 hash, never plaintext
  is_active BOOLEAN DEFAULT TRUE,
  last_used TIMESTAMP,
  created_at TIMESTAMP
);
```

**Token Generation:**
```python
import uuid
import hashlib

# Generate token
token = f"edon_{uuid.uuid4().hex}"
token_hash = hashlib.sha256(token.encode()).hexdigest()

# Store hash in database
db.create_api_token(tenant_id, token_hash)

# Return full token ONLY ONCE (during onboarding)
# After that, only show preview: "edon_abc123••••••"
```

**Token Lookup:**
```python
def verify_token(token: str) -> tuple[bool, Optional[dict]]:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    api_token = db.get_api_token_by_hash(token_hash)
    
    if not api_token or not api_token.is_active:
        return False, None
    
    tenant = db.get_tenant(api_token.tenant_id)
    if not tenant:
        return False, None
    
    # Check subscription status
    if tenant.status not in ["active", "trial"]:
        return False, {"status": tenant.status, "plan": tenant.plan}
    
    return True, {
        "tenant_id": tenant.id,
        "status": tenant.status,
        "plan": tenant.plan
    }
```

**Account Page - Tokens Tab:**
- Shows only tokens for the authenticated user's tenant
- Displays token preview (masked): `edon_abc123••••••`
- Full token available only in Console → Integrations → Clawdbot
- Last used timestamp
- Revoke functionality

---

### 3. Stripe Webhook is the Source of Truth

**Critical Rule:** Don't trust browser redirects. Webhook provisions tenant + token.

**Flow:**
```
1. User signs up → POST /auth/signup
   - Creates user account
   - Creates tenant placeholder (status="pending")
   - Returns session_token + tenant_id

2. Create checkout → POST /billing/checkout
   - Creates Stripe Checkout session
   - Returns checkout_url

3. User pays → Stripe Checkout
   - User completes payment
   - Stripe redirects to success_url

4. Webhook fires → POST /billing/webhook
   - Event: checkout.session.completed
   - **THIS IS WHERE TENANT IS PROVISIONED**
   - Generate API token
   - Set tenant.status="active"
   - Store token hash in database
   - Link Stripe subscription to tenant

5. User redirected → /onboarding/success
   - User logs in (session already exists)
   - Frontend fetches token from /account/api-keys
   - Shows endpoint + token
```

**Webhook Handler (Python Example):**
```python
@app.post("/billing/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    
    # Verify webhook signature
    event = stripe.Webhook.construct_event(
        payload, signature, webhook_secret
    )
    
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        tenant_id = session["metadata"]["tenant_id"]
        subscription_id = session["subscription"]
        
        # Get subscription details
        subscription = stripe.Subscription.retrieve(subscription_id)
        plan_name = subscription["items"]["data"][0]["price"]["nickname"]
        
        # Provision tenant (if not already done)
        tenant = db.get_tenant(tenant_id)
        if tenant.status == "pending":
            # Generate API token
            api_key = f"edon_{uuid.uuid4().hex}"
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            db.create_api_key(tenant_id, key_hash, "Initial Key")
            
            # Activate subscription
            db.update_tenant_subscription(
                tenant_id=tenant_id,
                status="active",
                plan=plan_name.lower(),
                stripe_subscription_id=subscription_id
            )
            
            # Store API key temporarily for onboarding
            # (or send email with token)
    
    elif event["type"] == "invoice.payment_failed":
        subscription_id = event["data"]["object"]["subscription"]
        tenant = db.get_tenant_by_stripe_subscription(subscription_id)
        if tenant:
            db.update_tenant_subscription(
                tenant_id=tenant.id,
                status="past_due"
            )
    
    elif event["type"] == "customer.subscription.deleted":
        subscription_id = event["data"]["object"]["id"]
        tenant = db.get_tenant_by_stripe_subscription(subscription_id)
        if tenant:
            db.update_tenant_subscription(
                tenant_id=tenant.id,
                status="canceled"
            )
            # Optionally revoke all tokens
            db.deactivate_all_tokens(tenant.id)
    
    return {"status": "success"}
```

**Webhook Security:**
- Verify Stripe signature (prevents spoofing)
- Idempotent processing (handle duplicate events)
- Handle race conditions (webhook arrives before redirect)

---

## Complete Paywall Flow

### Signup → Payment → Provisioning

```
┌─────────────┐
│   User      │
└──────┬──────┘
       │
       │ 1. POST /auth/signup
       ├──────────────────────┐
       │                      │
       ▼                      ▼
┌─────────────┐      ┌──────────────┐
│  Frontend   │      │   Backend    │
└──────┬──────┘      └──────┬───────┘
       │                     │
       │ 2. POST /billing/checkout
       ├──────────────────────┐
       │                      │
       ▼                      ▼
┌─────────────┐      ┌──────────────┐
│   Stripe    │      │   Backend    │
│  Checkout   │      │ (creates     │
└──────┬──────┘      │  session)    │
       │             └──────────────┘
       │
       │ 3. User pays
       │
       ▼
┌─────────────┐
│   Stripe    │
│  Processes  │
│  Payment    │
└──────┬──────┘
       │
       ├─────────────────┐
       │                 │
       ▼                 ▼
┌─────────────┐  ┌──────────────┐
│  Redirect   │  │   Webhook    │
│  to success │  │   fires      │
│  URL        │  │               │
└──────┬──────┘  └──────┬───────┘
       │                 │
       │                 │ 4. Provision tenant
       │                 │    Generate token
       │                 │    Set status="active"
       │                 │
       ▼                 ▼
┌─────────────┐  ┌──────────────┐
│ /onboarding │  │   Database   │
│  /success   │  │   Updated    │
└─────────────┘  └──────────────┘
```

---

## API Gateway Paywall Middleware

```python
async def paywall_middleware(request: Request, call_next):
    # Skip paywall for public endpoints
    if request.url.path in PUBLIC_ENDPOINTS:
        return await call_next(request)
    
    # Extract token
    token = request.headers.get("X-EDON-TOKEN")
    if not token:
        return JSONResponse(
            status_code=401,
            content={"detail": "Missing authentication token"}
        )
    
    # Verify token + check subscription
    is_valid, tenant_info = verify_token(token)
    
    if not is_valid:
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid authentication token"}
        )
    
    # Check subscription status (from Stripe webhook)
    if tenant_info["status"] not in ["active", "trial"]:
        return JSONResponse(
            status_code=402,
            content={
                "detail": f"Subscription inactive. Status: {tenant_info['status']}",
                "status": tenant_info["status"],
                "plan": tenant_info["plan"],
                "checkout_url": get_checkout_url(tenant_info["tenant_id"])
            }
        )
    
    # Token valid + subscription active → proceed
    request.state.tenant_id = tenant_info["tenant_id"]
    return await call_next(request)
```

---

## Summary

✅ **Server-Side Enforcement:** API gateway checks token + subscription status  
✅ **Per-Tenant Tokens:** Each customer gets their own token(s), stored as hash  
✅ **Stripe Webhook:** Source of truth for subscription status, provisions tenant + token  

**The paywall is real because:**
1. Even if UI is bypassed, API requires valid token
2. Token must map to tenant with active subscription
3. Subscription status comes from Stripe webhook (can't be faked)

*Last Updated: 2025-01-27*
