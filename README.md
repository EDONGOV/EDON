# EDON Governance Platform

Enterprise AI governance — monorepo.

## Structure

```
edongov/
├── frontend/        # React SPA — customer dashboard (edon-agent-ui)
├── backend/         # FastAPI gateway — governance engine
├── demos/           # Offline demo environments
│   ├── healthcare/
│   ├── law/
│   └── logistics/
├── infrastructure/  # Docker, deploy configs (Render, Fly)
├── docs/            # Architecture and API docs
├── sdk/             # Client SDKs (Python, JavaScript)
└── shared/          # Shared types across frontend/backend
```

## Quick Start

```bash
# Backend
cd backend
pip install -r requirements.txt
python -m uvicorn edon_gateway.main:app --host 0.0.0.0 --port 8000

# Frontend
cd frontend
npm install
npm run dev   # http://localhost:8080
```

## Deployment

- Frontend: Render (`infrastructure/render.frontend.yaml`)
- Backend: Render / Fly.dev (`infrastructure/render.backend.yaml`)
