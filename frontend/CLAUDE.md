# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
npm run dev          # Start dev server at http://localhost:8080
npm run build        # Production build → dist/
npm run build:dev    # Dev-mode build
npm run lint         # ESLint
npm run test         # Run tests once (vitest)
npm run test:watch   # Run tests in watch mode
npm run preview      # Preview production build locally
```

## Architecture Overview

**What it is**: A React + TypeScript SPA — the paid customer dashboard for EDON, an AI governance platform. Users monitor AI agent activity and configure security policies in real-time.

**Data flow**: User → Agent Console (this UI) → EDON Gateway API (FastAPI/Python, port 8000) → AI Agents

**Tech stack**: React 18, TypeScript, Vite, Tailwind CSS, shadcn-ui (Radix), React Router v6, TanStack React Query, Recharts, Framer Motion, Sonner (toasts), Zod + React Hook Form.

## Routing & Auth

Routes are defined in `src/App.tsx`. Unauthenticated users are redirected to `<AccessGate>` unless on `/settings`, `/quickstart`, or `/demo`.

Auth tokens are read from (in priority order): URL hash `#token=...&base=...` → URL params `?token=...&base=...` → localStorage. Hash params are preferred since they're never sent to servers. Keys stored in localStorage: `edon_token`, `edon_session_token`, `edon_api_key`, `edon_api_base`.

## State Management

No external state library — uses React Context + localStorage.

- **`src/lib/api.ts`** — EDON Gateway API client. Reads base URL from localStorage (`edon_api_base` / `EDON_BASE_URL`) or `VITE_EDON_GATEWAY_URL`. Default prod URL: `https://edon-gateway.fly.dev`. Supports mock mode via `edon_mock_mode` localStorage key (disabled by default).
- **`src/lib/dashboardContext.ts`** — Builds system prompts for the AI chat sidebar from live dashboard data (metrics, decisions, policies, gateway health). Central source of truth for the chat assistant.
- **`src/lib/workspaceProfile.ts`** — Multi-domain workspace system with 7 domain types (ai_agents, industrial, drones, humanoids, medical, edge, swarm). Controls feature flags and admin vs. customer views. Keys: `edon_workspace_profile`, `edon_active_domains`, `edon_is_admin`, `edon_preview_mode`.

## Gateway API Contract

All requests to the EDON Gateway must include `X-EDON-TOKEN: <token>` header. Optionally `X-Agent-ID` and `X-Intent-ID`.

**Key endpoints the UI calls:**

| Endpoint | Purpose |
|---|---|
| `GET /health` | Gateway health + component status |
| `GET /metrics` | Prometheus-format metrics |
| `GET /stats` | JSON stats (decision counts, latency) |
| `GET /audit/query` | Decision history with filters (agent_id, verdict, date range) |
| `GET /intent/get` | Active intent contract (scope, constraints, risk_level) |
| `GET /policy-packs` | Available policy packs |
| `POST /policy-packs/{name}/apply` | Activate a policy pack |
| `GET /agents` | Registered agent fleet |
| `GET /agents/{id}/stats` | Per-agent time-series stats (30d) |
| `POST /v1/action` | Evaluate an action (used in demo/testing) |

**Policy pack names** (backend identifiers): `casual_user`, `market_analyst`, `ops_commander`, `founder_mode`, `helpdesk`, `autonomy_mode`.

**Decision verdicts**: `ALLOW`, `BLOCK`, `ESCALATE`, `DEGRADE`, `PAUSE`, `ERROR`

**Reason codes**: `APPROVED`, `SCOPE_VIOLATION`, `RISK_TOO_HIGH`, `DATA_EXFIL`, `OUT_OF_HOURS`, `NEED_CONFIRMATION`, `LOOP_DETECTED`, `RATE_LIMIT`, `PROMPT_INJECTION`, `ANOMALY_DETECTED`

**Decision response shape:**
```json
{
  "action_id": "uuid",
  "verdict": "ALLOW",
  "reason_code": "APPROVED",
  "explanation": "...",
  "safe_alternative": {},
  "escalation_question": "...",
  "escalation_options": [{"id": "allow_once", "label": "..."}],
  "policy_snapshot_hash": "sha256..."
}
```

## Local Dev Setup (Full Stack)

The backend lives at `C:\Users\cjbig\Desktop\EDON\edon-cav-engine\edon_gateway`.

```bash
# Backend (Python/FastAPI)
pip install -r requirements.txt
# Set in edon_gateway/.env:
#   EDON_API_TOKEN=your-secret-token
#   EDON_CORS_ORIGINS=http://localhost:8080
#   EDON_AUTH_ENABLED=true
python -m uvicorn edon_gateway.main:app --host 0.0.0.0 --port 8000

# Frontend (this repo)
npm run dev   # http://localhost:8080
# Then set token + base URL in Settings or via URL:
# http://localhost:8080/#token=your-secret-token&base=http://localhost:8000
```

For demo/testing without a live backend, set `edon_mock_mode=true` in localStorage (or `VITE_EDON_MOCK_MODE=true`).

## Styling

- Dark mode by default, toggled via `.dark` class on `<html>`. Colors defined as HSL CSS variables in `src/index.css`.
- Primary accent: green (`hsl(142 70% 45%)`). Chart colors: green=allowed, red=blocked, orange=confirm.
- All custom animations (fade-in, slide-in, pulse-glow, shimmer) are in `tailwind.config.ts`.
- Path alias: `@/` → `src/`

## Key Component Patterns

- `src/components/ui/` — shadcn-ui base components (never modify these directly; regenerate via CLI if needed).
- `src/components/` — Custom app components. The AI chat UI spans `ChatShell`, `ChatSidebar`, and `ChatTrigger`.
- `src/pages/` — One file per route. `AdminPanel.tsx` is EDON-team-only; `DemoMode.tsx` is for demos/testing.

## Environment Variables

```env
VITE_EDON_GATEWAY_URL=http://localhost:8000   # Gateway API base (required for dev)
VITE_EDON_API_TOKEN=<token>                  # Auth token (dev/demo only)
VITE_EDON_MOCK_MODE=false                    # Enable synthetic mock data
```

Tokens can also be passed at runtime via URL: `http://localhost:8080/#token=...&base=...&email=...`

## Deployment

- Production: `https://agent.edoncore.com` (Render.com)
- Build command: `npm ci && npm run build`
- Publish directory: `dist`
- Requires SPA rewrite rule: `/*` → `/index.html`
