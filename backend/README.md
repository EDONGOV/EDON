# EDON Gateway (Backend)

FastAPI service that sits between AI agents and their tools, enforcing governance policies on every action.

```
AI Agent → POST /v1/action → EDON Gateway → verdict (ALLOW / BLOCK / ESCALATE)
```

## Quick Start

See the [root README](../README.md) for full setup. Short version:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.gateway.txt
cp .env.example .env   # set EDON_API_TOKEN
python -m uvicorn edon_gateway.main:app --host 0.0.0.0 --port 8000
```

## Structure

```
backend/
├── edon_gateway/        # Main application package
│   ├── main.py          # FastAPI app + route registration
│   ├── governor.py      # Core governance decision engine
│   ├── routes/          # API route handlers
│   ├── middleware/      # Auth, rate limiting, RBAC, validation
│   ├── policy/          # Policy engine (rules, storage, evaluation)
│   ├── security/        # Anti-bypass, encryption, anomaly detection
│   ├── connectors/      # External tool integrations (email, github, etc.)
│   ├── persistence/     # SQLite / PostgreSQL database layer
│   ├── billing/         # Stripe integration
│   └── ai/              # AI-powered advisory features
├── tests/               # pytest test suite
├── scripts/             # Utility and ops scripts
├── docs/                # Reference docs
├── Dockerfile           # Production image (used by Fly.io)
├── fly.toml             # Fly.io deploy config
├── requirements.gateway.txt  # Production dependencies (used by Docker)
└── requirements.txt          # Development dependencies (includes pytest)
```

## Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/action` | Evaluate an agent action — returns verdict |
| `GET` | `/health` | Health check |
| `GET` | `/stats` | Decision counts and latency |
| `GET` | `/audit/query` | Decision history with filters |
| `GET` | `/agents` | Registered agent fleet |
| `GET` | `/policy-packs` | Available policy packs |
| `POST` | `/policy-packs/{name}/apply` | Activate a policy pack |

All requests require header: `X-EDON-TOKEN: <your-token>`

## Environment Variables

See `docs/CONFIGURATION.md` for the full list. Minimum required:

```env
EDON_API_TOKEN=your-secret-token
EDON_AUTH_ENABLED=true
```

## Running Tests

```bash
EDON_API_TOKEN=test-token EDON_AUTH_ENABLED=false pytest tests/ -v
```

## Deployment

```bash
fly deploy   # must run from backend/ directory
```

See `docs/FLY_DEPLOY.md` for full instructions.
