"""EDON Proof Routes.

POST /v1/proof/generate           — generate proof for a failure state
POST /v1/proof/generate-batch     — generate proofs for multiple failure states
POST /v1/proof/sandbox            — run sandbox execution trace for a failure state
GET  /v1/proof/modes              — available proof levels and their requirements
GET  /v1/proof/report             — full client-facing risk report payload

Proof levels:
  logical    (Level 1)   — deterministic step-by-step chain. Always available.
  simulated  (Level 2)   — sandbox governor replay. Requires live governor.
  sandbox    (Level 2.5) — mock execution trace, no governor needed. Always available.
  controlled (Level 3)   — staging replay. Not yet implemented.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..tenancy import get_request_tenant_id
from ..logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v1/proof", tags=["proof"])


class ProofRequest(BaseModel):
    failure_state_id: Optional[str] = Field(None, description="Look up from ImpactStore")
    failure_state:    Optional[dict] = Field(None, description="Provide inline (for bootstrap demos)")
    mode:             str            = Field("logical", description="logical | simulated | controlled")
    tenant_id:        Optional[str]  = None


class BatchProofRequest(BaseModel):
    failure_state_ids: Optional[list[str]] = None
    failure_states:    Optional[list[dict]] = None
    mode:              str = "logical"
    tenant_id:         Optional[str] = None
    max_concurrent:    int = 5


@router.get("/modes")
async def list_modes():
    """List available proof levels and their requirements."""
    return {
        "modes": [
            {
                "mode": "logical",
                "level": 1,
                "description": "Deterministic step-by-step exploit chain from the execution graph",
                "requires_governor": False,
                "requires_live_traffic": False,
                "confidence_range": "0.85 – 0.95",
                "latency": "< 5ms",
                "use_case": "Demo, initial discovery, always available",
            },
            {
                "mode": "simulated",
                "level": 2,
                "description": "Sandbox replay of exploit steps through the live policy engine",
                "requires_governor": True,
                "requires_live_traffic": False,
                "confidence_range": "0.85 – 0.98",
                "latency": "< 100ms",
                "use_case": "Proof that exploit passes your actual governance rules",
            },
            {
                "mode": "sandbox",
                "level": 2.5,
                "description": "Mock execution trace — runs exploit steps against synthetic handlers, shows exactly what data is accessed/transmitted and side effects",
                "requires_governor": False,
                "requires_live_traffic": False,
                "confidence_range": "0.90 – 0.95",
                "latency": "< 10ms",
                "use_case": "Demo: shows the kill chain end-to-end without touching real systems",
            },
            {
                "mode": "controlled",
                "level": 3,
                "description": "Controlled replay against staging environment (future)",
                "requires_governor": True,
                "requires_live_traffic": True,
                "confidence_range": "0.95 – 1.0",
                "latency": "variable",
                "use_case": "Shannon slot — coming soon",
                "available": False,
            },
        ]
    }


@router.post("/generate")
async def generate_proof(body: ProofRequest, request: Request):
    """Generate a proof for a single failure state.

    Supply either failure_state_id (looked up from ImpactStore) or
    failure_state inline (for bootstrap/demo contexts).
    """
    from ..proof.engine import get_proof_engine, ProofMode

    tenant_id = body.tenant_id or get_request_tenant_id(request)
    governor  = getattr(request.app.state, "governor", None)

    # Resolve failure state
    fs = body.failure_state
    if fs is None and body.failure_state_id:
        try:
            from ..impact.store import get_impact_store
            store  = get_impact_store()
            states = store.get_failure_states(tenant_id=tenant_id, limit=1000)
            fs = next(
                (s for s in states if s.get("failure_state_id") == body.failure_state_id),
                None
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"ImpactStore lookup failed: {exc}")

    if fs is None:
        raise HTTPException(
            status_code=404,
            detail="No failure_state found. Provide failure_state_id or failure_state inline.",
        )

    try:
        mode = ProofMode(body.mode)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{body.mode}'. Use: logical | simulated | controlled",
        )

    engine = get_proof_engine()

    if mode == ProofMode.LOGICAL:
        result = engine.prove(fs)
    else:
        result = await engine.prove_async(fs, mode=mode, governor=governor, tenant_id=tenant_id)

    return result.to_dict()


@router.post("/sandbox")
async def run_sandbox_proof(body: ProofRequest, request: Request):
    """Run a Level 2.5 Sandbox execution trace for a failure state.

    No governor required. Mock handlers return realistic responses showing
    exactly what data would be accessed, transmitted, and what side effects
    would occur if the exploit chain were executed.

    Returns a SandboxExecution with step-by-step trace and blast radius summary.
    """
    from ..proof.logical import generate_logical_proof
    from ..proof.sandbox import execute_sandbox

    tenant_id = body.tenant_id or get_request_tenant_id(request)
    governor  = getattr(request.app.state, "governor", None)

    fs = body.failure_state
    if fs is None and body.failure_state_id:
        try:
            from ..impact.store import get_impact_store
            store  = get_impact_store()
            states = store.get_failure_states(tenant_id=tenant_id, limit=1000)
            fs = next(
                (s for s in states if s.get("failure_state_id") == body.failure_state_id),
                None,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"ImpactStore lookup failed: {exc}")

    if fs is None:
        raise HTTPException(
            status_code=404,
            detail="No failure_state found. Provide failure_state_id or failure_state inline.",
        )

    logical = generate_logical_proof(fs)
    sandbox = execute_sandbox(logical, fs, governor=governor, tenant_id=tenant_id)
    return sandbox.to_dict()


@router.get("/report")
async def get_report(
    request: Request,
    tenant_id: Optional[str] = None,
    top_n: int = 10,
    include_mitigated: bool = False,
    records_at_risk: Optional[int] = None,
    edon_contract: Optional[int] = None,
):
    """Assemble the full client-facing risk report payload.

    Returns a ReportPayload JSON consumed by the frontend report renderer.
    Includes: headline numbers, per-finding exploit chains, dollar impact, and the close slide.

    Query params:
      tenant_id          — scope to a specific tenant (default: all)
      top_n              — max findings to include (default: 10, sorted by severity)
      include_mitigated  — include already-mitigated findings (default: false)
      records_at_risk    — override default records count for dollar calculations
      edon_contract      — override suggested EDON contract value in the close slide
    """
    from ..proof.report import assemble_report

    resolved_tenant = tenant_id or get_request_tenant_id(request)

    try:
        payload = assemble_report(
            tenant_id=resolved_tenant,
            top_n=top_n,
            include_mitigated=include_mitigated,
            records_at_risk=records_at_risk,
            edon_contract_override=edon_contract,
        )
        return payload.to_dict()
    except Exception as exc:
        logger.exception("[proof/report] assembly failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Report assembly failed: {exc}")


@router.post("/generate-batch")
async def generate_proof_batch(body: BatchProofRequest, request: Request):
    """Generate proofs for multiple failure states concurrently."""
    from ..proof.engine import get_proof_engine

    tenant_id = body.tenant_id or get_request_tenant_id(request)
    governor  = getattr(request.app.state, "governor", None)

    # Resolve failure states
    states: list[dict] = []
    if body.failure_states:
        states = body.failure_states
    elif body.failure_state_ids:
        try:
            from ..impact.store import get_impact_store
            all_states = get_impact_store().get_failure_states(tenant_id=tenant_id, limit=1000)
            id_set = set(body.failure_state_ids)
            states = [s for s in all_states if s.get("failure_state_id") in id_set]
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"ImpactStore lookup failed: {exc}")

    if not states:
        raise HTTPException(status_code=400, detail="No failure states found or provided")

    engine  = get_proof_engine()
    results = await engine.prove_batch(
        states,
        governor=governor,
        tenant_id=tenant_id,
        max_concurrent=body.max_concurrent,
    )

    return {
        "count": len(results),
        "mode": body.mode,
        "proofs": [r.to_dict() for r in results],
    }
