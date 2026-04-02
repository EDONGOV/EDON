# Clawdbot Gateway Integration Guide

**Fast Integration Test (1-2 hours)**

This guide walks through integrating Clawdbot Gateway with EDON Gateway.

---

## Step 1: Run Clawdbot Gateway Locally

You need a running Clawdbot Gateway and its token.

### Sanity Check

**Linux/Mac (Bash):**
```bash
curl -sS http://127.0.0.1:18789/tools/invoke \
  -H "Authorization: Bearer $CLAWDBOT_GATEWAY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tool":"sessions_list","action":"json","args":{}}'
```

**Windows (PowerShell):**
```powershell
$headers = @{
    "Authorization" = "Bearer $env:CLAWDBOT_GATEWAY_TOKEN"
    "Content-Type" = "application/json"
}
$body = @{
    tool = "sessions_list"
    action = "json"
    args = @{}
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:18789/tools/invoke" `
    -Method Post `
    -Headers $headers `
    -Body $body
```

**Expected Response:**
- `200 { ok: true, result }` - Tool is allowlisted and executed
- `404` - Tool is not allowlisted (policy error)
- `401` - Authentication failed

---

## Step 2: Clawdbot Connector

The Clawdbot connector (`edon_gateway/connectors/clawdbot_connector.py`) is already implemented.

### Configuration

**Development Mode** (environment variables):

**Linux/Mac (Bash):**
```bash
export CLAWDBOT_GATEWAY_URL="http://127.0.0.1:18789"
export CLAWDBOT_GATEWAY_TOKEN="your-token-here"
```

**Windows (PowerShell):**
```powershell
$env:CLAWDBOT_GATEWAY_URL = "http://127.0.0.1:18789"
$env:CLAWDBOT_GATEWAY_TOKEN = "your-token-here"
```

**Production Mode** (database credentials):
```bash
# Set credential in database
curl -X POST http://127.0.0.1:8000/credentials/set \
  -H "X-EDON-TOKEN: your-edon-token" \
  -H "Content-Type: application/json" \
  -d '{
    "credential_id": "clawdbot-gateway-001",
    "tool_name": "clawdbot",
    "credential_type": "gateway",
    "credential_data": {
      "gateway_url": "http://127.0.0.1:18789",
      "gateway_token": "your-clawdbot-token"
    }
  }'
```

### Usage

The connector calls Clawdbot's `/tools/invoke` endpoint with the exact JSON body Clawdbot expects:

```python
result = clawdbot_connector.invoke(
    tool="sessions_list",
    action="json",
    args={},
    sessionKey=None  # Optional
)
```

---

## Step 3: Wire EDON Policy to Allow Clawdbot Tools

### Example Intent (Allowlist)

Start with a tiny allowlist:

```json
{
  "objective": "List Clawdbot sessions",
  "scope": {
    "clawdbot": ["invoke"]
  },
  "constraints": {
    "allowed_clawdbot_tools": ["sessions_list"]
  },
  "risk_level": "low",
  "approved_by_user": true
}
```

**Important Notes:**
- Clawdbot has its own allowlist/policy chain
- If a tool isn't allowed in Clawdbot, Clawdbot returns 404
- EDON becomes the **outer governor**; Clawdbot remains the **inner governor**
- EDON can block before Clawdbot even receives the call

### Setting Intent via API

```bash
curl -X POST http://127.0.0.1:8000/intent/set \
  -H "X-EDON-TOKEN: your-edon-token" \
  -H "Content-Type: application/json" \
  -d '{
    "objective": "List Clawdbot sessions",
    "scope": {
      "clawdbot": ["invoke"]
    },
    "constraints": {
      "allowed_clawdbot_tools": ["sessions_list"]
    },
    "risk_level": "low",
    "approved_by_user": true
  }'
```

---

## Step 4: Run End-to-End Tests

### ALLOW Case: Benign Tool Invocation

**EDON Intent:** "list sessions"  
**Action:** `clawdbot.invoke` calling `sessions_list`

```bash
curl -X POST http://127.0.0.1:8000/execute \
  -H "X-EDON-TOKEN: your-edon-token" \
  -H "Content-Type: application/json" \
  -d '{
    "action": {
      "tool": "clawdbot",
      "op": "invoke",
      "params": {
        "tool": "sessions_list",
        "action": "json",
        "args": {}
      }
    },
    "intent_id": "your-intent-id",
    "agent_id": "test-agent-001"
  }'
```

**Expected Response:**
```json
{
  "verdict": "ALLOW",
  "decision_id": "...",
  "explanation": "...",
  "execution": {
    "tool": "clawdbot",
    "op": "invoke",
    "result": {
      "success": true,
      "tool": "sessions_list",
      "result": { ... }
    }
  }
}
```

### BLOCK Case: Risky Tool

**Attempt:** Shell-like tool or anything outside scope

```bash
curl -X POST http://127.0.0.1:8000/execute \
  -H "X-EDON-TOKEN: your-edon-token" \
  -H "Content-Type: application/json" \
  -d '{
    "action": {
      "tool": "clawdbot",
      "op": "invoke",
      "params": {
        "tool": "web_execute",
        "action": "json",
        "args": {"command": "rm -rf /"}
      }
    },
    "intent_id": "your-intent-id",
    "agent_id": "test-agent-001"
  }'
```

**Expected Response:**
```json
{
  "verdict": "BLOCK",
  "decision_id": "...",
  "reason_code": "SCOPE_VIOLATION",
  "explanation": "Action clawdbot.invoke not in scope...",
  "execution": null
}
```

**Key Point:** EDON blocks; Clawdbot never receives the call.

---

## Running Integration Tests

### Automated Tests

**Linux/Mac (Bash):**
```bash
# Set environment variables
export EDON_GATEWAY_URL="http://127.0.0.1:8000"
export EDON_GATEWAY_TOKEN="your-edon-token"
export CLAWDBOT_GATEWAY_URL="http://127.0.0.1:18789"
export CLAWDBOT_GATEWAY_TOKEN="your-clawdbot-token"

# Run tests
python edon_gateway/test_clawdbot_integration.py

# Or with pytest
pytest edon_gateway/test_clawdbot_integration.py -v
```

**Windows (PowerShell):**
```powershell
# Set environment variables
$env:EDON_GATEWAY_URL = "http://127.0.0.1:8000"
$env:EDON_GATEWAY_TOKEN = "your-edon-token"
$env:CLAWDBOT_GATEWAY_URL = "http://127.0.0.1:18789"
$env:CLAWDBOT_GATEWAY_TOKEN = "your-clawdbot-token"

# Run tests
python edon_gateway/test_clawdbot_integration.py

# Or with pytest
pytest edon_gateway/test_clawdbot_integration.py -v
```

### Quick Test Script

**Linux/Mac:**
```bash
chmod +x edon_gateway/quick_test_clawdbot.sh
export CLAWDBOT_GATEWAY_TOKEN="your-token"
export EDON_GATEWAY_TOKEN="your-token"
./edon_gateway/quick_test_clawdbot.sh
```

**Windows (PowerShell):**
```powershell
$env:CLAWDBOT_GATEWAY_TOKEN = "your-token"
$env:EDON_GATEWAY_TOKEN = "your-token"
.\edon_gateway\quick_test_clawdbot.ps1
```

### Manual Testing

1. **Start Clawdbot Gateway** (if not already running)
2. **Start EDON Gateway** (if not already running)
3. **Run sanity check** (Step 1)
4. **Set intent** (Step 3)
5. **Test ALLOW case** (Step 4)
6. **Test BLOCK case** (Step 4)

---

## Architecture

```
┌─────────────┐
│   Agent     │
└──────┬──────┘
       │
       │ POST /execute
       │ (tool: clawdbot)
       ▼
┌─────────────────┐
│  EDON Gateway   │
│                 │
│  1. Validate    │
│  2. Evaluate    │
│  3. Authorize   │
└──────┬──────────┘
       │
       │ If ALLOW:
       │ POST /tools/invoke
       ▼
┌─────────────────┐
│ Clawdbot Gateway│
│                 │
│  1. Validate    │
│  2. Check policy │
│  3. Execute     │
└─────────────────┘
```

**Key Points:**
- EDON is the **outer governor** (blocks before Clawdbot sees the request)
- Clawdbot is the **inner governor** (has its own allowlist/policy)
- Both must allow for execution to occur
- EDON can block risky tools before they reach Clawdbot

---

## Troubleshooting

### Clawdbot Gateway Not Accessible

**Linux/Mac:**
```bash
# Check if Clawdbot Gateway is running
curl http://127.0.0.1:18789/health

# Check token
curl -H "Authorization: Bearer $CLAWDBOT_GATEWAY_TOKEN" \
  http://127.0.0.1:18789/tools/invoke \
  -d '{"tool":"sessions_list","action":"json","args":{}}'
```

**Windows (PowerShell):**
```powershell
# Check if Clawdbot Gateway is running
Invoke-RestMethod -Uri "http://127.0.0.1:18789/health" -Method Get

# Check token
$headers = @{
    "Authorization" = "Bearer $env:CLAWDBOT_GATEWAY_TOKEN"
    "Content-Type" = "application/json"
}
$body = @{
    tool = "sessions_list"
    action = "json"
    args = @{}
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:18789/tools/invoke" `
    -Method Post `
    -Headers $headers `
    -Body $body
```

### EDON Gateway Not Allowing

1. **Check intent scope:** Does it include `"clawdbot": ["invoke"]`?
2. **Check constraints:** Are Clawdbot tools allowlisted?
3. **Check credentials:** Is `CLAWDBOT_GATEWAY_TOKEN` set or credential in database?

### Clawdbot Returns 404

- Tool is not allowlisted in Clawdbot's policy
- This is expected - Clawdbot has its own allowlist
- EDON can still allow it, but Clawdbot will block it

---

## Next Steps

1. **Expand allowlist:** Add more Clawdbot tools (e.g., `web_*`)
2. **Add policy rules:** Implement `allowed_clawdbot_tools` constraint checking in governor
3. **Add monitoring:** Track Clawdbot tool usage in audit logs
4. **Add rate limiting:** Per-tool rate limits for Clawdbot operations

---

*Last Updated: 2025-01-27*
