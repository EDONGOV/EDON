"""Alembic environment for EDON Gateway.

Supports both SQLite (dev) and PostgreSQL (production).

Database URL resolution order:
  1. DATABASE_URL environment variable (PostgreSQL: postgresql://...)
  2. EDON_DB_URL environment variable (SQLite: sqlite:///path)
  3. EDON_DATABASE_PATH environment variable (bare file path)
  4. Default: sqlite:///edon_gateway.db
"""
from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool, text

# Alembic Config object — provides access to values within alembic.ini
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _get_database_url() -> str:
    """Resolve the database URL from environment variables."""
    # PostgreSQL takes priority (production)
    pg_url = os.getenv("DATABASE_URL", "").strip()
    if pg_url and pg_url.startswith("postgresql"):
        # Heroku/Fly.io sometimes gives postgres:// — normalise to postgresql://
        return pg_url.replace("postgres://", "postgresql://", 1)

    # SQLite — resolve from EDON_DB_URL or EDON_DATABASE_PATH
    sqlite_url = os.getenv("EDON_DB_URL", "").strip()
    if sqlite_url and sqlite_url.startswith("sqlite:///"):
        return sqlite_url

    db_path = os.getenv("EDON_DATABASE_PATH", "edon_gateway.db").strip()
    return f"sqlite:///{db_path}"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL, no DB connection needed)."""
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=None,  # raw SQL migrations — no ORM metadata
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite"),  # SQLite requires batch mode for ALTER
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (requires a live DB connection)."""
    url = _get_database_url()
    is_sqlite = url.startswith("sqlite")

    connect_args = {}
    if is_sqlite:
        connect_args["check_same_thread"] = False

    engine = create_engine(
        url,
        poolclass=pool.NullPool,  # no connection pooling for migrations
        connect_args=connect_args,
    )

    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=None,  # raw SQL migrations — no ORM metadata
            render_as_batch=is_sqlite,  # SQLite requires batch mode for ALTER TABLE
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
