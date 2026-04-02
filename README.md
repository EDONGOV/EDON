# EDON Governance Platform

Enterprise AI governance — monorepo.

## Repo Structure

```
edongov/
├── backend/         # FastAPI gateway — governance engine (Python)
├── frontend/        # React SPA — customer dashboard (TypeScript)
├── shared/          # Shared types used by frontend + SDK
├── demos/           # Standalone offline demo apps
├── infrastructure/  # Deploy configs (Render, Fly.io)
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
#   EDON_API_TOKEN=any-secret-you-choose
#   EDON_AUTH_ENABLED=true

# Run
python -m uvicorn edon_gateway.main:app --host 0.0.0.0 --port 8000
```

Gateway is now running at `http://localhost:8000`.  
Health check: `curl http://localhost:8000/health`

### 3. Frontend

```bash
cd frontend
npm install
npm run dev   # http://localhost:8080
```

Open `http://localhost:8080` — you'll be prompted for a token and gateway URL.  
Enter the token you set in `.env` and `http://localhost:8000`.

Or pass them via URL directly:
```
http://localhost:8080/#token=your-token&base=http://localhost:8000
```

### 4. No backend? Use mock mode

The frontend has a built-in mock mode with demo data — no backend needed:

```
http://localhost:8080/#token=demo
```

## Running Tests

```bash
# Backend
cd backend
pip install pytest
EDON_API_TOKEN=test-token EDON_AUTH_ENABLED=false pytest tests/ -v

# Frontend
cd frontend
npm run test
```

## Deployment

| Service | Platform | Config |
|---------|----------|--------|
| Backend | Fly.io | `backend/fly.toml` |
| Frontend | Render | `frontend/render.yaml` |

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
