from fastapi import Request

from edon_gateway.middleware import auth as auth_module
from edon_gateway.security.sensitive_patterns import scrub_string


def _req_with_headers(headers: dict):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
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
