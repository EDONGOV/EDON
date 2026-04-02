# Executor Credential Fix

## Problem

The executor was using a global `clawdbot_connector` instance that was initialized at module load time. This meant:
1. Credentials were loaded once at startup
2. If credentials weren't in DB yet, it would fail or fall back to env vars
3. No way to reload credentials without restarting the server

## Solution

### Temporary Fix (Quick Unblock)

Set `CLAWDBOT_GATEWAY_TOKEN` in `.env` and restart EDON:

```bash
# In edon_gateway/.env
CLAWDBOT_GATEWAY_TOKEN=your-clawdbot-gateway-token
```

This allows the connector to fall back to environment variables if DB credential is not found.

### Permanent Fix (Production Ready)

Updated the executor to:
1. **Load credential from DB on each request** - Creates a new connector instance per request
2. **Use config for credential_id** - Reads `EDON_CLAWDBOT_CREDENTIAL_ID` from config (default: `"clawdbot_gateway"`)
3. **Fail closed in production** - If `EDON_CREDENTIALS_STRICT=true` and credential not found, raises error

## Changes Made

### 1. Added `CLAWDBOT_CREDENTIAL_ID` to Config

**File:** `edon_gateway/config.py`

```python
# In __init__:
self._CLAWDBOT_CREDENTIAL_ID = os.getenv("EDON_CLAWDBOT_CREDENTIAL_ID", "clawdbot_gateway")

# Added property:
@property
def CLAWDBOT_CREDENTIAL_ID(self) -> str:
    return self._CLAWDBOT_CREDENTIAL_ID
```

### 2. Updated Executor Functions

**File:** `edon_gateway/main.py`

**Before:**
```python
result = clawdbot_connector.invoke(...)  # Uses global instance
```

**After:**
```python
from .connectors.clawdbot_connector import ClawdbotConnector

# Get credential_id from config (loads from DB)
credential_id = config.CLAWDBOT_CREDENTIAL_ID

# Create connector instance with credential_id (loads from DB)
connector = ClawdbotConnector(credential_id=credential_id)

result = connector.invoke(...)
```

**Updated in two places:**
1. `clawdbot_invoke_proxy()` - `/clawdbot/invoke` endpoint
2. `_execute_tool()` - `/execute` endpoint

### 3. Updated `.env` Default

**File:** `edon_gateway/.env`

Changed default credential_id to match the correct schema:
```bash
EDON_CLAWDBOT_CREDENTIAL_ID=clawdbot_gateway  # Was: clawdbot_gateway_token
```

## How It Works Now

1. **Request comes in** → `/clawdbot/invoke` or `/execute`
2. **Executor creates connector** → `ClawdbotConnector(credential_id=config.CLAWDBOT_CREDENTIAL_ID)`
3. **Connector loads credentials**:
   - First: Tries to load from database using `credential_id`
   - If not found and `EDON_CREDENTIALS_STRICT=false`: Falls back to env vars
   - If not found and `EDON_CREDENTIALS_STRICT=true`: Raises error (fail closed)
4. **Connector executes** → Calls Clawdbot Gateway with loaded credentials

## Benefits

✅ **Fresh credentials on each request** - No stale credentials  
✅ **DB-first approach** - Credentials stored securely in database  
✅ **Fail-closed in production** - `EDON_CREDENTIALS_STRICT=true` ensures credentials must be in DB  
✅ **Backward compatible** - Still supports env var fallback for development  

## Usage

### Store Credentials in DB

```powershell
.\set_clawdbot_credentials.ps1 `
    -EDON_TOKEN "NEW_GATEWAY_TOKEN_12345" `
    -CLAWDBOT_GATEWAY_TOKEN "your-clawdbot-token"
```

This stores credentials with `credential_id="clawdbot_gateway"` (matches config default).

### Verify It Works

```powershell
# Should use DB credential (if EDON_CREDENTIALS_STRICT=true)
# Or fall back to env var (if EDON_CREDENTIALS_STRICT=false)
Invoke-RestMethod -Method Post `
    -Uri "http://localhost:8000/clawdbot/invoke" `
    -Headers @{
        "X-EDON-TOKEN" = "NEW_GATEWAY_TOKEN_12345"
        "X-Intent-ID" = "<intent_id>"
    } `
    -Body (@{ tool = "sessions_list"; action = "json"; args = @{} } | ConvertTo-Json)
```

## Configuration

### Development Mode (Env Var Fallback)

```bash
EDON_CREDENTIALS_STRICT=false
CLAWDBOT_GATEWAY_TOKEN=your-token-here
```

### Production Mode (DB Only)

```bash
EDON_CREDENTIALS_STRICT=true
# CLAWDBOT_GATEWAY_TOKEN not needed (will fail if not in DB)
```

## Files Modified

1. `edon_gateway/config.py` - Added `CLAWDBOT_CREDENTIAL_ID` property
2. `edon_gateway/main.py` - Updated executor to create connector per request
3. `edon_gateway/.env` - Updated default credential_id
