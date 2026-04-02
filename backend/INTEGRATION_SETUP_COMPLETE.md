# EDON ↔ Clawdbot Integration Setup Guide

## Root Cause Analysis

The integration issues were caused by:
1. **Auth schema mismatch** - EDON uses DB-backed API keys or `EDON_API_TOKEN` (not `EDON_TOKEN`)
2. **Credential schema mismatch** - `/credentials/set` expects `base_url` + `token` (not `gateway_url` + `gateway_token`)

## Correct Setup Flow

### Step 1: Configure EDON Gateway `.env`

```bash
# Authentication
EDON_AUTH_ENABLED=true
EDON_API_TOKEN=<admin-token>  # Use this for admin operations

# Optional: Demo mode (bypasses subscription checks for local dev)
EDON_DEMO_MODE=true

# Optional: Strict credentials mode (requires DB credentials, no env fallback)
EDON_CREDENTIALS_STRICT=false  # Set to true in production
```

### Step 2: Restart EDON Gateway

```powershell
# Stop existing instance
# Then start:
python -m uvicorn edon_gateway.main:app --host 127.0.0.1 --port 8000
```

### Step 3: Get Tenant API Key (Optional)

For multi-tenant deployments, use `/demo/credentials` to mint a tenant API key:

```powershell
$headers = @{
    "X-EDON-TOKEN" = "<EDON_API_TOKEN from .env>"
    "Content-Type" = "application/json"
}

$body = @{
    tenant_id = "test-tenant"
    plan = "starter"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "http://localhost:8000/demo/credentials" `
    -Headers $headers `
    -Body $body
```

**Response:**
```json
{
  "api_key": "tenant-api-key-here",
  "tenant_id": "test-tenant"
}
```

### Step 4: Apply Clawdbot Safe Policy Pack

```powershell
$headers = @{
    "X-EDON-TOKEN" = "<EDON_API_TOKEN or tenant API key>"
    "Content-Type" = "application/json"
}

$response = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/policy-packs/clawdbot_safe/apply" `
    -Headers $headers

# Save the intent_id from response
$intentId = $response.intent_id
Write-Host "Intent ID: $intentId"
```

**Response:**
```json
{
  "intent_id": "intent_clawdbot_safe_abc123",
  "policy_pack": "clawdbot_safe",
  "message": "Policy pack applied. Use X-Intent-ID header: intent_clawdbot_safe_abc123"
}
```

### Step 5: Store Clawdbot Gateway Credentials

**Correct Schema:**
```json
{
  "credential_id": "clawdbot_gateway",
  "tool_name": "clawdbot",
  "credential_type": "gateway",
  "credential_data": {
    "base_url": "http://127.0.0.1:18789",
    "token": "<CLAWDBOT_GATEWAY_TOKEN>"
  },
  "encrypted": true
}
```

**Using PowerShell script:**
```powershell
.\set_clawdbot_credentials.ps1 `
    -EDON_TOKEN "<EDON_API_TOKEN or tenant API key>" `
    -CLAWDBOT_GATEWAY_URL "http://127.0.0.1:18789" `
    -CLAWDBOT_GATEWAY_TOKEN "<your-clawdbot-gateway-token>"
```

**Or manually:**
```powershell
$headers = @{
    "X-EDON-TOKEN" = "<EDON_API_TOKEN or tenant API key>"
    "Content-Type" = "application/json"
}

$body = @{
    credential_id   = "clawdbot_gateway"
    tool_name       = "clawdbot"
    credential_type = "gateway"
    credential_data = @{
        base_url = "http://127.0.0.1:18789"
        token    = "<CLAWDBOT_GATEWAY_TOKEN>"
    }
    encrypted       = $true
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Method Post -Uri "http://localhost:8000/credentials/set" `
    -Headers $headers `
    -Body $body
```

### Step 6: Invoke Clawdbot via EDON

```powershell
$headers = @{
    "X-EDON-TOKEN" = "<tenant API key or EDON_API_TOKEN>"
    "X-Intent-ID"  = "<intent_id from Step 4>"
    "Content-Type" = "application/json"
}

$body = @{
    tool   = "sessions_list"
    action = "json"
    args   = @{}
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "http://localhost:8000/clawdbot/invoke" `
    -Headers $headers `
    -Body $body
```

## Authentication Methods

### Method 1: EDON_API_TOKEN (Admin/Legacy)

Set in `.env`:
```bash
EDON_API_TOKEN=your-admin-token
```

Use in requests:
```bash
X-EDON-TOKEN: your-admin-token
```

### Method 2: Database API Keys (Multi-tenant)

Created via `/demo/credentials` or `/api-keys/create`.

Use in requests:
```bash
X-EDON-TOKEN: tenant-api-key-from-database
```

**EDON validates tokens in this order:**
1. Database API keys (SHA-256 hash lookup)
2. Fallback: `EDON_API_TOKEN` from `.env`

## Credential Schema

**Correct schema (current):**
```json
{
  "credential_id": "clawdbot_gateway",
  "tool_name": "clawdbot",
  "credential_type": "gateway",
  "credential_data": {
    "base_url": "http://127.0.0.1:18789",
    "token": "<CLAWDBOT_GATEWAY_TOKEN>"
  }
}
```

**Legacy schema (still supported for backward compatibility):**
```json
{
  "credential_data": {
    "gateway_url": "http://127.0.0.1:18789",
    "gateway_token": "<CLAWDBOT_GATEWAY_TOKEN>"
  }
}
```

The connector supports both schemas automatically.

## Clawdbot Side Setup

### Clawdbot Gateway

1. **Gateway running** on `127.0.0.1:18789`
2. **Token auth** supported via `--auth token --token <TOKEN>`
3. **No daemon issues** - Scheduled Task warnings are irrelevant to connectivity

### Clawdbot Tool Proxy

The tool proxy (`tool-proxy.js`) has been patched to forward `X-EDON-TOKEN`:

```javascript
headers: {
  'Content-Type': 'application/json',
  'Content-Length': Buffer.byteLength(payload),
  ...(process.env.TOOLS_PROXY_TOKEN ? { 'X-EDON-TOKEN': process.env.TOOLS_PROXY_TOKEN } : {}),
}
```

**Set environment variable:**
```bash
export TOOLS_PROXY_TOKEN="<EDON_API_TOKEN or tenant API key>"
```

## Verification Checklist

- [ ] EDON Gateway running on port 8000
- [ ] `.env` has `EDON_API_TOKEN` set
- [ ] `EDON_AUTH_ENABLED=true` in `.env`
- [ ] Clawdbot Gateway running on `127.0.0.1:18789`
- [ ] Credentials stored via `/credentials/set` with correct schema
- [ ] Policy pack applied (`clawdbot_safe`) → got `intent_id`
- [ ] Test request includes:
  - `X-EDON-TOKEN` header (valid token)
  - `X-Intent-ID` header (from policy pack)
  - Correct request body

## Troubleshooting

### Error: "Missing authentication token"

**Solution:** Add `X-EDON-TOKEN` header with valid `EDON_API_TOKEN` or tenant API key.

### Error: "Invalid authentication token"

**Solution:**
1. Verify `EDON_API_TOKEN` in `.env` matches the token you're using
2. For tenant API keys, verify the key exists in database
3. Check for typos or extra spaces in token

### Error: "Credential 'clawdbot_gateway' not found"

**Solution:**
1. Run `/credentials/set` with correct schema (`base_url` + `token`)
2. Verify `credential_id` is `"clawdbot_gateway"` (not `"clawdbot_gateway_token"`)
3. Set `EDON_CREDENTIALS_STRICT=false` to allow env var fallback (dev mode)

### Error: "Tool not in scope"

**Solution:**
1. Apply `clawdbot_safe` policy pack
2. Use the returned `intent_id` in `X-Intent-ID` header
3. Verify the tool (e.g., `sessions_list`) is in the pack's allowed list

## Files Updated

1. **`edon_gateway/connectors/clawdbot_connector.py`**
   - Supports both credential schemas (`base_url`/`token` and `gateway_url`/`gateway_token`)
   - Default credential_id changed to `"clawdbot_gateway"`

2. **`edon_gateway/set_clawdbot_credentials.ps1`**
   - Updated to use correct schema (`base_url` + `token`)
   - Credential ID changed to `"clawdbot_gateway"`

3. **`clawdbot/dist/agents/tool-proxy.js`** (patched)
   - Forwards `X-EDON-TOKEN` header from `TOOLS_PROXY_TOKEN` env var

## Net Result

✅ **EDON → Clawdbot proxy works** once auth source + credential schema are aligned.

The integration is now properly configured with:
- Correct authentication (DB API keys or `EDON_API_TOKEN`)
- Correct credential schema (`base_url` + `token`)
- Policy pack applied with `intent_id`
- Token forwarding from Clawdbot tool proxy
