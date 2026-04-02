# EDON Gateway Authentication Methods

EDON Gateway supports **two authentication methods** for API requests:

## Method 1: X-EDON-TOKEN Header (Recommended)

**Primary method** - Recommended for production use.

### Usage

**PowerShell:**
```powershell
$headers = @{
    "X-EDON-TOKEN" = "your-token-here"
    "Content-Type" = "application/json"
}

Invoke-RestMethod -Uri "http://localhost:8000/execute" `
    -Method Post `
    -Headers $headers `
    -Body ($body | ConvertTo-Json)
```

**cURL:**
```bash
curl -X POST http://localhost:8000/execute \
  -H "X-EDON-TOKEN: your-token-here" \
  -H "Content-Type: application/json" \
  -d '{"action": {...}}'
```

**JavaScript/Node.js:**
```javascript
fetch('http://localhost:8000/execute', {
  method: 'POST',
  headers: {
    'X-EDON-TOKEN': 'your-token-here',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ action: {...} })
});
```

**Python:**
```python
import requests

headers = {
    'X-EDON-TOKEN': 'your-token-here',
    'Content-Type': 'application/json'
}

response = requests.post(
    'http://localhost:8000/execute',
    headers=headers,
    json={'action': {...}}
)
```

## Method 2: Authorization Bearer Token (Fallback)

**Compatibility method** - Works with standard HTTP Bearer authentication.

### Usage

**PowerShell:**
```powershell
$headers = @{
    "Authorization" = "Bearer your-token-here"
    "Content-Type" = "application/json"
}

Invoke-RestMethod -Uri "http://localhost:8000/execute" `
    -Method Post `
    -Headers $headers `
    -Body ($body | ConvertTo-Json)
```

**cURL:**
```bash
curl -X POST http://localhost:8000/execute \
  -H "Authorization: Bearer your-token-here" \
  -H "Content-Type: application/json" \
  -d '{"action": {...}}'
```

**JavaScript/Node.js:**
```javascript
fetch('http://localhost:8000/execute', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer your-token-here',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ action: {...} })
});
```

**Python:**
```python
import requests

headers = {
    'Authorization': 'Bearer your-token-here',
    'Content-Type': 'application/json'
}

response = requests.post(
    'http://localhost:8000/execute',
    headers=headers,
    json={'action': {...}}
)
```

## Priority Order

The authentication middleware checks headers in this order:

1. **X-EDON-TOKEN** header (checked first)
2. **Authorization: Bearer** header (checked if X-EDON-TOKEN not found)

If both are present, `X-EDON-TOKEN` takes precedence.

## Error Response

If authentication fails or token is missing:

```json
{
  "detail": "Missing authentication token. Provide X-EDON-TOKEN header or Authorization Bearer token."
}
```

**HTTP Status:** `401 Unauthorized`

## Token Types

### 1. Environment Variable Token (Legacy)

Set in `.env`:
```bash
EDON_API_TOKEN=your-secret-token-change-me
```

**Use case:** Single-tenant deployments, development/testing

### 2. Database API Keys (Production)

Stored in database via `/api-keys/create` endpoint.

**Use case:** Multi-tenant deployments, production environments

**Features:**
- Tenant-scoped (each key belongs to a tenant)
- Usage tracking
- Subscription validation
- Rate limiting per plan

## Public Endpoints (No Authentication Required)

These endpoints don't require authentication:

- `GET /health` - Health check
- `GET /docs` - API documentation
- `GET /openapi.json` - OpenAPI schema
- `GET /redoc` - ReDoc documentation
- `POST /auth/signup` - User signup
- `POST /auth/session` - Session creation
- `POST /billing/checkout` - Stripe checkout
- `POST /billing/webhook` - Stripe webhook

## Protected Endpoints (Authentication Required)

All other endpoints require authentication:

- `POST /execute` - Execute action
- `POST /intent/set` - Set intent
- `GET /intent/get` - Get intent
- `GET /audit/query` - Query audit log
- `GET /decisions/query` - Query decisions
- `GET /decisions/{decision_id}` - Get decision
- `POST /credentials/set` - Set credentials
- `DELETE /credentials/{credential_id}` - Delete credentials
- `GET /metrics` - Get metrics
- `POST /clawdbot/invoke` - Clawdbot proxy
- `POST /policy-packs/{pack_name}/apply` - Apply policy pack

## Configuration

### Enable/Disable Authentication

Set in `.env`:
```bash
# Enable authentication (default: true)
EDON_AUTH_ENABLED=true

# API token (for single-tenant/legacy)
EDON_API_TOKEN=your-secret-token-change-me
```

### Token Binding (Optional)

Bind tokens to specific agent IDs:

```bash
EDON_TOKEN_BINDING_ENABLED=true
```

When enabled, tokens can be bound to agent IDs for additional security.

## Examples

### Example 1: Using X-EDON-TOKEN

```bash
curl -X POST http://localhost:8000/clawdbot/invoke \
  -H "X-EDON-TOKEN: NEW_GATEWAY_TOKEN_12345" \
  -H "X-Intent-ID: intent_clawdbot_safe_abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "sessions_list",
    "action": "json",
    "args": {}
  }'
```

### Example 2: Using Authorization Bearer

```bash
curl -X POST http://localhost:8000/clawdbot/invoke \
  -H "Authorization: Bearer NEW_GATEWAY_TOKEN_12345" \
  -H "X-Intent-ID: intent_clawdbot_safe_abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "sessions_list",
    "action": "json",
    "args": {}
  }'
```

### Example 3: Clawdbot Tool Proxy (Environment Variable)

Set environment variable:
```bash
export TOOLS_PROXY_TOKEN="NEW_GATEWAY_TOKEN_12345"
```

The Clawdbot tool proxy will automatically include `X-EDON-TOKEN` header in requests.

## Security Best Practices

1. **Use X-EDON-TOKEN** for production (more explicit)
2. **Store tokens securely** - Never commit tokens to version control
3. **Use database API keys** for multi-tenant deployments
4. **Rotate tokens regularly** - Change tokens periodically
5. **Enable token binding** - Bind tokens to specific agent IDs when possible
6. **Use HTTPS** - Always use HTTPS in production (never send tokens over HTTP)

## Troubleshooting

### Error: "Missing authentication token"

**Solution:** Add either `X-EDON-TOKEN` or `Authorization: Bearer` header to your request.

### Error: "Invalid authentication token"

**Solution:** 
1. Verify token is correct (check `.env` file or database)
2. Check for typos or extra spaces
3. Ensure token hasn't been rotated/changed

### Error: "Subscription inactive"

**Solution:** 
1. Check tenant status in database
2. Ensure subscription is active
3. For development, set `EDON_DEMO_MODE=true` to bypass subscription checks
