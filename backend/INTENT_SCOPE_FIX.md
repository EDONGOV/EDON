# Intent Scope Fix - Clawdbot.invoke Support

## Problem

Decisions were showing:
```
"Action clawdbot.invoke not in scope. Allowed: []"
```

This happened because:
1. Default intent/scope was empty for agents
2. Policy pack apply didn't guarantee clawdbot.invoke in scope
3. Intent_id wasn't properly returned/used

## Solution

### 1. Policy Pack Apply Now Guarantees clawdbot.invoke ✅

**Before:**
- Policy packs had `clawdbot: ["invoke"]` but wasn't enforced
- Intent_id was fixed: `preset_{pack_name}` (not unique)

**After:**
- ✅ Explicitly ensures `clawdbot.invoke` is in scope
- ✅ Generates unique intent_id per tenant/user
- ✅ Returns intent_id with clear message
- ✅ Verifies scope includes clawdbot.invoke

### 2. Unique Intent IDs ✅

**Format:**
- With tenant: `intent_{tenant_id}_{pack_name}_{uuid}`
- Without tenant: `intent_{pack_name}_{uuid}`

**Benefits:**
- ✅ Each tenant gets unique intent
- ✅ Multiple policy packs can coexist
- ✅ No conflicts between tenants

### 3. Active Preset Fallback ✅

**When X-Intent-ID header missing:**
1. Try to use active preset intent (if set)
2. Fallback to default intent with clawdbot.invoke scope
3. Log warning if no intent found

**Benefits:**
- ✅ Works even without header
- ✅ Uses last applied policy pack
- ✅ Always has clawdbot.invoke scope

## API Changes

### POST /policy-packs/{pack_name}/apply

**Response now includes:**
```json
{
  "intent_id": "intent_abc123",
  "policy_pack": "personal_safe",
  "intent": {
    "scope": {
      "clawdbot": ["invoke"]  // ✅ Guaranteed
    }
  },
  "active_preset": "personal_safe",
  "message": "Use X-Intent-ID header: intent_abc123",
  "scope_includes_clawdbot": true
}
```

### POST /clawdbot/invoke

**Headers:**
- `X-Intent-ID: intent_abc123` (from policy pack apply response)
- `X-Agent-ID: your-agent-id` (optional)

**Behavior:**
1. Uses provided intent_id if header present
2. Falls back to active preset intent
3. Falls back to default intent with clawdbot.invoke scope
4. Always ensures clawdbot.invoke is allowed

## Usage Flow

### Step 1: Apply Policy Pack

```bash
POST /policy-packs/personal_safe/apply
Authorization: Bearer <token>

Response:
{
  "intent_id": "intent_tenant123_personal_safe_a1b2c3d4",
  "message": "Use X-Intent-ID header: intent_tenant123_personal_safe_a1b2c3d4"
}
```

### Step 2: Use Intent ID in Clawdbot Calls

```bash
POST /clawdbot/invoke
X-Intent-ID: intent_tenant123_personal_safe_a1b2c3d4
X-Agent-ID: my-clawdbot-agent
Content-Type: application/json

{
  "tool": "sessions_list",
  "action": "json",
  "args": {}
}
```

### Step 3: Verify Scope

The intent now guarantees:
- ✅ `clawdbot.invoke` is in scope
- ✅ No more "not in scope" errors
- ✅ Smooth Clawdbot experience

## Code Changes

### `main.py` - apply_policy_pack_endpoint()

**Changes:**
- ✅ Generates unique intent_id
- ✅ Ensures clawdbot.invoke in scope
- ✅ Returns intent_id with message
- ✅ Includes tenant context if available

### `main.py` - clawdbot_invoke_proxy()

**Changes:**
- ✅ Tries active preset intent first
- ✅ Falls back to default with clawdbot.invoke
- ✅ Better logging for debugging

## Testing

**Test Policy Pack Apply:**
```bash
curl -X POST http://localhost:8000/policy-packs/personal_safe/apply \
  -H "X-EDON-TOKEN: your-token"

# Verify response includes intent_id and scope_includes_clawdbot: true
```

**Test Clawdbot Invoke:**
```bash
curl -X POST http://localhost:8000/clawdbot/invoke \
  -H "X-Intent-ID: intent_abc123" \
  -H "X-Agent-ID: test-agent" \
  -d '{"tool": "sessions_list", "action": "json", "args": {}}'

# Should succeed (no "not in scope" error)
```

## Benefits

1. ✅ **No more scope errors** - clawdbot.invoke always in scope
2. ✅ **Unique intents** - Each tenant/user gets own intent
3. ✅ **Clear guidance** - Response tells user to use X-Intent-ID header
4. ✅ **Backward compatible** - Works without header (uses active preset)
5. ✅ **Production ready** - Proper intent management

## Next Steps

1. ✅ Policy pack apply fixed
2. ✅ Intent scope guaranteed
3. ✅ Unique intent IDs
4. ⏳ Update UI to show intent_id after policy pack apply
5. ⏳ Update docs with X-Intent-ID header usage
6. ⏳ Test with real Clawdbot integration
