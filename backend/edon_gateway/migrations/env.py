"""Alembic environment configuration for EDON Gateway.

Reads EDON_DB_URL from environment to determine the database connection.
Falls back to SQLite via EDON_DATABASE_PATH when EDON_DB_URL is not set.

Usage:
    cd backend
    alembic upgrade head                           # apply migrations
    alembic revision --autogenerate -m "desc"      # generate new migration
    EDON_DB_URL=postgresql://... alembic upgrade head  # against PostgreSQL
"""

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ---------------------------------------------------------------------------
# Alembic Config object (gives access to .ini file values)
# ---------------------------------------------------------------------------
config = context.config

# Honour logging config in alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def get_db_url() -> str:
    """Return DB URL from EDON_DB_URL env var, falling back to SQLite."""
    url = os.getenv("EDON_DB_URL", "").strip()
    if url:
        return url
    db_path = os.getenv("EDON_DATABASE_PATH", "edon_gateway.db").strip()
    return f"sqlite:///{db_path}"


# Override the URL from the ini with the one derived from env vars
config.set_main_option("sqlalchemy.url", get_db_url())

# ---------------------------------------------------------------------------
# Import metadata so --autogenerate can detect schema changes.
# We use the SQLAlchemy metadata from the ORM-less migration layer.
# When no ORM metadata is defined, autogenerate won't detect diffs —
# the initial schema is defined manually in versions/001_initial_schema.py.
# ---------------------------------------------------------------------------
try:
    from edon_gateway.persistence.database import metadata as target_metadata  # type: ignore
except (ImportError, AttributeError):
    target_metadata = None


# ---------------------------------------------------------------------------
# Offline mode — emit SQL to stdout without connecting to the DB
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    url = get_db_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode — connect to the DB and apply migrations directly
# ---------------------------------------------------------------------------
def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
