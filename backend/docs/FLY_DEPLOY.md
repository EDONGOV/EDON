# EDON Gateway on Fly.io

**Current gateway URL:** **https://edon-gateway.fly.dev** (app `edon-gateway`).

Use this URL for provisioning, the Telegram worker, and the Agent UI. The **edonclaw** app is unchanged (still running OpenClaw); if you want to move the gateway to edonclaw.fly.dev later, use `fly.edonclaw.toml` and the steps in the optional section below.

---

## Optional later: Use edonclaw.fly.dev for the gateway

When you want to run the EDON Gateway on the existing **edonclaw** app (replacing OpenClaw there):

1. Deploy: `fly deploy -a edonclaw -c fly.edonclaw.toml`
2. Set secrets: `fly secrets set EDON_API_TOKEN=... EDON_TELEGRAM_BOT_SECRET=... -a edonclaw`
3. Point provision, Telegram worker, and Agent UI at `https://edonclaw.fly.dev`

A volume `edon_gateway_data` in region **dfw** already exists for the edonclaw app.

---

## Set secrets (required for auth and Telegram)

From the `edon_gateway` directory:

```powershell
fly secrets set EDON_API_TOKEN="<your-token>" -a edon-gateway
fly secrets set EDON_TELEGRAM_BOT_SECRET="<your-bot-secret>" -a edon-gateway
```

Optional (for Clawdbot, Stripe, etc.):

```powershell
fly secrets set CLAWDBOT_GATEWAY_URL="https://edonclaw.fly.dev" -a edon-gateway
fly secrets set CLAWDBOT_GATEWAY_TOKEN="<token>" -a edon-gateway
```

Get your token from `edon_gateway/edon_gateway/.env` (EDON_API_TOKEN). After setting secrets, the app will restart automatically.

## Provision credentials to this gateway

Point provision script at the new URL:

```powershell
cd edon_gateway
$env:EDON_GATEWAY_URL = 'https://edon-gateway.fly.dev'
.\provision_credentials.ps1
```

## Update Telegram bot and Console to use this gateway

- **edon-agent (Telegram):** In Cloudflare Worker vars/secrets, set `EDON_GATEWAY_URL` to `https://edon-gateway.fly.dev` (or set in wrangler.toml and redeploy).
- **Agent UI / Console:** Set the gateway URL to `https://edon-gateway.fly.dev` in env or settings.

## Useful commands

- **Status:** `fly status -a edon-gateway`
- **Logs:** `fly logs -a edon-gateway`
- **SSH:** `fly ssh console -a edon-gateway`
- **Scale:** `fly scale count 1 -a edon-gateway`
