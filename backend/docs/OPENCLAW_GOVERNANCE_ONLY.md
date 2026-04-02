# Use EDON Governance with Your Agent

**Goal:** Keep your existing agent and backend (OpenClaw, Clawdbot, or any tools/invoke-style API). Add EDON in front so every tool call goes through EDON (allow/block + audit). No need to adopt EDON tools (Brave, Gmail, etc.) — **governance only**. Works with **any agent**, not just one product.

---

## How simple is it?

**One URL change + one header change** in your agent. Same request body. EDON Gateway then:

1. Accepts your existing tools/invoke-style request.
2. Runs the governor (policy + intent).
3. If **ALLOW** → proxies to your connected agent backend and returns the result.
4. If **BLOCK** → returns an error and never calls your backend (you get `edon_verdict` and `edon_explanation`).
5. Every call is written to the audit log.

So: **your agent talks to EDON instead of directly to your backend**. EDON is a drop-in proxy with governance.

---

## Steps (governance only)

### 1. Get an EDON token

- **Hosted:** Sign up / log in and get an API token for your tenant.
- **Self‑hosted:** Run the gateway, create a tenant and API key (or use `EDON_API_TOKEN` in dev). Use that as `X-EDON-TOKEN`.

### 2. Connect your agent backend

EDON must be able to call your existing agent gateway when it allows a request.

**Option A – API (recommended, per-tenant):**

Connect your backend (same API whether you use OpenClaw, Clawdbot, or a custom gateway):

```bash
curl -X POST "https://edon-gateway.fly.dev/integrations/clawdbot/connect" \
  -H "X-EDON-TOKEN: YOUR_EDON_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "base_url": "https://your-agent-gateway.example.com",
    "auth_mode": "token",
    "secret": "YOUR_BACKEND_TOKEN",
    "credential_id": "agent_gateway",
    "probe": true
  }'
```

*(Under the hood this is still `clawdbot/connect`; it works for any compatible tools/invoke backend.)*

**Option B – Env (single-tenant / dev):**  
Set `CLAWDBOT_GATEWAY_URL` and `CLAWDBOT_GATEWAY_TOKEN` on the EDON Gateway.

### 3. Apply a policy pack (so EDON has an intent)

`/agent/invoke` requires an intent (what tools are allowed, etc.). Easiest is to apply a pack:

```bash
curl -X POST "https://edon-gateway.fly.dev/policy-packs/clawdbot_safe/apply" \
  -H "X-EDON-TOKEN: YOUR_EDON_TOKEN"
```

(Or use another pack from `GET /policy-packs` and tune later.)

### 4. Point your agent at EDON

In your agent config or code, change the **tool-invoke** call to use the **universal agent endpoint**:

| Before (direct to your backend) | After (via EDON governance) |
|---------------------------------|-----------------------------|
| `POST https://your-backend/tools/invoke` | `POST https://edon-gateway.fly.dev/agent/invoke` |
| `Authorization: Bearer <backend-token>` | `X-EDON-TOKEN: <your-edon-token>` |
| Same body: `{ "tool", "action", "args", "sessionKey" }` | **Same body** — no change |

Use **`/agent/invoke`** so users see it’s for any agent. Aliases (no code change needed): `/edon/invoke`, `/clawdbot/invoke`.

Optional but useful: send `X-Agent-ID` (and optionally `X-Intent-ID`) so audit and policies can distinguish agents/intents.

---

## Summary

| Step | What you do |
|------|------------------|
| 1 | Get an EDON tenant token |
| 2 | Connect your agent backend with EDON (`POST /integrations/clawdbot/connect` or env) |
| 3 | Apply a policy pack (`POST /policy-packs/clawdbot_safe/apply`) |
| 4 | In the agent: URL → `…/agent/invoke`, header → `X-EDON-TOKEN` |

**Code change:** Only the **URL** and **auth header**; request/response body stay the same. Blocked calls get `ok: false` plus `edon_verdict` and `edon_explanation`. So yes — **anyone with their own agent can use “only” the EDON governance system**, and it’s that simple.
