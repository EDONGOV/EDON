# Production Mode Configuration

## Overview

The EDON Agent UI now defaults to **production mode** (mock mode disabled) for production readiness.

## Changes Made

### 1. Default Behavior
- **Before**: Mock mode defaulted to `true` (development mode)
- **After**: Mock mode defaults to `false` (production mode)
- Mock mode badge only shows when explicitly enabled

### 2. Auto-Detection
- UI automatically detects when EDON Gateway is reachable
- Mock mode is automatically disabled when gateway connection succeeds
- Connection test in Settings page disables mock mode on success

### 3. Environment Variables
- `VITE_EDON_GATEWAY_URL`: Set gateway URL for production builds
- `VITE_EDON_MOCK_MODE`: Override mock mode (default: false)

## Configuration

### For Development

**Option 1: Enable mock mode manually**
```javascript
// Browser console
localStorage.setItem('edon_mock_mode', 'true');
location.reload();
```

**Option 2: Use Settings page**
- Go to `/settings`
- Toggle "Mock Mode" switch ON

### For Production

**Option 1: Environment Variables**
```bash
# .env or .env.production
VITE_EDON_GATEWAY_URL=https://your-gateway-url.com
VITE_EDON_MOCK_MODE=false
```

**Option 2: Settings Page**
- Go to `/settings`
- Enter Gateway URL and API token
- Click "Test Connection"
- Mock mode will be automatically disabled

## Verification

**Check if mock mode is enabled:**
- Look for "Mock Mode" badge in top navigation
- If badge is visible → mock mode is ON
- If badge is NOT visible → production mode (connected to gateway)

**Check connection status:**
- Look for "Connected" badge in top navigation
- Green badge = connected to EDON Gateway
- Red badge = disconnected

## Migration

If you have existing localStorage settings:
1. Clear old mock mode setting: `localStorage.removeItem('edon_mock_mode')`
2. Reload page → defaults to production mode
3. Configure gateway URL in Settings if needed

## Benefits

✅ **Production Ready**: Defaults to connecting to real gateway
✅ **Auto-Detection**: Automatically disables mock mode when gateway is available
✅ **Clear Status**: Mock mode badge only shows when explicitly enabled
✅ **Environment Config**: Supports production builds with env variables
