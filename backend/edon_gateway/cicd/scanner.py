"""EDON CI/CD Scanner.

Runs a security gate scan for a deployment context:

  1. Triggers an Impact cycle (Engine A→D) scoped to the tenant
  2. Evaluates gate policy: unmitigated critical/high findings → fail
  3. Posts GitHub commit status if commit_sha + token are present
  4. Returns a structured CicdScan result

Called from:
  POST /v1/cicd/scan   — direct API call from GitHub Actions / any CI
  POST /v1/cicd/event  — webhook receiver for push/deployment events

Config:
  EDON_CICD_GATE_ON_CRITICAL  default: true  — fail gate on unmitigated critical findings
  EDON_CICD_GATE_ON_HIGH      default: false — fail gate on unmitigated high findings
  EDON_CICD_MAX_CRITICAL       default: 0    — max allowed critical findings (0 = zero-tolerance)
  EDON_CICD_MAX_HIGH           default: -1   — max allowed high findings (-1 = no limit)
  EDON_GITHUB_TOKEN            — GitHub PAT for posting commit status checks
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from typing import Optional

from ..logging_config import get_logger

logger = get_logger(__name__)

_GATE_ON_CRITICAL = os.getenv("EDON_CICD_GATE_ON_CRITICAL", "true").lower() == "true"
_GATE_ON_HIGH     = os.getenv("EDON_CICD_GATE_ON_HIGH",     "false").lower() == "true"
_MAX_CRITICAL     = int(os.getenv("EDON_CICD_MAX_CRITICAL",  "0"))
_MAX_HIGH         = int(os.getenv("EDON_CICD_MAX_HIGH",      "-1"))


@dataclass
class CicdScan:
    scan_id:               str
    tenant_id:             Optional[str]
    repo:                  Optional[str]         # "owner/repo"
    commit_sha:            Optional[str]
    branch:                Optional[str]
    environment:           Optional[str]         # "production" | "staging" | etc.
    triggered_by:          str                   # "api" | "webhook" | "manual"
    status:                str                   # "pending" | "scanning" | "passed" | "failed" | "error"
    gate_passed:           bool = True
    gate_reason:           str  = ""
    critical_findings:     int  = 0
    high_findings:         int  = 0
    medium_findings:       int  = 0
    total_findings:        int  = 0
    mitigated_count:       int  = 0
    new_since_last:        int  = 0
    scan_duration_ms:      int  = 0
    github_status_posted:  bool = False
    impact_cycle_summary:  Optional[dict] = field(default=None)
    findings_detail:       list = field(default_factory=list)
    errors:                list = field(default_factory=list)
    created_at:            str  = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at:          Optional[str] = None


def _evaluate_gate(scan: CicdScan) -> tuple[bool, str]:
    """Apply gate policy. Returns (passed, reason)."""
    if _GATE_ON_CRITICAL and scan.critical_findings > _MAX_CRITICAL:
        return False, (
            f"{scan.critical_findings} unmitigated critical finding(s) — "
            f"threshold is {_MAX_CRITICAL}. Mitigate before deploying."
        )
    if _GATE_ON_HIGH and _MAX_HIGH >= 0 and scan.high_findings > _MAX_HIGH:
        return False, (
            f"{scan.high_findings} unmitigated high finding(s) — "
            f"threshold is {_MAX_HIGH}."
        )
    if scan.total_findings == 0:
        return True, "No unmitigated findings. Safe to deploy."
    return True, (
        f"{scan.total_findings} finding(s) found "
        f"({scan.critical_findings} critical, {scan.high_findings} high) — "
        "none exceed gate thresholds."
    )


async def run_scan(
    *,
    tenant_id: Optional[str] = None,
    repo: Optional[str] = None,
    commit_sha: Optional[str] = None,
    branch: Optional[str] = None,
    environment: Optional[str] = None,
    triggered_by: str = "api",
    governor=None,
    shadow_store=None,
    impact_store=None,
    github_token: Optional[str] = None,
) -> CicdScan:
    """Run a full CI/CD security gate scan.

    Triggers an Impact cycle, evaluates the gate policy, posts
    GitHub status if credentials are available.

    Returns a CicdScan dataclass — convert to dict via asdict().
    """
    from ..impact.loop import run_cycle
    from ..impact.store import get_impact_store
    from .github import post_commit_status

    scan = CicdScan(
        scan_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        repo=repo,
        commit_sha=commit_sha,
        branch=branch,
        environment=environment,
        triggered_by=triggered_by,
        status="scanning",
    )

    t0 = time.time()

    # Post pending status to GitHub immediately so engineers see the check
    _token = github_token or os.getenv("EDON_GITHUB_TOKEN", "").strip()
    if commit_sha and repo and _token:
        try:
            await asyncio.to_thread(
                post_commit_status,
                repo=repo,
                sha=commit_sha,
                state="pending",
                description="EDON security scan running…",
                token=_token,
            )
        except Exception as _e:
            logger.debug("[cicd/scanner] github pending status failed: %s", _e)

    # Run Impact cycle
    try:
        _store = impact_store or get_impact_store()
        cycle_result = await run_cycle(
            tenant_id=tenant_id,
            governor=governor,
            shadow_store=shadow_store,
            impact_store=_store,
            force=True,
        )
        scan.impact_cycle_summary = cycle_result
    except Exception as exc:
        logger.warning("[cicd/scanner] impact cycle failed: %s", exc)
        scan.errors.append(f"impact_cycle: {exc}")
        scan.status = "error"
        scan.gate_passed = False
        scan.gate_reason = f"Scan error: {exc}"
        scan.completed_at = datetime.now(UTC).isoformat()
        scan.scan_duration_ms = int((time.time() - t0) * 1000)
        return scan

    # Tally findings from Impact store
    try:
        _store = impact_store or get_impact_store()
        states = _store.get_failure_states(tenant_id=tenant_id, limit=500)
        unmitigated = [s for s in states if not s.get("mitigated_at")]

        scan.mitigated_count   = len(states) - len(unmitigated)
        scan.critical_findings = sum(1 for s in unmitigated if s.get("severity_score", 0) >= 0.75 and s.get("verified"))
        scan.high_findings     = sum(1 for s in unmitigated if 0.5 <= s.get("severity_score", 0) < 0.75 and s.get("verified"))
        scan.medium_findings   = sum(1 for s in unmitigated if 0.25 <= s.get("severity_score", 0) < 0.5 and s.get("verified"))
        scan.total_findings    = scan.critical_findings + scan.high_findings + scan.medium_findings
        scan.new_since_last    = cycle_result.get("new_failure_states", 0)

        # Include top 10 findings in detail
        scan.findings_detail = [
            {
                "failure_state_id": s["failure_state_id"][:16] + "…",
                "vulnerability_class": s["vulnerability_class"],
                "severity_score": round(s.get("severity_score", 0), 3),
                "severity": (
                    "critical" if s.get("severity_score", 0) >= 0.75 else
                    "high"     if s.get("severity_score", 0) >= 0.50 else
                    "medium"   if s.get("severity_score", 0) >= 0.25 else "low"
                ),
                "path_summary": " → ".join((s.get("path") or [])[:3]),
                "mitigated": bool(s.get("mitigated_at")),
            }
            for s in sorted(unmitigated[:10], key=lambda x: x.get("severity_score", 0), reverse=True)
            if s.get("verified")
        ]
    except Exception as exc:
        logger.warning("[cicd/scanner] findings tally failed: %s", exc)
        scan.errors.append(f"tally: {exc}")

    # Evaluate gate
    gate_passed, gate_reason = _evaluate_gate(scan)
    scan.gate_passed  = gate_passed
    scan.gate_reason  = gate_reason
    scan.status       = "passed" if gate_passed else "failed"
    scan.completed_at = datetime.now(UTC).isoformat()
    scan.scan_duration_ms = int((time.time() - t0) * 1000)

    # Post final GitHub status
    if commit_sha and repo and _token:
        try:
            gh_state = "success" if gate_passed else "failure"
            await asyncio.to_thread(
                post_commit_status,
                repo=repo,
                sha=commit_sha,
                state=gh_state,
                description=gate_reason[:139],   # GitHub limit
                token=_token,
            )
            scan.github_status_posted = True
        except Exception as _e:
            logger.debug("[cicd/scanner] github final status failed: %s", _e)

    logger.info(
        "[cicd/scanner] scan=%s repo=%s sha=%s gate=%s critical=%d high=%d duration=%dms",
        scan.scan_id[:8], repo, (commit_sha or "")[:8],
        scan.status, scan.critical_findings, scan.high_findings, scan.scan_duration_ms,
    )

    return scan
