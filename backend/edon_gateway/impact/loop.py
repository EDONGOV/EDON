"""Engine D — Continuous Coverage Expansion Loop.

Closes the cycle: new telemetry → graph update → failure state diff →
red team expansion → validation → coverage snapshot → repeat.

Triggers:
  1. Manual: POST /v1/impact/run-cycle
  2. On new shadow traces batch (called from shadow replay post-write)
  3. Scheduled: every N minutes via background task (configurable)

The loop is additive: each cycle only processes new state since the last run.
It never re-processes confirmed findings unless explicitly reset.

Safety:
  - Fail-open on every step: errors are logged, loop continues
  - Red team generation is gated by EDON_IMPACT_RED_TEAM_ENABLED
  - No governance decisions are made here — this is analysis only
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from dataclasses import asdict
from datetime import datetime, UTC
from typing import Optional

from .schemas import CoverageSnapshot, FailureState
from .store import ImpactStore, get_impact_store
from ..logging_config import get_logger

logger = get_logger(__name__)

_CYCLE_INTERVAL_SEC = int(os.getenv("EDON_IMPACT_CYCLE_INTERVAL_SEC", "300"))   # 5 min default
_MAX_FS_PER_CYCLE = int(os.getenv("EDON_IMPACT_MAX_FS_PER_CYCLE", "20"))
_AI_ENABLED = os.getenv("EDON_AI_ENABLED", "true").strip().lower() == "true"
_loop_lock = threading.Lock()
_last_cycle_at: dict[Optional[str], float] = {}   # tenant_id → last run timestamp


# ── Single cycle ───────────────────────────────────────────────────────────────


async def run_cycle(
    *,
    tenant_id: Optional[str] = None,
    governor=None,
    shadow_store=None,
    impact_store: Optional[ImpactStore] = None,
    force: bool = False,
) -> dict:
    """Run one full A→B→C→D cycle. Returns a summary dict.

    Args:
        tenant_id:      Scope analysis to this tenant.
        governor:       EDONGovernor — used by Engine C validation.
        shadow_store:   TraceStore — source of captured agent traces for Engine A.
        impact_store:   ImpactStore — persists graph, failure states, scenarios.
        force:          Skip the minimum-interval gate and run immediately.

    Returns:
        cycle_summary dict with counts for each stage.
    """
    from .graph import build_graph_from_store, enumerate_failure_states
    from .red_team import generate_scenarios_async
    from .validator import validate_all_scenarios_async

    now = time.time()
    tenant_key = tenant_id or "__global__"

    # ── Minimum interval gate ─────────────────────────────────────────────────
    if not force:
        last = _last_cycle_at.get(tenant_key, 0.0)
        if now - last < _CYCLE_INTERVAL_SEC:
            remaining = int(_CYCLE_INTERVAL_SEC - (now - last))
            return {
                "skipped": True,
                "reason": f"cycle ran {int(now - last)}s ago — next in {remaining}s",
            }

    _last_cycle_at[tenant_key] = now
    cycle_start = datetime.now(UTC).isoformat()
    summary: dict = {
        "tenant_id": tenant_id,
        "started_at": cycle_start,
        "edges_ingested": 0,
        "failure_states_found": 0,
        "new_failure_states": 0,
        "scenarios_generated": 0,
        "scenarios_valid": 0,
        "scenarios_invalid": 0,
        "scenarios_partial": 0,
        "errors": [],
    }

    store = impact_store or get_impact_store()
    prev_edge_count = store.edge_count(tenant_id=tenant_id)
    prev_fs_count = store.failure_state_count(tenant_id=tenant_id)

    # ── Engine A: ingest traces → build graph → enumerate failure states ───────
    try:
        if shadow_store is not None:
            edges_ingested = await asyncio.to_thread(
                build_graph_from_store,
                shadow_store, store, tenant_id,
            )
            summary["edges_ingested"] = edges_ingested
        else:
            logger.debug("[impact/loop] no shadow_store — skipping trace ingestion")
    except Exception as exc:
        logger.warning("[impact/loop] graph build failed: %s", exc)
        summary["errors"].append(f"graph_build: {exc}")

    try:
        failure_states = await asyncio.to_thread(
            enumerate_failure_states, store, tenant_id
        )
        summary["failure_states_found"] = len(failure_states)
        new_fs_count = store.failure_state_count(tenant_id=tenant_id)
        summary["new_failure_states"] = max(0, new_fs_count - prev_fs_count)
    except Exception as exc:
        logger.warning("[impact/loop] failure state enumeration failed: %s", exc)
        summary["errors"].append(f"enumerate_failure_states: {exc}")
        failure_states = []

    # ── Engine B: red team expand top N failure states ─────────────────────────
    # Prioritize by severity, only process new/unscenarioed failure states
    unprocessed = [
        fs for fs in failure_states
        if not store.get_scenarios(failure_state_id=fs.failure_state_id, limit=1)
    ]
    unprocessed.sort(key=lambda x: x.severity_score, reverse=True)
    batch = unprocessed[:_MAX_FS_PER_CYCLE]

    if not _AI_ENABLED:
        logger.debug("[impact/loop] EDON_AI_ENABLED=false — skipping red team and validation")
        batch = []

    for fs in batch:
        try:
            scenarios = await generate_scenarios_async(fs, store)
            summary["scenarios_generated"] += len(scenarios)
        except Exception as exc:
            logger.warning("[impact/loop] red team failed for fs=%s: %s", fs.failure_state_id, exc)
            summary["errors"].append(f"red_team:{fs.failure_state_id[:8]}: {exc}")

    # ── Engine C: validate all pending scenarios ───────────────────────────────
    for fs in batch:
        try:
            results = await validate_all_scenarios_async(fs, store, governor)
            for vr in results:
                if vr.status == "valid":
                    summary["scenarios_valid"] += 1
                elif vr.status == "invalid":
                    summary["scenarios_invalid"] += 1
                elif vr.status == "partial":
                    summary["scenarios_partial"] += 1
        except Exception as exc:
            logger.warning("[impact/loop] validation failed for fs=%s: %s", fs.failure_state_id, exc)
            summary["errors"].append(f"validate:{fs.failure_state_id[:8]}: {exc}")

    # ── Engine D: coverage snapshot ────────────────────────────────────────────
    try:
        agents = store.get_agents(tenant_id=tenant_id)
        tools = store.get_tools()
        current_edge_count = store.edge_count(tenant_id=tenant_id)
        current_fs_count = store.failure_state_count(tenant_id=tenant_id)
        all_scenarios = store.get_scenarios(limit=10000)
        verified_fs = store.get_failure_states(tenant_id=tenant_id, verified_only=True, limit=10000)

        prev_snap = store.latest_coverage(tenant_id=tenant_id)
        prev_edges = prev_snap["edge_count"] if prev_snap else prev_edge_count
        prev_fs = prev_snap["failure_state_count"] if prev_snap else prev_fs_count

        snap = CoverageSnapshot(
            tenant_id=tenant_id,
            agent_count=len(agents),
            tool_count=len(tools),
            edge_count=current_edge_count,
            failure_state_count=current_fs_count,
            verified_failure_count=len(verified_fs),
            scenario_count=len(all_scenarios),
            valid_scenario_count=sum(1 for s in all_scenarios if s.get("validation_status") == "valid"),
            new_edges_since_last=max(0, current_edge_count - prev_edges),
            new_failure_states_since_last=max(0, current_fs_count - prev_fs),
        )
        store.save_coverage(snap)
        summary["coverage"] = asdict(snap)

        # Fire cycle alert if new confirmed findings were produced this cycle
        new_confirmed = snap.valid_scenario_count - (
            prev_snap.get("valid_scenario_count", 0) if prev_snap else 0
        )
        if new_confirmed > 0:
            try:
                from ..alerts.dispatcher import fire_cycle_alert
                coverage_pct = (
                    snap.verified_failure_count / max(snap.failure_state_count, 1) * 100
                )
                fire_cycle_alert(
                    confirmed_findings=new_confirmed,
                    failure_states_found=snap.failure_state_count,
                    coverage_pct=coverage_pct,
                    cycle_number=getattr(snap, "cycle_number", 0),
                    tenant_id=tenant_id,
                )
            except Exception as _alert_err:
                logger.debug("[impact/loop] cycle alert failed (non-blocking): %s", _alert_err)

    except Exception as exc:
        logger.warning("[impact/loop] coverage snapshot failed: %s", exc)
        summary["errors"].append(f"coverage: {exc}")

    summary["completed_at"] = datetime.now(UTC).isoformat()
    summary["duration_ms"] = int(
        (datetime.fromisoformat(summary["completed_at"]) -
         datetime.fromisoformat(cycle_start)).total_seconds() * 1000
    )

    logger.info(
        "[impact/loop] cycle complete: tenant=%s edges=%d fs=%d (+%d) "
        "scenarios=%d valid=%d duration=%dms",
        tenant_id,
        summary["edges_ingested"],
        summary["failure_states_found"],
        summary["new_failure_states"],
        summary["scenarios_generated"],
        summary["scenarios_valid"],
        summary.get("duration_ms", 0),
    )

    return summary


# ── Background scheduler ───────────────────────────────────────────────────────


_scheduler_running = False
_scheduler_thread: Optional[threading.Thread] = None


def start_background_scheduler(
    *,
    governor=None,
    shadow_store=None,
    tenant_id: Optional[str] = None,
    interval_sec: Optional[int] = None,
) -> None:
    """Start the Impact loop as a background thread.

    Called from app startup (lifespan). Only starts once — idempotent.
    """
    global _scheduler_running, _scheduler_thread

    with _loop_lock:
        if _scheduler_running:
            logger.debug("[impact/loop] scheduler already running")
            return

        _scheduler_running = True

    interval = interval_sec or _CYCLE_INTERVAL_SEC

    def _run() -> None:
        logger.info(
            "[impact/loop] background scheduler started (interval=%ds)", interval
        )
        while _scheduler_running:
            try:
                # Run in a fresh event loop for the background thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(
                    run_cycle(
                        tenant_id=tenant_id,
                        governor=governor,
                        shadow_store=shadow_store,
                        force=False,
                    )
                )
                loop.close()
            except Exception as exc:
                logger.warning("[impact/loop] scheduler cycle error: %s", exc)
            time.sleep(interval)

    _scheduler_thread = threading.Thread(target=_run, daemon=True, name="impact-loop")
    _scheduler_thread.start()


def stop_background_scheduler() -> None:
    """Stop the background scheduler. Called on app shutdown."""
    global _scheduler_running
    _scheduler_running = False
    logger.info("[impact/loop] background scheduler stopped")
