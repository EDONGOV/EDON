"""EDON Docs Agent — keeps docs/api-reference.md in sync with the codebase.

Reads the git diff of changed backend files, compares against the current
API reference, and rewrites any sections that are stale or missing.

Usage (local):
    git diff HEAD~1 HEAD -- 'backend/edon_gateway/**' | \\
    ANTHROPIC_API_KEY=xxx python -m agents.docs_agent

    # Dry run — shows what would change without writing the file
    git diff HEAD~1 HEAD -- 'backend/edon_gateway/**' | \\
    ANTHROPIC_API_KEY=xxx python -m agents.docs_agent --dry-run

GitHub Actions: see .github/workflows/docs_agent.yml
The workflow writes the diff to a temp file and sets EDON_GIT_DIFF_FILE (not env).
If docs changed, the workflow opens a PR automatically.
"""

from __future__ import annotations

import argparse
import difflib
import os
import sys
from pathlib import Path

try:
    import anthropic
except ModuleNotFoundError:  # optional in unit tests / minimal CI
    anthropic = None

REPO_ROOT = Path(__file__).resolve().parents[2]
API_REF_PATH = REPO_ROOT / "docs" / "api-reference.md"
GOVERNANCE_MODEL_PATH = REPO_ROOT / "docs" / "governance-model.md"
CLINICAL_SAFETY_PATH = REPO_ROOT / "backend" / "edon_gateway" / "clinical_safety.py"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"[file not found: {path}]"


def _get_diff() -> str:
    """Read diff from a file path (CI), EDON_GIT_DIFF env, or stdin.

    Prefer EDON_GIT_DIFF_FILE / EDON_GIT_DIFF_PATH in CI — large diffs must not
    be passed via the environment (Linux ARG_MAX / env size limits).
    """
    for key in ("EDON_GIT_DIFF_FILE", "EDON_GIT_DIFF_PATH"):
        p = os.environ.get(key, "").strip()
        if p:
            fp = Path(p)
            if fp.is_file():
                return fp.read_text(encoding="utf-8").strip()
    diff = os.environ.get("EDON_GIT_DIFF", "").strip()
    if diff:
        return diff
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    return ""


def _anthropic_api_key() -> str:
    return os.getenv("ANTHROPIC_API_KEY", "").strip()


# ── Core ──────────────────────────────────────────────────────────────────────

def run(dry_run: bool = False) -> int:
    diff = _get_diff()
    if not diff:
        print("[docs] No diff provided — nothing to do.")
        return 0

    # Only care about meaningful backend changes
    relevant_markers = [
        "@router.", "def ", "class ", "rule_code", "condition_tool",
        "CLINICAL_SAFETY_RULES", "POLICY_PACKS", "REQUIRED_RULES",
    ]
    if not any(m in diff for m in relevant_markers):
        print("[docs] Diff contains no API/rule changes — skipping.")
        return 0

    print("[docs] Relevant changes detected. Reading current docs...")

    current_api_ref = _read(API_REF_PATH)
    clinical_safety_src = _read(CLINICAL_SAFETY_PATH)

    api_key = _anthropic_api_key()
    if not api_key:
        print("[docs] ANTHROPIC_API_KEY is not set — skipping Claude doc sync.")
        return 0

    if anthropic is None:
        print("[docs] anthropic package is not installed — skipping Claude doc sync.")
        return 0

    client = anthropic.Anthropic(api_key=api_key)

    print("[docs] Sending to Claude for doc update...")

    prompt = f"""You are the docs agent for EDON, an AI governance platform.
Your job is to keep `docs/api-reference.md` accurate and complete.

A developer just pushed code changes. Here is the git diff:

<diff>
{diff[:8000]}
</diff>

Here is the current `docs/api-reference.md`:

<current_docs>
{current_api_ref}
</current_docs>

Here is the current `clinical_safety.py` (regulation rule definitions):

<clinical_safety>
{clinical_safety_src[:4000]}
</clinical_safety>

Tasks:
1. Identify what changed: new routes, modified routes, removed routes, new/changed policy rules
2. Rewrite ONLY the sections of the API reference that are now stale or missing
3. If new regulation rules were added, update the governance model section if present
4. Do NOT change sections that are still accurate
5. Do NOT add marketing fluff — keep the same technical, direct tone

Return the COMPLETE updated `docs/api-reference.md` content.
Start directly with the markdown — no preamble."""

    try:
        msg = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError:
        print("[docs] Anthropic authentication failed — skipping doc sync. Check ANTHROPIC_API_KEY.")
        return 0

    updated_content = str(getattr(msg.content[0], "text", msg.content[0]))

    if updated_content.strip() == current_api_ref.strip():
        print("[docs] No changes needed — docs are already accurate.")
        return 0

    if dry_run:
        diff_lines = list(difflib.unified_diff(
            current_api_ref.splitlines(keepends=True),
            updated_content.splitlines(keepends=True),
            fromfile="docs/api-reference.md (current)",
            tofile="docs/api-reference.md (proposed)",
        ))
        print("[docs] DRY RUN — no files written. Proposed changes:\n")
        print("".join(diff_lines) if diff_lines else "[docs] (no diff lines — content identical after strip)")
        return 0

    API_REF_PATH.write_text(updated_content, encoding="utf-8")
    print(f"[docs] Updated {API_REF_PATH}")
    print("[docs] Done. If running in CI, the workflow will open a PR.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EDON Docs Agent")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show proposed doc changes as a diff without writing the file",
    )
    args = parser.parse_args()
    sys.exit(run(dry_run=args.dry_run))
