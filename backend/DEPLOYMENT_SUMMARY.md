# Gateway Deployment Summary

## ✅ Completed Steps

### 1. Fixed CORS Configuration
- **Gateway** (`edon_gateway/main.py`): Fixed wildcard CORS issue - now uses specific origins when `allow_credentials=True`
- **CAV Engine** (`app/main.py`): Fixed CORS to allow specific origins (localhost:5173, edoncore.com)

### 2. Created Deployment Configuration
- **`edon_gateway/render.yaml`**: Render deployment configuration
- **`edon_gateway/Procfile`**: Process file for Render
- **`edon_gateway/runtime.txt`**: Python version specification
- **`edon_gateway/DEPLOY_RENDER.md`**: Step-by-step deployment guide

### 3. Updated Frontend to Use Separate URLs
- **`VITE_API_BASE_URL`**: Points to CAV Engine (`https://api-edon.onrender.com`)
- **`VITE_GATEWAY_URL`**: Points to Gateway (`https://edon-gateway.onrender.com`) - NEW
- **Updated files**:
  - `src/pages/Account.tsx` - Uses `GATEWAY_URL` for `/account/*` endpoints
  - `src/contexts/AuthContext.tsx` - Uses `GATEWAY_URL` for `/auth/*` and `/billing/*` endpoints
  - `src/pages/OnboardingSuccess.tsx` - Uses `GATEWAY_URL` for tenant endpoints
  - `env.example` - Added `VITE_GATEWAY_URL` documentation

## 🚀 Next Steps to Deploy

### Step 1: Deploy Gateway to Render

1. Go to https://dashboard.render.com
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repo: `GHOSTCODERRRRAHAHA/edon-v2-engine`
4. Configure:
   - **Name**: `edon-gateway`
   - **Root Directory**: `edon_gateway`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r ../requirements.gateway.txt`
   - **Start Command**: `python -m uvicorn main:app --host 0.0.0.0 --port $PORT`

5. **Set Environment Variables**:
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
   EDON_CORS_ORIGINS=http://localhost:5173,http://localhost:3000,https://edoncore.com,https://www.edoncore.com
   
   STRIPE_SECRET_KEY=sk_live_... (from Stripe Dashboard)
   STRIPE_WEBHOOK_SECRET=whsec_... (from Stripe Dashboard)
   STRIPE_PAYMENT_LINK_STARTER=https://buy.stripe.com/00w7sK5a0b5077YgXSfIs02
   ```

6. Click **"Create Web Service"**

### Step 2: Configure Stripe Webhook

1. After gateway deploys, get your URL: `https://edon-gateway.onrender.com`
2. Go to Stripe Dashboard → Webhooks
3. Add endpoint: `https://edon-gateway.onrender.com/billing/webhook`
4. Select events:
   - `checkout.session.completed`
   - `invoice.paid`
   - `customer.subscription.updated`
   - `invoice.payment_failed`
5. Copy webhook signing secret → Add to `STRIPE_WEBHOOK_SECRET` env var in Render

### Step 3: Update Frontend Environment

Update `D:\dev\edon-sentinel-core\.env.local`:
```bash
VITE_GATEWAY_URL=https://edon-gateway.onrender.com
```

(Already added, but verify the URL matches your Render service name)

## 📋 Architecture

```
Frontend (edon-sentinel-core)
├── VITE_API_BASE_URL → https://api-edon.onrender.com (CAV Engine)
│   └── Core functionality: /oem/cav/batch, /oem/robot/stability
│
└── VITE_GATEWAY_URL → https://edon-gateway.onrender.com (Gateway)
    └── SaaS endpoints: /account/*, /billing/*, /auth/*
```

## ✅ Benefits

1. **Separation of Concerns**: CAV Engine stays focused on core intelligence
2. **Independent Scaling**: Scale gateway and engine separately
3. **Clear Boundaries**: Each service has a single responsibility
4. **Easier Maintenance**: Update SaaS features without touching core engine

## 🔍 Testing

After deployment:
1. Frontend should connect to gateway for account/billing endpoints
2. CORS errors should be resolved
3. 404 errors should be gone (endpoints exist in gateway)
4. Stripe webhook should provision tenants after payment
