"""EDON Gateway persistence layer.

Selects the appropriate database backend based on DATABASE_URL env var:
- postgresql:// or postgres:// → PostgreSQLDatabase (connection-pooled, scales to 100 agents)
- otherwise → SQLite Database (default, for dev/single-node deployments)
"""

import os
import logging

logger = logging.getLogger(__name__)

from .database import Database, get_db as _sqlite_get_db
from ..config import config

__all__ = ["Database", "get_db"]

_db_instance = None


def get_db():
    """Get global database instance.

    Checks DATABASE_URL env var:
    - If set to postgresql:// or postgres://, returns PostgreSQLDatabase
    - Otherwise returns SQLite Database (default)
    """
    global _db_instance
    if _db_instance is not None:
        return _db_instance

    database_url = os.getenv("DATABASE_URL", "").strip()

    if database_url.startswith(("postgresql://", "postgres://")):
        try:
            from .postgres import PostgreSQLDatabase
            logger.info("Using PostgreSQL database: %s", database_url.split("@")[-1])
            _db_instance = PostgreSQLDatabase(database_url)
        except Exception as exc:
            if config.is_production():
                raise RuntimeError(
                    "Failed to connect to PostgreSQL in production. "
                    "Refusing to fall back to SQLite."
                ) from exc
            logger.error(
                "Failed to connect to PostgreSQL (%s). Falling back to SQLite: %s",
                database_url.split("@")[-1],
                exc,
            )
            _db_instance = _sqlite_get_db()
    else:
        if config.is_production():
            raise RuntimeError("DATABASE_URL must be configured for PostgreSQL in production")
        _db_instance = _sqlite_get_db()

    return _db_instance
