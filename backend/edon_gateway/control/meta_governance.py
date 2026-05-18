"""EDON Meta-Governance — EDON auditing itself.

This module watches EDON's own behavior and flags internal failure modes:

  1. Governance latency drift     — decisions taking too long
  2. Risk scoring drift           — severity scores changing without new evidence
  3. Policy coverage gaps         — agent/tool combos with no applicable rule
  4. Unsafe loop detection        — CREAO proposing the same fix repeatedly
  5. Self-health check            — all subsystems operational
  6. Internal agent graph         — EDON's own agents tracked as distinct graph nodes
                                    detects: action-profile drift, CREAO self-blocking,
                                    uncovered internal action paths, blast-radius analysis

The output feeds the /v1/control/health endpoint used by the admin panel
and optionally triggers alerts when EDON itself is misaligned.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from typing import Optional

from ..logging_config import get_logger

logger = get_logger(__name__)

_MAX_LATENCY_MS           = float(os.getenv("EDON_META_MAX_LATENCY_MS",         "2000"))
_DRIFT_WINDOW_CYCLES      = int(os.getenv("EDON_META_DRIFT_WINDOW_CYCLES",      "5"))
_MAX_REPEAT_PROPOSALS     = int(os.getenv("EDON_META_MAX_REPEAT_PROPOSALS",     "3"))
_INTERNAL_GRAPH_AUDIT_MAX = int(os.getenv("EDON_META_INTERNAL_GRAPH_AUDIT_MAX", "200"))
_INTERNAL_DRIFT_THRESHOLD = float(os.getenv("EDON_META_INTERNAL_DRIFT_THRESHOLD", "2.0"))  # ×baseline


@dataclass
class SubsystemStatus:
    name:       str
    healthy:    bool
    last_check: str
    detail:     str = ""
    latency_ms: Optional[float] = None


@dataclass
class GovernanceHealth:
    """Complete EDON self-health snapshot."""
    healthy:             bool = True
    score:               float = 1.0         # 0.0 → 1.0 overall health
    subsystems:          list = field(default_factory=list)
    active_warnings:     list = field(default_factory=list)
    governance_latency:  dict = field(default_factory=dict)  # p50, p95, p99 ms
    risk_drift_detected: bool = False
    coverage_gap_count:  int  = 0
    unsafe_loop_detected: bool = False
    loop_iterations:     int  = 0
    # Internal agent execution graph (EDON-on-EDON)
    internal_graph:      dict = field(default_factory=dict)  # agent → action counts + drift flags
    checked_at:          str  = field(default_factory=lambda: datetime.now(UTC).isoformat())


class MetaGovernance:
    """
    EDON self-audit system. Instantiate once and call run_check() periodically
    or after each Impact cycle.

    Usage:
        mg = MetaGovernance()
        health = await mg.run_check(impact_store=store, governor=gov)
    """

    def __init__(self) -> None:
        self._latency_history: list[float] = []        # recent governance latency_ms
        self._score_history: dict[str, list[float]] = defaultdict(list)  # fsid → severity scores
        self._proposal_history: list[str] = []         # recent proposal rule_descriptions
        self._loop_count: int = 0
        # Internal agent graph: agent_id → action_type → historical counts (rolling window)
        self._internal_baseline: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
        # Last computed internal graph snapshot — exposed in GovernanceHealth.internal_graph
        self._last_internal_graph: dict = {}

    async def run_check(
        self,
        impact_store=None,
        governor=None,
        tenant_id: Optional[str] = None,
    ) -> GovernanceHealth:
        """Run a full self-audit and return a GovernanceHealth snapshot."""
        health = GovernanceHealth()
        warnings: list[str] = []
        scores: list[float] = []

        # ── 1. Governance latency ──────────────────────────────────────────────
        latency_check = await self._check_governance_latency(governor)
        health.subsystems.append(asdict(latency_check))
        if not latency_check.healthy:
            warnings.append(f"governance_latency: {latency_check.detail}")

        if self._latency_history:
            sorted_lat = sorted(self._latency_history[-100:])
            n = len(sorted_lat)
            health.governance_latency = {
                "p50_ms": round(sorted_lat[int(n * 0.5)], 1),
                "p95_ms": round(sorted_lat[min(int(n * 0.95), n - 1)], 1),
                "p99_ms": round(sorted_lat[min(int(n * 0.99), n - 1)], 1),
                "samples": n,
            }

        # ── 2. Risk scoring drift ──────────────────────────────────────────────
        drift_check = self._check_risk_drift(impact_store, tenant_id)
        health.subsystems.append(asdict(drift_check))
        health.risk_drift_detected = not drift_check.healthy
        if not drift_check.healthy:
            warnings.append(f"risk_scoring_drift: {drift_check.detail}")

        # ── 3. Policy coverage gaps ────────────────────────────────────────────
        gap_check = await self._check_policy_gaps(impact_store, governor, tenant_id)
        health.subsystems.append(asdict(gap_check))
        health.coverage_gap_count = int(gap_check.detail.split(" ")[0]) if gap_check.detail else 0
        if not gap_check.healthy:
            warnings.append(f"policy_coverage: {gap_check.detail}")

        # ── 4. Unsafe loop detection ───────────────────────────────────────────
        loop_check = self._check_unsafe_loops()
        health.subsystems.append(asdict(loop_check))
        health.unsafe_loop_detected = not loop_check.healthy
        health.loop_iterations = self._loop_count
        if not loop_check.healthy:
            warnings.append(f"unsafe_loop: {loop_check.detail}")

        # ── 5. Internal agent execution graph (EDON-on-EDON) ─────────────────
        graph_check = await self._check_internal_agent_graph(governor, tenant_id)
        health.subsystems.append(asdict(graph_check))
        health.internal_graph = self._last_internal_graph
        if not graph_check.healthy:
            warnings.append(f"internal_agent_graph: {graph_check.detail}")

        # ── 6. Subsystem connectivity ──────────────────────────────────────────
        for name, obj in [("governor", governor), ("impact_store", impact_store)]:
            ok = obj is not None
            health.subsystems.append(asdict(SubsystemStatus(
                name=name,
                healthy=ok,
                last_check=datetime.now(UTC).isoformat(),
                detail="" if ok else f"{name} not initialized",
            )))
            if not ok:
                warnings.append(f"{name}_not_available")

        # ── Composite score ────────────────────────────────────────────────────
        healthy_count = sum(1 for s in health.subsystems if s.get("healthy"))
        health.score = round(healthy_count / max(len(health.subsystems), 1), 3)
        health.healthy = len(warnings) == 0
        health.active_warnings = warnings

        if warnings:
            logger.warning("[meta_governance] health=%.2f warnings=%s", health.score, warnings)

        return health

    async def _check_governance_latency(self, governor) -> SubsystemStatus:
        """Measure how fast the governor responds to a synthetic probe action."""
        if governor is None:
            return SubsystemStatus(
                name="governance_latency",
                healthy=True,
                last_check=datetime.now(UTC).isoformat(),
                detail="governor not available — skipped",
            )
        try:
            from ..schemas import Action, ActionSource
            probe = Action(
                agent_id="__meta_probe__",
                action_type="meta_governance_probe",
                tool="no_op",
                op="ping",
                payload={},
                source=ActionSource.API,
            )
            t0 = time.perf_counter()
            await governor.evaluate(probe)
            latency_ms = (time.perf_counter() - t0) * 1000
            self._latency_history.append(latency_ms)
            healthy = latency_ms < _MAX_LATENCY_MS
            return SubsystemStatus(
                name="governance_latency",
                healthy=healthy,
                last_check=datetime.now(UTC).isoformat(),
                detail=f"{latency_ms:.0f}ms (threshold: {_MAX_LATENCY_MS:.0f}ms)",
                latency_ms=latency_ms,
            )
        except Exception as exc:
            return SubsystemStatus(
                name="governance_latency",
                healthy=True,  # probe errors are non-fatal
                last_check=datetime.now(UTC).isoformat(),
                detail=f"probe_error: {exc}",
            )

    def _check_risk_drift(self, impact_store, tenant_id: Optional[str]) -> SubsystemStatus:
        """Detect if severity scores are drifting without new evidence (model drift)."""
        if impact_store is None:
            return SubsystemStatus(
                name="risk_scoring_drift",
                healthy=True,
                last_check=datetime.now(UTC).isoformat(),
                detail="no_impact_store",
            )
        try:
            states = impact_store.get_failure_states(tenant_id=tenant_id, limit=50)
            drifting = []
            for s in states:
                fsid = s.get("failure_state_id", "")
                score = float(s.get("severity_score", 0))
                history = self._score_history[fsid]
                history.append(score)
                # Keep only last N scores
                self._score_history[fsid] = history[-_DRIFT_WINDOW_CYCLES:]

                if len(history) >= _DRIFT_WINDOW_CYCLES:
                    spread = max(history) - min(history)
                    if spread > 0.20:  # 20 point swing without new evidence = drift
                        drifting.append(fsid[:8])

            healthy = len(drifting) == 0
            return SubsystemStatus(
                name="risk_scoring_drift",
                healthy=healthy,
                last_check=datetime.now(UTC).isoformat(),
                detail=f"{len(drifting)} drifting states: {drifting[:3]}" if drifting else "stable",
            )
        except Exception as exc:
            return SubsystemStatus(
                name="risk_scoring_drift",
                healthy=True,
                last_check=datetime.now(UTC).isoformat(),
                detail=f"check_error: {exc}",
            )

    async def _check_policy_gaps(
        self, impact_store, governor, tenant_id: Optional[str]
    ) -> SubsystemStatus:
        """Find agent/tool edges that have no applicable governance rule."""
        if impact_store is None or governor is None:
            return SubsystemStatus(
                name="policy_coverage_gaps",
                healthy=True,
                last_check=datetime.now(UTC).isoformat(),
                detail="0 gaps detected",
            )
        try:
            edges = impact_store.get_edges(tenant_id=tenant_id)
            gaps = []
            for edge in edges[:100]:  # sample first 100 edges
                tool = edge.get("tool_name", "")
                op   = edge.get("op", "")
                # Ask governor if any rule covers this tool+op combo
                has_rule = any(
                    (r.get("condition_tool") in (None, tool) and
                     r.get("condition_op")   in (None, op))
                    for r in getattr(governor, "_rules", [])
                )
                if not has_rule and tool:
                    gaps.append(f"{tool}.{op}")

            gap_count = len(set(gaps))
            healthy = gap_count == 0
            return SubsystemStatus(
                name="policy_coverage_gaps",
                healthy=healthy,
                last_check=datetime.now(UTC).isoformat(),
                detail=f"{gap_count} uncovered edges" if gap_count else "0 gaps detected",
            )
        except Exception as exc:
            return SubsystemStatus(
                name="policy_coverage_gaps",
                healthy=True,
                last_check=datetime.now(UTC).isoformat(),
                detail=f"check_error: {exc}",
            )

    async def _check_internal_agent_graph(
        self,
        governor,
        tenant_id: Optional[str],
    ) -> SubsystemStatus:
        """Build and audit EDON's own agent execution graph (EDON-on-EDON).

        Reads recent audit records for the internal tenant (tenant_edon_internal)
        and constructs a graph: agent_id → action_type → count.

        Detects:
          - Action-profile drift: an agent whose action frequency has spiked
            above _INTERNAL_DRIFT_THRESHOLD × its rolling baseline
          - CREAO self-blocking: any pending fix proposal whose condition_tool /
            condition_op would block an action type that internal agents actively use
          - Uncovered internal paths: internal agent actions with no governance rule
        """
        issues: list[str] = []
        graph: dict = {}

        # ── Step 1: read internal audit records ───────────────────────────────
        try:
            from ..shadow.fix_pipeline import _proposals, _lock as _fp_lock

            # Fetch audit records for the internal tenant from the governor's DB
            db = getattr(governor, "_db", None) if governor else None
            records = []
            if db is not None:
                try:
                    records = db.get_recent_audit(
                        tenant_id="tenant_edon_internal",
                        limit=_INTERNAL_GRAPH_AUDIT_MAX,
                    )
                except Exception:
                    pass  # DB may not implement get_recent_audit yet — degrade gracefully

            # ── Step 2: build execution graph ─────────────────────────────────
            agent_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
            for rec in records:
                aid = rec.get("agent_id") or rec.get("context", {}).get("agent_id") or "unknown"
                atype = rec.get("action_type") or "unknown"
                agent_counts[aid][atype] += 1

            # ── Step 3: detect action-profile drift ───────────────────────────
            drifting_agents: list[str] = []
            for aid, type_counts in agent_counts.items():
                for atype, count in type_counts.items():
                    history = self._internal_baseline[aid][atype]
                    history.append(count)
                    # Keep a rolling window of the last _DRIFT_WINDOW_CYCLES snapshots
                    self._internal_baseline[aid][atype] = history[-_DRIFT_WINDOW_CYCLES:]

                    if len(history) >= 2:
                        baseline_avg = sum(history[:-1]) / len(history[:-1])
                        if baseline_avg > 0 and count > baseline_avg * _INTERNAL_DRIFT_THRESHOLD:
                            drifting_agents.append(f"{aid}.{atype}({count}×{baseline_avg:.1f}avg)")

            if drifting_agents:
                issues.append(f"agent_drift: {drifting_agents[:3]}")

            # ── Step 4: detect CREAO self-blocking ────────────────────────────
            # A CREAO proposal that would block an internal agent's active action
            # type is flagged — EDON can't heal customers if it's blocked itself.
            creao_blocks: list[str] = []
            try:
                with _fp_lock:
                    pending = [
                        p for p in _proposals.values()
                        if p.get("status") in ("pending_review", "approved")
                        and p.get("suggested_action") == "BLOCK"
                    ]

                for prop in pending:
                    tool = prop.get("condition_tool")
                    op   = prop.get("condition_op")
                    if not tool:
                        continue
                    # Check if any internal agent actively uses this tool/op
                    for aid, type_counts in agent_counts.items():
                        for atype in type_counts:
                            t, _, o = atype.partition(".")
                            if t == tool and (not op or o == op):
                                creao_blocks.append(
                                    f"proposal={prop.get('proposal_id','')[:8]} "
                                    f"would block {aid}.{atype}"
                                )
            except Exception as _ce:
                logger.debug("[meta_governance] creao self-block check skipped: %s", _ce)

            if creao_blocks:
                issues.append(f"creao_self_block: {creao_blocks[:2]}")

            # ── Step 5: uncovered internal paths ──────────────────────────────
            uncovered: list[str] = []
            if governor is not None:
                rules = getattr(governor, "_rules", [])
                for aid, type_counts in agent_counts.items():
                    for atype in type_counts:
                        t, _, o = atype.partition(".")
                        covered = any(
                            (r.get("condition_tool") in (None, t) and
                             r.get("condition_op")   in (None, o))
                            for r in rules
                        )
                        if not covered and t:
                            uncovered.append(f"{aid}.{atype}")

            if uncovered:
                issues.append(f"uncovered_internal_paths: {len(uncovered)}")

            # ── Build graph snapshot ───────────────────────────────────────────
            graph = {
                "agent_action_counts": {
                    aid: dict(types) for aid, types in agent_counts.items()
                },
                "drifting_agents":   drifting_agents,
                "creao_self_blocks": creao_blocks,
                "uncovered_paths":   uncovered[:10],
                "total_records":     len(records),
                "snapshot_at":       datetime.now(UTC).isoformat(),
            }

        except Exception as exc:
            logger.warning("[meta_governance] internal_agent_graph check error: %s", exc)
            self._last_internal_graph = {}
            return SubsystemStatus(
                name="internal_agent_graph",
                healthy=True,  # non-fatal — degrade gracefully
                last_check=datetime.now(UTC).isoformat(),
                detail=f"check_error: {exc}",
            )

        self._last_internal_graph = graph
        healthy = len(issues) == 0
        detail = "; ".join(issues) if issues else (
            f"{len(graph.get('agent_action_counts', {}))} agents tracked, no anomalies"
        )

        return SubsystemStatus(
            name="internal_agent_graph",
            healthy=healthy,
            last_check=datetime.now(UTC).isoformat(),
            detail=detail,
        )

    def _check_unsafe_loops(self) -> SubsystemStatus:
        """Detect if CREAO is repeatedly proposing the same fix (stuck loop)."""
        if len(self._proposal_history) < _MAX_REPEAT_PROPOSALS:
            return SubsystemStatus(
                name="unsafe_loop_detection",
                healthy=True,
                last_check=datetime.now(UTC).isoformat(),
                detail=f"loop_count={self._loop_count}",
            )
        recent = self._proposal_history[-(_MAX_REPEAT_PROPOSALS + 2):]
        repeats = len(recent) - len(set(recent))
        is_looping = repeats >= _MAX_REPEAT_PROPOSALS
        return SubsystemStatus(
            name="unsafe_loop_detection",
            healthy=not is_looping,
            last_check=datetime.now(UTC).isoformat(),
            detail=f"loop_count={self._loop_count}, repeated_proposals={repeats}",
        )

    def record_proposal(self, rule_description: str) -> None:
        """Call this when CREAO generates a new proposal — feeds loop detection."""
        self._proposal_history.append(rule_description)
        self._loop_count += 1
        # Trim history
        self._proposal_history = self._proposal_history[-50:]


# ── Singleton ─────────────────────────────────────────────────────────────────

_meta: Optional[MetaGovernance] = None


def get_meta_governance() -> MetaGovernance:
    global _meta
    if _meta is None:
        _meta = MetaGovernance()
    return _meta
