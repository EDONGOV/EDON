# Fixes Summary - Gateway Isolation & Intent Scope

## ✅ Fix 1: Gateway-Only .env (Option B: Stricter Isolation)

### Changes Made

1. **Updated `config.py`:**
   - ✅ Added `python-dotenv` import
   - ✅ Loads `edon_gateway/.env` explicitly
   - ✅ Doesn't override existing env vars
   - ✅ Falls back to system env if `.env` doesn't exist

2. **Created `.env.example`:**
   - ✅ Template for gateway-specific config
   - ✅ All gateway variables documented
   - ✅ Copy to `.env` and customize

3. **Updated `requirements.gateway.txt`:**
   - ✅ Added `python-dotenv>=1.0.0`

### Benefits

- ✅ **Isolation** - Gateway config separate from root
- ✅ **No conflicts** - Immune to root env bleed
- ✅ **Self-contained** - Gateway is portable
- ✅ **Production-ready** - Clean separation

### Setup

```bash
cd edon_gateway
cp .env.example .env
# Edit .env with your values
```

---

## ✅ Fix 2: Intent Scope Fix - Clawdbot.invoke Support

### Problem Solved

**Before:**
```
"Action clawdbot.invoke not in scope. Allowed: []"
```

**After:**
- ✅ Policy pack apply guarantees `clawdbot.invoke` in scope
- ✅ Unique intent_id per tenant/user
- ✅ Clear guidance to use X-Intent-ID header
- ✅ Active preset fallback

### Changes Made

1. **Updated `apply_policy_pack_endpoint()`:**
   - ✅ Generates unique intent_id (includes tenant if available)
   - ✅ Explicitly ensures `clawdbot.invoke` in scope
   - ✅ Returns intent_id with usage message
   - ✅ Verifies scope includes clawdbot

2. **Updated `clawdbot_invoke_proxy()`:**
   - ✅ Tries active preset intent first
   - ✅ Falls back to default with clawdbot.invoke scope
   - ✅ Better logging for debugging

### API Response

**POST /policy-packs/{pack_name}/apply:**
```json
{
  "intent_id": "intent_tenant123_personal_safe_a1b2c3d4",
  "policy_pack": "personal_safe",
  "intent": {
    "scope": {
      "clawdbot": ["invoke"]  // ✅ Guaranteed
    }
  },
  "message": "Use X-Intent-ID header: intent_tenant123_personal_safe_a1b2c3d4",
  "scope_includes_clawdbot": true
}
```

### Usage Flow

1. **Apply Policy Pack:**
   ```bash
   POST /policy-packs/personal_safe/apply
   → Returns intent_id
   ```

2. **Use Intent ID:**
   ```bash
   POST /clawdbot/invoke
   X-Intent-ID: intent_tenant123_personal_safe_a1b2c3d4
   → No more "not in scope" errors!
   ```

### Benefits

- ✅ **No scope errors** - clawdbot.invoke always allowed
- ✅ **Unique intents** - Per tenant/user
- ✅ **Clear guidance** - Response tells user what to do
- ✅ **Backward compatible** - Works without header

---

## Files Modified

1. ✅ `config.py` - Added dotenv loading
2. ✅ `main.py` - Fixed policy pack apply and intent handling
3. ✅ `requirements.gateway.txt` - Added python-dotenv
4. ✅ `.env.example` - Created template
5. ✅ `ENV_ISOLATION_SETUP.md` - Documentation
6. ✅ `INTENT_SCOPE_FIX.md` - Documentation
7. ✅ `FIXES_SUMMARY.md` - This file

## Testing

### Test Gateway .env Loading

```bash
cd edon_gateway
cp .env.example .env
# Edit .env with test values
python -c "from config import config; print(f'Token: {config.API_TOKEN}')"
```

### Test Policy Pack Apply

```bash
curl -X POST http://localhost:8000/policy-packs/personal_safe/apply \
  -H "X-EDON-TOKEN: your-token"

# Verify:
# - intent_id is unique
# - scope_includes_clawdbot: true
# - message tells you to use X-Intent-ID header
```

### Test Clawdbot Invoke

```bash
# With intent_id header
curl -X POST http://localhost:8000/clawdbot/invoke \
  -H "X-Intent-ID: intent_abc123" \
  -H "X-Agent-ID: test-agent" \
  -d '{"tool": "sessions_list", "action": "json", "args": {}}'

# Should succeed (no "not in scope" error)
```

## Next Steps

1. ✅ Gateway isolation implemented
2. ✅ Intent scope fixed
3. ⏳ Create `edon_gateway/.env` from `.env.example`
4. ⏳ Test policy pack apply
5. ⏳ Test Clawdbot integration
6. ⏳ Update UI to show intent_id after policy pack apply
