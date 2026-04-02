# Production Mode Validation Guide

This document describes how to validate that all production security features are working correctly.

## Three Main Invariants

### A) Strict Credentials Fail Closed

**Test**: Missing credentials return 503, no execution occurs.

**Steps**:
1. Set `EDON_CREDENTIALS_STRICT=true`
2. Ensure credential doesn't exist in database (or clear credentials table)
3. Call `/execute` with action requiring credential
4. Verify 503 response and no execution artifact created

**Expected Behavior**:
- Response: `503 Service Unavailable`
- Error message: `"Credential 'xxx' not found in database. EDON_CREDENTIALS_STRICT=true requires all credentials to be in database."`
- No execution artifact created in sandbox

**Run Test**:
```bash
# Set strict mode
export EDON_CREDENTIALS_STRICT=true

# Clear credential (if exists)
curl -X DELETE http://localhost:8000/credentials/test-email-credential-001 \
  -H "X-EDON-TOKEN: your-token"

# Try to execute (should fail)
curl -X POST http://localhost:8000/execute \
  -H "Content-Type: application/json" \
  -H "X-EDON-TOKEN: your-token" \
  -d '{
    "action": {
      "tool": "email",
      "op": "send",
      "params": {
        "recipients": ["test@example.com"],
        "subject": "Test",
        "body": "Test"
      }
    },
    "agent_id": "test-agent-001"
  }'

# Expected: 503 with credential error
```

### B) Validation Rejects Dangerous Payloads

**Test**: Invalid payloads are rejected with 400, not sanitized.

**Test Cases**:

1. **Oversized Body (>10MB)**
   ```bash
   # Create 11MB payload
   python -c "import json; print(json.dumps({'action': {'tool': 'email', 'op': 'draft', 'params': {'body': 'x' * (11 * 1024 * 1024)}}, 'agent_id': 'test'}))" | \
   curl -X POST http://localhost:8000/execute \
     -H "Content-Type: application/json" \
     -H "X-EDON-TOKEN: your-token" \
     --data-binary @-
   
   # Expected: 413 Request Entity Too Large
   ```

2. **Deep JSON Nesting (>10 levels)**
   ```bash
   # Create deeply nested JSON (11 levels)
   python edon_gateway/test_production_mode.py
   # Look for "Deep nesting test" - should return 400
   
   # Expected: 400 Bad Request with "depth exceeds maximum"
   ```

3. **Huge Arrays (>10,000 items)**
   ```bash
   # Create array with 10,001 items
   python edon_gateway/test_production_mode.py
   # Look for "Huge array test" - should return 400
   
   # Expected: 400 Bad Request with "array length exceeds maximum"
   ```

4. **Dangerous Patterns**
   ```bash
   # Script tags
   curl -X POST http://localhost:8000/execute \
     -H "Content-Type: application/json" \
     -H "X-EDON-TOKEN: your-token" \
     -d '{
       "action": {
         "tool": "email",
         "op": "draft",
         "params": {
           "body": "<script>alert(1)</script>"
         }
       },
       "agent_id": "test"
     }'
   
   # Expected: 400 Bad Request with "Script tags not allowed at path: action.params.body"
   ```

**Expected Behavior**:
- All invalid payloads rejected with 400/413
- Clear error messages with path to invalid field
- No mutation/sanitization - original payload preserved for audit

### C) Auth Truly Blocks Protected Endpoints

**Test**: Protected endpoints require authentication, public endpoints stay open.

**Steps**:
1. Set `EDON_AUTH_ENABLED=true`
2. Call protected endpoints without token → expect 401/403
3. Call `/health` without token → expect 200 OK

**Protected Endpoints** (require auth):
- `/execute`
- `/intent/set`
- `/intent/get`
- `/audit/query`
- `/decisions/query`
- `/decisions/{decision_id}`
- `/credentials/set`
- `/credentials/get/{credential_id}`
- `/credentials/tool/{tool_name}`
- `/credentials/{credential_id}` (DELETE)

**Public Endpoints** (no auth required):
- `/health`
- `/docs`
- `/openapi.json`
- `/redoc`

**Run Tests**:
```bash
# Set auth enabled
export EDON_AUTH_ENABLED=true
export EDON_API_TOKEN=your-secret-token

# Test protected endpoint without token (should fail)
curl -X POST http://localhost:8000/execute \
  -H "Content-Type: application/json" \
  -d '{"action": {"tool": "email", "op": "draft", "params": {}}, "agent_id": "test"}'

# Expected: 401 Unauthorized or 403 Forbidden

# Test protected endpoint with token (should succeed)
curl -X POST http://localhost:8000/execute \
  -H "Content-Type: application/json" \
  -H "X-EDON-TOKEN: your-secret-token" \
  -d '{"action": {"tool": "email", "op": "draft", "params": {}}, "agent_id": "test"}'

# Expected: 200 OK (or other success status)

# Test public endpoint without token (should succeed)
curl http://localhost:8000/health

# Expected: 200 OK with health status
```

## Running All Tests

### Option 1: Python Test Suite

```bash
# Set production environment
export EDON_CREDENTIALS_STRICT=true
export EDON_VALIDATE_STRICT=true
export EDON_AUTH_ENABLED=true
export EDON_API_TOKEN=your-secret-token
export EDON_GATEWAY_URL=http://localhost:8000

# Run tests
python edon_gateway/test_production_mode.py
```

### Option 2: Validation Scripts

**Linux/Mac**:
```bash
chmod +x edon_gateway/run_production_validation.sh
./edon_gateway/run_production_validation.sh
```

**Windows**:
```powershell
.\edon_gateway\run_production_validation.ps1
```

## Expected Test Results

All tests should pass when production mode is correctly configured:

```
============================================================
Production Mode Security Validation Tests
============================================================

Environment Configuration:
  EDON_CREDENTIALS_STRICT: true
  EDON_VALIDATE_STRICT: true
  EDON_AUTH_ENABLED: true
  EDON_GATEWAY_URL: http://localhost:8000

============================================================
Running: A) Strict Credentials
============================================================

  Running: test_credential_missing_fails_closed...
  ✓ PASSED: test_credential_missing_fails_closed

============================================================
Running: B) Validation Rejects Dangerous Payloads
============================================================

  Running: test_oversized_body_rejected...
  ✓ PASSED: test_oversized_body_rejected

  Running: test_deep_json_nesting_rejected...
  ✓ PASSED: test_deep_json_nesting_rejected

  Running: test_huge_array_rejected...
  ✓ PASSED: test_huge_array_rejected

  Running: test_dangerous_patterns_rejected...
  ✓ PASSED: test_dangerous_patterns_rejected

============================================================
Running: C) Auth Blocks Protected Endpoints
============================================================

  Running: test_execute_requires_auth...
  ✓ PASSED: test_execute_requires_auth

  Running: test_audit_query_requires_auth...
  ✓ PASSED: test_audit_query_requires_auth

  Running: test_credentials_endpoints_require_auth...
  ✓ PASSED: test_credentials_endpoints_require_auth

  Running: test_intent_endpoints_require_auth...
  ✓ PASSED: test_intent_endpoints_require_auth

  Running: test_health_endpoint_stays_open...
  ✓ PASSED: test_health_endpoint_stays_open

============================================================
Test Summary
============================================================
Passed: 10
Failed: 0
Total: 10

✅ All tests passed!
```

## Troubleshooting

### Tests Fail with "Gateway not running"
- Start the gateway: `python -m uvicorn edon_gateway.main:app --host 0.0.0.0 --port 8000`
- Check URL: `export EDON_GATEWAY_URL=http://localhost:8000`

### Credential Tests Fail
- Ensure `EDON_CREDENTIALS_STRICT=true` is set
- Restart the gateway after setting environment variables
- Verify credential doesn't exist in database

### Auth Tests Fail
- Ensure `EDON_AUTH_ENABLED=true` is set
- Set `EDON_API_TOKEN=your-secret-token`
- Restart the gateway after setting environment variables
- Use `X-EDON-TOKEN` header in requests

### Validation Tests Pass When They Should Fail
- Ensure `EDON_VALIDATE_STRICT=true` is set (default)
- Restart the gateway after setting environment variables
- Check that validation middleware is enabled in `main.py`

## Production Checklist

Before deploying to production, verify:

- [ ] `EDON_CREDENTIALS_STRICT=true` is set
- [ ] `EDON_VALIDATE_STRICT=true` is set
- [ ] `EDON_AUTH_ENABLED=true` is set
- [ ] `EDON_API_TOKEN` is set to a strong secret
- [ ] All credentials are stored in database (not env vars)
- [ ] All tests pass
- [ ] Gateway restarted with production environment variables
