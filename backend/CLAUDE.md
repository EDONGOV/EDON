# backend — EDON Gateway (FastAPI)

See root `CLAUDE.md` for the full project map.

- **Entry point:** `edon_gateway/main.py`
- **Dev:** `uvicorn edon_gateway.main:app --reload` (port 8000)
- **Tests:** `pytest tests/`

### Adding a new route
1. Create `edon_gateway/routes/your_route.py` with an `APIRouter`
2. Import and register it in `edon_gateway/main.py`

### Adding a new agent
- Place it in `agents/` (standalone) or `edon_gateway/agents/` (gateway-coupled)
- Register it in `agents/__init__.py`
