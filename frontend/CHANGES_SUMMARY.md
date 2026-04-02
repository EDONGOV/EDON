# API Routes & Filters - Changes Summary

## ✅ All Changes Applied

### 1. API Routes Updated

**Decisions:**
- ✅ `/decisions` → `/decisions/query`
- ✅ Added `/decisions/{decision_id}` method

**Audit:**
- ✅ `/audit` → `/audit/query`
- ✅ Response format: `events` → transformed to `records` for UI compatibility

### 2. Filter Mapping

**Decisions Filters:**
```typescript
// Verdict mapping (UI → Gateway)
allowed → ALLOW
blocked → BLOCK
confirm → CONFIRM

// Query params
/decisions/query?limit=100&verdict=ALLOW
/decisions/query?limit=100&agent_id=clawdbot-agent
/decisions/query?limit=100&verdict=BLOCK&agent_id=test-agent
```

**Audit Filters:**
```typescript
// Verdict mapping (UI → Gateway)
allowed → ALLOW
blocked → BLOCK
confirm → CONFIRM

// Query params
/audit/query?limit=100&verdict=BLOCK
/audit/query?limit=100&agent_id=clawdbot-agent
/audit/query?limit=100&intent_id=intent-123
```

**Removed:**
- ⚠️ `offset` parameter (gateway doesn't support it)

### 3. Fixed 404 Test

**Before:**
- Used `/decisions/nonexistent-id` (could return 401 if auth enabled)
- Expected 404 or 401

**After:**
- Uses `/__does_not_exist__` (guaranteed nonexistent)
- Always sends token if available
- Asserts 404 when token present
- Handles 401 when token missing

### 4. Response Format Transformations

**Audit Response:**
- Gateway returns: `{ events: [...], total: number, limit: number }`
- UI expects: `{ records: [...], total: number }`
- ✅ Added transformation in `getAudit()` method

## Code Changes

### `src/lib/api.ts`

1. **getDecisions()** - Updated endpoint and verdict mapping
2. **getDecisionById()** - New method for individual decision lookup
3. **getAudit()** - Updated endpoint, filters, and response transformation
4. **Mock handlers** - Updated to match new endpoints

### `src/test/integration.test.ts`

1. **404 test** - Fixed to use guaranteed nonexistent endpoint
2. **Audit pagination** - Removed offset parameter
3. **Verdict filter** - Updated to handle case conversion

## Testing

Run tests to verify:
```powershell
cd C:\Users\cjbig\Desktop\edon-agent-ui
npm test
```

**Expected Results:**
- ✅ All routes use correct endpoints
- ✅ Filters map correctly to gateway format
- ✅ 404 test is deterministic
- ✅ Response formats match UI expectations

## Breaking Changes

⚠️ **Audit Pagination:**
- `offset` parameter removed from `getAudit()`
- Use `limit` with filters for pagination
- Or implement client-side pagination

## Files Modified

1. ✅ `src/lib/api.ts` - API routes and filters
2. ✅ `src/test/integration.test.ts` - Test fixes
3. ✅ Mock data handlers updated

## Next Steps

1. ✅ Routes updated
2. ✅ Filters mapped
3. ✅ Tests fixed
4. ⏳ Run tests: `npm test`
5. ⏳ Test with real gateway
6. ⏳ Update UI components if needed
