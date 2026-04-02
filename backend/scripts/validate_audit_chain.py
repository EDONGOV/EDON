#!/usr/bin/env python3
"""Validate audit-chain integrity and return non-zero on failure."""

from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from edon_gateway.persistence import get_db


def main() -> int:
    db = get_db()
    result = db.verify_audit_chain()
    print(json.dumps(result, indent=2))
    if not result.get("valid"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
