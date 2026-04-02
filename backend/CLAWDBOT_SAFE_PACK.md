# Clawdbot Safe Policy Pack

## Overview

Added a new `clawdbot_safe` policy pack specifically designed for Clawdbot operations, focusing on session management tools rather than web agent tools.

## Changes Made

### 1. New Policy Pack: `clawdbot_safe`

**Location:** `edon_gateway/policy_packs.py`

**Allowed Tools (Baseline):**
- `sessions_list` - **Minimum required** - List active sessions
- `sessions_get` - Get session details
- `sessions_create` - Create new sessions
- `sessions_update` - Update existing sessions

**Blocked Tools:**
- `sessions_delete` - **NOT in safe** - Prevents accidental session deletion
- `web_execute` - Blocked by default (as requested)
- `web_send` - Block sending operations
- `shell_execute` - Block shell commands
- `file_write` - Block file write operations
- `mass_outbound` - Block mass operations
- `credential_operations` - Block credential changes

**Risk Level:** LOW
**Audit Level:** Standard

### 2. Updated Apply Endpoint

**Location:** `edon_gateway/main.py` - `apply_policy_pack_endpoint()`

**Enhancements:**
- Ensures `clawdbot: ["invoke"]` is always in scope (already existed)
- Validates constraints for Clawdbot-specific packs
- Explicitly ensures `web_execute` is blocked for `clawdbot_safe` pack
- Updated docstring to include `clawdbot_safe` in available packs

### 3. Updated Registry

**Location:** `edon_gateway/policy_packs.py`

- Added `clawdbot_safe` to `POLICY_PACKS` registry
- Updated `get_policy_pack()` docstring to include new pack

## Usage

### Apply the Pack

```bash
curl -X POST http://localhost:8000/policy-packs/clawdbot_safe/apply \
  -H "X-EDON-TOKEN: your-token" \
  -H "Content-Type: application/json"
```

**Response:**
```json
{
  "intent_id": "intent_clawdbot_safe_abc123",
  "policy_pack": "clawdbot_safe",
  "intent": {
    "objective": "Clawdbot Safe - Safe baseline for Clawdbot operations",
    "scope": {
      "clawdbot": ["invoke"]
    },
    "constraints": {
      "allowed_clawdbot_tools": [
        "sessions_list",
        "sessions_get",
        "sessions_create",
        "sessions_update"
      ],
      "blocked_clawdbot_tools": [
        "sessions_delete",
        "web_execute",
        "web_send",
        "shell_execute",
        "file_write",
        "mass_outbound",
        "credential_operations"
      ],
      "confirm_irreversible": true,
      "audit_level": "standard"
    },
    "risk_level": "low",
    "approved_by_user": true
  },
  "active_preset": "clawdbot_safe",
  "message": "Policy pack applied. Use X-Intent-ID header: intent_clawdbot_safe_abc123",
  "scope_includes_clawdbot": true
}
```

### Use the Intent ID

Include the `intent_id` in subsequent Clawdbot requests:

```bash
curl -X POST http://localhost:8000/clawdbot/invoke \
  -H "X-EDON-TOKEN: your-token" \
  -H "X-Intent-ID: intent_clawdbot_safe_abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "sessions_list",
    "action": "json",
    "args": {}
  }'
```

## Comparison with Other Packs

| Pack | Focus | Sessions Tools | Web Tools | Use Case |
|------|-------|----------------|-----------|----------|
| `personal_safe` | Web agent | ❌ | ✅ (read/summarize/draft/search) | Personal web browsing |
| `work_safe` | Work environment | ✅ (list) | ✅ (read/draft) | Work tasks |
| `ops_admin` | Operations | ✅ (list) | ✅ (most, with confirm) | Admin tasks |
| `clawdbot_safe` | **Clawdbot sessions** | ✅ (list/get/create/update) | ❌ (blocked) | **Clawdbot session management** |

## Key Differences

1. **`clawdbot_safe`** is the only pack that includes `sessions_get`, `sessions_create`, and `sessions_update` in the allowed list
2. **`clawdbot_safe`** explicitly blocks `web_execute` (as requested)
3. **`clawdbot_safe`** blocks `sessions_delete` (not in safe baseline)
4. **`personal_safe`** is web-agent focused (web_read, web_summarize, etc.) and doesn't include session management tools

## Testing

Test that the pack works correctly:

```bash
# 1. Apply the pack
INTENT_ID=$(curl -s -X POST http://localhost:8000/policy-packs/clawdbot_safe/apply \
  -H "X-EDON-TOKEN: your-token" | jq -r '.intent_id')

# 2. Test allowed tool (should work)
curl -X POST http://localhost:8000/clawdbot/invoke \
  -H "X-EDON-TOKEN: your-token" \
  -H "X-Intent-ID: $INTENT_ID" \
  -H "Content-Type: application/json" \
  -d '{"tool": "sessions_list", "action": "json", "args": {}}'

# 3. Test blocked tool (should fail)
curl -X POST http://localhost:8000/clawdbot/invoke \
  -H "X-EDON-TOKEN: your-token" \
  -H "X-Intent-ID: $INTENT_ID" \
  -H "Content-Type: application/json" \
  -d '{"tool": "web_execute", "action": "json", "args": {}}'
```

Expected:
- `sessions_list` → ✅ ALLOW
- `web_execute` → ❌ BLOCK (not in allowed list)

## Files Modified

1. `edon_gateway/policy_packs.py`
   - Added `CLAWDBOT_SAFE` pack definition
   - Updated `POLICY_PACKS` registry
   - Updated docstrings

2. `edon_gateway/main.py`
   - Enhanced `apply_policy_pack_endpoint()` to validate constraints for Clawdbot packs
   - Ensures `web_execute` is blocked for `clawdbot_safe`
   - Updated docstring

## Next Steps

1. ✅ Pack created and registered
2. ✅ Apply endpoint updated
3. ⏭️ Test with real Clawdbot integration
4. ⏭️ Update UI to show new pack option
5. ⏭️ Update documentation
