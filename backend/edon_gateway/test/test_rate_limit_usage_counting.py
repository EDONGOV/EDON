from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from edon_gateway.middleware.rate_limit import RateLimitMiddleware


class _StubDb:
    def __init__(self):
        self.usage_calls = []

    def increment_tenant_usage(self, tenant_id: str, amount: int):
        self.usage_calls.append((tenant_id, amount))

    def get_tenant(self, tenant_id: str):
        """Stub: return a truthy record so middleware proceeds to increment_tenant_usage."""
        return {"id": tenant_id}

    def get_counter(self, _key: str) -> int:
        return 0

    def increment_counter(self, _key: str, _amount: int):
        return 1


def _build_client(stub_db: _StubDb) -> TestClient:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/audit/query")
    async def audit_query(request: Request):
        request.state.tenant_id = "tenant_test"
        return JSONResponse({"ok": True})

    @app.post("/v1/action")
    async def v1_action(request: Request):
        request.state.tenant_id = "tenant_test"
        return JSONResponse({"ok": True})

    client = TestClient(app)
    return client


def test_refresh_read_endpoints_do_not_increment_usage(monkeypatch):
    stub_db = _StubDb()
    monkeypatch.setattr("edon_gateway.middleware.rate_limit.get_db", lambda: stub_db)
    monkeypatch.setattr("edon_gateway.persistence.get_db", lambda: stub_db)
    client = _build_client(stub_db)

    response = client.get("/audit/query", headers={"X-EDON-TOKEN": "test-token"})
    assert response.status_code == 200
    assert stub_db.usage_calls == []


def test_decision_endpoints_increment_usage_once(monkeypatch):
    stub_db = _StubDb()
    monkeypatch.setattr("edon_gateway.middleware.rate_limit.get_db", lambda: stub_db)
    monkeypatch.setattr("edon_gateway.persistence.get_db", lambda: stub_db)
    client = _build_client(stub_db)

    response = client.post("/v1/action", headers={"X-EDON-TOKEN": "test-token"}, json={"x": 1})
    assert response.status_code == 200
    assert stub_db.usage_calls == [("tenant_test", 1)]
