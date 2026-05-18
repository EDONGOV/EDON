"""EDON CI/CD integration routes.

Endpoints:
    POST /v1/cicd/scan            — trigger a full security gate scan
    GET  /v1/cicd/gate/{scan_id}  — poll gate result by scan ID
    GET  /v1/cicd/history         — list recent scans for this tenant
    POST /v1/cicd/event           — receive push/deployment webhooks from GitHub/GitLab/etc.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from dataclasses import asdict
from datetime import datetime, UTC
from typing import Optional

from fastapi import APIRouter, Body, Header, HTTPException, Query, Request
from pydantic import BaseModel

from ..tenancy import get_request_tenant_id
from ..logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v1/cicd", tags=["cicd"])

# In-process write-through cache — accelerates same-instance polling.
# All writes also go to DB so scans survive restarts and are visible across instances.
_scans: dict[str, dict] = {}


def _db_save_scan(tenant_id: str, scan_id: str, data: dict) -> None:
    try:
        from ..persistence import get_db
        get_db().save_cicd_scan(tenant_id or "__global__", scan_id, data)
    except Exception as exc:
        logger.warning("[cicd] DB scan persist failed (in-memory only): %s", exc)


def _db_get_scan(scan_id: str, tenant_id: str) -> Optional[dict]:
    try:
        from ..persistence import get_db
        return get_db().get_cicd_scan(scan_id, tenant_id or None)
    except Exception:
        return None


def _db_list_scans(tenant_id: str, limit: int, repo: Optional[str]) -> list:
    try:
        from ..persistence import get_db
        return get_db().list_cicd_scans(tenant_id or "__global__", limit=limit, repo=repo)
    except Exception:
        return []

_WEBHOOK_SECRET = os.getenv("EDON_CICD_WEBHOOK_SECRET", "").strip()


# ── Request models ─────────────────────────────────────────────────────────────


class ScanRequest(BaseModel):
    repo: Optional[str] = None           # "owner/repo"
    commit_sha: Optional[str] = None
    branch: Optional[str] = None
    environment: Optional[str] = None    # "production" | "staging" | etc.
    github_token: Optional[str] = None   # override EDON_GITHUB_TOKEN for this scan


# ── Scan endpoint ──────────────────────────────────────────────────────────────


@router.post("/scan")
async def trigger_scan(
    request: Request,
    body: ScanRequest = Body(default=ScanRequest()),
):
    """Trigger a full EDON security gate scan.

    Runs an Impact cycle scoped to the caller's tenant, evaluates the gate
    policy, and posts a GitHub commit status if `commit_sha` + a GitHub token
    are available.

    Returns the full `CicdScan` result (JSON). The `gate_passed` field is the
    canonical pass/fail signal for CI scripts.

    Example (GitHub Actions):
    ```yaml
    - name: EDON Security Gate
      run: |
        curl -sX POST https://api.edoncore.com/v1/cicd/scan \\
          -H "Authorization: Bearer ${{ secrets.EDON_API_KEY }}" \\
          -H "Content-Type: application/json" \\
          -d '{"repo":"${{ github.repository }}","commit_sha":"${{ github.sha }}","branch":"${{ github.ref_name }}"}'
    ```
    """
    from ..cicd.scanner import run_scan
    from ..shadow.trace_capture import get_trace_store
    from ..impact.store import get_impact_store

    tenant_id = get_request_tenant_id(request)
    governor = getattr(request.app.state, "governor", None)

    scan = await run_scan(
        tenant_id=tenant_id,
        repo=body.repo,
        commit_sha=body.commit_sha,
        branch=body.branch,
        environment=body.environment,
        triggered_by="api",
        governor=governor,
        shadow_store=get_trace_store(),
        impact_store=get_impact_store(),
        github_token=body.github_token,
    )

    result = asdict(scan)
    _scans[scan.scan_id] = result
    _db_save_scan(tenant_id or "__global__", scan.scan_id, result)
    return result


# ── Gate poll ──────────────────────────────────────────────────────────────────


@router.get("/gate/{scan_id}")
async def get_gate_result(scan_id: str, request: Request):
    """Poll a gate result by scan ID."""
    tenant_id = get_request_tenant_id(request)
    result = _scans.get(scan_id) or _db_get_scan(scan_id, tenant_id or "__global__")
    if result is None:
        raise HTTPException(status_code=404, detail=f"Scan '{scan_id}' not found.")
    return result


# ── History ────────────────────────────────────────────────────────────────────


@router.get("/history")
async def get_scan_history(
    request: Request,
    limit: int = Query(25, le=100),
    repo: Optional[str] = Query(None),
):
    """Return recent CI/CD scan history for this tenant, newest-first."""
    tenant_id = get_request_tenant_id(request)
    scans = _db_list_scans(tenant_id or "__global__", limit=limit, repo=repo)
    if not scans:
        # Fall back to in-process cache if DB is empty (e.g. first run)
        scans = list(_scans.values())
        if tenant_id:
            scans = [s for s in scans if s.get("tenant_id") == tenant_id]
        if repo:
            scans = [s for s in scans if s.get("repo") == repo]
        scans.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        scans = scans[:limit]

    return {
        "scans": scans,
        "count": len(scans),
        "tenant_id": tenant_id,
    }


# ── Webhook receiver ───────────────────────────────────────────────────────────


@router.post("/event")
async def receive_webhook_event(
    request: Request,
    x_github_event: Optional[str] = Header(None, alias="X-GitHub-Event"),
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    x_gitlab_event: Optional[str] = Header(None, alias="X-Gitlab-Event"),
):
    """Receive push/deployment webhook events from GitHub or GitLab.

    Automatically triggers a CI/CD security gate scan on relevant events:
    - GitHub: `push` to main/master/release/deploy branches, `deployment` events
    - GitLab: `Push Hook` to default/protected branches

    Configure your GitHub repo webhook:
      URL:          https://api.edoncore.com/v1/cicd/event
      Content type: application/json
      Secret:       Set EDON_CICD_WEBHOOK_SECRET to the same value
      Events:       Pushes, Deployments
    """
    raw = await request.body()

    # Validate HMAC signature if secret is configured
    if _WEBHOOK_SECRET:
        if x_hub_signature_256:
            expected = "sha256=" + hmac.new(
                _WEBHOOK_SECRET.encode(), raw, hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(expected, x_hub_signature_256):
                raise HTTPException(status_code=401, detail="Invalid webhook signature")
        else:
            logger.warning("[cicd/event] EDON_CICD_WEBHOOK_SECRET is set but no X-Hub-Signature-256 header received")

    try:
        payload = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = x_github_event or x_gitlab_event or "unknown"

    # ── GitHub push ────────────────────────────────────────────────────────────
    if x_github_event == "push":
        ref = payload.get("ref", "")
        branch = ref.replace("refs/heads/", "")
        if not _is_gate_branch(branch):
            return {"skipped": True, "reason": f"branch '{branch}' not in gate list"}

        repo = payload.get("repository", {}).get("full_name")
        commit_sha = payload.get("after") or payload.get("head_commit", {}).get("id")

        return await _fire_scan(
            request=request,
            repo=repo,
            commit_sha=commit_sha,
            branch=branch,
            environment=None,
            triggered_by="webhook",
            event_type=event_type,
        )

    # ── GitHub deployment ──────────────────────────────────────────────────────
    if x_github_event == "deployment":
        deployment = payload.get("deployment", {})
        repo = payload.get("repository", {}).get("full_name")
        commit_sha = deployment.get("sha")
        branch = deployment.get("ref", "")
        environment = deployment.get("environment", "unknown")

        return await _fire_scan(
            request=request,
            repo=repo,
            commit_sha=commit_sha,
            branch=branch,
            environment=environment,
            triggered_by="webhook",
            event_type=event_type,
        )

    # ── GitLab push ────────────────────────────────────────────────────────────
    if x_gitlab_event and "Push" in x_gitlab_event:
        ref = payload.get("ref", "")
        branch = ref.replace("refs/heads/", "")
        if not _is_gate_branch(branch):
            return {"skipped": True, "reason": f"branch '{branch}' not in gate list"}

        repo = payload.get("project", {}).get("path_with_namespace")
        commit_sha = payload.get("after") or (payload.get("commits") or [{}])[0].get("id")

        return await _fire_scan(
            request=request,
            repo=repo,
            commit_sha=commit_sha,
            branch=branch,
            environment=None,
            triggered_by="webhook",
            event_type=event_type,
        )

    return {"skipped": True, "reason": f"unhandled event type: {event_type}"}


# ── Helpers ────────────────────────────────────────────────────────────────────

_GATE_BRANCHES_DEFAULT = {"main", "master", "production", "deploy", "release"}
_GATE_BRANCHES_ENV = set(
    b.strip() for b in os.getenv("EDON_CICD_GATE_BRANCHES", "").split(",") if b.strip()
)
_GATE_BRANCHES = _GATE_BRANCHES_ENV or _GATE_BRANCHES_DEFAULT


def _is_gate_branch(branch: str) -> bool:
    """Return True if this branch should trigger a security gate scan."""
    if branch in _GATE_BRANCHES:
        return True
    return any(branch.startswith(prefix) for prefix in ("release/", "deploy/", "hotfix/"))


async def _fire_scan(
    request: Request,
    repo: Optional[str],
    commit_sha: Optional[str],
    branch: Optional[str],
    environment: Optional[str],
    triggered_by: str,
    event_type: str,
) -> dict:
    from ..cicd.scanner import run_scan
    from ..shadow.trace_capture import get_trace_store
    from ..impact.store import get_impact_store

    tenant_id = get_request_tenant_id(request)
    governor = getattr(request.app.state, "governor", None)

    scan = await run_scan(
        tenant_id=tenant_id,
        repo=repo,
        commit_sha=commit_sha,
        branch=branch,
        environment=environment,
        triggered_by=triggered_by,
        governor=governor,
        shadow_store=get_trace_store(),
        impact_store=get_impact_store(),
    )

    result = asdict(scan)
    _scans[scan.scan_id] = result
    _db_save_scan(tenant_id or "__global__", scan.scan_id, result)

    logger.info(
        "[cicd/event] event=%s repo=%s branch=%s gate=%s scan=%s",
        event_type, repo, branch, scan.status, scan.scan_id[:8],
    )

    return {
        "accepted": True,
        "scan_id": scan.scan_id,
        "gate_passed": scan.gate_passed,
        "status": scan.status,
        "gate_reason": scan.gate_reason,
    }
