# EDON + Clawdbot - 5 Minute Setup

## Two Commands, Maximum

### 1. Connect Clawdbot

```bash
curl -X POST http://localhost:8000/integrations/clawdbot/connect \
  -H "X-EDON-TOKEN: your-token" \
  -H "Content-Type: application/json" \
  -d '{
    "base_url": "http://127.0.0.1:18789",
    "auth_mode": "password",
    "secret": "local-dev",
    "probe": true
  }'
```

**Response:**
```json
{
  "connected": true,
  "credential_id": "clawdbot_gateway",
  "base_url": "http://127.0.0.1:18789",
  "auth_mode": "password",
  "message": "Clawdbot connected. Credential saved."
}
```

### 2. Point Clawdbot to EDON

Update your Clawdbot configuration to use EDON Gateway:

**Before:**
```
POST http://127.0.0.1:18789/tools/invoke
```

**After:**
```
POST http://localhost:8000/clawdbot/invoke
```

**Headers:**
- `X-EDON-TOKEN: your-token` (required)
- `X-Agent-ID: your-agent-id` (optional)

That's it! Clawdbot now routes through EDON for governance.

## Optional: Apply Policy Pack

```bash
curl -X POST http://localhost:8000/policy-packs/clawdbot_safe/apply \
  -H "X-EDON-TOKEN: your-token"
```

This sets a default intent so you don't need `X-Intent-ID` header.

## Check Status

```bash
curl http://localhost:8000/account/integrations \
  -H "X-EDON-TOKEN: your-token"
```

**Response:**
```json
{
  "clawdbot": {
    "connected": true,
    "base_url": "http://127.0.0.1:18789",
    "auth_mode": "password",
    "last_ok_at": "2026-01-28T19:40:12Z",
    "last_error": null,
    "active_policy_pack": "clawdbot_safe",
    "default_intent_id": "intent_abc123"
  }
}
```

## What Happens Now

1. ✅ Clawdbot calls `POST /clawdbot/invoke` (instead of Clawdbot Gateway)
2. ✅ EDON evaluates each tool call through governance
3. ✅ If ALLOW → EDON forwards to Clawdbot Gateway
4. ✅ If BLOCK → EDON returns error (Clawdbot never receives call)
5. ✅ All decisions logged in audit trail

## Troubleshooting

**Error: "Connection validation failed"**
- Check Clawdbot Gateway is running on `http://127.0.0.1:18789`
- Verify `secret` matches your Clawdbot Gateway auth token

**Error: "Missing authentication token"**
- Add `X-EDON-TOKEN` header with your EDON API token

**Error: "No intent configured"**
- Apply a policy pack: `POST /policy-packs/clawdbot_safe/apply`
- Or include `X-Intent-ID` header with a valid intent_id

## Production Hardening: Enable Network Gating

For production deployments, enable network gating to prevent agents from bypassing EDON Gateway:

```bash
# Set environment variable
export EDON_NETWORK_GATING=true
```

**What it does:**
- Validates at startup that Clawdbot Gateway is not publicly reachable
- Ensures Clawdbot Gateway is on loopback/private network only
- Fails fast with clear error if bypass risk detected

**Setup options:**
1. **Docker**: Use `docker-compose.network-isolation.yml` (see `NETWORK_ISOLATION_GUIDE.md`)
2. **Firewall**: Restrict port 18789 to EDON Gateway IP only (see `scripts/setup-firewall-isolation.sh`)
3. **Reverse Proxy**: Use nginx with IP whitelist (see `nginx/clawdbot-isolation.conf`)

**Verification:**
Check bypass risk status:
```bash
curl http://localhost:8000/account/integrations \
  -H "X-EDON-TOKEN: your-token"
```

Response includes `bypass_risk` and `clawdbot_reachability` fields. If `bypass_risk` is "high", follow the `recommendation` to fix.
