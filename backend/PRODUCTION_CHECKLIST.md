# Production Deployment Checklist

## Pre-Deployment

### 1. Environment Variables (Set in Render Dashboard)

**Required:**
```
EDON_AUTH_ENABLED=true
EDON_API_TOKEN=<generate-strong-random-token>
EDON_CREDENTIALS_STRICT=true
EDON_TOKEN_HARDENING=true
EDON_VALIDATE_STRICT=true
EDON_DATABASE_PATH=/tmp/edon_gateway.db
EDON_LOG_LEVEL=INFO
EDON_JSON_LOGGING=true
EDON_METRICS_ENABLED=true
EDON_RATE_LIMIT_ENABLED=true
EDON_CORS_ORIGINS=https://edoncore.com,https://www.edoncore.com
```

**Stripe (Required for billing):**
```
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PAYMENT_LINK_STARTER=https://buy.stripe.com/...
```

**Optional:**
```
EDON_DEMO_MODE=false  # Must be false in production!
PYTHON_VERSION=3.11
```

### 2. Security Checklist

- [ ] `EDON_DEMO_MODE=false` (or not set)
- [ ] `EDON_AUTH_ENABLED=true`
- [ ] `EDON_API_TOKEN` is a strong random token (not default)
- [ ] `EDON_CREDENTIALS_STRICT=true`
- [ ] `EDON_TOKEN_HARDENING=true`
- [ ] `EDON_CORS_ORIGINS` set to specific domains (not `*`)
- [ ] Stripe keys are production keys (not test keys)
- [ ] Database path is set (SQLite for now, PostgreSQL recommended for scale)

### 3. Stripe Webhook Configuration

1. Go to [Stripe Dashboard → Webhooks](https://dashboard.stripe.com/webhooks)
2. Add endpoint: `https://edon-gateway.onrender.com/billing/webhook`
3. Select events:
   - `checkout.session.completed`
   - `invoice.paid`
   - `customer.subscription.updated`
   - `invoice.payment_failed`
4. Copy webhook secret to `STRIPE_WEBHOOK_SECRET` in Render

### 4. Render Configuration

**Service Settings:**
- [ ] Root Directory: (blank - use repo root)
- [ ] Dockerfile Path: `edon_gateway/Dockerfile`
- [ ] Docker Build Context: `.` (repo root)
- [ ] Auto-Deploy: Enabled
- [ ] Health Check Path: `/healthz`

### 5. Code Verification

- [ ] All debug/print statements removed
- [ ] Demo mode code disabled (or behind `EDON_DEMO_MODE` check)
- [ ] Error messages don't leak sensitive info
- [ ] Logging doesn't include tokens/passwords

### 6. Database

**Current:** SQLite (`/tmp/edon_gateway.db`)
- ✅ Works for MVP
- ⚠️ Data lost on container restart (Render free tier)
- 🔄 For production: Use PostgreSQL addon

**To add PostgreSQL:**
1. Render Dashboard → New → PostgreSQL
2. Copy connection string
3. Set `EDON_DATABASE_PATH` to connection string

### 7. Testing

**Before going live:**
- [ ] Test `/healthz` endpoint
- [ ] Test `/auth/signup` with real Clerk token
- [ ] Test `/billing/checkout` creates Stripe session
- [ ] Test webhook receives Stripe events
- [ ] Test API endpoints require authentication
- [ ] Test rate limiting works
- [ ] Test CORS allows frontend domain

### 8. Monitoring

- [ ] Check Render logs for errors
- [ ] Monitor Stripe webhook delivery
- [ ] Set up alerts for 5xx errors
- [ ] Monitor database size (SQLite)

## Post-Deployment

### 1. Verify Endpoints

```bash
# Health check
curl https://edon-gateway.onrender.com/healthz

# API docs
open https://edon-gateway.onrender.com/docs
```

### 2. Test Payment Flow

1. Sign up on frontend
2. Click "Starter Plan" ($25)
3. Complete Stripe checkout
4. Verify webhook received
5. Check tenant status is "active"
6. Verify API key generated

### 3. Monitor

- Check Render logs daily
- Monitor Stripe dashboard for failed payments
- Watch for 401/402 errors (auth/payment issues)
- Track API usage per tenant

## Rollback Plan

If issues occur:
1. Go to Render Dashboard → `edon-gateway` → Manual Deploy
2. Select previous successful commit
3. Deploy

## Support

- **Render Logs:** Dashboard → `edon-gateway` → Logs
- **Stripe Logs:** Dashboard → Developers → Logs
- **Database:** Connect via Render shell or use SQLite browser
