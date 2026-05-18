"""EDON Self-Governing Code Agent.

Accepts natural language instructions, translates them into bounded code changes
using Claude, governs every action through EDON before executing, and opens a
GitHub PR for human review.

Safety constraints (inherited from code_agent.py):
  - Will only modify files in ALLOWED_PATHS
  - Will never write to auth, billing, DB schema, or encryption code
  - Every file read/write is governed before execution (fail-open)
  - Never pushes directly to master — always creates a feature branch + PR

Usage (from routes/codex.py):
    result = await run_code_task(task_id, instruction, agent_id="voice-codex")
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

import httpx

from ..logging_config import get_logger

logger = get_logger(__name__)

_ANTHROPIC_API = "https://api.anthropic.com/v1"
_MODEL         = "claude-sonnet-4-6"
_AGENT_ID      = "edon-codex"
_GITHUB_API    = "https://api.github.com"

# Only these paths may be modified — same as code_agent.py safety list
_ALLOWED_PATHS = {
    "backend/edon_gateway/clinical_safety.py",
    "backend/edon_gateway/policies.py",
    "backend/agents/incident_agent.py",
    "backend/tests/",
    "backend/edon_gateway/policy/engine.py",
    "backend/edon_gateway/governor.py",
}


# ── Task state ─────────────────────────────────────────────────────────────────

@dataclass
class CodeTaskResult:
    task_id: str
    instruction: str
    status: str = "pending"   # pending | running | done | failed | blocked
    started_at: str = ""
    finished_at: str = ""
    plan: str = ""
    files_changed: list[str] = field(default_factory=list)
    pr_url: str = ""
    summary: str = ""
    error: Optional[str] = None
    governed: bool = True


_tasks: dict[str, CodeTaskResult] = {}


def get_task(task_id: str) -> Optional[dict]:
    t = _tasks.get(task_id)
    return asdict(t) if t else None


def list_tasks(limit: int = 20) -> list[dict]:
    tasks = sorted(_tasks.values(), key=lambda t: t.started_at, reverse=True)
    return [asdict(t) for t in tasks[:limit]]


# ── Governance helper ──────────────────────────────────────────────────────────

def _gov_sync(action_type: str, parameters: dict, stated_intent: str) -> bool:
    """Run a governance check (sync, used in thread executor)."""
    try:
        import sys
        repo_root = Path(__file__).resolve().parents[3]
        if str(repo_root / "backend") not in sys.path:
            sys.path.insert(0, str(repo_root / "backend"))
        from agents.self_govern import gov_check
        decision = gov_check(
            agent_id=_AGENT_ID,
            action_type=action_type,
            parameters=parameters,
            stated_intent=stated_intent,
        )
        return bool(decision)
    except Exception as exc:
        logger.warning("[codex] gov_check failed: %s — fail-open", exc)
        return True


async def _gov(action_type: str, parameters: dict, stated_intent: str) -> bool:
    return await asyncio.to_thread(_gov_sync, action_type, parameters, stated_intent)


# ── Claude planning ───────────────────────────────────────────────────────────

_SYSTEM = """You are the EDON self-governing code agent. You receive a natural language instruction
and produce a precise JSON plan for safe code changes.

CONSTRAINTS:
- You may ONLY modify files in the following list:
  {allowed_paths}
- Never touch auth, billing, DB schema, security/crypto, or infra files
- Produce minimal, targeted changes — no refactoring, no style changes
- Each change must include: file_path, action (read_current | replace_lines | append_lines), and content

Respond ONLY with a JSON object:
{{
  "summary": "one sentence describing what will be done",
  "changes": [
    {{
      "file_path": "backend/...",
      "action": "replace_lines",
      "search": "exact lines to find",
      "replacement": "new lines to insert"
    }}
  ]
}}

If the instruction is ambiguous, unsafe, or outside allowed paths, respond with:
{{"summary": "BLOCKED: reason", "changes": []}}
"""


async def _plan_changes(instruction: str) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"summary": "ANTHROPIC_API_KEY not set", "changes": []}

    allowed = "\n  ".join(_ALLOWED_PATHS)
    system  = _SYSTEM.replace("{allowed_paths}", allowed)

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{_ANTHROPIC_API}/messages",
            headers={
                "x-api-key":         api_key,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
            json={
                "model":      _MODEL,
                "max_tokens": 2048,
                "system":     system,
                "messages": [{"role": "user", "content": instruction}],
            },
        )

    if resp.status_code != 200:
        raise RuntimeError(f"Claude API error {resp.status_code}")

    data = resp.json()
    text = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            text = block["text"]
            break

    # Extract JSON from response (may be wrapped in markdown)
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return json.loads(match.group())
    return {"summary": "Failed to parse plan", "changes": []}


# ── File apply ────────────────────────────────────────────────────────────────

def _apply_change_sync(change: dict) -> tuple[bool, str]:
    """Apply one planned change to disk. Returns (success, message)."""
    file_path = change.get("file_path", "")
    action    = change.get("action", "")
    repo_root = Path(__file__).resolve().parents[3]
    full_path = repo_root / file_path

    # Safety: must be in allowed paths
    allowed = any(
        file_path.startswith(p) or file_path == p
        for p in _ALLOWED_PATHS
    )
    if not allowed:
        return False, f"path not in allowed list: {file_path}"

    if not full_path.exists():
        return False, f"file not found: {file_path}"

    try:
        current = full_path.read_text(encoding="utf-8")

        if action in ("replace_lines", "replace"):
            search  = change.get("search", "")
            repl    = change.get("replacement", "")
            if search not in current:
                return False, f"search text not found in {file_path}"
            updated = current.replace(search, repl, 1)
            full_path.write_text(updated, encoding="utf-8")
            return True, f"replaced in {file_path}"

        elif action in ("append_lines", "append"):
            content = change.get("content", change.get("replacement", ""))
            full_path.write_text(current + "\n" + content, encoding="utf-8")
            return True, f"appended to {file_path}"

        else:
            return False, f"unknown action: {action}"
    except Exception as exc:
        return False, str(exc)


# ── GitHub PR ─────────────────────────────────────────────────────────────────

def _create_pr_sync(branch: str, title: str, body: str) -> str:
    """Push branch and create PR. Returns PR URL or error string."""
    token = os.getenv("GITHUB_TOKEN", "")
    repo  = os.getenv("GITHUB_REPO", "")
    if not token or not repo:
        return ""

    repo_root = Path(__file__).resolve().parents[3]
    try:
        subprocess.run(["git", "checkout", "-b", branch], cwd=repo_root, check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=repo_root, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", title],
            cwd=repo_root, check=True, capture_output=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "EDON Codex", "GIT_AUTHOR_EMAIL": "codex@edon.ai",
                 "GIT_COMMITTER_NAME": "EDON Codex", "GIT_COMMITTER_EMAIL": "codex@edon.ai"},
        )
        subprocess.run(["git", "push", "origin", branch], cwd=repo_root, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        return f"git error: {exc.stderr.decode()[:200] if exc.stderr else str(exc)}"

    try:
        import requests as _req
        resp = _req.post(
            f"{_GITHUB_API}/repos/{repo}/pulls",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            json={"title": title, "body": body, "head": branch, "base": "master"},
            timeout=15,
        )
        if resp.status_code in (200, 201):
            return resp.json().get("html_url", "")
        return f"PR API error {resp.status_code}: {resp.text[:200]}"
    except Exception as exc:
        return f"PR creation error: {exc}"


# ── Main task runner ──────────────────────────────────────────────────────────

async def run_code_task(task_id: str, instruction: str, agent_id: str = _AGENT_ID) -> dict:
    """Run a governed code task end-to-end. Returns final CodeTaskResult as dict."""
    result = CodeTaskResult(
        task_id=task_id,
        instruction=instruction,
        status="running",
        started_at=datetime.now(UTC).isoformat(),
    )
    _tasks[task_id] = result

    try:
        # Govern: can we plan changes?
        allowed = await _gov(
            "code.plan",
            {"task_id": task_id, "instruction": instruction[:200]},
            "autonomous code change requested via voice/codex",
        )
        if not allowed:
            result.status = "blocked"
            result.governed = False
            result.summary = "Governance blocked planning phase"
            result.finished_at = datetime.now(UTC).isoformat()
            return asdict(result)

        # Plan
        logger.info("[codex] task=%s planning changes", task_id)
        plan = await _plan_changes(instruction)
        result.plan = plan.get("summary", "")
        changes = plan.get("changes", [])

        if result.plan.startswith("BLOCKED"):
            result.status = "blocked"
            result.summary = result.plan
            result.finished_at = datetime.now(UTC).isoformat()
            return asdict(result)

        if not changes:
            result.status = "done"
            result.summary = "No changes needed: " + result.plan
            result.finished_at = datetime.now(UTC).isoformat()
            return asdict(result)

        # Apply each change (governed)
        applied_files: list[str] = []
        for change in changes:
            fp = change.get("file_path", "?")
            file_allowed = await _gov(
                "file.write",
                {"path": fp, "action": change.get("action")},
                f"applying planned code change: {result.plan}",
            )
            if not file_allowed:
                logger.warning("[codex] task=%s file write blocked: %s", task_id, fp)
                continue

            ok, msg = await asyncio.to_thread(_apply_change_sync, change)
            if ok:
                applied_files.append(fp)
                logger.info("[codex] task=%s applied %s", task_id, fp)
            else:
                logger.warning("[codex] task=%s apply failed %s: %s", task_id, fp, msg)

        result.files_changed = applied_files

        if not applied_files:
            result.status = "failed"
            result.error = "No changes could be applied"
            result.finished_at = datetime.now(UTC).isoformat()
            return asdict(result)

        # Create PR
        pr_allowed = await _gov(
            "github.pr_create",
            {"files": applied_files, "title": result.plan},
            "opening PR for reviewed code change",
        )
        if pr_allowed:
            branch = f"codex/{task_id[:8]}-{int(time.time())}"
            pr_title = f"[EDON Codex] {result.plan}"
            pr_body  = (
                f"**Instruction:** {instruction}\n\n"
                f"**Plan:** {result.plan}\n\n"
                f"**Files changed:** {', '.join(applied_files)}\n\n"
                f"*Generated by EDON self-governing code agent — task `{task_id}`*"
            )
            result.pr_url = await asyncio.to_thread(_create_pr_sync, branch, pr_title, pr_body)

        result.status = "done"
        result.summary = result.plan + (f" — PR: {result.pr_url}" if result.pr_url else " — no PR (GITHUB_TOKEN not set)")
        result.finished_at = datetime.now(UTC).isoformat()

    except Exception as exc:
        logger.error("[codex] task=%s error: %s", task_id, exc)
        result.status = "failed"
        result.error = str(exc)
        result.finished_at = datetime.now(UTC).isoformat()

    return asdict(result)
