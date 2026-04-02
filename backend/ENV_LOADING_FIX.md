# Env Loading Fix - Gateway .env Not Loading

## Problem

Gateway was still using old token `cb3d7...` instead of loading from `edon_gateway/.env`.

## Root Cause

The `load_dotenv()` was called in `config.py`, but:
1. Config class attributes are evaluated at class definition time
2. `os.getenv()` calls happen when the class is defined, not when it's instantiated
3. So dotenv loading happened too late

## Solution

**Load .env file BEFORE importing config module:**

1. ✅ Load dotenv at the very top of `main.py` (before any config imports)
2. ✅ Use `override=True` to ensure gateway .env takes precedence
3. ✅ Also keep loading in `config.py` as backup
4. ✅ Add print statements to verify loading

## Changes Made

### `main.py` - Load .env FIRST

```python
# IMPORTANT: Load gateway .env FIRST before any other imports
from pathlib import Path
from dotenv import load_dotenv

_gateway_env_path = Path(__file__).parent / ".env"
if _gateway_env_path.exists():
    load_dotenv(_gateway_env_path, override=True)
    print(f"✅ Loaded gateway .env from: {_gateway_env_path}")
else:
    print(f"⚠️  Gateway .env not found at: {_gateway_env_path}")

# NOW import config (which reads env vars)
from .config import config
```

### `config.py` - Backup Loading

```python
# Also load here as backup (in case main.py import order changes)
_gateway_env_path = Path(__file__).parent / ".env"
if _gateway_env_path.exists():
    load_dotenv(_gateway_env_path, override=True)
```

## Verification

**Check if .env is loading:**

1. Create `edon_gateway/.env`:
   ```env
   EDON_API_TOKEN=new-token-12345
   EDON_AUTH_ENABLED=true
   ```

2. Start gateway:
   ```bash
   python -m edon_gateway.main
   ```

3. Look for startup message:
   ```
   ✅ Loaded gateway .env from: /path/to/edon_gateway/.env
   ```

4. Verify token:
   ```python
   from edon_gateway.config import config
   print(config.API_TOKEN)  # Should show: new-token-12345
   ```

## Why This Works

**Before:**
```
1. Import config.py
2. Config class defined → reads os.getenv() → gets old token
3. load_dotenv() called → too late!
```

**After:**
```
1. load_dotenv() called FIRST → loads edon_gateway/.env
2. Import config.py
3. Config class defined → reads os.getenv() → gets NEW token ✅
```

## Testing

**Test the fix:**

```bash
# 1. Create .env with new token
cd edon_gateway
echo "EDON_API_TOKEN=test-new-token-999" > .env

# 2. Start gateway
python -m edon_gateway.main

# 3. Check startup output
# Should see: ✅ Loaded gateway .env from: ...

# 4. Verify token changed
# Check logs/config - should use test-new-token-999
```

## Files Modified

1. ✅ `main.py` - Load .env at very top
2. ✅ `config.py` - Backup loading (already there)
3. ✅ Added print statements for verification

## Next Steps

1. ✅ Fix applied
2. ⏳ Create `edon_gateway/.env` file
3. ⏳ Restart gateway
4. ⏳ Verify new token is loaded
