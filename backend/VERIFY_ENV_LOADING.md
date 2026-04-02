# Verify .env Loading

## Quick Test

**1. Create gateway .env:**
```bash
cd edon_gateway
echo "EDON_API_TOKEN=test-new-token-12345" > .env
```

**2. Start gateway:**
```bash
python -m edon_gateway.main
```

**3. Check startup output:**
```
✅ Loaded gateway .env from: /path/to/edon_gateway/.env
✅ Config verified: EDON_API_TOKEN loaded from .env (length: 20)
```

**4. Verify token in code:**
```python
from edon_gateway.config import config
print(config.API_TOKEN)  # Should be: test-new-token-12345
```

## If Still Using Old Token

**Check:**
1. Is `.env` file in `edon_gateway/` directory?
2. Does it contain `EDON_API_TOKEN=...`?
3. Are there system env vars set that override it?
4. Did you restart the gateway after creating .env?

**Debug:**
```python
import os
from pathlib import Path

# Check if file exists
env_path = Path("edon_gateway/.env")
print(f"File exists: {env_path.exists()}")

# Check what's in file
if env_path.exists():
    print(env_path.read_text())

# Check what Python sees
print(f"EDON_API_TOKEN from os.getenv: {os.getenv('EDON_API_TOKEN', 'NOT SET')}")
```

## Expected Behavior

**With .env file:**
- ✅ Startup shows: "✅ Loaded gateway .env from: ..."
- ✅ Config shows: "✅ Config verified: EDON_API_TOKEN loaded"
- ✅ Token matches what's in .env file

**Without .env file:**
- ⚠️ Startup shows: "⚠️ Gateway .env not found"
- ⚠️ Uses system env vars or defaults
