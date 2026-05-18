from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_SUFFIX_RE = re.compile(
    r"(\.db|\.db-wal|\.db-shm|\.sqlite3?|\.jsonl|\.log|\.tsbuildinfo)$"
)

TRACKED_SOURCE_EXCLUDE_RE = re.compile(
    r"(^|/)(docs/|backend/docs/|contracts/|node_modules/|dist/|__pycache__/|\.git/)"
)

TRACKED_FILE_EXCLUDE_RE = re.compile(
    r"(\.md$|\.example$|\.sample$|\.lock$|\.map$|\.min\.js$|\.pyc$|\.jsonl$|\.tsbuildinfo$)"
)

SECRET_PATTERNS = [
    re.compile(r"(?i)\bsk_(?:live|test)_[A-Za-z0-9]{8,}\b"),
    re.compile(r"(?i)\bwhsec_[A-Za-z0-9]{8,}\b"),
    re.compile(r"(?i)\bghp_[A-Za-z0-9]{8,}\b"),
    re.compile(r"(?i)\bxox[baprs]-[A-Za-z0-9-]{8,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\b(?:ANTHROPIC_API_KEY|EDON_API_TOKEN|CLERK_SECRET_KEY|STRIPE_SECRET_KEY|TELEGRAM_BOT_TOKEN|GITHUB_TOKEN|NPM_TOKEN|PYPI_TOKEN|TWINE_PASSWORD|EDON_BOOTSTRAP_SECRET|EDON_DB_ENCRYPTION_KEY)\s*=\s*([^#\s]+)"),
]

PLACEHOLDER_MARKERS = (
    "YOUR_VALUE_HERE",
    "REDACTED",
    "xxx",
    "XXXX",
    "...",
    "YOUR_TOKEN_HERE",
    "CHANGE_ME",
    "change-me",
    "test-token",
    "production-token-change-me",
)

COMMENT_PREFIXES = ("#", "//", "/*", "*", ";")


def _run_git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout


def _tracked_files() -> list[str]:
    output = _run_git("ls-files", "-z")
    return [p for p in output.split("\0") if p]


def _looks_like_placeholder(value: str) -> bool:
    stripped = value.strip().strip('"\'')
    upper = stripped.upper()
    lower = stripped.lower()
    if stripped.startswith("<") and stripped.endswith(">"):
        return True
    if lower.startswith(("your-", "change-", "replace-", "example-", "placeholder-")):
        return True
    return any(marker.upper() in upper for marker in PLACEHOLDER_MARKERS)


def _looks_like_env_accessor(value: str) -> bool:
    lower = value.strip().strip('"\'').lower()
    return lower.startswith(
        (
            "os.environ[",
            "os.environ.get(",
            "os.getenv(",
            "environment.get(",
            "environment[",
            "$env:",
            "$",
            "${",
        )
    )


def _contains_env_accessor(text: str) -> bool:
    lower = text.lower()
    return any(
        marker in lower
        for marker in (
            "os.environ",
            "os.getenv(",
            "environment.get(",
            "environment[",
            "$env:",
            "${",
        )
    )


def _scan_tracked_paths(paths: list[str]) -> list[str]:
    offenders = []
    for path in paths:
        basename = path.rsplit("/", 1)[-1]
        if basename == ".env":
            offenders.append(path)
            continue
        if basename.startswith(".env.") and not basename.endswith((".example", ".sample")):
            offenders.append(path)
            continue
        if basename.startswith("audit.log"):
            offenders.append(path)
            continue
        if FORBIDDEN_SUFFIX_RE.search(path):
            offenders.append(path)
    return offenders


def _scan_source_files(paths: list[str]) -> list[str]:
    findings: list[str] = []
    for rel_path in paths:
        if TRACKED_SOURCE_EXCLUDE_RE.search(rel_path) or TRACKED_FILE_EXCLUDE_RE.search(rel_path):
            continue
        abs_path = REPO_ROOT / rel_path
        if not abs_path.is_file():
            continue
        try:
            text = abs_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line in text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith(COMMENT_PREFIXES):
                continue
            if _contains_env_accessor(line):
                continue
            for pattern in SECRET_PATTERNS:
                for match in pattern.finditer(line):
                    value = match.group(1) if match.lastindex else match.group(0)
                    if _looks_like_env_accessor(value):
                        continue
                    if _looks_like_placeholder(value):
                        continue
                    findings.append(f"{rel_path}:{line.strip()}")
    return findings


def _scan_history(paths: list[str], base_ref: str | None) -> list[str]:
    if not paths or not base_ref:
        return []
    proc = subprocess.run(
        ["git", "log", "--no-merges", "-p", f"{base_ref}..HEAD", "--", *paths],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    findings: list[str] = []
    for line in proc.stdout.splitlines():
        if not line.startswith(("+", "-")):
            continue
        for pattern in SECRET_PATTERNS:
            for match in pattern.finditer(line):
                value = match.group(1) if match.lastindex else match.group(0)
                if _looks_like_env_accessor(value):
                    continue
                if _looks_like_placeholder(value):
                    continue
                findings.append(value)
    return findings


def main() -> int:
    tracked = _tracked_files()

    artifact_hits = _scan_tracked_paths(tracked)
    if artifact_hits:
        print("Tracked artifact paths found:")
        for path in artifact_hits:
            print(f"  - {path}")
        return 1

    source_hits = _scan_source_files(tracked)
    if source_hits:
        print("Potential secret values found in tracked source files:")
        for hit in source_hits:
            print(f"  - {hit}")
        return 1

    risky_paths = [
        "frontend/.env",
        "frontend/.env.production",
        "backend/.env.production",
        "backend/ui/console-ui/.env",
        "backend/edon_gateway/.env",
    ]
    history_hits = _scan_history(risky_paths, os.environ.get("SECRET_AUDIT_BASE_REF"))
    if history_hits:
        print("Potential secret values found in git history for risky config files:")
        for hit in history_hits:
            print(f"  - {hit}")
        return 1

    print("Secret audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
