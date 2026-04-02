# EDON Proxy Runner - Drop-in Integration Guide

**Goal:** Replace Clawdbot Gateway calls with EDON Gateway in 5 minutes.

---

## Quick Migration (5 Minutes)

### Before (Direct Clawdbot Gateway)

```python
import requests

response = requests.post(
    "http://clawdbot-gateway:18789/tools/invoke",
    headers={
        "Authorization": "Bearer your-clawdbot-token",
        "Content-Type": "application/json"
    },
    json={
        "tool": "sessions_list",
        "action": "json",
        "args": {}
    }
)
```

### After (EDON Proxy)

```python
import requests

response = requests.post(
    "http://edon-gateway:8000/clawdbot/invoke",  # Changed URL
    headers={
        "X-EDON-TOKEN": "your-edon-token",  # Changed header
        "Content-Type": "application/json",
        "X-Agent-ID": "your-agent-id"  # Optional but recommended
    },
    json={
        "tool": "sessions_list",  # Same body!
        "action": "json",
        "args": {}
    }
)
```

**That's it!** Zero code changes except URL and token header.

---

## Using the Client Library

### Option 1: Use EDON Proxy Client (Recommended)

```python
from edon_gateway.clients.clawdbot_proxy_client import EDONClawdbotProxyClient

# Initialize client
client = EDONClawdbotProxyClient(
    edon_gateway_url="http://edon-gateway:8000",
    edon_token="your-edon-token",
    agent_id="your-agent-id"
)

# Invoke tool (same API as Clawdbot client!)
result = client.invoke(
    tool="sessions_list",
    action="json",
    args={}
)

if result["ok"]:
    print("Success:", result["result"])
else:
    print("Blocked:", result["error"])
    print("EDON verdict:", result["edon_verdict"])
    print("Explanation:", result["edon_explanation"])
```

### Option 2: Command Line Tool

```bash
# Set environment variables
export EDON_GATEWAY_URL="http://127.0.0.1:8000"
export EDON_GATEWAY_TOKEN="your-token"

# Invoke tool
python -m edon_gateway.clients.clawdbot_proxy_client \
    --tool sessions_list \
    --action json \
    --args '{}'
```

---

## Request Schema

The `/clawdbot/invoke` endpoint accepts **exactly** the same request schema as Clawdbot Gateway:

```json
{
  "tool": "sessions_list",
  "action": "json",
  "args": {},
  "sessionKey": "optional-session-key"
}
```

**Headers:**
- `X-EDON-TOKEN`: Required - Your EDON Gateway authentication token
- `X-Agent-ID`: Optional - Agent identifier for audit logging (default: "clawdbot-agent")
- `X-Intent-ID`: Optional - Intent ID for governance (uses default if not provided)

---

## Response Schema

The response matches Clawdbot's format, with EDON transparency fields added:

### Success Response

```json
{
  "ok": true,
  "result": {
    "sessions": [...]
  },
  "edon_verdict": "ALLOW",
  "edon_explanation": "Action approved: within scope, constraints satisfied, risk acceptable"
}
```

### Blocked Response

```json
{
  "ok": false,
  "error": "Clawdbot tool 'web_execute' not in allowed list. Allowed: ['sessions_list']",
  "edon_verdict": "BLOCK",
  "edon_explanation": "Clawdbot tool 'web_execute' not in allowed list. Allowed: ['sessions_list']"
}
```

---

## How It Works

```
┌─────────────┐
│   Your      │
│   Agent     │
└──────┬──────┘
       │
       │ POST /clawdbot/invoke
       │ { tool, action, args }
       ▼
┌─────────────────┐
│  EDON Gateway   │
│                 │
│  1. Convert to  │
│     EDON Action │
│                 │
│  2. Evaluate    │
│     Governance  │
│                 │
│  3. If ALLOW →  │
│     Call        │
│     Clawdbot    │
│                 │
│  4. If BLOCK →  │
│     Return      │
│     Error       │
│     (Clawdbot   │
│     never       │
│     receives    │
│     call)       │
└──────┬──────────┘
       │
       │ (Only if ALLOW)
       ▼
┌─────────────────┐
│ Clawdbot Gateway│
│  /tools/invoke  │
└─────────────────┘
```

---

## Migration Checklist

- [ ] Set up EDON Gateway (see `QUICK_START_CLAWDBOT.md`)
- [ ] Configure Clawdbot credentials in EDON database
- [ ] Set up intent/policy for your agent
- [ ] Change URL: `clawdbot-gateway:18789/tools/invoke` → `edon-gateway:8000/clawdbot/invoke`
- [ ] Change header: `Authorization: Bearer <clawdbot-token>` → `X-EDON-TOKEN: <edon-token>`
- [ ] Add header: `X-Agent-ID: <your-agent-id>` (optional but recommended)
- [ ] Test with a benign tool (e.g., `sessions_list`)
- [ ] Verify blocked tools return proper error messages

---

## Benefits

1. **Zero Code Changes** - Same request schema, just change URL
2. **Governance** - All tool calls go through EDON policy
3. **Audit Trail** - Every call is logged and queryable
4. **Credential Security** - Clawdbot tokens stored in EDON, not exposed to agents
5. **Transparency** - Response includes EDON verdict and explanation

---

## Troubleshooting

### "Service unavailable: No credentials found"

**Problem:** EDON Gateway is in strict mode but credentials not configured.

**Solution:**
```bash
# Set credentials via API
curl -X POST http://edon-gateway:8000/credentials/set \
  -H "X-EDON-TOKEN: your-token" \
  -H "Content-Type: application/json" \
  -d '{
    "credential_id": "clawdbot-001",
    "tool_name": "clawdbot",
    "credential_type": "gateway",
    "credential_data": {
      "gateway_url": "http://clawdbot-gateway:18789",
      "gateway_token": "your-clawdbot-token"
    }
  }'
```

### "Invalid authentication token"

**Problem:** EDON token incorrect or missing.

**Solution:**
- Check `EDON_GATEWAY_TOKEN` environment variable
- Verify token matches gateway configuration
- Ensure `X-EDON-TOKEN` header is set correctly

### "Clawdbot tool 'X' not in allowed list"

**Problem:** Tool not in intent's `allowed_clawdbot_tools` constraint.

**Solution:**
- Update intent to include the tool in `allowed_clawdbot_tools`
- Or use a different intent that allows the tool

---

## Next Steps

- **Policy Packs** - Use pre-configured policy modes (Personal Safe, Work Safe, Ops/Admin)
- **Safety UX** - View intent, decisions, and audit trail in web UI
- **Anti-Bypass** - Configure network gating or token hardening

---

*Last Updated: 2025-01-27*
