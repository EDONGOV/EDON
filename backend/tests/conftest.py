import pytest
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def _dev_environment(monkeypatch):
    monkeypatch.setenv("EDON_ENV", "development")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("EDON_AUTH_ENABLED", "false")
    monkeypatch.setenv("EDON_CREDENTIALS_STRICT", "false")
    monkeypatch.setenv("EDON_STRICT_FAIL_CLOSED", "false")
    monkeypatch.setenv("EDON_DB_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("EDON_AI_ENABLED", "false")    # never burn credits in tests
    monkeypatch.setenv("EDON_PROBE_ENABLED", "false") # probe needs real policies; disable in tests
