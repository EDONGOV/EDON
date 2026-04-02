# EDON Agent UI - Test Results

## Test Setup

### Created Test Files

1. **`src/test/integration.test.ts`** - Integration tests for Gateway API
   - Health check endpoint
   - Metrics endpoint
   - Decisions endpoint
   - Audit endpoint
   - Intent endpoint
   - Error handling

2. **`src/test/clawdbot-integration.test.ts`** - Clawdbot integration tests
   - Clawdbot invoke endpoint
   - Decision tracking
   - Agent UI monitoring

3. **`test-gateway-integration.ps1`** - PowerShell test runner script
4. **`test-gateway-integration.sh`** - Bash test runner script

## Running Tests

### Prerequisites

1. **Start EDON Gateway:**
   ```powershell
   cd C:\Users\cjbig\Desktop\EDON\edon-cav-engine\edon_gateway
   python -m edon_gateway.main
   ```
   Gateway should be running on `http://localhost:8000`

2. **Install dependencies** (if not already done):
   ```powershell
   cd C:\Users\cjbig\Desktop\edon-agent-ui
   npm install
   ```

### Run Tests

**Option 1: Run all tests**
```powershell
cd C:\Users\cjbig\Desktop\edon-agent-ui
npm test
```

**Option 2: Run with gateway check**
```powershell
.\test-gateway-integration.ps1
```

**Option 3: Run specific test file**
```powershell
npm test src/test/integration.test.ts
npm test src/test/clawdbot-integration.test.ts
```

**Option 4: Watch mode (for development)**
```powershell
npm run test:watch
```

## Test Coverage

### Integration Tests (`integration.test.ts`)

✅ **Health Check**
- Tests `/health` endpoint
- Verifies gateway is accessible
- Checks response structure

✅ **Metrics Endpoint**
- Tests `/metrics` endpoint (via `/stats` for JSON)
- Verifies metrics structure (allowed_24h, blocked_24h, etc.)
- Validates data types

✅ **Decisions Endpoint**
- Tests `/decisions/query` endpoint
- Tests filtering by verdict
- Tests filtering by agent_id
- Validates response structure

✅ **Audit Endpoint**
- Tests `/audit/query` endpoint
- Tests pagination (offset/limit)
- Validates response structure

✅ **Intent Endpoint**
- Tests `/intent/get` endpoint
- Handles case when no intent is set

✅ **Error Handling**
- Tests 404 error handling
- Tests network error handling
- Validates graceful degradation

✅ **Mock Mode**
- Tests that mock mode works when gateway unavailable
- Validates mock data structure

### Clawdbot Integration Tests (`clawdbot-integration.test.ts`)

✅ **Clawdbot Invoke Endpoint**
- Tests `/clawdbot/invoke` endpoint exists
- Tests Clawdbot request format acceptance
- Validates headers (X-Agent-ID, X-EDON-TOKEN)

✅ **Decision Tracking**
- Tests that Clawdbot requests create audit entries
- Verifies decisions appear in audit log
- Tests agent_id tracking

✅ **Agent UI Monitoring**
- Tests that decisions appear in UI endpoints
- Validates decision structure for UI display
- Tests filtering by agent_id

## Expected Results

### When Gateway is Running

All integration tests should pass:
- ✅ Health check succeeds
- ✅ Metrics endpoint returns data
- ✅ Decisions endpoint returns decisions (may be empty)
- ✅ Audit endpoint returns audit logs (may be empty)
- ✅ Clawdbot endpoint accepts requests (may require auth/credentials)

### When Gateway is Not Running

Tests will:
- ⚠️ Show warnings about gateway not being available
- ✅ Mock mode tests will still pass
- ⚠️ Integration tests will fail gracefully

## Manual Testing Checklist

### 1. Start Gateway
- [ ] Gateway starts on port 8000
- [ ] `/healthz` endpoint returns 200
- [ ] `/docs` shows API documentation

### 2. Start Agent UI
- [ ] UI starts on port 5174 (or next available)
- [ ] Browser console shows no errors
- [ ] UI loads dashboard

### 3. Connect UI to Gateway
- [ ] Open browser console
- [ ] Run: `localStorage.setItem('edon_mock_mode', 'false')`
- [ ] Run: `localStorage.setItem('edon_api_base', 'http://localhost:8000')`
- [ ] Reload page
- [ ] Dashboard shows real data (or empty state if no data)

### 4. Test Clawdbot Integration
- [ ] Make a request to `/clawdbot/invoke` (via Postman/curl)
- [ ] Check that decision appears in UI
- [ ] Verify audit log shows the request
- [ ] Check metrics update

## Troubleshooting

### Tests Fail with "Gateway not available"

**Solution:** Start the gateway first:
```powershell
cd C:\Users\cjbig\Desktop\EDON\edon-cav-engine\edon_gateway
python -m edon_gateway.main
```

### Tests Fail with CORS Errors

**Solution:** Check gateway CORS configuration:
```env
EDON_CORS_ORIGINS=http://localhost:5174,http://localhost:5173
```

### Tests Fail with 401/403 Errors

**Solution:** Either:
1. Disable auth in gateway: `EDON_AUTH_ENABLED=false`
2. Or set token in tests: `localStorage.setItem('edon_api_token', 'your-token')`

### UI Shows Mock Data Instead of Real Data

**Solution:** Disable mock mode:
```javascript
localStorage.setItem('edon_mock_mode', 'false');
localStorage.setItem('edon_api_base', 'http://localhost:8000');
location.reload();
```

## Next Steps

1. **Run tests with gateway running**
2. **Verify all endpoints work**
3. **Test with real Clawdbot** (if available)
4. **Add more edge case tests**
5. **Set up CI/CD integration**

## Test Results Log

### [Date] - Initial Test Run
- Status: ⏳ Pending
- Gateway Running: ⏳ Check
- Tests Passed: ⏳ TBD
- Notes: Tests created, ready to run

---

**To update this log, run tests and document results here.**
