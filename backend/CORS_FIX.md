# CORS Configuration Fix

## Issue

The Agent UI running on `http://localhost:8080` was blocked by CORS policy when trying to connect to EDON Gateway on `http://localhost:8000`.

## Solution

Updated CORS configuration to include `http://localhost:8080` in allowed origins.

### Changes Made

1. **Updated `main.py`**: Added `http://localhost:8080` to default development origins when CORS wildcard is detected
2. **Updated `.env`**: Changed from wildcard `*` to explicit list including port 8080

### Configuration

**For Local Development:**

In `.env`:
```bash
EDON_CORS_ORIGINS=http://localhost:8080,http://localhost:5173,http://localhost:3000,http://127.0.0.1:8080
```

**For Production:**

Set specific production domains:
```bash
EDON_CORS_ORIGINS=https://console.edon.ai,https://app.edon.ai
```

### Restart Required

After updating `.env`, **restart EDON Gateway** for changes to take effect:

```bash
# Stop the gateway
# Then restart
python -m uvicorn edon_gateway.main:app --host 127.0.0.1 --port 8000
```

### Verification

After restart, the Agent UI should be able to connect without CORS errors. Check browser console - CORS errors should be gone.

## Default Development Origins

When `EDON_CORS_ORIGINS=*` is detected, the gateway now includes:
- `http://localhost:8080` (Agent UI)
- `http://localhost:5173` (Vite default)
- `http://localhost:3000` (Common React port)
- `http://127.0.0.1:8080` (IPv4 localhost)
- `http://localhost:5174` (Vite fallback)
