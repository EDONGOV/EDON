import pytest


def test_get_db_refuses_sqlite_without_postgres_in_production(monkeypatch):
    monkeypatch.setenv("EDON_ENV", "production")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    import edon_gateway.persistence as persistence

    monkeypatch.setattr(persistence, "_db_instance", None)

    with pytest.raises(RuntimeError, match="DATABASE_URL must be configured"):
        persistence.get_db()


def test_get_db_refuses_sqlite_fallback_when_postgres_connection_fails_in_production(monkeypatch):
    monkeypatch.setenv("EDON_ENV", "production")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/edon")

    import edon_gateway.persistence as persistence
    import edon_gateway.persistence.postgres as postgres_mod

    class BrokenPostgres:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("connection failed")

    monkeypatch.setattr(persistence, "_db_instance", None)
    monkeypatch.setattr(postgres_mod, "PostgreSQLDatabase", BrokenPostgres)

    with pytest.raises(RuntimeError, match="Failed to connect to PostgreSQL in production"):
        persistence.get_db()
