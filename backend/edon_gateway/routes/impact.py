"""EDON Impact — HTTP API routes.

Exposes the four-engine continuous risk intelligence system over REST.

Endpoints:
    POST  /v1/impact/run-cycle          — trigger a full A→B→C→D cycle
    GET   /v1/impact/graph              — execution graph (agents, tools, edges)
    GET   /v1/impact/failure-states     — list discovered failure states
    GET   /v1/impact/failure-states/{id} — detail + scenarios for one failure state
    GET   /v1/impact/scenarios          — list red team scenarios
    GET   /v1/impact/coverage           — latest coverage snapshot
    GET   /v1/impact/report             — full risk intelligence report (JSON)
    GET   /v1/impact/report.csv         — CSV version for CISO/compliance
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, UTC
from typing import Optional

from fastapi import APIRouter, Query, Request, HTTPException
from fastapi.responses import StreamingResponse

from ..tenancy import get_request_tenant_id
from ..impact.store import get_impact_store
from ..logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v1/impact", tags=["impact"])


# ── Cycle trigger ──────────────────────────────────────────────────────────────


@router.post("/run-cycle")
async def run_impact_cycle(
    request: Request,
    force: bool = Query(False, description="Skip minimum-interval gate and run immediately"),
    limit_traces: int = Query(500, le=2000, description="Max shadow traces to ingest"),
):
    """Trigger a full Engine A→B→C→D cycle.

    Engine A ingests recent shadow traces into the execution graph and
    enumerates failure states. Engine B generates adversarial scenarios
    for new failure states. Engine C validates each scenario. Engine D
    saves a coverage snapshot.

    Returns a cycle summary with counts and timing. Idempotent — if run
    recently, returns skip message unless force=true.
    """
    from ..impact.loop import run_cycle
    from ..shadow.trace_capture import get_trace_store

    governor = getattr(request.app.state, "governor", None)
    tenant_id = get_request_tenant_id(request)
    shadow_store = get_trace_store()
    impact_store = get_impact_store()

    summary = await run_cycle(
        tenant_id=tenant_id,
        governor=governor,
        shadow_store=shadow_store,
        impact_store=impact_store,
        force=force,
    )
    return summary


# ── Execution graph ────────────────────────────────────────────────────────────


@router.get("/graph")
async def get_execution_graph(
    request: Request,
    include_edges: bool = Query(True),
):
    """Return the current execution graph: agents, tools, and edges.

    The graph is built from real agent telemetry captured by /v1/action.
    Each node and edge is evidence-backed — nothing is assumed.
    """
    tenant_id = get_request_tenant_id(request)
    store = get_impact_store()

    agents = store.get_agents(tenant_id=tenant_id)
    tools = store.get_tools()
    edges = store.get_edges(tenant_id=tenant_id) if include_edges else []

    return {
        "agents": agents,
        "tools": tools,
        "edges": edges,
        "stats": {
            "agent_count": len(agents),
            "tool_count": len(tools),
            "edge_count": len(edges),
        },
    }


# ── Failure states ─────────────────────────────────────────────────────────────


@router.get("/failure-states")
async def get_failure_states(
    request: Request,
    vulnerability_class: Optional[str] = Query(None, enum=[
        "data_exfiltration", "privilege_escalation", "confused_deputy",
        "prompt_injection_propagation", "policy_bypass_via_chaining",
        "unconstrained_credential_access", "unconstrained_tool_fanout",
        "audit_gap", "kill_switch_bypass",
    ]),
    verified_only: bool = Query(False),
    limit: int = Query(50, le=200),
):
    """List discovered failure states, ranked by severity score.

    verified=true means there is trace evidence proving the path is reachable.
    severity_score = (likelihood × blast_radius) / recoverability_factor.
    """
    tenant_id = get_request_tenant_id(request)
    store = get_impact_store()
    states = store.get_failure_states(
        tenant_id=tenant_id,
        vulnerability_class=vulnerability_class,
        verified_only=verified_only,
        limit=limit,
    )
    # Derive status string from DB fields so the UI can render it directly
    for s in states:
        if s.get("mitigated_at"):
            s["status"] = "mitigated"
        elif s.get("verified"):
            s["status"] = "confirmed"
        else:
            scenarios = store.get_scenarios(failure_state_id=s["failure_state_id"], limit=1)
            s["status"] = "probed" if scenarios else "unprobed"
    return {
        "failure_states": states,
        "count": len(states),
        "tenant_id": tenant_id,
    }


@router.get("/failure-states/{failure_state_id}")
async def get_failure_state_detail(
    failure_state_id: str,
    request: Request,
):
    """Return a single failure state with all associated scenarios and validations."""
    tenant_id = get_request_tenant_id(request)
    store = get_impact_store()

    fs = store.get_failure_state(failure_state_id)
    if fs is None:
        raise HTTPException(
            status_code=404,
            detail=f"Failure state '{failure_state_id}' not found. "
                   "Run POST /v1/impact/run-cycle to discover failure states."
        )

    scenarios = store.get_scenarios(failure_state_id=failure_state_id)
    for s in scenarios:
        s["validation"] = store.get_validation(s["scenario_id"])

    return {
        "failure_state": fs,
        "scenarios": scenarios,
        "scenario_count": len(scenarios),
        "valid_scenario_count": sum(1 for s in scenarios if s.get("validation_status") == "valid"),
    }


# ── Scenarios ──────────────────────────────────────────────────────────────────


@router.get("/scenarios")
async def get_scenarios(
    request: Request,
    failure_state_id: Optional[str] = Query(None),
    validation_status: Optional[str] = Query(None, enum=["pending", "valid", "invalid", "partial"]),
    limit: int = Query(50, le=200),
):
    """List AI-generated red team scenarios.

    Only scenarios with validation_status='valid' are confirmed findings.
    Pending scenarios are awaiting Engine C verification.
    """
    store = get_impact_store()
    scenarios = store.get_scenarios(
        failure_state_id=failure_state_id,
        validation_status=validation_status,
        limit=limit,
    )
    return {"scenarios": scenarios, "count": len(scenarios)}


# ── Coverage ───────────────────────────────────────────────────────────────────


@router.get("/coverage")
async def get_coverage(request: Request):
    """Return the latest coverage snapshot.

    Coverage measures how much of the reachable execution state space has been
    explored. new_edges_since_last and new_failure_states_since_last show
    whether the system is discovering new risk surface.
    """
    tenant_id = get_request_tenant_id(request)
    store = get_impact_store()
    snap = store.latest_coverage(tenant_id=tenant_id)
    if snap is None:
        return {
            "message": "No coverage data yet. Run POST /v1/impact/run-cycle first.",
            "coverage": None,
        }
    return {"coverage": snap}


# ── Full report ────────────────────────────────────────────────────────────────


@router.get("/report")
async def get_impact_report(
    request: Request,
    verified_only: bool = Query(False),
):
    """Return a full risk intelligence report as structured JSON.

    Includes: executive summary, failure states ranked by severity,
    confirmed exploitation scenarios, coverage metrics, and remediation guidance.
    """
    tenant_id = get_request_tenant_id(request)
    store = get_impact_store()

    all_fs = store.get_failure_states(tenant_id=tenant_id, limit=200)
    critical = [f for f in all_fs if f["severity_score"] >= 0.5]
    high = [f for f in all_fs if 0.25 <= f["severity_score"] < 0.5]
    medium = [f for f in all_fs if f["severity_score"] < 0.25]

    valid_scenarios = store.get_scenarios(validation_status="valid", limit=200)
    coverage = store.latest_coverage(tenant_id=tenant_id)

    def _enrich_fs(fs: dict) -> dict:
        fs = dict(fs)
        scenarios = store.get_scenarios(failure_state_id=fs["failure_state_id"], limit=5)
        fs["confirmed_scenarios"] = [s for s in scenarios if s.get("validation_status") == "valid"]
        fs["scenario_count"] = len(scenarios)
        return fs

    return {
        "report": {
            "generated_at": datetime.now(UTC).isoformat(),
            "tenant_id": tenant_id,
            "tool": "EDON Impact — Continuous AI Risk Intelligence",
        },
        "executive_summary": {
            "total_failure_states": len(all_fs),
            "critical": len(critical),
            "high": len(high),
            "medium": len(medium),
            "confirmed_scenarios": len(valid_scenarios),
            "coverage": coverage,
        },
        "critical_failure_states": [_enrich_fs(f) for f in critical],
        "high_failure_states": [_enrich_fs(f) for f in high[:10]],
        "all_confirmed_scenarios": valid_scenarios,
    }


@router.get("/report.csv")
async def get_impact_report_csv(request: Request):
    """Return the risk intelligence report as a CSV for CISO/compliance filing."""
    tenant_id = get_request_tenant_id(request)
    store = get_impact_store()
    all_fs = store.get_failure_states(tenant_id=tenant_id, limit=1000)
    coverage = store.latest_coverage(tenant_id=tenant_id) or {}

    buf = io.StringIO()
    writer = csv.writer(buf)

    writer.writerow(["EDON Impact — AI Risk Intelligence Report"])
    writer.writerow(["Generated", datetime.now(UTC).isoformat()])
    writer.writerow(["Tenant", tenant_id or "all"])
    writer.writerow([])

    writer.writerow(["COVERAGE SUMMARY"])
    writer.writerow(["Agents discovered", coverage.get("agent_count", 0)])
    writer.writerow(["Tools discovered", coverage.get("tool_count", 0)])
    writer.writerow(["Execution edges", coverage.get("edge_count", 0)])
    writer.writerow(["Failure states found", coverage.get("failure_state_count", 0)])
    writer.writerow(["Verified failure states", coverage.get("verified_failure_count", 0)])
    writer.writerow(["Valid exploitation scenarios", coverage.get("valid_scenario_count", 0)])
    writer.writerow([])

    writer.writerow(["FAILURE STATES"])
    writer.writerow([
        "failure_state_id", "vulnerability_class", "severity_score",
        "likelihood", "blast_radius", "recoverability",
        "exploitability_window", "data_classes", "is_external_sink",
        "verified", "constraint_violation", "path",
    ])
    for f in all_fs:
        writer.writerow([
            f.get("failure_state_id"),
            f.get("vulnerability_class"),
            f.get("severity_score"),
            f.get("likelihood_score"),
            f.get("blast_radius_score"),
            f.get("recoverability_factor"),
            f.get("exploitability_window"),
            " | ".join(f.get("data_classes", [])),
            f.get("is_external_sink"),
            f.get("verified"),
            f.get("constraint_violation"),
            " → ".join(f.get("path", [])),
        ])

    writer.writerow([])
    writer.writerow(["EXPLOITATION SCENARIOS (VALID)"])
    writer.writerow([
        "scenario_id", "failure_state_id", "title",
        "attacker_type", "attack_vector", "validation_status",
        "impact_description", "generated_at",
    ])
    valid_scenarios = store.get_scenarios(validation_status="valid", limit=500)
    for s in valid_scenarios:
        writer.writerow([
            s.get("scenario_id"), s.get("failure_state_id"), s.get("title"),
            s.get("attacker_type"), s.get("attack_vector"),
            s.get("validation_status"), s.get("impact_description"),
            s.get("generated_at"),
        ])

    buf.seek(0)
    fname = f"edon_impact_report_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


@router.get("/probe/status")
async def get_probe_status(request: Request):
    """Return active adversarial probe scheduler status and last run findings."""
    try:
        from ..impact.active_probe import get_active_probe
        return get_active_probe().status()
    except Exception as exc:
        return {"error": str(exc)}


@router.post("/probe/run")
async def run_probe_now(request: Request):
    """Trigger one immediate probe cycle (non-blocking in background)."""
    import threading
    try:
        from ..impact.active_probe import get_active_probe
        probe = get_active_probe()
        t = threading.Thread(target=probe.run_once, daemon=True, name="probe_manual")
        t.start()
        return {"status": "probe_started", "seed_count": len(probe._findings) or 8}
    except Exception as exc:
        return {"error": str(exc)}


@router.get("/fleet/stats")
async def get_fleet_stats(request: Request, window_h: float = 24.0):
    """Return cross-tenant action fingerprint stats — top campaign patterns."""
    try:
        from ..fleet.campaign_detector import get_campaign_detector
        return get_campaign_detector().fleet_stats(window_h=window_h)
    except Exception as exc:
        return {"error": str(exc)}


@router.get("/latency/sla")
async def get_latency_sla(_request: Request):
    """Return p50/p95/p99 latency stats and SLA breach status for each
    pre-governor enrichment layer.

    status values:
      ok      → p95 within budget
      warn    → p95 > 1.5× budget
      breach  → p95 > 2.0× budget
      no_data → insufficient samples
    """
    from ..latency_guard import sla_stats, budget_summary
    stats = sla_stats()
    overall = "ok"
    for layer_stat in stats.values():
        s = layer_stat.get("status", "ok")
        if s == "breach":
            overall = "breach"
            break
        if s == "warn" and overall == "ok":
            overall = "warn"
    return {
        "overall_status": overall,
        "budgets_ms":     budget_summary(),
        "layers":         stats,
    }
