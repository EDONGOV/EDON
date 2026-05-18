"""Output governance endpoint — /v1/output.

Agents submit tool execution results here before using them. EDON scans the
response for PHI/PII, credential leakage, bulk-data signals, and sensitive
path exposure, then returns a verdict with an optionally redacted payload.

Usage:
    POST /v1/output
    {
        "agent_id":       "agent-123",
        "action_type":    "database.query",
        "action_id":      "dec-abc123",        // ties back to the /v1/action audit record
        "response":       { ...tool output... },
        "context":        { "intent_id": "...", "tenant_id": "..." }
    }

Response:
    {
        "verdict":   "PASS" | "REDACT" | "BLOCK",
        "payload":   { ...original or redacted... },
        "findings":  [...],
        "action_id": "..."
    }

Audit:
  Every output governance decision is appended to the same audit trail as
  /v1/action, linked by action_id so reviewers can see both input and output
  governance for a single agent action in one audit thread.
"""

from __future__ import annotations

import time
import logging
from datetime import datetime, UTC

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Any, Optional

from ..tenancy import get_request_tenant_id
from ..logging_config import get_logger
from ..security.output_filter import filter_output

logger = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["v1-output"])


class V1OutputRequest(BaseModel):
    agent_id: str
    action_type: str
    action_id: Optional[str] = None
    response: Any
    context: Optional[dict] = None


class V1OutputResponse(BaseModel):
    verdict: str
    payload: Any
    findings: list[dict]
    action_id: Optional[str] = None
    redacted: bool = False
    processing_latency_ms: int = 0


@router.post("/output", response_model=V1OutputResponse)
async def govern_output(request: Request, req: V1OutputRequest):
    """Govern a tool execution response before the agent uses it."""
    start = time.time()
    tenant_id = get_request_tenant_id(request)

    if not req.agent_id or not req.agent_id.strip():
        raise HTTPException(status_code=400, detail="agent_id is required")
    if not req.action_type or not req.action_type.strip():
        raise HTTPException(status_code=400, detail="action_type is required")

    # Kill switch — if active, block all output too
    if tenant_id:
        try:
            from .kill_switch import is_kill_switch_active
            if is_kill_switch_active(tenant_id):
                raise HTTPException(
                    status_code=403,
                    detail="Emergency kill switch active. All agent output is blocked.",
                )
        except HTTPException:
            raise
        except Exception:
            pass

    parts = req.action_type.split(".", 1)
    tool = parts[0] if parts else req.action_type
    op   = parts[1] if len(parts) > 1 else ""

    result = filter_output(req.response, action_tool=tool, action_op=op)

    latency_ms = int((time.time() - start) * 1000)

    # Audit the output governance decision (non-blocking)
    try:
        from ..persistence import get_db
        db = get_db()
        db.log_audit_event({
            "event_type":     "output_governance",
            "agent_id":       req.agent_id,
            "tenant_id":      tenant_id,
            "action_type":    req.action_type,
            "action_id":      req.action_id,
            "verdict":        result.verdict,
            "findings":       [
                {"category": f.category, "pattern": f.pattern_name, "count": f.count}
                for f in result.findings
            ],
            "record_count":   result.record_count,
            "original_size":  result.original_size_bytes,
            "latency_ms":     latency_ms,
            "timestamp":      datetime.now(UTC).isoformat(),
        })
    except Exception as exc:
        logger.debug("output governance audit write failed (non-fatal): %s", exc)

    # Determine what payload to return
    if result.verdict == "BLOCK":
        return V1OutputResponse(
            verdict="BLOCK",
            payload=None,
            findings=[
                {"category": f.category, "pattern": f.pattern_name, "count": f.count}
                for f in result.findings
            ],
            action_id=req.action_id,
            redacted=False,
            processing_latency_ms=latency_ms,
        )

    if result.verdict == "REDACT" and result.redacted_text is not None:
        import json as _json
        try:
            payload = _json.loads(result.redacted_text)
        except Exception:
            payload = result.redacted_text
        return V1OutputResponse(
            verdict="REDACT",
            payload=payload,
            findings=[
                {"category": f.category, "pattern": f.pattern_name, "count": f.count}
                for f in result.findings
            ],
            action_id=req.action_id,
            redacted=True,
            processing_latency_ms=latency_ms,
        )

    return V1OutputResponse(
        verdict="PASS",
        payload=req.response,
        findings=[],
        action_id=req.action_id,
        redacted=False,
        processing_latency_ms=latency_ms,
    )
