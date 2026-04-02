#!/usr/bin/env python3
"""Create SQLite or PostgreSQL backups for EDON Gateway."""

from __future__ import annotations

import argparse
import gzip
import os
import shutil
import sqlite3
from datetime import datetime, UTC
from pathlib import Path


def _resolve_sqlite_path() -> Path:
    db_url = (os.getenv("EDON_DB_URL") or "").strip()
    if db_url.startswith("sqlite:///"):
        return Path(db_url.replace("sqlite:///", "", 1))
    return Path(os.getenv("EDON_DATABASE_PATH", "edon_gateway.db"))


def _backup_sqlite(out_dir: Path) -> Path:
    src = _resolve_sqlite_path()
    if not src.exists():
        raise FileNotFoundError(f"SQLite DB not found: {src}")

    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    dest = out_dir / f"edon_gateway_sqlite_{ts}.db"

    # Online-safe backup API.
    src_conn = sqlite3.connect(str(src))
    dest_conn = sqlite3.connect(str(dest))
    try:
        src_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        src_conn.close()
    return dest


def _backup_postgres(out_dir: Path) -> Path:
    db_url = (os.getenv("DATABASE_URL") or "").strip()
    if not db_url.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("DATABASE_URL must be postgresql://... or postgres://...")

    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    sql_path = out_dir / f"edon_gateway_postgres_{ts}.sql"
    gz_path = out_dir / f"edon_gateway_postgres_{ts}.sql.gz"

    # Use pg_dump if available.
    from subprocess import run, CalledProcessError

    try:
        with sql_path.open("wb") as fh:
            run(["pg_dump", db_url], check=True, stdout=fh)
    except CalledProcessError as exc:
        raise RuntimeError(f"pg_dump failed: {exc}") from exc

    with sql_path.open("rb") as src, gzip.open(gz_path, "wb") as dst:
        shutil.copyfileobj(src, dst)
    sql_path.unlink(missing_ok=True)
    return gz_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup EDON Gateway database.")
    parser.add_argument("--output-dir", default="backups", help="Backup output directory")
    parser.add_argument(
        "--mode",
        choices=["auto", "sqlite", "postgres"],
        default="auto",
        help="Backup mode. auto uses DATABASE_URL when present.",
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    mode = args.mode
    if mode == "auto":
        database_url = (os.getenv("DATABASE_URL") or "").strip()
        mode = "postgres" if database_url.startswith(("postgresql://", "postgres://")) else "sqlite"

    backup_path = _backup_postgres(out_dir) if mode == "postgres" else _backup_sqlite(out_dir)
    print(str(backup_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
