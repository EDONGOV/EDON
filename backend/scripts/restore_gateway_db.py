#!/usr/bin/env python3
"""Restore SQLite or PostgreSQL backups for EDON Gateway."""

from __future__ import annotations

import argparse
import gzip
import os
import shutil
from pathlib import Path
from subprocess import run, CalledProcessError


def _resolve_sqlite_path() -> Path:
    db_url = (os.getenv("EDON_DB_URL") or "").strip()
    if db_url.startswith("sqlite:///"):
        return Path(db_url.replace("sqlite:///", "", 1))
    return Path(os.getenv("EDON_DATABASE_PATH", "edon_gateway.db"))


def _restore_sqlite(backup_path: Path) -> Path:
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup not found: {backup_path}")
    target = _resolve_sqlite_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup_path, target)
    return target


def _restore_postgres(backup_path: Path) -> None:
    db_url = (os.getenv("DATABASE_URL") or "").strip()
    if not db_url.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("DATABASE_URL must be postgresql://... or postgres://...")
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup not found: {backup_path}")

    if backup_path.suffix == ".gz":
        with gzip.open(backup_path, "rb") as fh:
            try:
                run(["psql", db_url], check=True, stdin=fh)
            except CalledProcessError as exc:
                raise RuntimeError(f"psql restore failed: {exc}") from exc
        return

    with backup_path.open("rb") as fh:
        try:
            run(["psql", db_url], check=True, stdin=fh)
        except CalledProcessError as exc:
            raise RuntimeError(f"psql restore failed: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore EDON Gateway database backup.")
    parser.add_argument("backup_file", help="Path to backup file")
    parser.add_argument(
        "--mode",
        choices=["auto", "sqlite", "postgres"],
        default="auto",
        help="Restore mode. auto uses DATABASE_URL when present.",
    )
    args = parser.parse_args()

    backup_path = Path(args.backup_file)
    mode = args.mode
    if mode == "auto":
        database_url = (os.getenv("DATABASE_URL") or "").strip()
        mode = "postgres" if database_url.startswith(("postgresql://", "postgres://")) else "sqlite"

    if mode == "postgres":
        _restore_postgres(backup_path)
        print("postgres restore complete")
    else:
        target = _restore_sqlite(backup_path)
        print(str(target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
