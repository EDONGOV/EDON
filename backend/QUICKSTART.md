# EDON Gateway — Quick Start (<10 min)

Get the gateway running and verify connect → apply → invoke in under 10 minutes.

## 1. Install

From the `edon_gateway` directory (or repo root with `edon_gateway` as the package):

```bash
pip install -r requirements.txt
```

## 2. Set env vars

Copy the example env and set a token (required when auth is enabled):

```bash
cp .env.example .env
# Edit .env: set EDON_API_TOKEN=your-secret-token
# For local dev, EDON_AUTH_ENABLED=true and EDON_CREDENTIALS_STRICT=false are typical.
```

Minimal dev set (or export these):

```bash
export EDON_AUTH_ENABLED=true
export EDON_API_TOKEN=test-token
export EDON_CREDENTIALS_STRICT=false
export EDON_CORS_ORIGINS=http://localhost:5173
```

## 3. Start the gateway

```bash
# From edon_gateway directory (so PYTHONPATH includes the package)
python -m uvicorn edon_gateway.main:app --host 0.0.0.0 --port 8000
```

Or with module run:

```bash
python -c "import uvicorn; uvicorn.run('edon_gateway.main:app', host='0.0.0.0', port=8000)"
```

Expected: server starts; you see `Uvicorn running on http://0.0.0.0:8000`.

## 4. Health check

```bash
curl -s http://localhost:8000/health
```

Expected: JSON with `"status": "healthy"` (and version, governor info).

With auth enabled:

```bash
curl -s -H "X-EDON-TOKEN: test-token" http://localhost:8000/health
```

## 5. Connect Clawdbot

Point the gateway at your Clawdbot (or a stub URL for testing). Replace the URL if your Clawdbot runs elsewhere.

```bash
curl -s -X POST http://localhost:8000/integrations/clawdbot/connect \
  -H "Content-Type: application/json" \
  -H "X-EDON-TOKEN: test-token" \
  -d '{
    "base_url": "http://127.0.0.1:18789",
    "auth_mode": "password",
    "secret": "your-clawdbot-secret",
    "probe": false
  }'
```

Expected: `{"connected":true,"credential_id":"...","base_url":"...","auth_mode":"password","message":"Clawdbot connected. Credential saved."}`

## 6. Apply a policy pack

```bash
curl -s -X POST http://localhost:8000/policy-packs/clawdbot_safe/apply \
  -H "Content-Type: application/json" \
  -H "X-EDON-TOKEN: test-token" \
  -d '{}'
```

Expected: JSON with `intent_id`, e.g. `{"intent_id":"intent_clawdbot_safe_...","policy_pack":"clawdbot_safe",...}`. Copy `intent_id` for the next step.

## 7. Invoke a tool

Use the `intent_id` from the previous response:

```bash
curl -s -X POST http://localhost:8000/clawdbot/invoke \
  -H "Content-Type: application/json" \
  -H "X-EDON-TOKEN: test-token" \
  -H "X-Intent-ID: <PASTE_INTENT_ID_HERE>" \
  -H "X-Agent-ID: my-agent" \
  -d '{"tool":"sessions_list","action":"json","args":{},"sessionKey":"main"}'
```

Expected: JSON with `ok: true` and a result if Clawdbot is reachable; or `ok: false` with an error (e.g. connection refused) and, when the gateway considers the downstream unavailable, HTTP 503 with the same envelope.

---

## Summary

| Step        | Command / action                          |
|------------|--------------------------------------------|
| Install    | `pip install -r requirements.txt`          |
| Env        | `EDON_AUTH_ENABLED=true`, `EDON_API_TOKEN=test-token`, etc. |
| Start      | `uvicorn edon_gateway.main:app --host 0.0.0.0 --port 8000` |
| Health     | `GET /health` with `X-EDON-TOKEN` if auth on |
| Connect    | `POST /integrations/clawdbot/connect` with base_url, secret |
| Apply      | `POST /policy-packs/clawdbot_safe/apply` → get `intent_id` |
| Invoke     | `POST /clawdbot/invoke` with `X-Intent-ID`, `X-Agent-ID`, body |

The gateway has no built-in UI. Use **edon-agent-ui** for a user-facing console; it talks to this API over HTTP with the same auth header (`X-EDON-TOKEN`).
