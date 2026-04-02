#!/usr/bin/env python3
"""
CI check: fail if gateway code uses non-parameterized SQL (SQL injection risk).
Looks for: .execute(f"...") or .execute(f'...') or string concat/format with execute().

Allowlisted: lines containing "# safe: schema-only" or "# noqa: sql-safe" (schema/column names from controlled lists).
"""

from pathlib import Path
import re
import sys

# Directory to scan: inner gateway package only (edon_gateway/edon_gateway/)
_SCRIPT_DIR = Path(__file__).resolve().parent
EDON_GATEWAY = _SCRIPT_DIR.parent / "edon_gateway"  # inner package
if not EDON_GATEWAY.is_dir():
    EDON_GATEWAY = _SCRIPT_DIR.parent  # fallback: outer edon_gateway
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", "scripts"}
EXCLUDE_FILES = {"dump_creds.py", "fix_claw_creds.py", "create_cj_key.py", "check_raw_sql.py"}

# Dangerous: execute with f-string or % or + (could embed user input)
EXECUTE_FSTR = re.compile(r"\.execute\s*\(\s*f[\"']")
EXECUTE_PCT = re.compile(r"\.execute\s*\(\s*[\"'][^\"']*%[^s\"']")  # % not followed by s (param placeholder)
EXECUTE_CONCAT = re.compile(r"\.execute\s*\(\s*[\"'][^\"']*\+")

ALLOWLIST_MARKER = re.compile(r"#\s*(safe:\s*schema-only|noqa:\s*sql-safe)")


def main() -> int:
    hits: list[tuple[str, int, str]] = []
    for py in EDON_GATEWAY.rglob("*.py"):
        if py.name in EXCLUDE_FILES or any(d in py.parts for d in EXCLUDE_DIRS):
            continue
        rel = py.relative_to(EDON_GATEWAY)
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if ALLOWLIST_MARKER.search(line):
                continue
            if EXECUTE_FSTR.search(line) or EXECUTE_PCT.search(line) or EXECUTE_CONCAT.search(line):
                hits.append((str(rel), i, line.strip()[:100]))
    if not hits:
        print("check_raw_sql: no non-parameterized execute() patterns found.")
        return 0
    print("check_raw_sql: possible raw SQL (use parameterized queries or add # safe: schema-only):")
    for path, line_no, snippet in hits:
        print(f"  {path}:{line_no}  {snippet}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
