# Env Loading Fix - Complete Implementation

## ✅ Root Cause Fixed

**Problem:** Config class attributes were evaluated at class definition time, before .env was loaded.

**Solution:** 
1. ✅ Load dotenv at VERY TOP of config.py (before class definition)
2. ✅ Changed Config to use `__init__` + properties (lazy loading)
3. ✅ Removed all dotenv loading from main.py
4. ✅ Fixed auth.py to use config instead of direct os.getenv()
5. ✅ Added guardrail to fail fast if token missing

## Changes Made

### 1. `config.py` - Complete Rewrite ✅

**Before (BROKEN):**
```python
class Config:
    API_TOKEN: str = os.getenv("EDON_API_TOKEN")  # ❌ Evaluated at class definition time
```

**After (FIXED):**
```python
# Load .env FIRST, before anything else
from dotenv import load_dotenv
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

# Guardrail: fail fast if token missing
if os.getenv("EDON_AUTH_ENABLED", "true").lower() == "true":
    token = os.getenv("EDON_API_TOKEN")
    if not token or token == "your-secret-token":
        raise RuntimeError("EDON_API_TOKEN missing — gateway cannot start")

class Config:
    def __init__(self):
        # ✅ Reads env vars at instance creation time (after .env loaded)
        self._API_TOKEN = os.getenv("EDON_API_TOKEN", "your-secret-token")
    
    @property
    def API_TOKEN(self) -> str:
        return self._API_TOKEN  # ✅ Lazy access via property
```

### 2. `main.py` - Removed dotenv loading ✅

**Before:**
```python
# Load dotenv here
load_dotenv(...)
from .config import config
```

**After:**
```python
# NOTE: dotenv loading is now handled in config.py (at the very top)
# Do NOT load dotenv here
from .config import config  # config.py loads .env before Config class is defined
```

### 3. `middleware/auth.py` - Use config instead of os.getenv() ✅

**Before:**
```python
EDON_AUTH_ENABLED = os.getenv("EDON_AUTH_ENABLED")  # ❌ Module-level, reads before .env
EDON_API_TOKEN = os.getenv("EDON_API_TOKEN")  # ❌ Module-level
```

**After:**
```python
# Use config (loaded from .env) instead of module-level env vars
if not config.AUTH_ENABLED:  # ✅ Reads from config instance
    ...
if token == config.API_TOKEN:  # ✅ Reads from config instance
    ...
```

## Execution Order (Fixed)

**Correct Order:**
```
1. config.py imports → dotenv loads edon_gateway/.env FIRST
2. Guardrail checks token exists
3. Config class defined (but doesn't read env vars yet)
4. Config instance created → __init__ reads env vars (from .env) ✅
5. Properties return values from instance ✅
```

## Testing

**1. Create .env:**
```bash
cd edon_gateway
echo "EDON_API_TOKEN=NEW_GATEWAY_TOKEN_12345" > .env
```

**2. Start gateway:**
```bash
python -m edon_gateway.main
```

**3. Expected:**
- ✅ Gateway starts successfully
- ✅ Uses `NEW_GATEWAY_TOKEN_12345` from .env
- ✅ Old token `cb3d7...` rejected

**4. Test with old token (should fail):**
```bash
curl -H "X-EDON-TOKEN: cb3d7..." http://localhost:8000/stats
# Should return: 401 Invalid token
```

**5. Test with new token (should work):**
```bash
curl -H "X-EDON-TOKEN: NEW_GATEWAY_TOKEN_12345" http://localhost:8000/stats
# Should return: 200 OK with metrics
```

## Why This Works

1. **dotenv loads FIRST** - Before any class definitions
2. **Config uses __init__** - Reads env vars at instance creation, not class definition
3. **Properties** - Lazy access, always reads from instance
4. **No module-level reads** - auth.py uses config, not os.getenv()
5. **Guardrail** - Fails fast if token missing

## Files Modified

1. ✅ `config.py` - Complete rewrite with lazy loading
2. ✅ `main.py` - Removed dotenv loading
3. ✅ `middleware/auth.py` - Use config instead of os.getenv()

## Verification Checklist

- [ ] Create `edon_gateway/.env` with `EDON_API_TOKEN=NEW_GATEWAY_TOKEN_12345`
- [ ] Restart gateway
- [ ] Test with old token → Should fail (401)
- [ ] Test with new token → Should work (200)
- [ ] Check startup logs → Should show token loaded

## Next Steps

1. ✅ Fix implemented
2. ⏳ Create `edon_gateway/.env` file
3. ⏳ Restart gateway
4. ⏳ Verify new token works
