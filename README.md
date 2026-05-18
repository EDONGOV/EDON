# EDON Governance Platform

Enterprise AI governance — monorepo.

## Repo Structure

```
edongov/
├── backend/         # FastAPI gateway — governance engine (Python)
├── console/         # React governance console
├── shared/          # Shared types and UI helpers
├── demos/           # Standalone offline demo apps
├── docs/            # Architecture and API docs
└── sdk/             # Client SDKs (Python, JavaScript)
```

## Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.11+ |
| Node.js | 18+ |
| npm | 9+ |

## Local Setup

### 1. Clone

```bash
git clone https://github.com/GHOSTCODERRRRAHAHA/edongov.git
cd edongov
```

### 2. Backend

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate        # Mac/Linux
# .venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.gateway.txt

# Configure environment
cp .env.example .env
# Open .env and set at minimum:
#   EDON_API_TOKEN=<strong-random-token>
#   EDON_AUTH_ENABLED=true

# Run
python -m uvicorn edon_gateway.main:app --host 0.0.0.0 --port 8000
```

Gateway is now running at `http://localhost:8000`.  
Health check: `curl http://localhost:8000/health`

### 3. Console

```bash
cd console
npm install
npm run dev   # http://localhost:8080
```

Open the console URL in the browser and select a role-based view.

### 4. No backend? Use mock mode

The console has a built-in mock mode with demo data — no backend needed:

```
http://localhost:8080/#token=demo
```

## Running Tests

```bash
# Backend
cd backend
pip install pytest
EDON_API_TOKEN=<test-only-token> EDON_AUTH_ENABLED=false pytest tests/ -v

# Console
cd console
npm run test
```

## Deployment

| Service | Platform | Config |
|---------|----------|--------|
| Backend | Fly.io | `backend/fly.toml` |
| Console | Static host or local dev | `console/` |

Deploy backend:
```bash
cd backend
fly deploy
```

## Key Docs

- `backend/docs/CONFIGURATION.md` — all env vars explained
- `backend/docs/AUTHENTICATION_METHODS.md` — auth setup
- `backend/docs/DEMO_MODE_GUIDE.md` — running demos
- `backend/docs/FLY_DEPLOY.md` — Fly.io deployment guide
- `docs/repeatable-architecture-standard.md` — invariant runtime, execution binding, and customer pack contract
