import asyncio

from starlette.responses import Response
from fastapi import Request

from edon_gateway.middleware import auth as auth_module
from edon_gateway.security.sensitive_patterns import scrub_string


def _req_with_headers(headers: dict):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [(k.lower().encode("utf-8"), v.encode("utf-8")) for k, v in headers.items()],
    }
    return Request(scope)


def test_log_scrubber_redacts_edon_token_formats():
    raw = 'X-EDON-TOKEN: edon_abcdef1234567890 and {"X-EDON-TOKEN":"edon-prod-secret"} and bearer sk-live-like'
    scrubbed = scrub_string(raw)
    assert "edon_abcdef1234567890" not in scrubbed
    assert "edon-prod-secret" not in scrubbed
    assert "X-EDON-TOKEN: [REDACTED]" in scrubbed


def test_get_token_from_header_prefers_x_edon_token():
    request = _req_with_headers(
        {
            "X-EDON-TOKEN": "token-from-header",
            "Authorization": "Bearer token-from-bearer",
        }
    )
    assert auth_module.get_token_from_header(request) == "token-from-header"


def test_verify_token_blocks_env_fallback_in_production(monkeypatch):
    # Config.is_production() creates a new Config() which reads from os.environ, so patch env
    monkeypatch.setenv("EDON_AUTH_ENABLED", "true")
    monkeypatch.setenv("EDON_ALLOW_ENV_TOKEN_IN_PROD", "false")
    monkeypatch.setenv("EDON_ENV", "production")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("EDON_API_TOKEN", "prod-token")
    # Force config to re-read (singleton may already be created)
    from edon_gateway.config import Config
    monkeypatch.setattr(auth_module, "config", Config())

    is_valid, tenant = auth_module.verify_token("prod-token")
    assert is_valid is False
    assert tenant is None


def test_token_binding_rejects_replay_without_matching_agent(monkeypatch):
    monkeypatch.setenv("EDON_AUTH_ENABLED", "true")
    monkeypatch.setenv("EDON_TOKEN_BINDING_ENABLED", "true")

    from edon_gateway.config import Config

    monkeypatch.setattr(auth_module, "config", Config())
    monkeypatch.setattr(auth_module, "verify_token", lambda _token: (True, {"tenant_id": "tenant-1", "status": "active", "plan": "pro"}))
    monkeypatch.setattr(auth_module, "_is_brute_force_locked", lambda _ip: False)
    monkeypatch.setattr(auth_module, "_record_failed_auth", lambda _ip: None)

    class _DB:
        def __init__(self):
            self.bound = "agent-001"
            self.calls = []

        def get_agent_id_for_token(self, _token):
            return self.bound

        def bind_token_to_agent(self, token, agent_id):
            self.calls.append(("bind", token, agent_id))

        def update_token_last_used(self, token):
            self.calls.append(("last_used", token))

        def get_tenant(self, tenant_id):
            return {"id": tenant_id, "status": "active", "plan": "pro"}

        def get_tenant_usage(self, tenant_id, period=None):
            return 0

        def get_ip_allowlist(self, tenant_id):
            return []

    db = _DB()
    import edon_gateway.persistence as persistence_pkg
    monkeypatch.setattr(persistence_pkg, "get_db", lambda: db)

    request = _req_with_headers({
        "X-EDON-TOKEN": "token-123",
        "X-Agent-ID": "agent-002",
    })

    async def _call_next(_request):
        return Response("ok")

    middleware = auth_module.AuthMiddleware(app=lambda scope, receive, send: None)
    response = asyncio.run(middleware.dispatch(request, _call_next))

    assert response.status_code == 401
    assert "different agent" in response.body.decode("utf-8").lower()
