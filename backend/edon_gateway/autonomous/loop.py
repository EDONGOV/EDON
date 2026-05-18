"""EDON Autonomous Governance Loop.

Closes the full observe → harden → heal → verify → adapt cycle without human input.

Phase timeline per iteration:
  1. OBSERVE  — impact/loop.run_cycle()            — finds new failure states from shadow traces
  2. HARDEN   — hardening/runner.run()             — coverage + policy + regression agents
  3. HEAL     — healing/runner.run_healing_pass()  — deploys qualifying rules
  4. VERIFY   — re-counts open failure states, diffed against pre-cycle baseline
  5. ADAPT    — fleet_learning signals             — drift tightening, threshold suggestions,
                                                     high-confidence policy auto-apply

Each phase is self-governed: before running, the loop asks EDON to evaluate the
action. If EDON blocks, the phase is skipped and the incident is logged.

Loop control:
  EDON_AUTO_LOOP_ENABLED   — master switch (default: true)
  EDON_AUTO_LOOP_INTERVAL  — seconds between full cycles (default: 600)
  EDON_AUTO_LOOP_TENANTS   — comma-separated tenant IDs to govern (default: all)

Use start_autonomous_loop() / stop_autonomous_loop() at app startup/shutdown.
Use get_loop_status() to introspect the current state.
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from typing import Optional

from ..logging_config import get_logger

logger = get_logger(__name__)

_ENABLED                  = os.getenv("EDON_AUTO_LOOP_ENABLED", "true").lower() == "true"
_INTERVAL_SEC             = int(os.getenv("EDON_AUTO_LOOP_INTERVAL", "600"))
_TENANT_IDS_ENV           = os.getenv("EDON_AUTO_LOOP_TENANTS", "")
_AGENT_ID                 = "edon-autonomous-loop"
_MAX_AUTO_SUGGESTIONS     = int(os.getenv("EDON_AUTO_LOOP_MAX_SUGGESTIONS", "3"))
_DRIFT_CEILING_BUMP       = float(os.getenv("EDON_AUTO_LOOP_DRIFT_CEILING_BUMP", "0.1"))

# ── Patch D: ADAPT meta-policy safety bounds ──────────────────────────────────
# Minimum evidence before ADAPT may auto-create an ALLOW rule (sample count).
_ADAPT_MIN_EVIDENCE       = int(os.getenv("EDON_ADAPT_MIN_EVIDENCE", "20"))
# Wildcard patterns for action names ADAPT must never auto-allow regardless of stats.
_ADAPT_FORBIDDEN_PATTERNS = [p for p in
    os.getenv("EDON_ADAPT_FORBIDDEN_PATTERNS", "delete.*,drop.*,purge.*,admin.*").split(",")
    if p.strip()
]

_loop_task: Optional[asyncio.Task] = None
_running   = False


# ── State ─────────────────────────────────────────────────────────────────────

@dataclass
class CycleResult:
    cycle_id: int
    started_at: str
    finished_at: str = ""
    tenant_id: Optional[str] = None
    observe: dict = field(default_factory=dict)
    harden: dict = field(default_factory=dict)
    heal:   dict = field(default_factory=dict)
    verify: dict = field(default_factory=dict)
    adapt:  dict = field(default_factory=dict)
    governed: bool = True   # False if governance blocked a phase
    error: Optional[str] = None


_history: list[CycleResult] = []   # last 50 cycles


def get_loop_status() -> dict:
    last = _history[-1] if _history else None
    return {
        "running":        _running,
        "enabled":        _ENABLED,
        "interval_sec":   _INTERVAL_SEC,
        "total_cycles":   len(_history),
        "last_cycle":     asdict(last) if last else None,
    }


# ── Self-governance helper ────────────────────────────────────────────────────

def _gov_check(governor, action_type: str, payload: dict, tenant_id: Optional[str]) -> bool:
    """Ask EDON to evaluate a phase action. Returns True if allowed.

    Kill switch is checked first — if active for this tenant, all autonomous
    phases are blocked. This is the answer to "who governs the governor?":
    the same kill switch that halts external agents also halts the loop itself.
    """
    # Kill switch check — applies to all phases regardless of Tool enum mapping
    if tenant_id:
        try:
            from ..routes.kill_switch import is_kill_switch_active
            if is_kill_switch_active(tenant_id):
                logger.warning(
                    "[autoloop] kill_switch active for tenant=%s — blocking phase: %s",
                    tenant_id, action_type,
                )
                return False
        except Exception as _ks_err:
            logger.debug("[autoloop] kill_switch check failed: %s", _ks_err)

    if governor is None:
        return True
    try:
        from ..schemas import Action, Tool, RiskLevel, ActionSource
        tool_str, op_str = (action_type.split(".", 1) + ["run"])[:2]
        try:
            tool_enum = Tool(tool_str)
        except ValueError:
            # Internal phases (healing, learning, etc.) don't map to Tool enum values.
            # Kill switch already checked above; no further policy evaluation needed.
            return True
        action = Action(
            tool=tool_enum,
            op=op_str,
            estimated_risk=RiskLevel.LOW,
            source=ActionSource.AGENT,
        )
        from ..governor import EDONGovernor
        decision = governor.evaluate(
            action=action,
            agent_id=_AGENT_ID,
            tenant_id=tenant_id,
        )
        verdict = decision.verdict.value if hasattr(decision.verdict, "value") else str(decision.verdict)
        if verdict not in ("ALLOW", "DEGRADE"):
            logger.warning("[autoloop] phase=%s blocked by governance: %s", action_type, verdict)
            return False
        return True
    except Exception as exc:
        logger.warning("[autoloop] gov_check failed for %s: %s — defaulting ALLOW", action_type, exc)
        return True


# ── Phase runners ─────────────────────────────────────────────────────────────

async def _phase_observe(governor, tenant_id: Optional[str], shadow_store=None, impact_store=None) -> dict:
    if not _gov_check(governor, "impact.observe", {}, tenant_id):
        return {"skipped": True, "reason": "governance_block"}
    try:
        from ..impact.loop import run_cycle
        result = await run_cycle(
            tenant_id=tenant_id,
            governor=governor,
            shadow_store=shadow_store,
            impact_store=impact_store,
            force=True,
        )
        return result or {}
    except Exception as exc:
        logger.error("[autoloop] observe error: %s", exc)
        return {"error": str(exc)}


async def _phase_harden(governor, tenant_id: Optional[str], impact_store=None, shadow_store=None) -> dict:
    if not _gov_check(governor, "hardening.run", {}, tenant_id):
        return {"skipped": True, "reason": "governance_block"}
    try:
        from ..agents.hardening.runner import run as hardening_run
        result = await hardening_run(
            governor=governor,
            impact_store=impact_store,
            shadow_store=shadow_store,
            tenant_id=tenant_id,
            force=True,
        )
        return result or {}
    except Exception as exc:
        logger.error("[autoloop] harden error: %s", exc)
        return {"error": str(exc)}


async def _phase_heal(governor, tenant_id: Optional[str], hardening_result: dict, impact_store=None) -> dict:
    if not _gov_check(governor, "healing.deploy", {}, tenant_id):
        return {"skipped": True, "reason": "governance_block"}
    try:
        from ..healing.runner import run_healing_pass
        result = await run_healing_pass(
            hardening_result=hardening_result,
            governor=governor,
            tenant_id=tenant_id,
            impact_store=impact_store,
            force=True,
        )
        return result or {}
    except Exception as exc:
        logger.error("[autoloop] heal error: %s", exc)
        return {"error": str(exc)}


async def _phase_verify(impact_store=None) -> dict:
    """Count open critical failure states after healing."""
    try:
        from ..impact.store import get_impact_store
        store = impact_store or get_impact_store()
        if hasattr(store, "get_failure_states"):
            states = store.get_failure_states(limit=200)
            open_states = [s for s in states if not s.get("verified")]
            critical    = sum(1 for s in open_states if float(s.get("severity_score", 0)) >= 0.8)
            return {"open_findings": len(open_states), "critical": critical}
        return {"open_findings": -1, "critical": -1}
    except Exception as exc:
        logger.error("[autoloop] verify error: %s", exc)
        return {"error": str(exc)}


def _adapt_meta_safe(action_name: str, sample_count: int, circuit_breaker_active: bool) -> tuple[bool, str]:
    """Patch D: meta-policy safety gate for ADAPT auto-apply decisions.

    Returns (safe: bool, reason: str).
    Hard safety bounds that ADAPT may never cross regardless of fleet learning signals:
      - Circuit breaker active  → pause all auto-applies
      - Insufficient evidence   → require at least _ADAPT_MIN_EVIDENCE samples
      - Forbidden pattern match → permanent exclusion for dangerous action classes
    """
    import fnmatch as _fnmatch
    if circuit_breaker_active:
        return False, "circuit_breaker_active"
    if sample_count < _ADAPT_MIN_EVIDENCE:
        return False, f"insufficient_evidence({sample_count}<{_ADAPT_MIN_EVIDENCE})"
    name_lower = action_name.lower()
    for pattern in _ADAPT_FORBIDDEN_PATTERNS:
        if _fnmatch.fnmatch(name_lower, pattern.strip()):
            return False, f"forbidden_pattern({pattern})"
    return True, "ok"


async def _phase_adapt(governor, tenant_id: Optional[str], verify_result: dict) -> dict:
    """ADAPT — connect fleet learning signals to live policy.

    Three sub-tasks (each self-governed, all non-blocking on failure):

    1. Drift tightening — detect drifting agents via fleet learning; for each,
       record an OOB reinforcement signal so future OOB predictions are elevated.
       The signal source is "drift_detection" to distinguish it from real outcomes.

    2. Threshold suggestions — precision stats surface over-sensitive tool/op pairs
       (precision < 0.40, ≥ 20 blocks); auto_escalate suggestions get an ALLOW rule
       created immediately without requiring a human click.

    3. AI policy suggestions — high-confidence (auto_escalate=True) suggestions from
       the background suggestion loop are written as live enabled rules, capped at
       _MAX_AUTO_SUGGESTIONS per pass to limit blast radius.
    """
    if not _gov_check(governor, "learning.adapt", {}, tenant_id):
        return {"skipped": True, "reason": "governance_block"}

    result: dict = {
        "drifting_agents": [],
        "thresholds_suggested": 0,
        "allow_rules_created": 0,
        "suggestions_auto_applied": 0,
        "errors": [],
    }

    try:
        from ..fleet_learning import get_fleet_learning_engine
        from ..persistence import get_db
        engine = get_fleet_learning_engine()
        db = get_db()

        # Patch D: circuit breaker state, shared across all auto-apply sections
        _cb_active = False
        try:
            from ..trust import get_trust_engine as _gte
            _cb_active = _gte().is_circuit_breaker_active(tenant_id or "")
        except Exception:
            pass

        # ── 1. Drift detection + OOB reinforcement ─────────────────────────────
        if _gov_check(governor, "learning.drift_check", {}, tenant_id):
            try:
                # Collect agent IDs seen in recent audit events
                recent_events = db.query_audit_events(
                    customer_id=tenant_id, limit=500
                ) if hasattr(db, "query_audit_events") else []
                seen_agents: set = {
                    (e.get("action") or {}).get("agent_id")
                    for e in recent_events
                    if (e.get("action") or {}).get("agent_id")
                }
                drifting: list = []
                for agent_id in seen_agents:
                    try:
                        report = engine.detect_agent_drift(
                            db=db, tenant_id=tenant_id, agent_id=agent_id
                        )
                        if report.get("drift"):
                            drifting.append(agent_id)
                            # Reinforce OOB signal so the next predict_action()
                            # scores this agent higher without hardcoding a ceiling.
                            dominant_tool = report.get("signals", {}).get(
                                "dominant_tool", "unknown"
                            )
                            parts = dominant_tool.split(".", 1)
                            _tool = parts[0] or "unknown"
                            _op = parts[1] if len(parts) > 1 else ""
                            engine.record_feedback(
                                tenant_id=tenant_id,
                                agent_id=agent_id,
                                action_tool=_tool,
                                action_op=_op,
                                label="oob",
                                source="drift_detection",
                                notes=f"drift={report.get('signals')}",
                            )
                    except Exception as _da_err:
                        result["errors"].append(f"drift/{agent_id}: {_da_err}")
                result["drifting_agents"] = drifting
                if drifting:
                    logger.warning(
                        "[autoloop/adapt] %d drifting agent(s) detected and reinforced: %s",
                        len(drifting), drifting,
                    )
            except Exception as _drift_err:
                result["errors"].append(f"drift_detection: {_drift_err}")

        # ── 2. Threshold suggestions → submit proposals (Fix 4: no direct mutation) ─
        if _gov_check(governor, "learning.threshold_suggest", {}, tenant_id):
            try:
                from ..policy.proposals import get_proposal_store as _gps
                _proposal_store = _gps()

                threshold_suggestions = engine.suggest_threshold_adjustments(
                    tenant_id=tenant_id
                )
                result["thresholds_suggested"] = len(threshold_suggestions)
                submitted = 0
                for ts in threshold_suggestions:
                    if not ts.get("auto_escalate") or not tenant_id:
                        continue
                    tool_op = ts.get("tool_op", "")
                    _safe, _reason = _adapt_meta_safe(
                        action_name=tool_op,
                        sample_count=ts.get("blocks", 0),
                        circuit_breaker_active=_cb_active,
                    )
                    if not _safe:
                        result["errors"].append(f"proposal_skipped/{tool_op}: {_reason}")
                        logger.info(
                            "[autoloop/adapt] meta-policy blocked proposal for %s: %s",
                            tool_op, _reason,
                        )
                        continue
                    try:
                        pid = _proposal_store.submit(
                            tenant_id=tenant_id,
                            source="adapt_threshold",
                            action="ALLOW",
                            name=f"auto_allow_{tool_op.replace('.', '_')}",
                            description=f"[autoloop] Over-sensitive block: {ts.get('recommendation','')}",
                            rationale=ts.get("recommendation", ""),
                            condition_tool=ts.get("action_tool"),
                            condition_op=ts.get("action_op"),
                            priority=600,
                            evidence=(
                                f"precision={ts.get('precision',0):.0%} "
                                f"over {ts.get('blocks',0)} blocks"
                            ),
                        )
                        submitted += 1
                        logger.info(
                            "[autoloop/adapt] submitted proposal %s for tool_op=%s "
                            "(precision=%.0f%% over %d blocks) — awaiting human review",
                            pid, tool_op, ts.get("precision", 0) * 100, ts.get("blocks", 0),
                        )
                    except Exception as _rule_err:
                        result["errors"].append(f"proposal_submit/{tool_op}: {_rule_err}")
                result["allow_rules_created"] = submitted  # now means "proposals submitted"
            except Exception as _thresh_err:
                result["errors"].append(f"threshold_suggest: {_thresh_err}")

        # ── 3. AI policy suggestions → submit proposals (Fix 4: no direct mutation) ─
        if _gov_check(governor, "learning.policy_apply", {}, tenant_id):
            try:
                from ..ai.policy_suggester import get_cached_suggestions
                from ..policy.proposals import get_proposal_store as _gps2
                _proposal_store2 = _gps2()

                cached = get_cached_suggestions()
                pending = [
                    s for s in (cached.get("suggestions") or [])
                    if s.get("auto_escalate") and not s.get("applied")
                ]
                submitted2 = 0
                for suggestion in pending[:_MAX_AUTO_SUGGESTIONS]:
                    if not tenant_id:
                        break
                    _s_safe, _s_reason = _adapt_meta_safe(
                        action_name=suggestion.get("name", ""),
                        sample_count=suggestion.get("sample_count", _ADAPT_MIN_EVIDENCE),
                        circuit_breaker_active=_cb_active,
                    )
                    if not _s_safe:
                        result["errors"].append(
                            f"proposal_skipped/{suggestion.get('name')}: {_s_reason}"
                        )
                        continue
                    try:
                        pid2 = _proposal_store2.submit(
                            tenant_id=tenant_id,
                            source="adapt_ai_suggestion",
                            action=suggestion.get("action", "ALLOW"),
                            name=suggestion["name"],
                            description=suggestion.get("description", ""),
                            rationale=suggestion.get("rationale", ""),
                            condition_tool=suggestion.get("condition_tool"),
                            condition_op=suggestion.get("condition_op"),
                            priority=500,
                            evidence=f"confidence={suggestion.get('confidence',0):.0%}",
                        )
                        suggestion["applied"] = True  # prevent re-submission next cycle
                        submitted2 += 1
                        logger.info(
                            "[autoloop/adapt] submitted AI suggestion proposal %s '%s' "
                            "(confidence=%.0f%%) — awaiting human review",
                            pid2, suggestion["name"], suggestion.get("confidence", 0) * 100,
                        )
                    except Exception as _apply_err:
                        result["errors"].append(
                            f"proposal_submit/{suggestion.get('name')}: {_apply_err}"
                        )
                result["suggestions_auto_applied"] = submitted2
            except Exception as _sugg_err:
                result["errors"].append(f"policy_suggestions: {_sugg_err}")

    except Exception as exc:
        logger.error("[autoloop] adapt error: %s", exc)
        result["errors"].append(str(exc))

    return result


# ── Notification helper ───────────────────────────────────────────────────────

async def _notify(cycle: CycleResult) -> None:
    """Send a Telegram notification if anything notable happened."""
    try:
        heal = cycle.heal
        rules_deployed = heal.get("rules_deployed", 0)
        verify = cycle.verify
        critical = verify.get("critical", 0)
        adapt = cycle.adapt
        drifting = len(adapt.get("drifting_agents", []))
        suggestions_applied = adapt.get("suggestions_auto_applied", 0)
        allow_rules = adapt.get("allow_rules_created", 0)
        if not rules_deployed and not critical and not drifting and not suggestions_applied:
            return   # nothing worth reporting

        lines = [f"*EDON Auto-Loop — Cycle #{cycle.cycle_id}*"]
        if cycle.tenant_id:
            lines.append(f"Tenant: `{cycle.tenant_id}`")
        if rules_deployed:
            lines.append(f"Rules deployed: {rules_deployed}")
        if critical:
            lines.append(f"⚠️ Critical findings open: {critical}")
        if drifting:
            lines.append(f"Drifting agents: {drifting}")
        if suggestions_applied:
            lines.append(f"AI suggestions auto-applied: {suggestions_applied}")
        if allow_rules:
            lines.append(f"Over-sensitive ALLOW rules created: {allow_rules}")
        if cycle.error:
            lines.append(f"Error: `{cycle.error}`")

        msg = "\n".join(lines)

        token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if token and chat_id:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
                )
    except Exception as exc:
        logger.debug("[autoloop] notify error: %s", exc)


# ── Main cycle ────────────────────────────────────────────────────────────────

async def _run_one_cycle(cycle_id: int, tenant_id: Optional[str], governor) -> CycleResult:
    from ..impact.store import get_impact_store  # noqa: F401 (side effects)
    from ..shadow.trace_capture import get_trace_store

    impact_store  = get_impact_store()
    shadow_store  = get_trace_store()

    result = CycleResult(
        cycle_id=cycle_id,
        started_at=datetime.now(UTC).isoformat(),
        tenant_id=tenant_id,
    )

    logger.info("[autoloop] cycle=%d tenant=%s OBSERVE", cycle_id, tenant_id)
    result.observe = await _phase_observe(governor, tenant_id, shadow_store, impact_store)

    logger.info("[autoloop] cycle=%d tenant=%s HARDEN", cycle_id, tenant_id)
    result.harden  = await _phase_harden(governor, tenant_id, impact_store, shadow_store)

    logger.info("[autoloop] cycle=%d tenant=%s HEAL", cycle_id, tenant_id)
    result.heal    = await _phase_heal(governor, tenant_id, result.harden, impact_store)

    logger.info("[autoloop] cycle=%d tenant=%s VERIFY", cycle_id, tenant_id)
    result.verify  = await _phase_verify(impact_store)

    logger.info("[autoloop] cycle=%d tenant=%s ADAPT", cycle_id, tenant_id)
    result.adapt   = await _phase_adapt(governor, tenant_id, result.verify)

    result.finished_at = datetime.now(UTC).isoformat()
    logger.info(
        "[autoloop] cycle=%d done — open=%s critical=%s rules_deployed=%s "
        "drifting=%s suggestions_applied=%s",
        cycle_id,
        result.verify.get("open_findings"),
        result.verify.get("critical"),
        result.heal.get("rules_deployed"),
        len(result.adapt.get("drifting_agents", [])),
        result.adapt.get("suggestions_auto_applied", 0),
    )
    return result


async def _loop_main(governor) -> None:
    global _running
    _running = True
    cycle_id = 0
    tenants: list[Optional[str]] = (
        [t.strip() for t in _TENANT_IDS_ENV.split(",") if t.strip()]
        if _TENANT_IDS_ENV else [None]
    )

    logger.info("[autoloop] started — interval=%ds tenants=%s", _INTERVAL_SEC, tenants)

    while _running:
        cycle_id += 1
        cycle_start = time.monotonic()

        for tenant_id in tenants:
            if not _running:
                break
            try:
                cycle = await _run_one_cycle(cycle_id, tenant_id, governor)
                _history.append(cycle)
                if len(_history) > 50:
                    _history.pop(0)
                await _notify(cycle)
            except Exception as exc:
                logger.error("[autoloop] unexpected error in cycle %d: %s", cycle_id, exc)
                err = CycleResult(
                    cycle_id=cycle_id,
                    started_at=datetime.now(UTC).isoformat(),
                    finished_at=datetime.now(UTC).isoformat(),
                    tenant_id=tenant_id,
                    error=str(exc),
                )
                _history.append(err)

        elapsed = time.monotonic() - cycle_start
        sleep_for = max(0, _INTERVAL_SEC - elapsed)
        logger.debug("[autoloop] sleeping %.0fs until next cycle", sleep_for)

        try:
            await asyncio.sleep(sleep_for)
        except asyncio.CancelledError:
            break

    _running = False
    logger.info("[autoloop] stopped after %d cycles", cycle_id)


# ── Public API ────────────────────────────────────────────────────────────────

def start_autonomous_loop(governor=None) -> None:
    """Start the autonomous loop as a background asyncio task."""
    global _loop_task, _running
    if not _ENABLED:
        logger.info("[autoloop] disabled via EDON_AUTO_LOOP_ENABLED=false")
        return
    if _loop_task and not _loop_task.done():
        logger.info("[autoloop] already running")
        return
    _loop_task = asyncio.create_task(_loop_main(governor))
    logger.info("[autoloop] task created")


def stop_autonomous_loop() -> None:
    """Cancel the background loop task."""
    global _loop_task, _running
    _running = False
    if _loop_task and not _loop_task.done():
        _loop_task.cancel()
        logger.info("[autoloop] task cancelled")


async def run_cycle_now(tenant_id: Optional[str] = None, governor=None) -> dict:
    """Run a single cycle immediately (manual trigger)."""
    cycle_id = len(_history) + 1
    cycle = await _run_one_cycle(cycle_id, tenant_id, governor)
    _history.append(cycle)
    if len(_history) > 50:
        _history.pop(0)
    await _notify(cycle)
    return asdict(cycle)
