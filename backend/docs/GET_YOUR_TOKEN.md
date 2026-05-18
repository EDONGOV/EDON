# How to Get Your EDON Gateway API Token

## Token policy

EDON does not ship a shared production token. Use a unique secret for local
gateway auth, or use tenant-scoped credentials for production access.

## Production options

### Option 1: Clerk JWT

For production deployments that use Clerk, authenticate with a Clerk-issued JWT
and set `CLERK_SECRET_KEY` plus issuer/audience configuration as required by
your deployment.

### Option 2: Tenant API key

For tenant-scoped access, create an API key through the billing / key-management
surface exposed by your deployment.

## Local development

If you are running the gateway locally and want token auth enabled:

```powershell
# In .env
EDON_AUTH_ENABLED=true
EDON_API_TOKEN=<strong-random-token>
```

Then send the same value in the `X-EDON-TOKEN` header when calling the gateway.

If you do not need auth during local development, disable it explicitly:

```powershell
EDON_AUTH_ENABLED=false
```

## Demo mode

Demo mode may expose a separate non-production token or mock path. Keep that
token isolated to local testing and never reuse it in production.

## Quick check

To confirm whether auth is enabled, inspect the gateway configuration from the
project root:

```powershell
cd backend
python -c "from edon_gateway.config import config; print(f'Auth Enabled: {config.AUTH_ENABLED}')"
```

## Next steps

1. Decide whether your deployment uses Clerk JWTs or tenant API keys.
2. Set a unique gateway token only for local development and test harnesses.
3. Keep production secrets in a secrets manager, not in the repository or docs.
