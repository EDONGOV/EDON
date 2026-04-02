# How to Get Your EDON Gateway API Token

## Current Token Status

Based on your configuration, here are your token options:

### Option 1: Environment Variable Token (Legacy)

If `EDON_AUTH_ENABLED=true`, the gateway uses `EDON_API_TOKEN` from environment variables.

**Check your token:**
```powershell
cd C:\Users\cjbig\Desktop\EDON\edon-cav-engine\edon_gateway
python -c "import os; print(os.getenv('EDON_API_TOKEN', 'Not set'))"
```

**Default token** (if not set): `your-secret-token`

**Set a custom token:**
```powershell
# In .env file
EDON_API_TOKEN=your-custom-token-here
```

---

### Option 2: Tenant-Scoped API Keys (Recommended)

If you have a tenant account, you can create API keys via the API:

**Create API Key:**
```powershell
# First, authenticate (if using Clerk)
# Then create API key:
curl -X POST http://localhost:8000/billing/api-keys `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer YOUR_CLERK_TOKEN" `
  -d '{"name": "Test Key"}'
```

**List API Keys:**
```powershell
curl http://localhost:8000/billing/api-keys `
  -H "Authorization: Bearer YOUR_CLERK_TOKEN"
```

---

### Option 3: Demo Mode Token

If demo mode is enabled, you can use:
```
Token: edon_demo_key_12345
```

**Enable demo mode:**
```env
EDON_DEMO_MODE=true
EDON_DEMO_API_KEY=edon_demo_key_12345
```

---

## Quick Check

**Check if auth is enabled:**
```powershell
cd C:\Users\cjbig\Desktop\EDON\edon-cav-engine\edon_gateway
python -c "from config import Config; print(f'Auth Enabled: {Config.AUTH_ENABLED}'); print(f'Token: {Config.API_TOKEN}')"
```

**If auth is disabled:**
- No token needed! ✅
- All endpoints are public
- Perfect for local development/testing

**If auth is enabled:**
- Use `EDON_API_TOKEN` value from `.env`
- Or create tenant API key via `/billing/api-keys`
- Or use demo token if demo mode enabled

---

## For Testing

**Easiest option:** Disable auth for local testing
```env
EDON_AUTH_ENABLED=false
```

Then no token needed! ✅

---

## Next Steps

1. **Check your current config** (run the command above)
2. **Choose your approach:**
   - Local dev: Disable auth
   - Testing: Use demo token
   - Production: Create tenant API keys
