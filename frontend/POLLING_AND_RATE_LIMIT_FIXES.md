# Polling and Rate Limit Fixes

## Summary

Fixed polling behavior and rate limiting issues in both UI and backend to prevent self-DDoS during development.

## UI Fixes

### A) DecisionStreamTable.tsx - Sane Polling ✅

**Changes:**
- Changed polling interval from 3 seconds to **8 seconds** (`POLL_MS = 8000`)
- Improved visibility API handling to properly pause/resume polling
- Used `window.setInterval`/`clearInterval` for better browser compatibility
- Converted `fetchDecisions` to `useCallback` to prevent unnecessary re-renders

**Behavior:**
- Polls every 8 seconds when tab is visible
- Automatically pauses when tab is hidden
- Resumes and fetches immediately when tab becomes visible again

### B) React StrictMode Duplicate Request Prevention ✅

**Files Updated:**
- `DecisionsOverTimeChart.tsx`
- `TopReasonsChart.tsx`

**Changes:**
- Added `useRef` hook with `didRun` flag to prevent duplicate requests
- Prevents React 18 StrictMode from running effects twice in development

**Pattern:**
```typescript
const didRun = useRef(false);

useEffect(() => {
  if (didRun.current) return;
  didRun.current = true;
  
  fetchData();
}, [dependencies]);
```

### C) Client-Side 429 Retry Logic ✅

**File:** `api.ts`

**Changes:**
- Added exponential backoff retry logic for 429 (Too Many Requests) errors
- Respects `Retry-After` header from server
- Falls back to exponential backoff: 500ms, 1000ms, 2000ms + jitter
- Maximum 3 retries before giving up

**Behavior:**
- Automatically retries on 429 errors
- Waits for `Retry-After` seconds if provided
- Uses exponential backoff with jitter if no header
- Shows clear error message if all retries exhausted

## Backend Fixes

### D) Development-Friendly Rate Limiting ✅

**File:** `middleware/rate_limit.py`

**Changes:**

1. **Environment Detection:**
   - Checks `ENVIRONMENT` or `EDON_ENV` environment variable
   - Treats `development`, `dev`, or `local` as development mode

2. **Rate Limiting Behavior:**
   - **Development:** Disabled by default (unless explicitly enabled)
   - **Production:** Enabled by default
   - Can be overridden with `EDON_RATE_LIMIT_ENABLED=true/false`

3. **Higher Limits for Polling Endpoints:**
   - `/decisions/query` - 120/min in dev, 60/min in prod
   - `/audit/query` - Same higher limits
   - `/timeseries` - Same higher limits
   - `/block-reasons` - Same higher limits

4. **Improved Retry-After Headers:**
   - Returns appropriate `Retry-After` based on which limit was hit:
     - Per-minute limit: 60 seconds
     - Per-hour limit: 3600 seconds (1 hour)
     - Per-day limit: 86400 seconds (1 day)

**Rate Limits:**

| Mode | Endpoint Type | Per Minute | Per Hour | Per Day |
|------|--------------|------------|----------|---------|
| **Dev** | Default | 300 | 10,000 | 100,000 |
| **Dev** | Polling | 120 | 20,000 | 200,000 |
| **Dev** | Anonymous | 60 | 1,000 | 5,000 |
| **Prod** | Default | 60 | 1,000 | 10,000 |
| **Prod** | Polling | 60 | 2,000 | 20,000 |
| **Prod** | Anonymous | 10 | 100 | 500 |

## Configuration

### Environment Variables

**Backend (`.env`):**
```bash
# Set environment mode
ENVIRONMENT=development  # or "production"

# Explicitly control rate limiting (optional)
EDON_RATE_LIMIT_ENABLED=false  # Disabled in dev by default
```

**Frontend (`.env`):**
No changes needed - polling interval is hardcoded to 8 seconds.

## Testing

### Verify Polling Behavior:
1. Open browser DevTools → Network tab
2. Navigate to Dashboard
3. Observe requests to `/decisions/query` every 8 seconds
4. Switch to another tab → polling should pause
5. Switch back → polling should resume immediately

### Verify Rate Limiting:
1. **Development Mode:**
   ```bash
   ENVIRONMENT=development python -m uvicorn edon_gateway.main:app
   ```
   - Should not see 429 errors during normal usage

2. **Production Mode:**
   ```bash
   ENVIRONMENT=production python -m uvicorn edon_gateway.main:app
   ```
   - Rate limiting should be active
   - Polling endpoints have higher limits

### Verify 429 Retry Logic:
1. Temporarily set very low rate limits
2. Make multiple rapid requests
3. Observe retry attempts in Network tab
4. Check that requests wait for `Retry-After` header

## Benefits

1. **No Self-DDoS:** Development mode has relaxed/disabled rate limiting
2. **Better UX:** Polling pauses when tab is hidden, saving resources
3. **Resilient:** Automatic retry on 429 errors with exponential backoff
4. **Production Ready:** Strict limits in production, relaxed in development
5. **React 18 Compatible:** Prevents duplicate requests in StrictMode

## Migration Notes

- **No breaking changes** - all changes are backward compatible
- Existing `.env` files will work (rate limiting enabled by default)
- Set `ENVIRONMENT=development` to get dev-friendly behavior
- UI changes are automatic - no configuration needed
