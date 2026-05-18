# Deployment Readiness — Launch Checklist

This checklist is the production hardening gate. It is not a claim that the platform is enterprise-ready by default.

---

## What’s working

- Backend live on Fly.io (`edon-gatewaybk.fly.dev`)
- Clerk auth, Stripe billing, governance engine, audit chain
- Sentinel-core portal: sign up, subscribe, get token
- Agent UI dashboard with real data
- **API key creation in production** — `POST /billing/api-keys` is allowed for authenticated tenants (no longer gated by DEMO_MODE). Users can create and rotate keys from the dashboard.
- **Quick start** — Account → Quick start has a TypeScript snippet showing how to call `/v1/action` with `X-EDON-TOKEN`.

---

## Critical — fix before marketing

### 1. ~~No API key creation in production~~ ✅ Fixed

- **Done:** Production gate removed in `edon_gateway/billing/bootstrap.py`. Authenticated users (X-EDON-TOKEN or Clerk) can call `POST /billing/api-keys` to create new keys. List and revoke were already auth-only.

### 2. SQLite + 2 machines = data split

- **Issue:** With `min_machines_running = 2` on Fly, two instances use two SQLite files. Data is not shared.
- **Options:**
  - **A. Single machine:** In `fly.toml`, set `[http_service] min_machines_running = 1` (or omit). No code change.
  - **B. PostgreSQL:** Set `DATABASE_URL=postgresql://...` and use the existing Postgres adapter (gateway uses it when `DATABASE_URL` is a postgres URL). Both machines share one DB.
  - **C. Fly Volumes + affinity:** Use a shared volume and affinity so both replicas use the same SQLite file (more ops work).

**Recommendation:** For enterprise launch, switch to PostgreSQL. SQLite remains acceptable only for local development and single-node demos.

### 3. ~~No governance SDK for JS/TS~~ ✅ Mitigated

- **Done:** Quick start tab on the Account page includes a copy-paste TypeScript/JavaScript snippet that shows how to call the gateway (`/v1/action` with `X-EDON-TOKEN`). Covers the “how do I call EDON?” gap without a full npm package.

---

## Important (not blocking day one)

| Item | Action |
|------|--------|
| **CORS wildcard** | In production, set `EDON_CORS_ORIGINS=https://edoncore.com,https://www.edoncore.com` (and agent UI / console domains if different). Do not use `*` in prod. |
| **Database backend** | Production must use PostgreSQL. SQLite is not an enterprise production store. |
| **Readiness evidence** | Use `GET /health/dependencies` to verify database backend, schema version, and production control flags before go-live. |
| **SDK on PyPI** | Publish the Python SDK: `cd sdk/python && python -m build && twine upload dist/*` (after configuring PyPI credentials). |
| **dev@edon.ai → edoncore.com** | ✅ Fixed in `sdk/python/setup.py`: `author_email="dev@edoncore.com"`. |
| **API key rotation in dashboard** | Create/revoke are available via API; ensure the portal Account/Billing UI exposes “Create key” and “Revoke” if desired. |

---

## Recommended path to launch

1. **Data consistency:** Set `DATABASE_URL` to PostgreSQL and verify the database is healthy on startup.
2. **API keys:** ✅ Enabled in production for authenticated tenants.
3. **TS snippet:** ✅ On Quick start page in sentinel-core.
4. **Python SDK:** Publish to PyPI when ready (`twine upload`).
5. **CORS:** Set `EDON_CORS_ORIGINS` to explicit origins in production (see `.env.example`).

---

## Env reference (production)

- **fly.toml** already sets `ENVIRONMENT=production`, `EDON_ENV=production`, and `EDON_CORS_ORIGINS` (no wildcard). The gateway now fails fast if production checks are incomplete.
- Set secrets via `fly secrets set` (never commit .env). **One-shot from .env:** run `.\scripts\fly_secrets_from_env.ps1` from `edon_gateway`; it reads `.env` and sets all of the following in one go:
  - `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `CLERK_SECRET_KEY`, `EDON_API_TOKEN`
  - Optional: `EDON_CREDENTIALS_STRICT`, `EDON_ALLOW_ENV_TOKEN_IN_PROD`

```bash
# Lock CORS to your domains (no wildcard) — fly.toml sets this for Fly
EDON_CORS_ORIGINS=https://edoncore.com,https://www.edoncore.com,https://agent.edoncore.com

# Single DB for all instances (if using Postgres)
DATABASE_URL=postgresql://user:password@host:5432/edon
```

See `.env.example` and `STRIPE_LIVE_SETUP.md` for full Stripe and billing setup.
