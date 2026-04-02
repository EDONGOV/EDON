# EDON Gateway — Docker Compose

One-command run for the gateway with persisted SQLite and auth.

## Prerequisites

- Docker and Docker Compose
- A token for API auth (you choose the value)

## Steps

### 1. Copy env and set token

```bash
cp .env.example .env
```

Edit `.env` and set:

```bash
EDON_API_TOKEN=your-secret-token
```

(Use any string; this is the token you’ll send in the `X-EDON-TOKEN` header.)

### 2. Start the gateway

```bash
docker compose up --build
```

The gateway listens on `http://localhost:8000`. SQLite data is stored in a Docker volume (`gateway_data`) so it survives restarts.

### 3. Check health (with auth)

```bash
curl -s -H "X-EDON-TOKEN: your-secret-token" http://localhost:8000/health
```

Expected: JSON with `"ok": true` and `"status": "healthy"`.

### 4. Check version

```bash
curl -s -H "X-EDON-TOKEN: your-secret-token" http://localhost:8000/version
```

Expected: `{"version":"1.0.1","git_sha":"unknown"}` (or a real `git_sha` if built with `--build-arg GIT_SHA=...`).

## Build with git SHA

To bake the git commit into the image (for `/version`):

```bash
docker compose build --build-arg GIT_SHA=$(git rev-parse --short HEAD)
docker compose up -d
```

## Env used by Compose

- `env_file: .env` — loads `EDON_API_TOKEN`, etc.
- `EDON_DB_URL=sqlite:////app/data/edon.db` — DB path inside the container (persisted via volume).
- `EDON_AUTH_ENABLED=true` — auth required; UI/tests must send `X-EDON-TOKEN`.
- `EDON_CORS_ORIGINS=http://localhost:5173,...` — so the Vite dev server (edon-agent-ui) can call the API.

## Note on Docker HEALTHCHECK

When `EDON_AUTH_ENABLED=true`, the image’s `HEALTHCHECK` calls `/health` without a token, so it may get 401 and report the container as unhealthy. The gateway still runs; use `curl` with `X-EDON-TOKEN` to verify health.

## Troubleshooting

- **401 on /health or /version** — Send the header: `-H "X-EDON-TOKEN: <token>"` (token must match `EDON_API_TOKEN` in `.env`).
- **DB not persisting** — Ensure you’re using the Compose volume (`gateway_data`); don’t remove the volume if you want to keep data.
- **CORS errors from UI** — Ensure `EDON_CORS_ORIGINS` in Compose includes the UI origin (e.g. `http://localhost:5173`).
