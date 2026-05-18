"""
Shared fixtures for edon_gateway/test/ suite.

Sets development-mode env vars on every test so the app startup
doesn't refuse to boot because production secrets are missing.
Individual test files can override these with their own monkeypatches.
"""
import pytest
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def _dev_environment(monkeypatch):
    """Put the app in development mode for all tests in this directory."""
    monkeypatch.setenv("EDON_ENV", "development")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("EDON_AUTH_ENABLED", "false")
    monkeypatch.setenv("EDON_CREDENTIALS_STRICT", "false")
    monkeypatch.setenv("EDON_STRICT_FAIL_CLOSED", "false")
    monkeypatch.setenv("EDON_DB_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("EDON_AI_ENABLED", "false")    # never burn credits in tests
    monkeypatch.setenv("EDON_PROBE_ENABLED", "false") # probe needs real policies; disable in tests

    import backend.edon_gateway.config as cfg
    monkeypatch.setattr(cfg.config, "_AUTH_ENABLED", False)
    monkeypatch.setattr(cfg.config, "_ENVIRONMENT", "development")
    monkeypatch.setattr(cfg.config, "_CREDENTIALS_STRICT", False)
