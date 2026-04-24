"""Hardening Agent Runner — orchestrates all three hardening agents.

Runs coverage → policy → regression in sequence. Each agent's output
feeds the next:

  coverage_agent  →  new shadow findings  →  fix_pipeline
  policy_agent    →  rule_ready dicts      →  regression_agent
  regression_agent →  regression reports  →  returned to caller

Called from:
  1. POST /v1/hardening/run  (manual trigger)
  2. Impact loop Engine D     (after each cycle, if configured)

Each agent is independently gated:
  EDON_HARDENING_COVERAGE_ENABLED  (default: true)
  EDON_HARDENING_POLICY_ENABLED    (default: true)
  EDON_HARDENING_REGRESSION_ENABLED (default: true)

Fail-open: if any agent errors, the error is recorded and the runner
continues to the next agent.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from datetime import datetime, UTC
from typing import Optional

from ...logging_config import get_logger

logger = get_logger(__name__)

_COVERAGE_ENABLED  = os.getenv("EDON_HARDENING_COVERAGE_ENABLED",   "true").lower() == "true"
_POLICY_ENABLED    = os.getenv("EDON_HARDENING_POLICY_ENABLED",      "true").lower() == "true"
_REGRESSION_ENABLED = os.getenv("EDON_HARDENING_REGRESSION_ENABLED", "true").lower() == "true"
_RUN_INTERVAL_SEC  = int(os.getenv("EDON_HARDENING_INTERVAL_SEC",    "600"))  # 10 min default

_runner_lock = threading.Lock()
_last_run_at: dict[Optional[str], float] = {}


async def run(
    *,
    governor,
    impact_store=None,
    shadow_store=None,
    tenant_id: Optional[str] = None,
    force: bool = False,
    max_coverage_states: int = 10,
    max_policy_proposals: int = 20,
    regression_trace_limit: int = 40,
) -> dict:
    """Run all three hardening agents in sequence.

    Returns a combined summary with per-agent results and timing.
    """
    from ...impact.store import get_impact_store
    from ...shadow.trace_capture import get_trace_store

    now = time.time()
    tenant_key = tenant_id or "__global__"

    if not force:
        last = _last_run_at.get(tenant_key, 0.0)
        if now - last < _RUN_INTERVAL_SEC:
            remaining = int(_RUN_INTERVAL_SEC - (now - last))
            return {
                "skipped": True,
                "reason": f"hardening ran {int(now - last)}s ago — next in {remaining}s",
            }

    _last_run_at[tenant_key] = now
    started_at = datetime.now(UTC).isoformat()

    _impact_store = impact_store or get_impact_store()
    _shadow_store = shadow_store or get_trace_store()

    summary: dict = {
        "tenant_id": tenant_id,
        "started_at": started_at,
        "coverage": None,
        "policy": None,
        "regression": None,
        "errors": [],
    }

    # ── Agent 1: Coverage ──────────────────────────────────────────────────────
    if _COVERAGE_ENABLED:
        try:
            from . import coverage_agent
            summary["coverage"] = await coverage_agent.run(
                impact_store=_impact_store,
                shadow_store=_shadow_store,
                governor=governor,
                tenant_id=tenant_id,
                max_states=max_coverage_states,
            )
        except Exception as exc:
            logger.warning("[hardening/runner] coverage agent error: %s", exc)
            summary["errors"].append(f"coverage: {exc}")
            summary["coverage"] = {"agent": "coverage", "error": str(exc)}
    else:
        summary["coverage"] = {"agent": "coverage", "skipped": True}

    # ── Agent 2: Policy ────────────────────────────────────────────────────────
    rule_ready_list: list[dict] = []
    if _POLICY_ENABLED:
        try:
            from . import policy_agent
            policy_result = await policy_agent.run(
                tenant_id=tenant_id,
                max_proposals=max_policy_proposals,
            )
            summary["policy"] = policy_result
            rule_ready_list = policy_result.get("rules", [])
        except Exception as exc:
            logger.warning("[hardening/runner] policy agent error: %s", exc)
            summary["errors"].append(f"policy: {exc}")
            summary["policy"] = {"agent": "policy", "error": str(exc)}
    else:
        summary["policy"] = {"agent": "policy", "skipped": True}

    # ── Agent 3: Regression ────────────────────────────────────────────────────
    if _REGRESSION_ENABLED and rule_ready_list:
        try:
            from . import regression_agent
            summary["regression"] = await regression_agent.run(
                rules=rule_ready_list,
                governor=governor,
                tenant_id=tenant_id,
                limit_traces=regression_trace_limit,
            )
        except Exception as exc:
            logger.warning("[hardening/runner] regression agent error: %s", exc)
            summary["errors"].append(f"regression: {exc}")
            summary["regression"] = {"agent": "regression", "error": str(exc)}
    elif not rule_ready_list:
        summary["regression"] = {
            "agent": "regression",
            "skipped": True,
            "reason": "no rule_ready rules from policy agent",
        }
    else:
        summary["regression"] = {"agent": "regression", "skipped": True}

    # ── Agent 4: Self-healing — deploy + verify ────────────────────────────────
    try:
        from ...healing.runner import run_healing_pass
        summary["healing"] = await run_healing_pass(
            hardening_result=summary,
            governor=governor,
            tenant_id=tenant_id,
        )
    except Exception as exc:
        logger.warning("[hardening/runner] healing agent error: %s", exc)
        summary["errors"].append(f"healing: {exc}")
        summary["healing"] = {"agent": "healing", "error": str(exc)}

    summary["completed_at"] = datetime.now(UTC).isoformat()
    summary["duration_ms"] = int(
        (datetime.fromisoformat(summary["completed_at"]) -
         datetime.fromisoformat(started_at)).total_seconds() * 1000
    )

    logger.info(
        "[hardening/runner] complete: tenant=%s duration=%dms "
        "coverage_probed=%d policy_rules=%d regression_tested=%d",
        tenant_id,
        summary["duration_ms"],
        (summary["coverage"] or {}).get("failure_states_probed", 0),
        (summary["policy"] or {}).get("rules_generated", 0),
        (summary["regression"] or {}).get("rules_tested", 0),
    )

    return summary


# ── Background scheduler ───────────────────────────────────────────────────────

_scheduler_running = False
_scheduler_thread: Optional[threading.Thread] = None


def start_background_scheduler(
    *,
    governor,
    tenant_id: Optional[str] = None,
    interval_sec: Optional[int] = None,
) -> None:
    """Start hardening agents as a background daemon thread. Idempotent."""
    global _scheduler_running, _scheduler_thread

    with _runner_lock:
        if _scheduler_running:
            return
        _scheduler_running = True

    interval = interval_sec or _RUN_INTERVAL_SEC

    def _loop() -> None:
        logger.info("[hardening/runner] scheduler started (interval=%ds)", interval)
        while _scheduler_running:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                # Run against every active tenant, not just the default one.
                # This ensures self-healing fires for ALL clients automatically.
                tenant_ids_to_run: list[Optional[str]] = []
                try:
                    from ...persistence import get_db as _get_db
                    _db = _get_db()
                    if hasattr(_db, "list_tenants"):
                        tenant_ids_to_run = [t["id"] for t in _db.list_tenants() if t.get("id")]
                except Exception as _te:
                    logger.debug("[hardening/runner] could not list tenants (using default): %s", _te)

                if not tenant_ids_to_run:
                    tenant_ids_to_run = [tenant_id]  # fallback to configured tenant or None

                for tid in tenant_ids_to_run:
                    try:
                        loop.run_until_complete(
                            run(governor=governor, tenant_id=tid, force=False)
                        )
                    except Exception as _terr:
                        logger.warning("[hardening/runner] tenant=%s error: %s", tid, _terr)

                loop.close()
            except Exception as exc:
                logger.warning("[hardening/runner] scheduler error: %s", exc)
            time.sleep(interval)

    _scheduler_thread = threading.Thread(target=_loop, daemon=True, name="hardening-runner")
    _scheduler_thread.start()


def stop_background_scheduler() -> None:
    global _scheduler_running
    _scheduler_running = False
    logger.info("[hardening/runner] scheduler stopped")
