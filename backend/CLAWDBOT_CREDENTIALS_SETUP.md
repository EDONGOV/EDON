# Clawdbot Credentials Setup Guide

## Overview

EDON Gateway can store Clawdbot Gateway credentials in the database (recommended for production) or use environment variables (development mode).

## Method 1: Database Storage (Recommended for Production)

### Step 1: Set Credentials via API

Use the provided PowerShell script:

```powershell
.\set_clawdbot_credentials.ps1 `
  -EDON_TOKEN "NEW_GATEWAY_TOKEN_12345" `
  -CLAWDBOT_GATEWAY_URL "http://127.0.0.1:18789" `
  -CLAWDBOT_GATEWAY_TOKEN "your-clawdbot-token-here"
```

**Or manually:**

```powershell
$edonToken = "NEW_GATEWAY_TOKEN_12345"

$body = @{
  credential_id   = "clawdbot_gateway_token"
  tool_name       = "clawdbot"              # Must be "clawdbot"
  credential_type  = "gateway"
  credential_data = @{
    gateway_url   = "http://127.0.0.1:18789"
    gateway_token = "PASTE_YOUR_CLAWDBOT_GATEWAY_TOKEN_HERE"
  }
  encrypted       = $true
}

Invoke-RestMethod -Method Post -Uri "http://localhost:8000/credentials/set" `
  -Headers @{ "X-EDON-TOKEN" = $edonToken; "Content-Type"="application/json" } `
  -Body ($body | ConvertTo-Json -Depth 10)
```

### Step 2: How It Works

The `ClawdbotConnector` automatically:
1. Tries to load credential `clawdbot_gateway_token` from database
2. Falls back to environment variables if not found (dev mode)
3. Raises error if `EDON_CREDENTIALS_STRICT=true` and credential not found

### Step 3: Enable Strict Mode (Production)

Set in `.env`:
```bash
EDON_CREDENTIALS_STRICT=true
```

This ensures credentials **must** be in the database (no env var fallback).

## Method 2: Environment Variables (Development)

For development/testing, you can use environment variables:

```powershell
$env:CLAWDBOT_GATEWAY_URL = "http://127.0.0.1:18789"
$env:CLAWDBOT_GATEWAY_TOKEN = "your-token"
```

Or in `.env`:
```bash
CLAWDBOT_GATEWAY_URL=http://127.0.0.1:18789
CLAWDBOT_GATEWAY_TOKEN=your-token
```

## Credential Format

The credential must match what `ClawdbotConnector` expects:

```json
{
  "credential_id": "clawdbot_gateway_token",
  "tool_name": "clawdbot",
  "credential_type": "gateway",
  "credential_data": {
    "gateway_url": "http://127.0.0.1:18789",
    "gateway_token": "your-token"
  },
  "encrypted": true
}
```

**Important:**
- `tool_name` must be `"clawdbot"` (not "clawdbot_gateway")
- `credential_data` must have `gateway_url` and `gateway_token` keys
- `credential_id` defaults to `"clawdbot_gateway_token"` (can be overridden via `EDON_CLAWDBOT_CREDENTIAL_ID` env var)

## Verification

Test that credentials are loaded:

```bash
# Test Clawdbot invoke (should use database credential)
curl -X POST http://localhost:8000/clawdbot/invoke \
  -H "X-EDON-TOKEN: your-token" \
  -H "X-Intent-ID: intent_clawdbot_safe_abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "sessions_list",
    "action": "json",
    "args": {}
  }'
```

If credentials are correct, you should get a successful response from Clawdbot Gateway.

## Troubleshooting

### Error: "Credential 'clawdbot_gateway_token' not found"

**Solution:**
1. Run `.\set_clawdbot_credentials.ps1` to set credentials
2. Or set `EDON_CREDENTIALS_STRICT=false` to allow env var fallback

### Error: "Clawdbot Gateway token not configured"

**Solution:**
- Check that `credential_data` has `gateway_token` key (not `token`)
- Verify credential was saved: Check database or re-run setup script

### Error: "HTTP 401 Unauthorized" from Clawdbot Gateway

**Solution:**
- Verify `gateway_token` is correct
- Check that Clawdbot Gateway is running and accessible at `gateway_url`

## Security Notes

1. **Encryption:** Credentials are stored encrypted in the database (`encrypted: true`)
2. **No Readback:** Credentials cannot be read back via API (security feature)
3. **Strict Mode:** Use `EDON_CREDENTIALS_STRICT=true` in production to prevent env var fallback
4. **Token Hardening:** Tokens are never exposed to agents/users (only used internally by EDON)

## Files Modified

- `edon_gateway/connectors/clawdbot_connector.py` - Updated to use default credential_id
- `edon_gateway/set_clawdbot_credentials.ps1` - Setup script with correct format
