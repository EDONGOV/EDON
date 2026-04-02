#!/usr/bin/env python3
"""Encryption key rotation script for EDON Gateway.

Re-encrypts all encrypted audit payloads from OLD_KEY → NEW_KEY atomically.

Usage:
    OLD_KEY=<base64-fernet-key> NEW_KEY=<base64-fernet-key> python scripts/rotate_encryption_key.py

Environment variables:
    OLD_KEY               Old Fernet key (base64, 32 bytes)
    NEW_KEY               New Fernet key (base64, 32 bytes)
    EDON_DATABASE_PATH    Path to SQLite DB (default: edon_gateway.db)
    EDON_DB_URL           sqlite:///path or postgresql://... (takes precedence)
    DRY_RUN               Set to 'true' to preview without writing changes

Generates a new Fernet key if needed:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import os
import sys
import json
import sqlite3
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("key_rotation")


def _load_fernet(key_b64: str):
    from cryptography.fernet import Fernet, InvalidToken  # noqa: F401
    return Fernet(key_b64.encode() if isinstance(key_b64, str) else key_b64)


def _resolve_db_path() -> Path:
    url = os.getenv("EDON_DB_URL", "").strip()
    if url.startswith("sqlite:///"):
        return Path(url.replace("sqlite:///", "", 1))
    return Path(os.getenv("EDON_DATABASE_PATH", "edon_gateway.db"))


def _is_postgresql() -> bool:
    url = os.getenv("DATABASE_URL", "").strip()
    return url.startswith(("postgresql://", "postgres://"))


def rotate_sqlite(db_path: Path, old_fernet, new_fernet, dry_run: bool) -> int:
    """Rotate keys for SQLite database. Returns count of rows rotated."""
    if not db_path.exists():
        logger.error("Database not found: %s", db_path)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, action_params FROM audit_events WHERE is_payload_encrypted = 1"
        )
        rows = cursor.fetchall()

        if not rows:
            logger.info("No encrypted rows found. Nothing to rotate.")
            return 0

        logger.info("Found %d encrypted rows to rotate.", len(rows))

        rotated = 0
        errors = 0

        for row in rows:
            row_id = row["id"]
            try:
                # Decrypt with old key
                plaintext = old_fernet.decrypt(row["action_params"].encode()).decode("utf-8")
                # Re-encrypt with new key
                new_ciphertext = new_fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

                if not dry_run:
                    cursor.execute(
                        "UPDATE audit_events SET action_params = ? WHERE id = ?",
                        (new_ciphertext, row_id),
                    )
                rotated += 1

                if rotated % 500 == 0:
                    logger.info("  Rotated %d/%d rows...", rotated, len(rows))

            except Exception as exc:
                logger.error("  Failed to rotate row id=%s: %s", row_id, exc)
                errors += 1

        if errors:
            logger.error("%d rows failed to rotate. Rolling back.", errors)
            conn.rollback()
            sys.exit(1)

        if dry_run:
            logger.info("DRY RUN: would rotate %d rows (no changes written)", rotated)
            conn.rollback()
        else:
            conn.commit()
            logger.info("Committed %d rotated rows.", rotated)

        return rotated

    finally:
        conn.close()


def rotate_postgresql(database_url: str, old_fernet, new_fernet, dry_run: bool) -> int:
    """Rotate keys for PostgreSQL database. Returns count of rows rotated."""
    try:
        import psycopg2
    except ImportError:
        logger.error("psycopg2 not installed. Run: pip install psycopg2-binary")
        sys.exit(1)

    conn = psycopg2.connect(database_url)
    conn.autocommit = False

    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, action_params FROM audit_events WHERE is_payload_encrypted = TRUE"
        )
        rows = cursor.fetchall()

        if not rows:
            logger.info("No encrypted rows found. Nothing to rotate.")
            return 0

        logger.info("Found %d encrypted rows to rotate.", len(rows))

        rotated = 0
        errors = 0

        for row_id, action_params in rows:
            try:
                plaintext = old_fernet.decrypt(action_params.encode()).decode("utf-8")
                new_ciphertext = new_fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

                if not dry_run:
                    cursor.execute(
                        "UPDATE audit_events SET action_params = %s WHERE id = %s",
                        (new_ciphertext, row_id),
                    )
                rotated += 1

                if rotated % 500 == 0:
                    logger.info("  Rotated %d/%d rows...", rotated, len(rows))

            except Exception as exc:
                logger.error("  Failed to rotate row id=%s: %s", row_id, exc)
                errors += 1

        if errors:
            logger.error("%d rows failed to rotate. Rolling back.", errors)
            conn.rollback()
            sys.exit(1)

        if dry_run:
            logger.info("DRY RUN: would rotate %d rows (no changes written)", rotated)
            conn.rollback()
        else:
            conn.commit()
            logger.info("Committed %d rotated rows.", rotated)

        return rotated

    finally:
        conn.close()


def main():
    old_key = os.getenv("OLD_KEY", "").strip()
    new_key = os.getenv("NEW_KEY", "").strip()
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"

    if not old_key:
        logger.error("OLD_KEY environment variable is required.")
        logger.error("Generate a key: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")
        sys.exit(1)

    if not new_key:
        logger.error("NEW_KEY environment variable is required.")
        sys.exit(1)

    if old_key == new_key:
        logger.error("OLD_KEY and NEW_KEY are the same. Nothing to rotate.")
        sys.exit(1)

    # Validate keys
    try:
        old_fernet = _load_fernet(old_key)
        new_fernet = _load_fernet(new_key)
    except Exception as exc:
        logger.error("Invalid Fernet key: %s", exc)
        sys.exit(1)

    if dry_run:
        logger.info("=== DRY RUN MODE: No data will be modified ===")

    logger.info("Starting encryption key rotation...")

    if _is_postgresql():
        database_url = os.getenv("DATABASE_URL", "")
        logger.info("Using PostgreSQL backend")
        count = rotate_postgresql(database_url, old_fernet, new_fernet, dry_run)
    else:
        db_path = _resolve_db_path()
        logger.info("Using SQLite backend: %s", db_path)
        count = rotate_sqlite(db_path, old_fernet, new_fernet, dry_run)

    if dry_run:
        logger.info("DRY RUN complete. %d rows would be rotated.", count)
    else:
        logger.info("Key rotation complete. %d rows rotated.", count)
        logger.info(
            "IMPORTANT: Update EDON_DB_ENCRYPTION_KEY in your environment to the new key. "
            "Old key is no longer valid for new writes."
        )


if __name__ == "__main__":
    main()
