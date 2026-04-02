# Stripe Live Setup — Real Price IDs & Billing Wired

Get Stripe checkout working with **real Price IDs** so the table below is live.

| Plan       | Price   | Decisions/mo | Agents | Retention      |
|------------|---------|--------------|--------|----------------|
| free       | $0      | 10,000       | 1      | 7 days         |
| starter    | $49     | 500,000      | 5      | 90 days        |
| growth     | $199    | 5,000,000    | 25     | 1 year         |
| business   | $499    | 25,000,000   | 100    | 3 years        |
| enterprise | Contact | Unlimited    | Unl.   | Unlimited      |

---

## 1. Create prices in Stripe (one-time)

1. Go to [Stripe Dashboard → Products](https://dashboard.stripe.com/products).
2. Create **one product** (e.g. "EDON Subscription") or one per tier.
3. For each paid tier, add a **recurring Price**:
   - **Starter:** $49/month → copy the **Price ID** (e.g. `price_1ABC...`).
   - **Growth:** $199/month → copy Price ID.
   - **Business:** $499/month → copy Price ID.

---

## 2. Set env vars (real keys)

In `.env` or Fly secrets, set:

```bash
# Required for live billing
STRIPE_SECRET_KEY=sk_live_...          # or sk_test_... for testing
STRIPE_WEBHOOK_SECRET=whsec_...

# Real Price IDs (from step 1)
STRIPE_PRICE_STARTER=price_xxxx
STRIPE_PRICE_GROWTH=price_xxxx
STRIPE_PRICE_BUSINESS=price_xxxx
```

**Fly:**

```bash
fly secrets set STRIPE_SECRET_KEY=sk_live_...
fly secrets set STRIPE_WEBHOOK_SECRET=whsec_...
fly secrets set STRIPE_PRICE_STARTER=price_...
fly secrets set STRIPE_PRICE_GROWTH=price_...
fly secrets set STRIPE_PRICE_BUSINESS=price_...
```

---

## 3. Webhook (so plans update after payment)

**One webhook handles everything** — both Payment Links and session-based checkout use the same endpoint and events. You do *not* need a separate webhook for Payment Links.

1. Stripe Dashboard → **Developers → Webhooks** → Add endpoint.
2. URL: `https://<your-gateway-host>/billing/webhook` (e.g. `https://edon-gatewaybk.fly.dev/billing/webhook`).
3. Events: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.paid`, `invoice.payment_failed`.
4. Copy the **Signing secret** → set as `STRIPE_WEBHOOK_SECRET`.

When a customer pays via a **Payment Link**, Stripe sends `checkout.session.completed` (with `client_reference_id` = tenant id). The gateway uses that to activate the subscription and set the plan — same as for API-created checkout sessions.

---

## 4. Faster “Stripe links” (optional)

- **Current flow:** Frontend calls `POST /billing/checkout` with `{"plan": "starter"}` → gateway creates a Stripe Checkout Session → returns `checkout_url`. One Stripe API call per click.
- **Faster option:** Use **Stripe Payment Links** (static URLs). Create a Payment Link per plan in Stripe, then set:

```bash
STRIPE_PAYMENT_LINK_STARTER=https://buy.stripe.com/...
STRIPE_PAYMENT_LINK_GROWTH=https://buy.stripe.com/...
STRIPE_PAYMENT_LINK_BUSINESS=https://buy.stripe.com/...
```

If the app supports it, the UI can redirect straight to these URLs (no gateway call), so links are instant. The **same webhook** (step 3) handles Payment Link completions — no extra webhook or events needed.

**Payment Link redirect (required):** In Stripe Dashboard, for each Payment Link, set **After payment** → **Redirect to a page** to:

```
https://edoncore.com/account/billing?payment=success
```

Without this, customers are not sent back to your app after paying.

---

## 5. Verify

- Call `POST /billing/checkout` with `{"plan": "starter"}` (with a valid tenant auth). You should get a `checkout_url` to Stripe.
- After paying in test mode, the webhook should set the tenant’s `plan` and `stripe_subscription_id` in the DB.

Your plan limits are already defined in `edon_gateway/billing/plans.py` (free, starter, growth, business, enterprise); once the env vars and webhook are set, **Stripe billing is wired** and the table above is live.
