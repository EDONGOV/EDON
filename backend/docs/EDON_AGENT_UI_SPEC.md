# edon-agent-ui — Implementation Spec (Gateway Auth + Status)

The **edon-agent-ui** repo (Vite/React) should implement the following so users can run `docker compose up` for the gateway and use the UI with a single token.

## 1. Gateway settings + auth token

- **Default gateway URL:** `http://localhost:8000` (editable in UI or via env).
- **Token:** User pastes token in UI; store in `localStorage` (e.g. key `edon_api_token` or `edon_token`). Do **not** put token in env or commit it.
- **All API requests:** Include header `X-EDON-TOKEN: <token>` when token is set.

## 2. Connection status indicator (top-level)

- On load and when gateway URL or token changes, call `GET <gateway_url>/health` with header `X-EDON-TOKEN`.
- **States:**
  - **Connected:** HTTP 200 → show “Connected”.
  - **Unauthorized:** HTTP 401 → show “Unauthorized” and prompt user to paste token (or open settings).
  - **Offline / Unreachable:** Network error or non-2xx (other than 401) → show “Offline” or “Unreachable” and suggest checking URL / gateway running.

## 3. Status page/panel

- **Minimal Status view:** Show:
  - Health: from `GET /health` (e.g. “ok: true”).
  - Version: from `GET /version` (fields `version`, `git_sha`).
  - Last checked: timestamp of last successful health/version fetch.

## 4. .env.example (edon-agent-ui)

```bash
# Gateway URL (no trailing slash). Token is pasted in UI, not in env.
VITE_EDON_GATEWAY_URL=http://localhost:8000
```

Token must **not** be in env; user pastes it in the UI.

## 5. README (edon-agent-ui)

- **Run UI against Compose gateway:**
  - Start gateway: `cd edon-gateway && docker compose up --build`.
  - Run UI: `npm run dev` (or `vite`); ensure `VITE_EDON_GATEWAY_URL=http://localhost:8000` (or leave default).
- **Where to paste token:** Settings / Connection panel; token is sent as `X-EDON-TOKEN` on every request.
- **Troubleshooting:**
  - **401 Unauthorized:** Token missing or wrong. Paste the same token set in gateway `.env` as `EDON_API_TOKEN`.
  - **Network error / CORS:** Gateway not running, or wrong URL; ensure gateway has `EDON_CORS_ORIGINS` including UI origin (e.g. `http://localhost:5173`).

## Constraints

- Do **not** weaken gateway auth; `/health` and `/version` require `X-EDON-TOKEN` when `EDON_AUTH_ENABLED=true`.
- Do **not** commit secrets; token is user-provided at runtime and stored only in localStorage (or session) in the browser.
