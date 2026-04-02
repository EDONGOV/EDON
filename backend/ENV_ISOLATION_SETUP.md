# Gateway-Only .env Setup (Option B: Stricter Isolation)

## Overview

This setup isolates gateway configuration in `edon_gateway/.env`, preventing root-level env var bleed and keeping the gateway self-contained.

## Setup Steps

### 1. Create Gateway .env File

```bash
cd edon_gateway
cp .env.example .env
```

### 2. Configure Gateway Variables

Edit `edon_gateway/.env`:

```env
# Required for production
EDON_AUTH_ENABLED=true
EDON_API_TOKEN=your-secure-token-here

# Database
EDON_DATABASE_PATH=edon_gateway.db

# Other gateway-specific vars...
```

### 3. How It Works

**Before (root .env):**
- Root `.env` could affect gateway
- Risk of env var conflicts
- Harder to isolate gateway config

**After (gateway .env):**
- Gateway loads `edon_gateway/.env` explicitly
- Isolated from root-level vars
- Self-contained configuration

### 4. Code Changes

**`config.py` now loads:**
```python
from dotenv import load_dotenv

# Load gateway-specific .env file
_gateway_env_path = Path(__file__).parent / ".env"
if _gateway_env_path.exists():
    load_dotenv(_gateway_env_path, override=False)
```

**Behavior:**
- ✅ Loads `edon_gateway/.env` if it exists
- ✅ Doesn't override existing env vars (set by system/CI)
- ✅ Falls back to system env vars if `.env` doesn't exist

## Benefits

1. **Isolation** - Gateway config separate from root
2. **Cleaner** - No env var conflicts
3. **Portable** - Gateway is self-contained
4. **Production-ready** - Easy to deploy with isolated config

## Migration

**If you have root `.env`:**
1. Copy gateway vars to `edon_gateway/.env`
2. Remove gateway vars from root `.env`
3. Restart gateway

**Testing:**
```bash
# Verify gateway loads its own .env
cd edon_gateway
python -c "from config import config; print(f'Token: {config.API_TOKEN[:20]}...')"
```

## Files

- ✅ `edon_gateway/.env.example` - Template
- ✅ `edon_gateway/config.py` - Updated to load gateway .env
- ✅ `edon_gateway/ENV_ISOLATION_SETUP.md` - This file
