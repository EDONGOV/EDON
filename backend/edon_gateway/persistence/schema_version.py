"""Schema version tracking for database migrations."""

from pathlib import Path
from typing import Optional
import sqlite3
from .database import Database


SCHEMA_VERSION = "1.0.0"


def get_current_schema_version(db: Database) -> Optional[str]:
    """Get current schema version from database."""
    try:
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
            """)
            
            cursor.execute("SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1")
            result = cursor.fetchone()
            return result[0] if result else None
    except Exception:
        return None


def set_schema_version(db: Database, version: str):
    """Set schema version in database."""
    from datetime import datetime, UTC

    is_postgres = type(db).__name__ == 'PostgreSQLDatabase'

    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
        """)

        if is_postgres:
            cursor.execute("""
                INSERT INTO schema_version (version, applied_at)
                VALUES (%s, %s)
                ON CONFLICT (version) DO UPDATE SET applied_at = EXCLUDED.applied_at
            """, (version, datetime.now(UTC).isoformat()))
        else:
            cursor.execute("""
                INSERT OR REPLACE INTO schema_version (version, applied_at)
                VALUES (?, ?)
            """, (version, datetime.now(UTC).isoformat()))
        conn.commit()


def check_schema_version(db: Database) -> bool:
    """Check if database schema is up to date."""
    current = get_current_schema_version(db)
    if current is None:
        # First run - set initial version
        set_schema_version(db, SCHEMA_VERSION)
        return True
    
    return current == SCHEMA_VERSION
