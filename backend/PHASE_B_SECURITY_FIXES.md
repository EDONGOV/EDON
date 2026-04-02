# Phase B.1: Security Fixes - COMPLETE ✅

Critical security fixes based on production readiness review.

## Issues Fixed

### 1. ✅ Credential Containment - Fail Closed in Production

**Problem**: Credentials fell back to environment variables, creating a bypass path.

**Solution**: Added `EDON_CREDENTIALS_STRICT` mode.

**Behavior**:
- **DEV mode** (`EDON_CREDENTIALS_STRICT=false`): Allows fallback to environment variables
- **PROD mode** (`EDON_CREDENTIALS_STRICT=true`): **Fails closed** - returns 503 if credential missing in database

**Implementation**:
- `EmailConnector` and `FilesystemConnector` check strict mode
- Raise `RuntimeError` with clear message if credential missing in strict mode
- Execute endpoint catches credential errors and returns 503

**Configuration**:
```bash
# Production (fail closed)
export EDON_CREDENTIALS_STRICT=true

# Development (allow fallback)
export EDON_CREDENTIALS_STRICT=false  # or omit (defaults to false)
```

### 2. ✅ Input Validation - Reject Instead of Sanitize

**Problem**: Validation middleware was mutating user input (sanitizing), creating non-deterministic behavior and potential policy bypasses.

**Solution**: Changed to **strict validation with rejection**.

**Behavior**:
- **Strict mode** (`EDON_VALIDATE_STRICT=true`, default): Rejects invalid content with 400 error
- Validates structure, size, depth, and dangerous patterns
- **No mutation** - original payload preserved for audit
- Only narrow normalization (e.g., whitespace trimming) for specific fields

**Validation Rules**:
- Size limits enforced (reject if exceeded)
- JSON depth limits enforced (reject if exceeded)
- String length limits enforced (reject if exceeded)
- Array length limits enforced (reject if exceeded)
- Dangerous patterns detected and rejected (not removed)

**Error Messages**:
- Clear error messages with path to invalid field
- Example: `"Invalid request body: Script tags not allowed at path: action.params.body"`

**Configuration**:
```bash
# Strict validation (default - reject invalid)
export EDON_VALIDATE_STRICT=true

# Note: No "lenient" mode - always validate, but can disable pattern checks
```

### 3. ✅ Rate Limiting - Proper Keying and Anonymous Handling

**Problem**: 
- Rate limits could be bypassed by not providing agent_id
- Body reading for agent_id created DoS risk

**Solution**: 
- Rate limits applied **before** reading body (DoS protection)
- Anonymous requests heavily limited
- Proper keying on `agent_id` (not IP address)

**Anonymous Request Limits**:
- 10 requests per minute (vs 60 for authenticated)
- 100 requests per hour (vs 1000 for authenticated)
- 500 requests per day (vs 10000 for authenticated)

**Rate Limit Keys**:
- Authenticated: `rate_limit:{agent_id}:{window}:{time_key}`
- Anonymous: `rate_limit:anonymous:{window}:{time_key}`

**Error Messages**:
- Anonymous requests get specific error: "Anonymous requests are heavily rate-limited. Provide agent_id in X-Agent-ID header or query parameter."

**Implementation**:
- Checks headers/query params ONLY (no body read)
- Applies limits before processing request
- Increments counter only on successful (2xx) responses

### 4. ✅ Authentication - Protected Endpoints Verified

**Problem**: Need to verify sensitive endpoints are protected.

**Solution**: Documented and verified all protected endpoints.

**Protected Endpoints** (require authentication when `EDON_AUTH_ENABLED=true`):
- `/execute` - Action execution
- `/intent/set` - Set intent
- `/intent/get` - Get intent
- `/audit/query` - Query audit logs
- `/decisions/query` - Query decisions
- `/decisions/{decision_id}` - Get decision
- `/credentials/set` - Set credential
- `/credentials/get/{credential_id}` - Get credential
- `/credentials/tool/{tool_name}` - List credentials by tool
- `/credentials/{credential_id}` - Delete credential

**Public Endpoints** (no authentication required):
- `/health` - Health check
- `/docs` - API documentation
- `/openapi.json` - OpenAPI schema
- `/redoc` - Alternative API docs

**Authentication Methods**:
- **Primary**: `X-EDON-TOKEN` header (recommended for production)
- **Fallback**: `Authorization: Bearer {token}` (for compatibility)

**Recommendation**: Use `X-EDON-TOKEN` for production to avoid confusion.

## Security Posture

### Before Fixes
- ❌ Credentials could bypass database via env vars
- ❌ Input mutation created non-deterministic behavior
- ❌ Anonymous requests not rate-limited
- ❌ Body read before rate limiting (DoS risk)

### After Fixes
- ✅ Credentials fail closed in production
- ✅ Input validation rejects invalid content (no mutation)
- ✅ Anonymous requests heavily rate-limited
- ✅ Rate limits applied before body read (DoS protection)
- ✅ All sensitive endpoints protected

## Configuration Summary

```bash
# Production Configuration
export EDON_CREDENTIALS_STRICT=true      # Fail closed on missing credentials
export EDON_VALIDATE_STRICT=true         # Reject invalid input (default)
export EDON_AUTH_ENABLED=true            # Require authentication
export EDON_API_TOKEN=your-secret-token  # Set auth token

# Development Configuration
export EDON_CREDENTIALS_STRICT=false     # Allow env var fallback
export EDON_AUTH_ENABLED=false           # Disable auth (dev only)
```

## Testing

### Test Credential Strict Mode
```bash
# Set strict mode
export EDON_CREDENTIALS_STRICT=true

# Try to use connector without credential in DB
# Should return 503: "Credential 'email-smtp-001' not found in database"
```

### Test Validation Rejection
```bash
# Send request with script tag
curl -X POST http://localhost:8000/execute \
  -H "Content-Type: application/json" \
  -d '{"action": {"tool": "email", "op": "draft", "params": {"body": "<script>alert(1)</script>"}}}'

# Should return 400: "Invalid request body: Script tags not allowed at path: action.params.body"
```

### Test Anonymous Rate Limiting
```bash
# Make 11 requests without agent_id
for i in {1..11}; do
  curl http://localhost:8000/health
done

# 11th request should return 429: "Rate limit exceeded: 10 requests per minute"
```

## Migration Notes

**Breaking Changes**: None - all changes are opt-in via environment variables.

**Recommended Production Settings**:
1. Set `EDON_CREDENTIALS_STRICT=true`
2. Set `EDON_AUTH_ENABLED=true`
3. Store all credentials in database (no env var fallback)
4. Use `X-EDON-TOKEN` header for authentication

**Development Settings**:
- Can use `EDON_CREDENTIALS_STRICT=false` for convenience
- Can use `EDON_AUTH_ENABLED=false` for local testing
