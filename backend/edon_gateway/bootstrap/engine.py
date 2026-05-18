"""EDON Bootstrap Engine.

Orchestrates the full cold-start intake pipeline:

  1. Parse artifacts    (parser.py)
  2. Build graph        (graph_builder.py → ImpactStore)
  3. Find failure states (impact/graph.py enumerate_failure_states)
  4. Red team top paths  (impact/red_team.py)
  5. Validate scenarios  (impact/validator.py)
  6. Generate report     (first findings — the "oh shit" moment)

The report is what gets shown in Phase 1 of the customer lifecycle.
It contains:
  - Top 3 failure states ranked by severity
  - Multi-path exploit tree per finding
  - $ impact estimate per path
  - Data sources used + confidence level
  - Narrative summary ("what we found in X minutes")

Usage:
    result = await run_bootstrap(
        tenant_id="acme_corp",
        openapi_spec=spec_dict,
        agent_config=config_dict,
        log_lines=lines,
        job_id=job_id,          # optional — for progress tracking
    )
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from typing import Optional

from ..logging_config import get_logger
from .parser import parse_artifacts, ParsedSystem
from .graph_builder import build_graph
from .job_store import update_job

logger = get_logger(__name__)


# ── $ impact estimation ────────────────────────────────────────────────────────
# Industry baseline estimates (conservative). Multiply by blast_radius score.

_BASE_IMPACT_USD: dict[str, float] = {
    "data_exfiltration":             500_000,
    "privilege_escalation":          250_000,
    "prompt_injection_propagation":  150_000,
    "policy_bypass_via_chaining":    300_000,
    "unconstrained_tool_fanout":     100_000,
    "confused_deputy":               200_000,
    "audit_gap":                      50_000,
    "unconstrained_credential_access": 400_000,
    "kill_switch_bypass":            150_000,
    "_default":                      100_000,
}

_DATA_CLASS_MULTIPLIER: dict[str, float] = {
    "PHI":      3.0,   # HIPAA exposure
    "PCI":      2.5,   # PCI-DSS fines
    "PII":      1.5,   # GDPR / CCPA
    "AUTH":     2.0,   # credential theft
    "INTERNAL": 1.0,
    "PUBLIC":   0.3,
}


def _estimate_impact_usd(failure_state: dict) -> dict:
    """Estimate financial impact for a single failure state."""
    vuln_class = failure_state.get("vulnerability_class", "_default")
    base = _BASE_IMPACT_USD.get(vuln_class, _BASE_IMPACT_USD["_default"])
    severity = float(failure_state.get("severity_score", 0.5))
    data_classes = failure_state.get("data_classes", ["INTERNAL"])

    # Apply highest data class multiplier
    dc_mult = max(
        (_DATA_CLASS_MULTIPLIER.get(dc, 1.0) for dc in data_classes),
        default=1.0,
    )
    estimated = round(base * severity * dc_mult)
    return {
        "estimated_usd": estimated,
        "base_usd": base,
        "severity_score": severity,
        "data_class_multiplier": dc_mult,
        "calculation": f"${base:,.0f} × {severity:.2f} severity × {dc_mult:.1f} data_class",
    }


# ── Path narrative builder ─────────────────────────────────────────────────────

def _path_narrative(path: list[str], vuln_class: str) -> str:
    """Convert a graph path into a human-readable attack narrative."""
    parts = []
    for node in path:
        if node.startswith("agent:"):
            parts.append(f"Agent '{node[6:]}' initiates")
        elif node.startswith("tool:"):
            parts.append(f"calls {node[5:]} tool")
        elif node.startswith("op:"):
            parts.append(f"performing '{node[3:]}' operation")
        elif node.startswith("read:"):
            parts.append(f"reads from {node[5:]}")
        elif node.startswith("write:"):
            parts.append(f"writes to {node[6:]}")
        elif node == "sink:external":
            parts.append("→ data exits system boundary")
        elif node == "sink:internal":
            parts.append("→ internal system affected")
        elif node == "user_input":
            parts.append("User-controlled input enters")
        elif node == "subagent:spawned":
            parts.append("spawning ungoverned sub-agent")
    return " → ".join(parts) if parts else f"{vuln_class} path"


# ── Report model ───────────────────────────────────────────────────────────────

@dataclass
class ExploitPath:
    path_id: str
    narrative: str
    estimated_usd: int
    severity_score: float
    exploitability_window: str
    data_classes: list[str]


@dataclass
class FindingCard:
    failure_state_id: str
    vulnerability_class: str
    description: str
    severity_score: float
    total_estimated_usd: int
    exploit_paths: list[dict]
    constraint_violation: str
    verified: bool                     # True = confirmed by log evidence
    source_type: str                   # "openapi" | "log" | "agent_config" | "mixed"
    proof: Optional[dict] = None       # Level 1 LogicalProof (always present)
    sandbox: Optional[dict] = None     # Level 2.5 Sandbox execution trace


@dataclass
class BootstrapReport:
    """The first findings report. This is the Phase 1 customer deliverable."""
    tenant_id: Optional[str]
    job_id: str

    # System graph summary
    agents_discovered: int
    tools_discovered: int
    endpoints_analyzed: int
    log_lines_processed: int
    data_sources: list[str]

    # Findings
    total_failure_states: int
    critical_count: int              # severity >= 0.75
    high_count: int                  # severity >= 0.50
    top_findings: list[dict]         # top 3 FindingCards as dicts

    # Headline numbers (for the Impact screen)
    total_estimated_risk_usd: int
    top_vulnerability_class: str
    confidence: float                # 0–1, based on data source quality

    # Graph ingest summary
    graph_summary: dict

    # Narrative
    executive_summary: str

    # Meta
    elapsed_seconds: float
    completed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    warnings: list[str] = field(default_factory=list)


# ── Engine ────────────────────────────────────────────────────────────────────

class BootstrapEngine:
    """Cold-start intake orchestrator."""

    async def run(
        self,
        *,
        tenant_id: Optional[str] = None,
        openapi_spec: Optional[dict] = None,
        openapi_yaml: Optional[str] = None,
        agent_config: Optional[dict | list] = None,
        log_lines: Optional[list[str]] = None,
        job_id: Optional[str] = None,
        impact_store=None,
    ) -> BootstrapReport:
        """Run the full bootstrap pipeline and return a BootstrapReport."""
        t0 = time.perf_counter()
        job_id = job_id or str(uuid.uuid4())
        tid = tenant_id

        def _progress(pct: int, msg: str) -> None:
            update_job(job_id, status="running", progress=pct, progress_message=msg)
            logger.info("[bootstrap] %d%% — %s", pct, msg)

        _progress(5, "parsing artifacts")

        # ── Step 1: Parse ──────────────────────────────────────────────────────
        system: ParsedSystem = await asyncio.to_thread(
            parse_artifacts,
            openapi_spec=openapi_spec,
            openapi_yaml=openapi_yaml,
            agent_config=agent_config,
            log_lines=log_lines or [],
            tenant_id=tid,
        )
        _progress(20, f"parsed {len(system.source_types)} artifact types")

        # ── Step 2: Build graph ────────────────────────────────────────────────
        if impact_store is None:
            from ..impact.store import get_impact_store
            impact_store = get_impact_store()

        graph_summary = await asyncio.to_thread(build_graph, system, impact_store, tid)
        _progress(40, f"built graph: {graph_summary['edges_created']} edges")

        # ── Step 3: Enumerate failure states ──────────────────────────────────
        from ..impact.graph import enumerate_failure_states
        failure_states = await asyncio.to_thread(
            enumerate_failure_states, impact_store, tid
        )
        _progress(60, f"found {len(failure_states)} failure states")

        # ── Step 4: Red team top 3 findings ───────────────────────────────────
        fs_dicts = [fs.to_dict() if hasattr(fs, "to_dict") else asdict(fs)
                    for fs in failure_states]
        # Sort by severity descending, take top 5 for red team
        top_states = sorted(
            fs_dicts, key=lambda s: s.get("severity_score", 0), reverse=True
        )[:5]

        scenarios: list[dict] = []
        if top_states:
            try:
                from ..impact.red_team import generate_scenarios_async
                from ..impact.schemas import FailureState as FS
                for fs_dict in top_states:
                    try:
                        fs_obj = FS(**{k: fs_dict[k] for k in FS.__dataclass_fields__ if k in fs_dict})
                        fs_scenarios = await generate_scenarios_async(fs_obj, impact_store)
                        scenarios.extend([
                            s.to_dict() if hasattr(s, "to_dict") else asdict(s)
                            for s in fs_scenarios
                        ])
                    except Exception as _se:
                        logger.debug("[bootstrap] red_team for fs failed: %s", _se)
                _progress(80, f"generated {len(scenarios)} exploit scenarios")
            except Exception as exc:
                logger.warning("[bootstrap] red_team failed (non-blocking): %s", exc)
                _progress(80, "red team skipped (non-blocking)")

        # ── Step 4b: Level 1 Logical Proofs + Level 2.5 Sandbox (always available) ──
        _progress(75, "generating proofs and sandbox traces")
        from ..proof.engine import get_proof_engine
        proof_engine = get_proof_engine()
        proof_by_fs: dict[str, dict] = {}
        sandbox_by_fs: dict[str, dict] = {}
        for fs in top_states[:3]:
            try:
                proof_result = proof_engine.prove(fs)
                pr_dict = proof_result.to_dict()
                proof_by_fs[fs.get("failure_state_id", "")] = pr_dict
                if pr_dict.get("sandbox_proof"):
                    sandbox_by_fs[fs.get("failure_state_id", "")] = pr_dict["sandbox_proof"]
            except Exception as exc:
                logger.debug("[bootstrap] proof generation failed (non-blocking): %s", exc)

        # ── Step 5: Build finding cards ────────────────────────────────────────
        finding_cards: list[FindingCard] = []
        scenario_by_fs: dict[str, list[dict]] = {}
        for s in scenarios:
            fsid = s.get("failure_state_id", "")
            scenario_by_fs.setdefault(fsid, []).append(s)

        for fs in top_states[:3]:
            fsid   = fs.get("failure_state_id", "")
            vuln   = fs.get("vulnerability_class", "unknown")
            impact = _estimate_impact_usd(fs)
            path   = fs.get("path", [])

            # Build exploit paths from scenarios + the raw failure state
            exploit_paths: list[dict] = []
            fs_scenarios = scenario_by_fs.get(fsid, [])

            if fs_scenarios:
                for sc in fs_scenarios[:3]:
                    sc_path = sc.get("scenario_path") or path
                    sc_impact = _estimate_impact_usd({
                        **fs,
                        "severity_score": float(sc.get("severity_score", fs.get("severity_score", 0.5))),
                    })
                    exploit_paths.append({
                        "path_id": sc.get("scenario_id", str(uuid.uuid4()))[:8],
                        "narrative": sc.get("description") or _path_narrative(sc_path, vuln),
                        "estimated_usd": sc_impact["estimated_usd"],
                        "severity_score": sc.get("severity_score", fs.get("severity_score")),
                        "exploitability_window": sc.get("exploitability_window",
                                                        fs.get("exploitability_window", "session")),
                        "data_classes": sc.get("data_classes", fs.get("data_classes", [])),
                        "confidence_score": sc.get("confidence_score", 0.5),
                    })
            else:
                # No scenarios — fall back to the failure state itself as a single path
                exploit_paths.append({
                    "path_id": fsid[:8],
                    "narrative": _path_narrative(path, vuln),
                    "estimated_usd": impact["estimated_usd"],
                    "severity_score": fs.get("severity_score", 0),
                    "exploitability_window": fs.get("exploitability_window", "session"),
                    "data_classes": fs.get("data_classes", []),
                    "confidence_score": 0.4,  # lower — no red team confirmation
                })

            # Determine source type
            evidence = fs.get("evidence_trace_ids", [])
            if any("log" in e for e in evidence):
                source_type = "log"
            elif any("agent_config" in e for e in evidence):
                source_type = "agent_config"
            elif any("openapi" in e for e in evidence):
                source_type = "openapi"
            else:
                source_type = "mixed"

            card = FindingCard(
                failure_state_id=fsid,
                vulnerability_class=vuln,
                description=fs.get("description", ""),
                severity_score=float(fs.get("severity_score", 0)),
                total_estimated_usd=sum(p["estimated_usd"] for p in exploit_paths),
                exploit_paths=exploit_paths,
                constraint_violation=fs.get("constraint_violation", ""),
                verified=bool(fs.get("verified")),
                source_type=source_type,
                proof=proof_by_fs.get(fsid),
                sandbox=sandbox_by_fs.get(fsid),
            )
            finding_cards.append(card)

        # ── Step 6: Build report ───────────────────────────────────────────────
        total_risk_usd = sum(c.total_estimated_usd for c in finding_cards)
        critical_count = sum(1 for s in fs_dicts if s.get("severity_score", 0) >= 0.75)
        high_count     = sum(1 for s in fs_dicts if 0.50 <= s.get("severity_score", 0) < 0.75)

        top_vuln = (
            finding_cards[0].vulnerability_class if finding_cards else "none"
        )

        # Confidence: higher when we have multiple source types + log evidence
        confidence = 0.3  # schema-only baseline
        if "logs" in system.source_types:
            confidence += 0.4
        if "agent_config" in system.source_types:
            confidence += 0.1
        if len(system.source_types) >= 2:
            confidence += 0.1
        if scenarios:
            confidence += 0.1
        confidence = min(round(confidence, 2), 0.95)

        # Executive summary narrative
        elapsed = round(time.perf_counter() - t0, 1)
        source_desc = " + ".join(system.source_types) if system.source_types else "artifact"
        summary = (
            f"EDON analyzed {source_desc} and discovered {len(failure_states)} potential "
            f"failure states in {elapsed}s. "
        )
        if finding_cards:
            top = finding_cards[0]
            summary += (
                f"The highest-severity finding is a {top.vulnerability_class.replace('_', ' ')} "
                f"risk with an estimated ${top.total_estimated_usd:,.0f} exposure across "
                f"{len(top.exploit_paths)} attack path{'s' if len(top.exploit_paths) != 1 else ''}. "
            )
        summary += (
            f"${total_risk_usd:,.0f} total estimated risk exposure identified. "
            f"Confidence: {int(confidence * 100)}%."
        )

        report = BootstrapReport(
            tenant_id=tid,
            job_id=job_id,
            agents_discovered=len(system.agents) or graph_summary.get("agents_created", 0),
            tools_discovered=graph_summary.get("tools_created", 0),
            endpoints_analyzed=len(system.endpoints),
            log_lines_processed=len(log_lines or []),
            data_sources=system.source_types,
            total_failure_states=len(failure_states),
            critical_count=critical_count,
            high_count=high_count,
            top_findings=[asdict(c) for c in finding_cards],
            total_estimated_risk_usd=total_risk_usd,
            top_vulnerability_class=top_vuln,
            confidence=confidence,
            graph_summary=graph_summary,
            executive_summary=summary,
            elapsed_seconds=elapsed,
            warnings=system.parse_warnings,
        )

        _progress(100, "complete")
        update_job(job_id, status="complete", report=asdict(report))

        logger.info(
            "[bootstrap] complete: tenant=%s states=%d risk=$%s elapsed=%.1fs",
            tid, len(failure_states), f"{total_risk_usd:,.0f}", elapsed,
        )
        return report


# ── Module singleton ───────────────────────────────────────────────────────────

_engine: Optional[BootstrapEngine] = None


def get_bootstrap_engine() -> BootstrapEngine:
    global _engine
    if _engine is None:
        _engine = BootstrapEngine()
    return _engine


async def run_bootstrap(
    *,
    tenant_id: Optional[str] = None,
    openapi_spec: Optional[dict] = None,
    openapi_yaml: Optional[str] = None,
    agent_config: Optional[dict | list] = None,
    log_lines: Optional[list[str]] = None,
    job_id: Optional[str] = None,
    impact_store=None,
) -> BootstrapReport:
    """Convenience wrapper — calls get_bootstrap_engine().run(...)."""
    return await get_bootstrap_engine().run(
        tenant_id=tenant_id,
        openapi_spec=openapi_spec,
        openapi_yaml=openapi_yaml,
        agent_config=agent_config,
        log_lines=log_lines,
        job_id=job_id,
        impact_store=impact_store,
    )
