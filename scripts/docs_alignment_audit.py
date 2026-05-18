"""Lightweight docs alignment audit for EDON.

This check keeps user-facing docs aligned with the current governance posture:
- no shared/default production token guidance
- no SQLite-as-production guidance
- repeatable-architecture language stays visible in the top-level docs
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


RULES: dict[str, dict[str, list[str]]] = {
    "README.md": {
        "require": [
            "console/",
            "docs/repeatable-architecture-standard.md",
        ],
        "forbid": [
            "any-secret-you-choose",
            "your-secret-token",
            "frontend/",
        ],
    },
    "backend/docs/CONFIGURATION.md": {
        "require": [
            "Use a unique secret from your secrets manager",
            "Development/demo only. Set `DATABASE_URL` to PostgreSQL for enterprise production.",
        ],
        "forbid": [
            "your-secret-token",
        ],
    },
    "backend/docs/DOCKER.md": {
        "require": [
            "local development or single-node testing",
            "Production must use PostgreSQL-backed storage",
        ],
        "forbid": [
            "your-secret-token",
            "Use any string",
            "persisted SQLite",
        ],
    },
    "backend/docs/GET_YOUR_TOKEN.md": {
        "require": [
            "EDON does not ship a shared production token",
            "tenant API key",
        ],
        "forbid": [
            "your-secret-token",
            "Use any string",
            "No token needed!",
        ],
    },
    "backend/docs/OPERATIONS_RUNBOOK.md": {
        "require": [
            "SQLite (development only) / PostgreSQL (required for production)",
            "DATABASE_URL",
        ],
        "forbid": [
            "SQLite (default)",
            "prefer `EDON_DB_URL` for PostgreSQL",
        ],
    },
    "docs/architecture.md": {
        "require": [
            "Repeatable architecture standard",
            "Decision Kernel",
            "same kernel, same decision record, same audit proof, same enforcement semantics",
        ],
        "forbid": [
            "SQLite (single machine) -> PostgreSQL (required for production, attach via fly postgres)",
        ],
    },
    "docs/EDON_FEATURES_INDEX.md": {
        "require": [
            "Repeatable architecture standard",
            "execution binding",
            "customer packs",
        ],
        "forbid": [],
    },
    "docs/repeatable-architecture-standard.md": {
        "require": [
            "same kernel, same decision record, same audit proof, same enforcement semantics",
            "no approved `DecisionRecord`, no valid execution token",
        ],
        "forbid": [],
    },
}


def main() -> int:
    errors: list[str] = []

    for relpath, rule in RULES.items():
        path = ROOT / relpath
        text = path.read_text(encoding="utf-8")

        for needle in rule["require"]:
            if needle not in text:
                errors.append(f"{relpath}: missing required text: {needle}")

        for needle in rule["forbid"]:
            if needle in text:
                errors.append(f"{relpath}: found forbidden text: {needle}")

    if errors:
        print("Docs alignment audit failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Docs alignment audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
