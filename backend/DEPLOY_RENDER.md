# Deploying EDON Gateway to Render

## Quick Deploy Steps

1. **Go to Render Dashboard**: https://dashboard.render.com
2. **Create New Web Service**
3. **Connect Repository**: Link your GitHub repo (`GHOSTCODERRRRAHAHA/edon-v2-engine`)
4. **Configure Service**:
   - **Name**: `edon-gateway`
   - **Root Directory**: `edon_gateway` (IMPORTANT: Set this so build runs from gateway directory)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r ../requirements.gateway.txt` (requirements.gateway.txt is in repo root)
   - **Start Command**: `python -m uvicorn main:app --host 0.0.0.0 --port $PORT`

5. **Set Environment Variables** (in Render dashboard):
   ```
   EDON_AUTH_ENABLED=true
   EDON_CREDENTIALS_STRICT=true
   EDON_TOKEN_HARDENING=true
   EDON_VALIDATE_STRICT=true
   EDON_DATABASE_PATH=/tmp/edon_gateway.db
   EDON_LOG_LEVEL=INFO
   EDON_JSON_LOGGING=true
   EDON_METRICS_ENABLED=true
   EDON_RATE_LIMIT_ENABLED=true
   EDON_CORS_ORIGINS=http://localhost:5173,http://localhost:3000,https://edoncore.com
   
   # Stripe (get from Stripe Dashboard)
   STRIPE_SECRET_KEY=sk_live_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   STRIPE_PAYMENT_LINK_STARTER=https://buy.stripe.com/00w7sK5a0b5077YgXSfIs02
   ```

6. **Deploy!**

## After Deployment

1. **Get your gateway URL**: `https://edon-gateway.onrender.com` (or your custom domain)
2. **Update frontend** `.env.local`:
   ```
   VITE_GATEWAY_URL=https://edon-gateway.onrender.com
   ```
3. **Configure Stripe Webhook**:
   - Go to Stripe Dashboard → Webhooks
   - Add endpoint: `https://edon-gateway.onrender.com/billing/webhook`
   - Copy webhook secret to `STRIPE_WEBHOOK_SECRET` env var

## Database

Gateway uses SQLite by default (`/tmp/edon_gateway.db`). For production:
- Use Render's PostgreSQL addon, OR
- Use external database (Supabase, etc.)
- Update `EDON_DATABASE_PATH` to use PostgreSQL connection string
