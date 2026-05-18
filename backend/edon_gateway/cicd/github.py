"""GitHub Commit Status API client.

Posts EDON scan results as GitHub commit status checks so engineers
see pass/fail directly on PRs and branch pushes.

Two flavours:
  post_commit_status   — the classic Statuses API (simple, no annotations)
  post_check_run       — the newer Checks API (supports rich output + annotations)

Both are synchronous because they're called via asyncio.to_thread in scanner.py.
"""

from __future__ import annotations

from typing import Optional

import requests

GITHUB_API = "https://api.github.com"

_DEFAULT_CONTEXT = "EDON Security Gate"
_DEFAULT_CHECK_NAME = "EDON Security Gate"
_TIMEOUT = 10


def post_commit_status(
    repo: str,
    sha: str,
    state: str,
    description: str,
    token: str,
    context: str = _DEFAULT_CONTEXT,
    target_url: Optional[str] = None,
) -> dict:
    """Post a GitHub commit status (Statuses API).

    Args:
        repo:        "owner/repo"
        sha:         Full or partial commit SHA
        state:       "pending" | "success" | "failure" | "error"
        description: Short human-readable message (truncated to 139 chars by GitHub)
        token:       GitHub PAT or installation token with repo:status scope
        context:     Identifies this status check (default: "EDON Security Gate")
        target_url:  Optional link to the EDON scan details page

    Returns:
        Parsed JSON response from GitHub.
    """
    url = f"{GITHUB_API}/repos/{repo}/statuses/{sha}"

    payload: dict = {
        "state": state,
        "description": description[:139],
        "context": context,
    }
    if target_url:
        payload["target_url"] = target_url

    resp = requests.post(
        url,
        json=payload,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def post_check_run(
    repo: str,
    sha: str,
    conclusion: Optional[str],
    title: str,
    summary: str,
    token: str,
    name: str = _DEFAULT_CHECK_NAME,
    details_url: Optional[str] = None,
    annotations: Optional[list] = None,
    status: str = "completed",
) -> dict:
    """Post a GitHub Check Run (Checks API).

    Richer than commit statuses — supports a markdown summary, file
    annotations, and a "Details" link.

    Args:
        repo:        "owner/repo"
        sha:         Full commit SHA (partial SHAs not accepted by Checks API)
        conclusion:  "success" | "failure" | "neutral" | "cancelled" | "skipped"
                     | "timed_out" | "action_required" — required when status=completed
        title:       One-line title shown in the check header
        summary:     Markdown body shown in the check details panel
        token:       GitHub App installation token (PAT works for personal repos)
        name:        Check run name (default: "EDON Security Gate")
        details_url: Optional URL back to the EDON console for this scan
        annotations: Optional list of file-level annotations
        status:      "queued" | "in_progress" | "completed" (default: "completed")

    Returns:
        Parsed JSON response from GitHub.
    """
    url = f"{GITHUB_API}/repos/{repo}/check-runs"

    output: dict = {
        "title": title[:255],
        "summary": summary[:65535],
    }
    if annotations:
        output["annotations"] = annotations[:50]  # GitHub max per request

    payload: dict = {
        "name": name,
        "head_sha": sha,
        "status": status,
        "output": output,
    }
    if conclusion:
        payload["conclusion"] = conclusion
    if details_url:
        payload["details_url"] = details_url

    resp = requests.post(
        url,
        json=payload,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()
