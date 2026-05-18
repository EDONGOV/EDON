"""Shadow → Fix Pipeline.

Converts critical/advisory shadow findings into concrete policy change proposals
and queues them for human review. This closes the self-healing loop:

    Shadow finds bypass → Fix pipeline proposes patch → Human approves → Policy updated

Design principles:
- Never auto-applies anything. Every proposal requires explicit approval.
- Proposals are deterministic: same finding always produces the same rule suggestion.
- Source-tagged so operators know which proposals came from shadow vs manual review.
- Fail-open: any error produces a best-effort proposal rather than crashing.

Integration point (called from shadow/replay.py after each critical/advisory result):

    from .fix_pipeline import queue_fix_proposal
    if result.severity in ("critical", "advisory"):
        queue_fix_proposal(result, trace)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Data model ─────────────────────────────────────────────────────────────────


@dataclass
class FixProposal:
    """A policy change proposed by the shadow engine to close a detected bypass."""

    proposal_id: str
    trace_id: str
    perturbation_name: str
    perturbation_type: str
    severity: str                    # "critical" | "advisory"
    original_verdict: str            # what the governor said originally
    shadow_verdict: str              # what shadow got after perturbation
    perturbed_field: Optional[str]   # which field was mutated

    # The actual rule patch — ready to be applied as a tenant policy rule
    suggested_action: str            # "BLOCK" | "ESCALATE"
    condition_tool: Optional[str]    # tool to match (None = any)
    condition_op: Optional[str]      # operation to match (None = any)
    rule_description: str            # human-readable what this rule does
    rationale: str                   # why this perturbation warranted this rule

    tenant_id: Optional[str]
    agent_id: str
    action_type: str

    status: str = "pending_review"   # "pending_review" | "approved" | "rejected" | "applied"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None
    resolution_note: Optional[str] = None


# ── In-memory store with disk persistence ─────────────────────────────────────

_lock = threading.Lock()
_proposals: dict[str, dict] = {}   # proposal_id → FixProposal as dict
_TTL_HOURS = int(os.getenv("EDON_FIX_PROPOSAL_TTL_HOURS", "168"))  # 7 days default


def _data_dir() -> Path:
    db_path = os.getenv("EDON_DATABASE_PATH", "").strip()
    if db_path:
        p = Path(db_path).parent
        p.mkdir(parents=True, exist_ok=True)
        return p
    url = os.getenv("EDON_DB_URL", "").strip()
    if url.startswith("sqlite:///"):
        p = Path(url.replace("sqlite:///", "", 1)).parent
        p.mkdir(parents=True, exist_ok=True)
        return p
    p = Path("/data") if Path("/data").exists() else Path("/tmp/edon_data")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _proposals_path() -> Path:
    return _data_dir() / "fix_proposals.json"


def _persist() -> None:
    try:
        _proposals_path().write_text(json.dumps(_proposals, indent=2))
    except Exception as exc:
        logger.warning("[fix_pipeline] persist failed: %s", exc)


def _db_write(proposal_id: str, data: dict) -> None:
    """Write proposal to DB. Logs but never raises."""
    try:
        from ..persistence import get_db
        get_db().save_fix_proposal(proposal_id, data)
    except Exception as exc:
        logger.warning("[fix_pipeline] DB write failed (JSON-only): %s", exc)


def _load_from_disk() -> None:
    """Warm in-memory proposals from DB first, fall back to JSON file."""
    cutoff = (datetime.now(UTC) - timedelta(hours=_TTL_HOURS)).isoformat()
    # Primary: DB
    try:
        from ..persistence import get_db
        rows = get_db().list_fix_proposals(status=None, limit=5000)
        with _lock:
            for v in rows:
                if v.get("created_at", "") >= cutoff:
                    _proposals[v["proposal_id"]] = v
        if _proposals:
            logger.info("[fix_pipeline] loaded %d proposals from DB", len(_proposals))
            return
    except Exception as exc:
        logger.debug("[fix_pipeline] DB load failed, trying JSON file: %s", exc)
    # Fallback: JSON file
    path = _proposals_path()
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text())
        cutoff2 = (datetime.now(UTC) - timedelta(hours=_TTL_HOURS)).isoformat()
        with _lock:
            for k, v in data.items():
                if v.get("created_at", "") >= cutoff2:
                    _proposals[k] = v
    except Exception as exc:
        logger.warning("[fix_pipeline] load from disk failed: %s", exc)


_load_from_disk()


# ── Proposal generation ────────────────────────────────────────────────────────

# Perturbation type → suggested action mapping
# Critical bypasses (blocked → allowed) always produce a BLOCK proposal.
# Advisory changes produce ESCALATE to bring them to human attention.
_SEVERITY_ACTION: dict[str, str] = {
    "critical": "BLOCK",
    "advisory": "ESCALATE",
}

# Per-perturbation type rationale templates
_RATIONALES: dict[str, str] = {
    "prompt_injection": (
        "Shadow testing found that injected adversarial strings in this payload field "
        "changed the governance verdict. Adding an explicit rule hardens this action "
        "against prompt injection attacks targeting the policy engine."
    ),
    "privilege_escalation": (
        "Shadow testing found that escalating the action_type to a higher-privilege "
        "operation bypassed existing rules. Block the escalated action_type explicitly."
    ),
    "context_poisoning": (
        "Shadow testing found that replacing stated_intent or user_message with false "
        "signals changed the governance verdict. This rule prevents context-based overrides "
        "for this tool/operation."
    ),
    "malformed_payload": (
        "Shadow testing found that malformed payload values (null, oversized, wrong types) "
        "caused the governor to allow an action it should block. Adding schema validation "
        "at the rule level closes this gap."
    ),
    "boundary_input": (
        "Shadow testing found that extreme boundary inputs (empty payload, max-length strings) "
        "produced unexpected verdicts. This rule ensures consistent enforcement at boundaries."
    ),
}

_DEFAULT_RATIONALE = (
    "Shadow testing detected a verdict change under adversarial perturbation. "
    "This rule proposal closes the identified gap."
)


def _build_proposal(result, trace, tenant_id: Optional[str]) -> FixProposal:
    """Build a FixProposal from a ShadowRunResult and its source AgentTrace."""
    parts = (result.trace_id or "").split("-")
    action_type = getattr(trace, "action_type", "unknown")
    tool_str, _, op_str = action_type.partition(".")
    condition_tool = tool_str.lower() if tool_str else None
    condition_op = op_str.lower() if op_str else None

    ptype = result.perturbation_type or "unknown"
    action = _SEVERITY_ACTION.get(result.severity, "ESCALATE")
    rationale = _RATIONALES.get(ptype, _DEFAULT_RATIONALE)

    perturbed = result.perturbed_field or "unknown field"

    rule_desc = (
        f"Auto-proposed by shadow engine ({result.severity.upper()}): "
        f"{action} {action_type} when {ptype} perturbation on {perturbed} "
        f"changes verdict from {result.shadow_verdict} "
        f"(original: {getattr(trace, 'original_verdict', 'unknown')})."
    )

    return FixProposal(
        proposal_id=str(uuid.uuid4()),
        trace_id=result.trace_id,
        perturbation_name=result.perturbation_name,
        perturbation_type=ptype,
        severity=result.severity,
        original_verdict=getattr(trace, "original_verdict", "unknown"),
        shadow_verdict=result.shadow_verdict,
        perturbed_field=result.perturbed_field,
        suggested_action=action,
        condition_tool=condition_tool,
        condition_op=condition_op,
        rule_description=rule_desc[:300],
        rationale=rationale,
        tenant_id=tenant_id or getattr(trace, "tenant_id", None),
        agent_id=getattr(trace, "agent_id", "unknown"),
        action_type=action_type,
    )


# ── Public API ─────────────────────────────────────────────────────────────────


def queue_fix_proposal(result, trace, tenant_id: Optional[str] = None) -> Optional[FixProposal]:
    """Convert a critical/advisory ShadowRunResult into a FixProposal and queue it.

    Called from shadow_run_trace after each critical or advisory finding.
    Fail-open: any error is logged and None is returned.

    Args:
        result: ShadowRunResult from replay.py
        trace:  AgentTrace that was replayed
        tenant_id: Override tenant; falls back to trace.tenant_id

    Returns:
        The queued FixProposal, or None on failure.
    """
    if result.severity not in ("critical", "advisory"):
        return None

    try:
        proposal = _build_proposal(result, trace, tenant_id)
        d = asdict(proposal)
        with _lock:
            _proposals[proposal.proposal_id] = d
            _persist()
        _db_write(proposal.proposal_id, d)

        logger.info(
            "[fix_pipeline] proposal queued: id=%s severity=%s perturbation=%s trace=%s",
            proposal.proposal_id[:8],
            proposal.severity,
            proposal.perturbation_type,
            proposal.trace_id[:8],
        )
        return proposal

    except Exception as exc:
        logger.warning("[fix_pipeline] proposal generation failed (fail-open): %s", exc)
        return None


def get_proposals(
    tenant_id: Optional[str] = None,
    status: Optional[str] = "pending_review",
    severity: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    """Return queued fix proposals, optionally filtered."""
    cutoff = (datetime.now(UTC) - timedelta(hours=_TTL_HOURS)).isoformat()
    with _lock:
        items = list(_proposals.values())

    results = []
    for p in items:
        if p.get("created_at", "") < cutoff:
            continue
        if tenant_id and p.get("tenant_id") and p["tenant_id"] != tenant_id:
            continue
        if status and p.get("status") != status:
            continue
        if severity and p.get("severity") != severity:
            continue
        results.append(p)

    results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return results[:limit]


def approve_proposal(proposal_id: str, resolved_by: str, note: Optional[str] = None) -> Optional[dict]:
    """Mark a proposal as approved. Returns updated proposal or None if not found."""
    with _lock:
        p = _proposals.get(proposal_id)
        if not p:
            return None
        p["status"] = "approved"
        p["resolved_at"] = datetime.now(UTC).isoformat()
        p["resolved_by"] = resolved_by
        p["resolution_note"] = note
        _persist()
    _db_write(proposal_id, p)
    logger.info("[fix_pipeline] APPROVED proposal=%s by=%s", proposal_id[:8], resolved_by)
    return dict(p)


def reject_proposal(proposal_id: str, resolved_by: str, note: Optional[str] = None) -> Optional[dict]:
    """Mark a proposal as rejected. Returns updated proposal or None if not found."""
    with _lock:
        p = _proposals.get(proposal_id)
        if not p:
            return None
        p["status"] = "rejected"
        p["resolved_at"] = datetime.now(UTC).isoformat()
        p["resolved_by"] = resolved_by
        p["resolution_note"] = note
        _persist()
    _db_write(proposal_id, p)
    logger.info("[fix_pipeline] REJECTED proposal=%s by=%s", proposal_id[:8], resolved_by)
    return dict(p)


def proposal_summary(tenant_id: Optional[str] = None) -> dict:
    """Return count breakdown by status and severity."""
    items = get_proposals(tenant_id=tenant_id, status=None, limit=10000)
    summary: dict = {
        "pending_review": 0, "approved": 0, "rejected": 0, "applied": 0,
        "critical": 0, "advisory": 0,
    }
    for p in items:
        summary[p.get("status", "pending_review")] = summary.get(p.get("status", ""), 0) + 1
        summary[p.get("severity", "advisory")] = summary.get(p.get("severity", ""), 0) + 1
    summary["total"] = len(items)
    return summary
