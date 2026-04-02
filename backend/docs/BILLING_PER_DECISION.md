# Per-decision billing (e.g. FedEx-style)

Bill customers by **governed decision volume** at a configurable rate (e.g. $0.000001 or $0.00001 per decision).

**Example:** At $0.00001 per decision (one thousandth of a cent), 12B decisions/day × 365 days = **$43.8M annually** from one customer.

---

## 1. Config

| Env var | Description | Example |
|--------|-------------|--------|
| `EDON_PRICE_PER_DECISION_USD` | Price in USD per single governed decision | `0.00001` ($0.00001) or `0.000001` ($0.000001) |

Defined in `edon_gateway/edon_gateway/billing/plans.py`: `get_price_per_decision_usd()`.

---

## 2. How usage is tracked

- Every successful **governed request** (e.g. `/v1/action`, `/execute`) is counted in **tenant_usage** (see `increment_tenant_usage` in rate_limit middleware and persistence).
- Usage is stored per tenant and per period (day or month depending on backend). You can sum by tenant for the billing period.

---

## 3. Stripe metered billing (recommended)

Stripe’s **metered billing** charges at period end: **usage × price**. Stripe’s smallest unit is **1 cent** per unit, so for sub-cent per decision you report **blocks** of decisions as one unit.

**Example:** $0.00001 per decision  
- Create a **Price** in Stripe: **usage_type = metered**, **unit_amount = 1** (1 cent), currency USD.  
- Report **quantity = decisions / 1000** (so 1 unit = 1000 decisions → 1 cent per 1000 = $0.00001 per decision).

**Example:** $0.000001 per decision  
- Same Price (1 cent per unit).  
- Report **quantity = decisions / 10,000** (1 unit = 10,000 decisions → 1 cent per 10,000 = $0.000001 per decision).

### Steps in Stripe Dashboard

1. **Product:** Create product e.g. “EDON Governed Decisions”.
2. **Price:** Add a price to that product:
   - **Pricing model:** Standard pricing  
   - **Usage type:** Metered  
   - **Price:** e.g. **$0.01** per unit (1 unit = 1000 or 10,000 decisions depending on `EDON_PRICE_PER_DECISION_USD`)  
   - Save and copy the **Price ID** (e.g. `price_xxx`).
3. **Subscription:** When creating a customer subscription, add this price as a **metered** line item (quantity can be 0; you report usage via API).
4. **Report usage:** Use `StripeClient.report_usage(subscription_item_id, quantity=...)` (see below). Get `subscription_item_id` from `Subscription.retrieve(subscription_id).items.data[0].id` for the metered item.

### Reporting usage from the gateway

- **Option A (batch, e.g. daily cron):** For each tenant with a Stripe subscription, sum `tenant_usage` for the current billing period, convert to “units” (e.g. `usage // 1000`), then call `stripe_client.report_usage(subscription_item_id, quantity=units, action="set")` so Stripe has the total for the period (or use “increment” for incremental reporting).
- **Option B (incremental):** On each decision (or every N decisions), call `report_usage(..., quantity=1, action="increment")` if you defined 1 unit = N decisions.

`edon_gateway/edon_gateway/billing/stripe_client.py` defines:

```python
def report_usage(self, subscription_item_id: str, quantity: int, timestamp=None, action="increment") -> Dict
```

Use this with the subscription item ID of the metered price attached to the customer’s subscription.

---

## 4. Computing revenue (no Stripe)

If you invoice outside Stripe:

- **Monthly charge** = `get_tenant_usage(tenant_id, period)` × `get_price_per_decision_usd()`.
- Example: 20M decisions/month × $0.00001 = **$200/month** per tenant.

---

## 5. Summary

| Goal | Action |
|------|--------|
| Set price per decision | `EDON_PRICE_PER_DECISION_USD=0.00001` (or `0.000001`) |
| Track decisions | Already done via `increment_tenant_usage` and audit/decisions tables |
| Bill via Stripe | Create metered Price, attach to subscription, report usage with `report_usage()` |
| Bill outside Stripe | Use `get_tenant_usage()` × `get_price_per_decision_usd()` per period |
