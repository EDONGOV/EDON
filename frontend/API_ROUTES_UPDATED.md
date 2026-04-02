# API Routes Updated

## Changes Applied

### 1. Updated API Endpoints ✅

**Decisions:**
- ✅ Old: `/decisions` → New: `/decisions/query`
- ✅ Added: `/decisions/{decision_id}` for individual decision lookup

**Audit:**
- ✅ Old: `/audit` → New: `/audit/query`

### 2. Filter Mapping ✅

**Decisions Filters:**
- ✅ `verdict`: Maps UI format (lowercase) to gateway format (uppercase)
  - `allowed` → `ALLOW`
  - `blocked` → `BLOCK`
  - `confirm` → `CONFIRM`
- ✅ `agent_id`: Passed directly
- ✅ `tool`: Passed directly
- ✅ `limit`: Passed directly

**Audit Filters:**
- ✅ `verdict`: Maps UI format to gateway format (uppercase)
- ✅ `agent_id`: Passed directly
- ✅ `intent_id`: Passed directly
- ✅ `limit`: Passed directly
- ⚠️ `offset`: Removed (gateway doesn't support offset, only limit)

### 3. Fixed 404 Test ✅

- ✅ Uses guaranteed nonexistent endpoint: `/__does_not_exist__`
- ✅ Always sends token if available to avoid 401 masking 404
- ✅ Asserts 404 when token is present
- ✅ Handles both 404 and 401 when token is missing

## Updated Code

### `src/lib/api.ts`

**getDecisions():**
```typescript
async getDecisions(params?: { verdict?: string; tool?: string; agent_id?: string; limit?: number }) {
  // Maps verdict to uppercase (ALLOW, BLOCK, CONFIRM)
  // Uses /decisions/query endpoint
}
```

**getDecisionById():**
```typescript
async getDecisionById(decisionId: string) {
  return this.request<Decision>(`/decisions/${decisionId}`);
}
```

**getAudit():**
```typescript
async getAudit(params?: { limit?: number; verdict?: string; agent_id?: string; intent_id?: string }) {
  // Maps verdict to uppercase
  // Supports verdict, agent_id, intent_id filters
  // Uses /audit/query endpoint
  // Note: offset removed (not supported by gateway)
}
```

## Example API Calls

**Decisions:**
```
GET /decisions/query?limit=100&verdict=ALLOW
GET /decisions/query?limit=100&agent_id=clawdbot-agent
GET /decisions/query?limit=100&verdict=BLOCK&agent_id=test-agent
GET /decisions/{decision_id}
```

**Audit:**
```
GET /audit/query?limit=100&verdict=BLOCK
GET /audit/query?limit=100&agent_id=clawdbot-agent
GET /audit/query?limit=100&intent_id=intent-123
GET /audit/query?limit=100&verdict=ALLOW&agent_id=test-agent
```

## Test Updates

- ✅ Updated 404 test to use `/__does_not_exist__`
- ✅ Updated audit pagination test (removed offset)
- ✅ Updated verdict filter test to handle case conversion

## Breaking Changes

⚠️ **Audit pagination:** `offset` parameter removed (gateway doesn't support it)
- Use `limit` with other filters for pagination
- Or implement client-side pagination

## Next Steps

1. ✅ Routes updated
2. ✅ Filters mapped correctly
3. ✅ Tests fixed
4. ⏳ Run tests to verify: `npm test`
