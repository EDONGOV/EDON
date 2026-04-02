# Quick Start: Clawdbot Integration Testing

**Fast setup guide for testing Clawdbot integration with EDON Gateway.**

---

## Prerequisites

1. **EDON Gateway running** on `http://127.0.0.1:8000`
2. **Clawdbot Gateway running** on `http://127.0.0.1:18789` (optional - some tests will skip if not available)
3. **Authentication tokens** configured

---

## Step 1: Check EDON Gateway Authentication

EDON Gateway may have authentication enabled. Check and configure:

### Option A: Authentication Disabled (Development)

If `EDON_AUTH_ENABLED=false` (default), no token needed:

```powershell
# No token needed - auth is disabled
python edon_gateway/test_clawdbot_integration.py
```

### Option B: Authentication Enabled (Production)

If you're using `start_production_gateway.ps1`, it sets `EDON_API_TOKEN=your-secret-token` by default.

**Quick Fix - Use the default token:**
```powershell
# The test defaults to "your-secret-token" which matches the production script
python edon_gateway/test_clawdbot_integration.py
```

**Or set your own token:**
```powershell
# Set the token that matches your EDON Gateway configuration
$env:EDON_API_TOKEN = "your-actual-token-here"
$env:EDON_GATEWAY_TOKEN = $env:EDON_API_TOKEN  # Use same token

# Run tests
python edon_gateway/test_clawdbot_integration.py
```

**How to find your token:**
- Check the output when you start EDON Gateway - it shows `EDON_API_TOKEN=...`
- If using `start_production_gateway.ps1`, it defaults to `your-secret-token` unless you set `EDON_API_TOKEN` before running it
- Or check your gateway startup script/configuration

---

## Step 2: Set Up Clawdbot Credentials (Required in Production Mode)

If your EDON Gateway is running with `EDON_CREDENTIALS_STRICT=true` (production mode), you must set up credentials in the database before running tests.

### Option A: Use Setup Script (Recommended)

```powershell
# Set your tokens
$env:EDON_GATEWAY_TOKEN = "your-secret-token"
$env:CLAWDBOT_GATEWAY_TOKEN = "your-clawdbot-token"  # Optional

# Run setup script
.\edon_gateway\setup_clawdbot_credentials.ps1
```

### Option B: Manual Setup via API

```powershell
$headers = @{
    "X-EDON-TOKEN" = "your-secret-token"
    "Content-Type" = "application/json"
}

$body = @{
    credential_id = "clawdbot-gateway-001"
    tool_name = "clawdbot"
    credential_type = "gateway"
    credential_data = @{
        gateway_url = "http://127.0.0.1:18789"
        gateway_token = "your-clawdbot-token"
    }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Uri "http://127.0.0.1:8000/credentials/set" `
    -Method Post `
    -Headers $headers `
    -Body $body
```

**Note:** The test script will attempt to set credentials automatically, but it's better to set them up beforehand.

---

## Step 3: Run Tests

### Quick Test Script (Recommended)

```powershell
# Set tokens
$env:EDON_GATEWAY_TOKEN = "your-token"  # Or use EDON_API_TOKEN if auth enabled
$env:CLAWDBOT_GATEWAY_TOKEN = "your-clawdbot-token"  # Optional

# Run quick test
.\edon_gateway\quick_test_clawdbot.ps1
```

### Python Test Script

```powershell
# Set tokens
$env:EDON_GATEWAY_TOKEN = "your-token"  # Or use EDON_API_TOKEN if auth enabled
$env:CLAWDBOT_GATEWAY_TOKEN = "your-clawdbot-token"  # Optional

# Run tests
python edon_gateway/test_clawdbot_integration.py
```

### With Pytest

```powershell
# Set tokens
$env:EDON_GATEWAY_TOKEN = "your-token"
$env:CLAWDBOT_GATEWAY_TOKEN = "your-clawdbot-token"

# Run with pytest
pytest edon_gateway/test_clawdbot_integration.py -v
```

---

## Troubleshooting

### "Invalid authentication token"

**Problem:** EDON Gateway has authentication enabled but token doesn't match.

**Solution:**
1. Check if `EDON_AUTH_ENABLED=true` in your gateway environment
2. Find the correct `EDON_API_TOKEN` value
3. Set it in your test environment:
   ```powershell
   $env:EDON_API_TOKEN = "your-actual-token"
   $env:EDON_GATEWAY_TOKEN = $env:EDON_API_TOKEN
   ```

### "Clawdbot Gateway not accessible"

**Problem:** Clawdbot Gateway is not running or not accessible.

**Solution:**
1. Start Clawdbot Gateway on port 18789
2. Or skip Clawdbot-specific tests (they will be skipped automatically)

### "EDON Gateway not accessible"

**Problem:** EDON Gateway is not running.

**Solution:**
1. Start EDON Gateway:
   ```powershell
   python -m edon_gateway.main
   ```
2. Or check if it's running on a different port and update `EDON_GATEWAY_URL`

---

## Environment Variables Summary

| Variable | Description | Required |
|----------|-------------|----------|
| `EDON_GATEWAY_URL` | EDON Gateway URL | No (default: http://127.0.0.1:8000) |
| `EDON_GATEWAY_TOKEN` | Token for EDON Gateway | Yes (if auth enabled) |
| `EDON_API_TOKEN` | Same as EDON_GATEWAY_TOKEN (auto-used if set) | Yes (if auth enabled) |
| `CLAWDBOT_GATEWAY_URL` | Clawdbot Gateway URL | No (default: http://127.0.0.1:18789) |
| `CLAWDBOT_GATEWAY_TOKEN` | Token for Clawdbot Gateway | Optional |

---

## Quick Command Reference

**PowerShell:**
```powershell
# Set tokens
$env:EDON_GATEWAY_TOKEN = "your-token"
$env:CLAWDBOT_GATEWAY_TOKEN = "your-clawdbot-token"

# Run quick test
.\edon_gateway\quick_test_clawdbot.ps1

# Or run Python tests
python edon_gateway/test_clawdbot_integration.py
```

**Bash:**
```bash
# Set tokens
export EDON_GATEWAY_TOKEN="your-token"
export CLAWDBOT_GATEWAY_TOKEN="your-clawdbot-token"

# Run quick test
./edon_gateway/quick_test_clawdbot.sh

# Or run Python tests
python edon_gateway/test_clawdbot_integration.py
```

---

*Last Updated: 2025-01-27*
