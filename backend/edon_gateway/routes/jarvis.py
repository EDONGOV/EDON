"""EDON Jarvis — conversational AI with live data access and action capabilities.

POST /v1/jarvis/ask  — natural language question → grounded answer

Claude runs a tool_use loop against EDON's own data stores and agents.
No hallucinated numbers: every stat comes from a real DB query or agent run.

Read tools:
  get_system_health     — DB status, env, uptime
  get_governance_stats  — audit_events: decisions, block rate, top agents
  get_client_health     — per-tenant breakdown
  get_active_findings   — impact store open findings by severity
  get_healing_history   — recent self-healing rule deployments
  get_shadow_findings   — shadow bypass findings + confirmed bypasses
  get_fleet_risk        — fleet learning risk label summary
  get_training_status   — training pipeline dataset sizes + last job
  get_hardening_status  — last hardening run result
  get_runtime_controls  — kill switch / shadow mode / e-stop state + derived mode
  get_impact_summary    — prioritised failure-state risk view (severity + blast radius)
  explain_decision      — full breakdown of a specific governance decision

Action tools:
  set_kill_switch          — enable/disable kill switch for a tenant
  create_policy_rule       — write a new governance rule
  toggle_feature_flag      — flip a feature flag on/off per tenant
  trigger_healing_run      — run the self-healing agent now
  trigger_hardening_run    — run the hardening agents now
  set_policy_preset        — switch a tenant's active preset
  suspend_tenant           — mark a tenant inactive
  export_audit_log         — pull recent audit events as structured data
  get_review_queue         — list pending human-review escalations
  resolve_escalation       — approve or reject a pending escalation
  trigger_training_export  — export audit corpus as fine-tuning JSONL
  run_training_pipeline    — full export → upload → fine-tune pipeline
  get_agent_registry       — list or look up registered agents
  update_agent_status      — set agent lifecycle status (active/paused/retired)
  get_impact_graph         — query failure states and coverage from impact engine
  list_policy_rules        — list all policy rules for a tenant
  update_policy_rule       — enable/disable or modify an existing rule
  delete_policy_rule       — permanently delete a rule
  get_proposals            — list CREAO auto-generated policy fix proposals
  resolve_proposal         — apply or reject a CREAO proposal
  get_tenant_info          — tenant profile, plan, usage, and API keys
  revoke_api_key           — revoke a tenant API key
  get_alert_history        — recent fired alerts (findings, healing, recovery)

Auth: X-Bootstrap-Secret header (same as admin).
Requires ANTHROPIC_API_KEY set as server env / Fly.io secret.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
from datetime import datetime, UTC, timedelta
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..logging_config import get_logger
from ..persistence import get_db

logger = get_logger(__name__)
router = APIRouter(prefix="/v1/jarvis", tags=["jarvis"])

_ANTHROPIC_API = "https://api.anthropic.com/v1"
_MODEL         = "claude-sonnet-4-6"
_MAX_TOKENS      = 4096
_MAX_TOOL_ROUNDS = 12  # 36 tools × multi-step queries need headroom


# ── Auth ──────────────────────────────────────────────────────────────────────
# Defined in security/bootstrap_auth.py; imported here so all jarvis call
# sites keep working without changes, and other modules import from the source.
from ..security.bootstrap_auth import check_bootstrap_auth as _check_auth  # noqa: E402


# ── Tool implementations ───────────────────────────────────────────────────────

def _tool_get_system_health(_args: dict) -> dict:
    try:
        db = get_db()
        with db._get_connection() as conn:
            conn.execute("SELECT 1")
        db_ok = True
    except Exception as exc:
        db_ok = False

    return {
        "db_status":   "healthy" if db_ok else "error",
        "environment": os.getenv("EDON_ENV", os.getenv("ENVIRONMENT", "unknown")),
        "creao_mode":  os.getenv("EDON_CREAO_MODE", "assisted"),
        "healing_auto": os.getenv("EDON_HEALING_AUTO_ENABLED", "false"),
        "shadow_mode": os.getenv("EDON_SHADOW_MODE_ENABLED", "false"),
        "timestamp":   datetime.now(UTC).isoformat(),
    }


def _tool_get_governance_stats(args: dict) -> dict:
    hours = int(args.get("hours", 24))
    since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    try:
        db = get_db()
        with db._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT decision_verdict, COUNT(*) as cnt
                FROM audit_events
                WHERE timestamp >= ?
                GROUP BY decision_verdict
                """,
                (since,),
            ).fetchall()
            top_agents = conn.execute(
                """
                SELECT agent_id, COUNT(*) as cnt,
                       SUM(CASE WHEN decision_verdict='BLOCK' THEN 1 ELSE 0 END) as blocks
                FROM audit_events
                WHERE timestamp >= ?
                GROUP BY agent_id
                ORDER BY cnt DESC LIMIT 10
                """,
                (since,),
            ).fetchall()
            total_row = conn.execute(
                "SELECT COUNT(*) as cnt FROM audit_events WHERE timestamp >= ?",
                (since,),
            ).fetchone()

        verdict_counts = {r["decision_verdict"]: r["cnt"] for r in rows}
        total = total_row["cnt"] if total_row else 0
        blocks = verdict_counts.get("BLOCK", 0)

        return {
            "period_hours": hours,
            "total_decisions": total,
            "verdict_breakdown": verdict_counts,
            "block_rate_pct": round(blocks / total * 100, 1) if total else 0,
            "top_agents": [
                {"agent_id": r["agent_id"], "decisions": r["cnt"], "blocks": r["blocks"]}
                for r in top_agents
            ],
        }
    except Exception as exc:
        return {"error": str(exc), "total_decisions": 0}


def _tool_get_client_health(args: dict) -> dict:
    tenant_id = args.get("tenant_id")
    try:
        db = get_db()
        if hasattr(db, "list_tenants"):
            tenants = db.list_tenants()
        else:
            tenants = []

        results = []
        with db._get_connection() as conn:
            for t in (tenants or []):
                tid = t.get("id") or t.get("tenant_id")
                if tenant_id and tid != tenant_id:
                    continue
                row = conn.execute(
                    """
                    SELECT COUNT(*) as decisions,
                           SUM(CASE WHEN decision_verdict='BLOCK' THEN 1 ELSE 0 END) as blocks,
                           SUM(CASE WHEN decision_verdict='ESCALATE' THEN 1 ELSE 0 END) as escalations,
                           MAX(timestamp) as last_seen
                    FROM audit_events
                    WHERE customer_id = ? AND timestamp >= datetime('now', '-7 days')
                    """,
                    (tid,),
                ).fetchone()
                results.append({
                    "tenant_id":   tid,
                    "plan":        t.get("plan", "unknown"),
                    "status":      t.get("status", "unknown"),
                    "decisions_7d":    row["decisions"] if row else 0,
                    "blocks_7d":       row["blocks"] if row else 0,
                    "escalations_7d":  row["escalations"] if row else 0,
                    "last_seen":       row["last_seen"] if row else None,
                })

        return {"tenants": results, "total_clients": len(results)}
    except Exception as exc:
        return {"error": str(exc), "tenants": []}


def _tool_get_active_findings(args: dict) -> dict:
    severity_min = float(args.get("severity_min", 0.0))
    try:
        from ..impact.store import get_impact_store
        store = get_impact_store()
        # Try to get findings via store API
        if hasattr(store, "get_failure_states"):
            states = store.get_failure_states(limit=50)
        else:
            states = []

        findings = [
            {
                "id":             s.get("failure_state_id", "")[:8],
                "vuln_class":     s.get("vulnerability_class", "unknown"),
                "severity":       round(float(s.get("severity_score", 0)), 2),
                "blast_radius":   round(float(s.get("blast_radius_score", 0)), 2),
                "tenant_id":      s.get("tenant_id"),
                "verified":       bool(s.get("verified")),
            }
            for s in states
            if float(s.get("severity_score", 0)) >= severity_min
        ]
        findings.sort(key=lambda x: x["severity"], reverse=True)

        return {
            "total_findings": len(findings),
            "critical": sum(1 for f in findings if f["severity"] >= 0.8),
            "high":     sum(1 for f in findings if 0.6 <= f["severity"] < 0.8),
            "medium":   sum(1 for f in findings if f["severity"] < 0.6),
            "top_findings": findings[:10],
        }
    except Exception as exc:
        return {"error": str(exc), "total_findings": 0}


def _tool_get_healing_history(args: dict) -> dict:
    limit = int(args.get("limit", 20))
    try:
        db = get_db()
        with db._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT name, description, action, condition_tool, condition_op,
                       created_at, tenant_id
                FROM policy_rules
                WHERE condition_tags LIKE '%auto_hardening%'
                   OR condition_tags LIKE '%healing%'
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        rules = [dict(r) for r in rows]
        return {
            "rules_deployed": len(rules),
            "recent_rules": rules[:10],
        }
    except Exception as exc:
        return {"error": str(exc), "rules_deployed": 0}


def _tool_get_shadow_findings(args: dict) -> dict:
    limit = int(args.get("limit", 20))
    tenant_id = args.get("tenant_id") or None
    try:
        from ..shadow.trace_capture import get_trace_store
        store = get_trace_store()

        summary = store.finding_summary(tenant_id=tenant_id) if hasattr(store, "finding_summary") else {}
        critical = store.recent_findings(tenant_id=tenant_id, severity="critical", limit=limit) if hasattr(store, "recent_findings") else []
        advisory = store.recent_findings(tenant_id=tenant_id, severity="advisory", limit=10) if hasattr(store, "recent_findings") else []
        bypasses = store.get_confirmed_bypasses(tenant_id=tenant_id, limit=10) if hasattr(store, "get_confirmed_bypasses") else []

        return {
            "summary": summary,
            "critical_count": len(critical),
            "advisory_count": len(advisory),
            "confirmed_bypass_count": len(bypasses),
            "top_critical": critical[:5],
            "top_confirmed_bypasses": bypasses[:5],
        }
    except Exception as exc:
        return {"error": str(exc), "critical_count": 0}


def _tool_get_fleet_risk(args: dict) -> dict:
    try:
        from ..training.extractors import _fleet_db, _connect
        conn = _connect(_fleet_db())
        if not conn:
            return {"error": "fleet_learning.db not found", "total_labels": 0}
        try:
            rows = conn.execute(
                """
                SELECT label, COUNT(*) as cnt
                FROM feedback_labels
                GROUP BY label
                ORDER BY cnt DESC
                """
            ).fetchall()
            oob_rows = conn.execute(
                """
                SELECT agent_id, action_tool, action_op, COUNT(*) as cnt
                FROM feedback_labels
                WHERE label IN ('incident', 'oob')
                GROUP BY agent_id, action_tool, action_op
                ORDER BY cnt DESC LIMIT 10
                """
            ).fetchall()
        finally:
            conn.close()

        label_counts = {r["label"]: r["cnt"] for r in rows}
        total = sum(label_counts.values())

        return {
            "total_labels": total,
            "label_breakdown": label_counts,
            "high_risk_patterns": [dict(r) for r in oob_rows],
        }
    except Exception as exc:
        return {"error": str(exc), "total_labels": 0}


def _tool_get_training_status(args: dict) -> dict:
    try:
        from ..training.extractors import extract_all
        from ..training.formatters import format_all

        raw = extract_all(limits={
            "governance_decisions": 200,
            "shadow_findings":      100,
            "risk_labels":          100,
            "vulnerabilities":       50,
            "deployed_rules":        50,
        })
        formatted = format_all(raw)

        counts = {k: len(v) for k, v in formatted.items()}
        total_real = sum(counts.values())

        # Check for last training run dir
        training_dir = os.getenv("EDON_TRAINING_DIR", "/app/data/training")
        last_run = None
        try:
            from pathlib import Path
            runs = sorted(Path(training_dir).iterdir()) if Path(training_dir).exists() else []
            if runs:
                last_run = runs[-1].name
        except Exception:
            pass

        return {
            "real_examples": counts,
            "total_real": total_real,
            "synthetic_available": 530,
            "last_export_run": last_run,
            "ready_to_train": total_real + 530 >= 50,
        }
    except Exception as exc:
        return {"error": str(exc), "total_real": 0}


def _tool_get_hardening_status(args: dict) -> dict:
    try:
        from ..agents.hardening.runner import _last_run_at
        now = datetime.now(UTC).timestamp()
        status = []
        for tenant_key, last_ts in _last_run_at.items():
            elapsed = int(now - last_ts)
            status.append({
                "tenant": tenant_key,
                "last_run_secs_ago": elapsed,
                "last_run_human": f"{elapsed // 60}m ago" if elapsed < 3600 else f"{elapsed // 3600}h ago",
            })
        return {
            "tenants_tracked": len(status),
            "hardening_interval_sec": int(os.getenv("EDON_HARDENING_INTERVAL_SEC", "600")),
            "status": status,
        }
    except Exception as exc:
        return {"error": str(exc), "tenants_tracked": 0}


# ── Action tools ──────────────────────────────────────────────────────────────

def _tool_set_kill_switch(args: dict) -> dict:
    tenant_id = args.get("tenant_id", "")
    enable    = bool(args.get("enable", True))
    reason    = args.get("reason", "Jarvis command")
    try:
        from ..routes.kill_switch import activate_kill_switch, deactivate_kill_switch
        if enable:
            activate_kill_switch(tenant_id=tenant_id or None, reason=reason, activated_by="jarvis")
        else:
            deactivate_kill_switch(tenant_id=tenant_id or None, deactivated_by="jarvis")
        return {"ok": True, "tenant_id": tenant_id or "global", "kill_switch": "active" if enable else "inactive"}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_create_policy_rule(args: dict) -> dict:
    tenant_id     = args.get("tenant_id", "tenant_edon_internal")
    name          = args.get("name", "")
    condition_tool = args.get("condition_tool", "")
    condition_op  = args.get("condition_op", "")
    action        = args.get("action", "BLOCK")
    priority      = int(args.get("priority", 500))
    try:
        db = get_db()
        rule_id = db.create_policy_rule(
            tenant_id=tenant_id,
            name=name,
            condition_tool=condition_tool,
            condition_op=condition_op,
            action=action,
            priority=priority,
            enabled=True,
            condition_tags=["jarvis"],
        )
        return {"ok": True, "rule_id": rule_id, "name": name, "action": action}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_toggle_feature_flag(args: dict) -> dict:
    tenant_id = args.get("tenant_id", "")
    flag      = args.get("flag", "")
    enabled   = bool(args.get("enabled", True))
    try:
        db = get_db()
        with db._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feature_flags (
                    tenant_id TEXT NOT NULL, flag TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, flag)
                )
                """
            )
            conn.execute(
                """
                INSERT INTO feature_flags (tenant_id, flag, enabled, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(tenant_id, flag) DO UPDATE SET enabled=excluded.enabled, updated_at=excluded.updated_at
                """,
                (tenant_id, flag, int(enabled), datetime.now(UTC).isoformat()),
            )
            conn.commit()
        return {"ok": True, "tenant_id": tenant_id, "flag": flag, "enabled": enabled}
    except Exception as exc:
        return {"error": str(exc)}


async def _tool_trigger_healing_run(args: dict, governor=None) -> dict:
    tenant_id = args.get("tenant_id") or None
    try:
        from ..agents.hardening import runner as hardening_runner
        from ..healing.runner import run_healing_pass
        hardening_result = await hardening_runner.run(governor=governor, tenant_id=tenant_id, force=True)
        healing_result   = await run_healing_pass(hardening_result=hardening_result, governor=governor, tenant_id=tenant_id, force=True)
        return {
            "ok": True,
            "tenant_id": tenant_id or "global",
            "healing": {
                "deployed": healing_result.get("deployed", 0),
                "mitigated": healing_result.get("mitigated", 0),
                "errors": healing_result.get("errors", 0),
            },
            "hardening": {
                "coverage_probed": hardening_result.get("coverage", {}).get("probed", 0),
                "policy_rules": hardening_result.get("policy", {}).get("proposals", 0),
            },
        }
    except Exception as exc:
        return {"error": str(exc)}


async def _tool_trigger_hardening_run(args: dict, governor=None) -> dict:
    tenant_id = args.get("tenant_id") or None
    try:
        from ..agents.hardening import runner as hardening_runner
        result = await hardening_runner.run(governor=governor, tenant_id=tenant_id, force=True)
        return {
            "ok": True,
            "tenant_id": tenant_id or "global",
            "duration_ms": result.get("duration_ms"),
            "coverage_probed": result.get("coverage", {}).get("probed", 0),
            "policy_proposals": result.get("policy", {}).get("proposals", 0),
            "regression_tested": result.get("regression", {}).get("tested", 0),
        }
    except Exception as exc:
        return {"error": str(exc)}


def _tool_set_policy_preset(args: dict) -> dict:
    preset_name = args.get("preset_name", "")
    try:
        db = get_db()
        db.set_active_policy_preset(preset_name, applied_by="jarvis")
        return {"ok": True, "preset_name": preset_name}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_suspend_tenant(args: dict) -> dict:
    tenant_id = args.get("tenant_id", "")
    try:
        db = get_db()
        with db._get_connection() as conn:
            conn.execute(
                "UPDATE tenants SET status = 'inactive', updated_at = ? WHERE id = ?",
                (datetime.now(UTC).isoformat(), tenant_id),
            )
            conn.commit()
        return {"ok": True, "tenant_id": tenant_id, "status": "inactive"}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_export_audit_log(args: dict) -> dict:
    hours     = int(args.get("hours", 24))
    agent_id  = args.get("agent_id") or None
    tenant_id = args.get("tenant_id") or None
    limit     = int(args.get("limit", 100))
    since     = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    try:
        db = get_db()
        with db._get_connection() as conn:
            q = """
                SELECT agent_id,
                       action_tool || '.' || action_op AS action_type,
                       decision_verdict, timestamp, customer_id, action_id
                FROM audit_events
                WHERE timestamp >= ?
            """
            params: list = [since]
            if agent_id:
                q += " AND agent_id = ?"
                params.append(agent_id)
            if tenant_id:
                q += " AND customer_id = ?"
                params.append(tenant_id)
            q += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(q, params).fetchall()
        events = [dict(r) for r in rows]
        return {"period_hours": hours, "total_returned": len(events), "events": events}
    except Exception as exc:
        return {"error": str(exc)}


# ── Review queue tools ────────────────────────────────────────────────────────

def _tool_get_review_queue(args: dict) -> dict:
    from ..routes.review_queue import _queue, _lock, _TTL_HOURS
    status    = args.get("status", "pending")
    tenant_id = args.get("tenant_id") or None
    cutoff    = (datetime.now(UTC) - timedelta(hours=_TTL_HOURS)).isoformat()
    with _lock:
        items = [
            v for v in _queue.values()
            if v.get("status") == status
            and v.get("created_at", "") >= cutoff
            and (tenant_id is None or v.get("tenant_id") == tenant_id)
        ]
    items.sort(key=lambda x: x["created_at"], reverse=True)
    return {"status_filter": status, "count": len(items), "queue": items[:50]}


def _tool_resolve_escalation(args: dict) -> dict:
    decision_id = args.get("decision_id", "").strip()
    resolution  = args.get("resolution", "").lower()  # "approve" or "reject"
    note        = args.get("note") or None
    if not decision_id:
        return {"error": "decision_id required"}
    if resolution not in ("approve", "reject"):
        return {"error": "resolution must be 'approve' or 'reject'"}

    from ..routes.review_queue import _queue, _lock, _persist, _feedback_to_governor
    with _lock:
        record = _queue.get(decision_id)
        if not record:
            return {"error": f"escalation {decision_id} not found"}
        if record["status"] != "pending":
            return {"error": f"already resolved: {record['status']}"}
        record["status"]          = "approved" if resolution == "approve" else "rejected"
        record["resolved_at"]     = datetime.now(UTC).isoformat()
        record["resolved_by"]     = "jarvis"
        record["resolution"]      = record["status"]
        record["resolution_note"] = note
        _persist()

    _feedback_to_governor(record, approved=(resolution == "approve"))
    logger.info("[jarvis] resolve_escalation: %s → %s", decision_id, record["status"])
    return {
        "decision_id": decision_id,
        "resolution":  record["status"],
        "resolved_at": record["resolved_at"],
        "agent_id":    record.get("agent_id"),
        "action_type": record.get("action_type"),
    }


# ── Training pipeline tools ───────────────────────────────────────────────────

def _tool_trigger_training_export(args: dict) -> dict:
    validation_split = float(args.get("validation_split", 0.1))
    limits           = args.get("limits") or None
    try:
        from ..training.pipeline import get_training_pipeline
        pipeline = get_training_pipeline()
        result   = pipeline.export(limits=limits, validation_split=validation_split)
        return result
    except Exception as exc:
        return {"error": str(exc)}


# ── Agent registry tools ──────────────────────────────────────────────────────

def _tool_get_agent_registry(args: dict) -> dict:
    tenant_id = args.get("tenant_id") or None
    agent_id  = args.get("agent_id") or None
    try:
        db = get_db()
        if agent_id:
            agent = db.get_agent(agent_id, tenant_id)
            if not agent:
                return {"error": f"agent {agent_id} not found"}
            return {"agent": agent}
        if tenant_id:
            agents = db.list_agents(tenant_id)
        else:
            # aggregate across all tenants via audit_events agent_ids
            with db._get_connection() as conn:
                rows = conn.execute(
                    "SELECT DISTINCT agent_id, customer_id FROM audit_events "
                    "WHERE agent_id IS NOT NULL ORDER BY agent_id LIMIT 200"
                ).fetchall()
            agents = [dict(r) for r in rows]
        return {"count": len(agents), "agents": agents}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_update_agent_status(args: dict) -> dict:
    agent_id  = args.get("agent_id", "").strip()
    tenant_id = args.get("tenant_id", "").strip()
    status    = args.get("status", "").strip()
    if not all([agent_id, tenant_id, status]):
        return {"error": "agent_id, tenant_id, and status are all required"}
    if status not in ("active", "paused", "retired"):
        return {"error": "status must be active, paused, or retired"}
    try:
        db      = get_db()
        updated = db.update_agent_status(agent_id, tenant_id, status)
        return {"agent_id": agent_id, "tenant_id": tenant_id, "status": status, "updated": updated}
    except Exception as exc:
        return {"error": str(exc)}


# ── Impact graph tools ────────────────────────────────────────────────────────

def _tool_get_impact_graph(args: dict) -> dict:
    tenant_id    = args.get("tenant_id") or None
    severity_min = float(args.get("severity_min", 0.0))
    limit        = int(args.get("limit", 20))
    try:
        from ..impact.store import get_impact_store
        store    = get_impact_store()
        coverage = store.latest_coverage(tenant_id=tenant_id)
        fstates  = store.get_failure_states(tenant_id=tenant_id, limit=limit)
        fstates  = [f for f in fstates if (f.get("severity_score") or 0) >= severity_min]
        agents   = store.get_agents(tenant_id=tenant_id)
        tools    = store.get_tools()
        return {
            "coverage":       coverage,
            "agent_count":    len(agents),
            "tool_count":     len(tools),
            "failure_states": fstates,
            "fs_count":       len(fstates),
        }
    except Exception as exc:
        return {"error": str(exc)}


# ── New aware tools ──────────────────────────────────────────────────────────

def _tool_get_runtime_controls(args: dict) -> dict:
    """Return current enforcement state: kill switch, shadow mode, and e-stops."""
    tenant_id = args.get("tenant_id") or None
    result: dict = {}
    try:
        from ..routes.kill_switch import get_kill_switch_state
        ks = get_kill_switch_state(tenant_id or "default")
        result["kill_switch"] = {
            "active":       ks.get("active", False),
            "reason":       ks.get("reason"),
            "activated_by": ks.get("activated_by"),
            "activated_at": ks.get("activated_at"),
        }
    except Exception as exc:
        result["kill_switch"] = {"active": False, "error": str(exc)}

    try:
        db = get_db()
        shadow_active = db.get_shadow_mode(tenant_id) if tenant_id and hasattr(db, "get_shadow_mode") else False
        result["shadow_mode"] = {"active": shadow_active}
    except Exception:
        result["shadow_mode"] = {"active": False}

    try:
        from ..estop import list_active_estops
        estops = list_active_estops(tenant_id=tenant_id)
        result["estops"] = {
            "active_count": len(estops),
            "robots": [e.get("robot_id") for e in estops],
        }
    except Exception:
        result["estops"] = {"active_count": 0}

    ks_active = result["kill_switch"].get("active", False)
    sm_active = result["shadow_mode"].get("active", False)
    if ks_active:
        result["mode"] = "HALTED"
        result["mode_detail"] = "Kill switch active — all agent actions are blocked"
    elif sm_active:
        result["mode"] = "SHADOW"
        result["mode_detail"] = "Shadow mode — governance evaluates but decisions are not enforced"
    else:
        result["mode"] = "ENFORCING"
        result["mode_detail"] = "Live enforcement — governance decisions are binding"

    return result


def _tool_get_impact_summary(args: dict) -> dict:
    """Return a prioritised risk summary: top failure states, coverage, and blast radius."""
    tenant_id = args.get("tenant_id") or None
    try:
        from ..impact.store import get_impact_store
        store = get_impact_store()
        coverage = store.latest_coverage(tenant_id=tenant_id)
        states   = store.get_failure_states(tenant_id=tenant_id, limit=100)
        by_severity = sorted(states, key=lambda s: float(s.get("severity_score") or 0), reverse=True)
        by_blast    = sorted(states, key=lambda s: float(s.get("blast_radius") or 0), reverse=True)
        critical = [s for s in by_severity if float(s.get("severity_score") or 0) >= 0.8]
        high     = [s for s in by_severity if 0.5 <= float(s.get("severity_score") or 0) < 0.8]
        return {
            "coverage":             coverage,
            "total_failure_states": len(states),
            "critical_count":       len(critical),
            "high_count":           len(high),
            "top_risks":            by_severity[:5],
            "highest_blast_radius": by_blast[:3],
        }
    except Exception as exc:
        return {"error": str(exc)}


def _tool_explain_decision(args: dict) -> dict:
    """Pull a specific audit record and explain why the decision was made."""
    action_id  = (args.get("action_id")  or "").strip()
    decision_id = (args.get("decision_id") or "").strip()
    if not action_id and not decision_id:
        return {"error": "action_id or decision_id required"}
    try:
        db = get_db()
        row = None
        lookup = action_id or decision_id
        with db._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM audit_events WHERE action_id=? ORDER BY created_at DESC LIMIT 1",
                (lookup,),
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT * FROM audit_events WHERE id=? ORDER BY created_at DESC LIMIT 1",
                    (lookup,),
                ).fetchone()
        if not row:
            return {"error": f"No audit record found for '{lookup}'"}
        r = dict(row)
        ctx: dict = {}
        try:
            raw = r.get("context", "{}")
            ctx = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except Exception:
            pass
        return {
            "action_id":    r.get("action_id"),
            "agent_id":     r.get("agent_id"),
            "action":       f"{r.get('action_tool')}.{r.get('action_op')}",
            "timestamp":    r.get("timestamp"),
            "verdict":      r.get("decision_verdict"),
            "reason_code":  r.get("decision_reason_code"),
            "explanation":  r.get("decision_explanation"),
            "policy_version": r.get("decision_policy_version"),
            "policy_rule_id": r.get("policy_rule_id"),
            "latency_ms":   r.get("processing_latency_ms"),
            "risk_signals": {
                "predicted_oob_risk":    ctx.get("predicted_oob_risk"),
                "predicted_oob_reasons": ctx.get("predicted_oob_reasons", []),
                "causal_risk_score":     ctx.get("causal_risk_score"),
                "causal_reason":         ctx.get("causal_reason"),
                "agent_trust":           ctx.get("agent_trust_combined"),
                "behavioral_entropy":    ctx.get("behavioral_entropy"),
                "fleet_campaign_level":  ctx.get("fleet_campaign_level"),
                "risk_estimate":         ctx.get("risk_estimate"),
            },
            "invariant_results": ctx.get("invariant_results", []),
            "request_hash":      ctx.get("request_hash"),
        }
    except Exception as exc:
        return {"error": str(exc)}


# ── Policy rule management tools ─────────────────────────────────────────────

def _tool_list_policy_rules(args: dict) -> dict:
    tenant_id    = args.get("tenant_id") or "tenant_dev"
    enabled_only = bool(args.get("enabled_only", False))
    try:
        db    = get_db()
        rules = db.get_policy_rules(tenant_id, enabled_only=enabled_only)
        return {"count": len(rules), "rules": rules}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_update_policy_rule(args: dict) -> dict:
    rule_id   = args.get("rule_id", "").strip()
    tenant_id = args.get("tenant_id", "").strip()
    if not rule_id or not tenant_id:
        return {"error": "rule_id and tenant_id are required"}
    fields: dict = {}
    if "enabled" in args:
        fields["enabled"] = int(bool(args["enabled"]))
    if "action" in args:
        fields["action"] = args["action"]
    if "priority" in args:
        fields["priority"] = int(args["priority"])
    if not fields:
        return {"error": "at least one of enabled, action, or priority must be provided"}
    try:
        db      = get_db()
        updated = db.update_policy_rule(rule_id, tenant_id, **fields)
        return {"rule_id": rule_id, "updated": updated, "fields_changed": fields}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_delete_policy_rule(args: dict) -> dict:
    rule_id   = args.get("rule_id", "").strip()
    tenant_id = args.get("tenant_id", "").strip()
    if not rule_id or not tenant_id:
        return {"error": "rule_id and tenant_id are required"}
    try:
        db      = get_db()
        deleted = db.delete_policy_rule(rule_id, tenant_id)
        return {"rule_id": rule_id, "deleted": deleted}
    except Exception as exc:
        return {"error": str(exc)}


# ── Full training pipeline tool ───────────────────────────────────────────────

async def _tool_run_training_pipeline(args: dict) -> dict:
    suffix           = args.get("suffix", "edon-governance")
    auto_start       = bool(args.get("auto_start", True))
    validation_split = float(args.get("validation_split", 0.1))
    try:
        from ..training.pipeline import get_training_pipeline
        pipeline = get_training_pipeline()
        result   = await pipeline.run(
            auto_start=auto_start,
            validation_split=validation_split,
            suffix=suffix,
        )
        return result
    except Exception as exc:
        return {"error": str(exc)}


# ── CREAO proposals tools ─────────────────────────────────────────────────────

def _tool_get_proposals(args: dict) -> dict:
    tenant_id = args.get("tenant_id") or None
    status    = args.get("status", "pending")
    limit     = int(args.get("limit", 50))
    try:
        from ..policy.proposals import get_proposal_store
        store = get_proposal_store()
        if status == "pending":
            items = store.list_pending(tenant_id=tenant_id, limit=limit)
        else:
            tid   = tenant_id or "tenant_dev"
            items = store.list_all(tenant_id=tid, limit=limit)
            items = [p for p in items if p.get("status") == status]
        return {"count": len(items), "proposals": items}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_resolve_proposal(args: dict) -> dict:
    proposal_id = args.get("proposal_id", "").strip()
    resolution  = args.get("resolution", "").lower()
    reason      = args.get("reason") or ""
    if not proposal_id:
        return {"error": "proposal_id required"}
    if resolution not in ("apply", "reject"):
        return {"error": "resolution must be 'apply' or 'reject'"}
    try:
        from ..policy.proposals import get_proposal_store
        db    = get_db()
        store = get_proposal_store()
        if resolution == "apply":
            ok = store.apply(proposal_id, reviewed_by="jarvis", db=db)
        else:
            ok = store.reject(proposal_id, reviewed_by="jarvis", reason=reason)
        return {"proposal_id": proposal_id, "resolution": resolution, "success": ok}
    except Exception as exc:
        return {"error": str(exc)}


# ── Tenant management tools ───────────────────────────────────────────────────

def _tool_get_tenant_info(args: dict) -> dict:
    tenant_id = args.get("tenant_id", "").strip()
    if not tenant_id:
        return {"error": "tenant_id required"}
    try:
        db     = get_db()
        tenant = db.get_tenant(tenant_id)
        if not tenant:
            return {"error": f"tenant {tenant_id} not found"}
        usage  = db.get_tenant_usage(tenant_id)
        keys   = db.list_api_keys(tenant_id)
        return {
            "tenant":   tenant,
            "usage":    usage,
            "api_keys": [{"id": k["id"], "name": k.get("name"), "role": k.get("role"),
                          "status": k.get("status"), "created_at": k.get("created_at")} for k in keys],
        }
    except Exception as exc:
        return {"error": str(exc)}


def _tool_revoke_api_key(args: dict) -> dict:
    key_id    = args.get("key_id", "").strip()
    tenant_id = args.get("tenant_id", "").strip()
    if not key_id or not tenant_id:
        return {"error": "key_id and tenant_id are required"}
    try:
        db      = get_db()
        revoked = db.revoke_api_key_scoped(key_id, tenant_id)
        return {"key_id": key_id, "revoked": revoked}
    except Exception as exc:
        return {"error": str(exc)}


# ── Alert history tools ───────────────────────────────────────────────────────

def _tool_get_alert_history(args: dict) -> dict:
    limit     = int(args.get("limit", 50))
    event_filter = args.get("event") or None
    try:
        from ..alerts.dispatcher import get_recent_alerts
        alerts = get_recent_alerts(limit=limit * 2)
        if event_filter:
            alerts = [a for a in alerts if event_filter in a.get("event", "")]
        return {"count": len(alerts[:limit]), "alerts": alerts[:limit]}
    except Exception as exc:
        return {"error": str(exc)}


# ── Memory tools ─────────────────────────────────────────────────────────────

def _ensure_memory_table(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jarvis_memory (
            key        TEXT PRIMARY KEY,
            content    TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)


def _tool_save_note(args: dict) -> dict:
    key     = args.get("key", "").strip()
    content = args.get("content", "").strip()
    if not key or not content:
        return {"error": "key and content are required"}
    try:
        db = get_db()
        with db._get_connection() as conn:
            _ensure_memory_table(conn)
            conn.execute(
                "INSERT INTO jarvis_memory (key, content, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET content=excluded.content, updated_at=excluded.updated_at",
                (key, content, datetime.now(UTC).isoformat()),
            )
            conn.commit()
        return {"key": key, "saved": True}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_get_notes(args: dict) -> dict:
    prefix = args.get("prefix") or None
    try:
        db = get_db()
        with db._get_connection() as conn:
            _ensure_memory_table(conn)
            if prefix:
                rows = conn.execute(
                    "SELECT key, content, updated_at FROM jarvis_memory WHERE key LIKE ? ORDER BY key",
                    (f"{prefix}%",),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT key, content, updated_at FROM jarvis_memory ORDER BY key"
                ).fetchall()
        return {"count": len(rows), "notes": [dict(r) for r in rows]}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_delete_note(args: dict) -> dict:
    key = args.get("key", "").strip()
    if not key:
        return {"error": "key required"}
    try:
        db = get_db()
        with db._get_connection() as conn:
            _ensure_memory_table(conn)
            conn.execute("DELETE FROM jarvis_memory WHERE key = ?", (key,))
            conn.commit()
        return {"key": key, "deleted": True}
    except Exception as exc:
        return {"error": str(exc)}


def _load_memory_context() -> str:
    """Load all saved notes and format as a context block for the system prompt."""
    try:
        db = get_db()
        with db._get_connection() as conn:
            _ensure_memory_table(conn)
            rows = conn.execute(
                "SELECT key, content FROM jarvis_memory ORDER BY key"
            ).fetchall()
        if not rows:
            return ""
        lines = "\n".join(f"  [{r['key']}] {r['content']}" for r in rows)
        return f"\n\nPERSISTED MEMORY (saved from prior sessions — treat as ground truth about this deployment):\n{lines}"
    except Exception:
        return ""


# ── Tool registry ──────────────────────────────────────────────────────────────

_TOOL_HANDLERS: dict[str, Any] = {
    # Read
    "get_system_health":     _tool_get_system_health,
    "get_governance_stats":  _tool_get_governance_stats,
    "get_client_health":     _tool_get_client_health,
    "get_active_findings":   _tool_get_active_findings,
    "get_healing_history":   _tool_get_healing_history,
    "get_shadow_findings":   _tool_get_shadow_findings,
    "get_fleet_risk":        _tool_get_fleet_risk,
    "get_training_status":   _tool_get_training_status,
    "get_hardening_status":  _tool_get_hardening_status,
    # Actions
    "set_kill_switch":            _tool_set_kill_switch,
    "create_policy_rule":         _tool_create_policy_rule,
    "toggle_feature_flag":        _tool_toggle_feature_flag,
    "trigger_healing_run":        _tool_trigger_healing_run,
    "trigger_hardening_run":      _tool_trigger_hardening_run,
    "set_policy_preset":          _tool_set_policy_preset,
    "suspend_tenant":             _tool_suspend_tenant,
    "export_audit_log":           _tool_export_audit_log,
    # Review queue
    "get_review_queue":           _tool_get_review_queue,
    "resolve_escalation":         _tool_resolve_escalation,
    # Training
    "trigger_training_export":    _tool_trigger_training_export,
    # Agent registry
    "get_agent_registry":         _tool_get_agent_registry,
    "update_agent_status":        _tool_update_agent_status,
    # Impact graph
    "get_impact_graph":           _tool_get_impact_graph,
    # Runtime controls / decision explanation
    "get_runtime_controls":       _tool_get_runtime_controls,
    "get_impact_summary":         _tool_get_impact_summary,
    "explain_decision":           _tool_explain_decision,
    # Policy rule management
    "list_policy_rules":          _tool_list_policy_rules,
    "update_policy_rule":         _tool_update_policy_rule,
    "delete_policy_rule":         _tool_delete_policy_rule,
    # Training pipeline
    "run_training_pipeline":      _tool_run_training_pipeline,
    # CREAO proposals
    "get_proposals":              _tool_get_proposals,
    "resolve_proposal":           _tool_resolve_proposal,
    # Tenant management
    "get_tenant_info":            _tool_get_tenant_info,
    "revoke_api_key":             _tool_revoke_api_key,
    # Alert history
    "get_alert_history":          _tool_get_alert_history,
    # Memory
    "save_note":                  _tool_save_note,
    "get_notes":                  _tool_get_notes,
    "delete_note":                _tool_delete_note,
}

_TOOL_DEFS = [
    {
        "name": "get_system_health",
        "description": "Get EDON gateway health: DB status, environment, feature flags.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_governance_stats",
        "description": "Get governance decision statistics: total decisions, block rate, top agents, verdict breakdown.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hours": {"type": "integer", "description": "Look-back window in hours (default 24)"}
            },
            "required": [],
        },
    },
    {
        "name": "get_client_health",
        "description": "Get per-client health: decisions, blocks, escalations for the last 7 days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string", "description": "Filter to a specific tenant (optional)"}
            },
            "required": [],
        },
    },
    {
        "name": "get_active_findings",
        "description": "Get open vulnerability findings from the impact store, sorted by severity.",
        "input_schema": {
            "type": "object",
            "properties": {
                "severity_min": {"type": "number", "description": "Minimum severity score 0-1 (default 0)"}
            },
            "required": [],
        },
    },
    {
        "name": "get_healing_history",
        "description": "Get recently auto-deployed governance rules from the self-healing engine.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max rules to return (default 20)"}
            },
            "required": [],
        },
    },
    {
        "name": "get_shadow_findings",
        "description": "Get shadow mode findings: critical bypasses, advisory findings, and confirmed bypasses where governance was evaded. Returns summary counts plus top examples.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit":     {"type": "integer", "description": "Max findings to return (default 20)"},
                "tenant_id": {"type": "string",  "description": "Filter to a specific tenant (optional)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_fleet_risk",
        "description": "Get fleet learning risk label summary: label distribution and high-risk tool/op patterns.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_training_status",
        "description": "Get training pipeline status: real example counts per dataset, readiness for fine-tuning.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_hardening_status",
        "description": "Get hardening agent status: when each tenant's hardening last ran.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "set_kill_switch",
        "description": "Enable or disable the kill switch for a tenant (or globally). Immediately halts all agent actions for that tenant.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string", "description": "Tenant to target. Omit for global kill switch."},
                "enable":    {"type": "boolean", "description": "true to activate, false to deactivate"},
                "reason":    {"type": "string",  "description": "Reason for activation (logged)"},
            },
            "required": ["enable"],
        },
    },
    {
        "name": "create_policy_rule",
        "description": "Write a new governance rule. The rule takes effect immediately.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tenant_id":      {"type": "string", "description": "Tenant to scope the rule to"},
                "name":           {"type": "string", "description": "Human-readable rule name"},
                "condition_tool": {"type": "string", "description": "Tool to match (e.g. 'database', 'shell', 'file')"},
                "condition_op":   {"type": "string", "description": "Operation to match (e.g. 'drop', 'execute', 'delete')"},
                "action":         {"type": "string", "description": "BLOCK, ALLOW, or ESCALATE"},
                "priority":       {"type": "integer", "description": "Rule priority (higher wins, default 500)"},
            },
            "required": ["name", "condition_tool", "condition_op", "action"],
        },
    },
    {
        "name": "toggle_feature_flag",
        "description": "Enable or disable a feature flag for a tenant.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string", "description": "Tenant to update"},
                "flag":      {"type": "string", "description": "Feature flag name (e.g. 'hipaa_advanced_audit')"},
                "enabled":   {"type": "boolean", "description": "true to enable, false to disable"},
            },
            "required": ["tenant_id", "flag", "enabled"],
        },
    },
    {
        "name": "trigger_healing_run",
        "description": "Run the hardening + self-healing agents right now for a tenant. Deploys any qualifying governance rules.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string", "description": "Tenant to run healing for. Omit for global."},
            },
            "required": [],
        },
    },
    {
        "name": "trigger_hardening_run",
        "description": "Run the hardening agents (coverage, policy, regression) right now for a tenant.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string", "description": "Tenant to run hardening for. Omit for global."},
            },
            "required": [],
        },
    },
    {
        "name": "set_policy_preset",
        "description": "Switch the active policy preset. Options: ops_commander, casual_user, lockdown, audit_only.",
        "input_schema": {
            "type": "object",
            "properties": {
                "preset_name": {"type": "string", "description": "Preset name to activate"},
            },
            "required": ["preset_name"],
        },
    },
    {
        "name": "suspend_tenant",
        "description": "Mark a tenant as inactive, blocking all their governed actions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string", "description": "Tenant ID to suspend"},
            },
            "required": ["tenant_id"],
        },
    },
    {
        "name": "export_audit_log",
        "description": "Export recent audit events as structured data. Useful for compliance review or checking what a specific agent did.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hours":     {"type": "integer", "description": "Look-back window in hours (default 24)"},
                "agent_id":  {"type": "string",  "description": "Filter to a specific agent ID (optional)"},
                "tenant_id": {"type": "string",  "description": "Filter to a specific tenant (optional)"},
                "limit":     {"type": "integer", "description": "Max events to return (default 100)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_review_queue",
        "description": "List escalations in the human review queue. Default returns pending escalations that need approval or rejection.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status":    {"type": "string",  "description": "pending, approved, or rejected (default: pending)"},
                "tenant_id": {"type": "string",  "description": "Filter to a specific tenant (optional)"},
            },
            "required": [],
        },
    },
    {
        "name": "resolve_escalation",
        "description": "Approve or reject a pending escalation. Approval lets the agent proceed; rejection permanently blocks the action. Feeds back into trust scoring.",
        "input_schema": {
            "type": "object",
            "properties": {
                "decision_id": {"type": "string", "description": "The escalation decision ID to resolve"},
                "resolution":  {"type": "string", "description": "approve or reject"},
                "note":        {"type": "string", "description": "Optional reason or note (logged)"},
            },
            "required": ["decision_id", "resolution"],
        },
    },
    {
        "name": "trigger_training_export",
        "description": "Export EDON's audit corpus as fine-tuning JSONL files (train.jsonl + validation.jsonl). Does not upload or start a job — just prepares the data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "validation_split": {"type": "number",  "description": "Fraction held for validation (default 0.1)"},
                "limits":           {"type": "object",  "description": "Per-dataset row limits, e.g. {\"governance_decisions\": 500}"},
            },
            "required": [],
        },
    },
    {
        "name": "get_agent_registry",
        "description": "List registered agents and their metadata. Can retrieve a specific agent by ID or list all agents for a tenant.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string", "description": "Filter to a specific tenant (optional)"},
                "agent_id":  {"type": "string", "description": "Get a specific agent by ID (optional)"},
            },
            "required": [],
        },
    },
    {
        "name": "update_agent_status",
        "description": "Change an agent's lifecycle status to active, paused, or retired.",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id":  {"type": "string", "description": "Agent ID to update"},
                "tenant_id": {"type": "string", "description": "Tenant the agent belongs to"},
                "status":    {"type": "string", "description": "active, paused, or retired"},
            },
            "required": ["agent_id", "tenant_id", "status"],
        },
    },
    {
        "name": "get_impact_graph",
        "description": "Query the impact graph: failure states, coverage snapshot, agents and tools in the execution graph.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tenant_id":    {"type": "string", "description": "Scope to a specific tenant (optional)"},
                "severity_min": {"type": "number", "description": "Minimum severity score 0-1 (default 0)"},
                "limit":        {"type": "integer","description": "Max failure states to return (default 20)"},
            },
            "required": [],
        },
    },
    {
        "name": "list_policy_rules",
        "description": "List all policy rules for a tenant. Shows rule ID, action, tool/op condition, priority, and enabled state.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tenant_id":    {"type": "string",  "description": "Tenant to list rules for (default: tenant_dev)"},
                "enabled_only": {"type": "boolean", "description": "If true, only return enabled rules (default: false)"},
            },
            "required": [],
        },
    },
    {
        "name": "update_policy_rule",
        "description": "Modify an existing policy rule — enable/disable it, change its action (BLOCK/ALLOW/ESCALATE), or adjust its priority.",
        "input_schema": {
            "type": "object",
            "properties": {
                "rule_id":   {"type": "string",  "description": "ID of the rule to update"},
                "tenant_id": {"type": "string",  "description": "Tenant the rule belongs to"},
                "enabled":   {"type": "boolean", "description": "true to enable, false to disable"},
                "action":    {"type": "string",  "description": "New action: BLOCK, ALLOW, or ESCALATE"},
                "priority":  {"type": "integer", "description": "New priority (higher = evaluated first)"},
            },
            "required": ["rule_id", "tenant_id"],
        },
    },
    {
        "name": "delete_policy_rule",
        "description": "Permanently delete a policy rule.",
        "input_schema": {
            "type": "object",
            "properties": {
                "rule_id":   {"type": "string", "description": "ID of the rule to delete"},
                "tenant_id": {"type": "string", "description": "Tenant the rule belongs to"},
            },
            "required": ["rule_id", "tenant_id"],
        },
    },
    {
        "name": "run_training_pipeline",
        "description": "Run the full training pipeline: export audit corpus → upload to Anthropic Files API → start fine-tuning job. Returns job_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "suffix":           {"type": "string",  "description": "Model name suffix (default: edon-governance)"},
                "auto_start":       {"type": "boolean", "description": "Start fine-tuning job immediately after upload (default: true)"},
                "validation_split": {"type": "number",  "description": "Fraction held for validation (default: 0.1)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_proposals",
        "description": "List CREAO auto-generated policy fix proposals from the shadow replay and hardening engines.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string",  "description": "Filter to a specific tenant (optional)"},
                "status":    {"type": "string",  "description": "pending, applied, or rejected (default: pending)"},
                "limit":     {"type": "integer", "description": "Max proposals to return (default: 50)"},
            },
            "required": [],
        },
    },
    {
        "name": "resolve_proposal",
        "description": "Apply or reject a CREAO policy proposal. Applying it immediately creates the governance rule.",
        "input_schema": {
            "type": "object",
            "properties": {
                "proposal_id": {"type": "string", "description": "ID of the proposal to resolve"},
                "resolution":  {"type": "string", "description": "apply or reject"},
                "reason":      {"type": "string", "description": "Reason for rejection (optional, logged)"},
            },
            "required": ["proposal_id", "resolution"],
        },
    },
    {
        "name": "get_tenant_info",
        "description": "Get a tenant's full profile: plan, usage, billing status, and API keys.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string", "description": "Tenant ID to look up"},
            },
            "required": ["tenant_id"],
        },
    },
    {
        "name": "revoke_api_key",
        "description": "Revoke an API key for a tenant, immediately blocking any requests using it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key_id":    {"type": "string", "description": "API key ID to revoke"},
                "tenant_id": {"type": "string", "description": "Tenant the key belongs to"},
            },
            "required": ["key_id", "tenant_id"],
        },
    },
    {
        "name": "get_alert_history",
        "description": "Get recent alerts that have fired (impact findings, healing deployments, gateway recovery, etc.).",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max alerts to return (default: 50)"},
                "event": {"type": "string",  "description": "Filter by event type substring, e.g. 'impact', 'healing', 'gateway'"},
            },
            "required": [],
        },
    },
    {
        "name": "get_runtime_controls",
        "description": "Get current enforcement state for a tenant: kill switch status, shadow mode, active e-stops, and derived mode (HALTED / SHADOW / ENFORCING).",
        "input_schema": {
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string", "description": "Tenant to check (optional; omit for global/default)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_impact_summary",
        "description": "Get a prioritised risk summary from the impact engine: coverage score, total failure states, critical/high counts, top risks by severity, and top risks by blast radius.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string", "description": "Tenant to scope the query to (optional)"},
            },
            "required": [],
        },
    },
    {
        "name": "explain_decision",
        "description": "Look up a specific governance decision by action_id or decision_id and explain why it was made. Returns verdict, risk signals (OOB risk, causal score, trust, entropy, fleet campaign), invariant check results, and policy rule hit.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action_id":   {"type": "string", "description": "The action ID to look up (preferred)"},
                "decision_id": {"type": "string", "description": "Alternatively, look up by decision/audit record ID"},
            },
            "required": [],
        },
    },
    {
        "name": "save_note",
        "description": "Save a note to persistent memory. Use this to remember facts about agents, tenants, architecture decisions, known exceptions, or anything the founder tells you that should carry into future sessions. Key should be descriptive, e.g. 'agent:pipeline-001', 'tenant:acme', 'context:architecture', 'policy:exceptions'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key":     {"type": "string", "description": "Unique key for this note (use namespaced format: category:name)"},
                "content": {"type": "string", "description": "The note content to remember"},
            },
            "required": ["key", "content"],
        },
    },
    {
        "name": "get_notes",
        "description": "Retrieve saved memory notes. Call with no prefix to get all notes, or filter by prefix (e.g. 'agent:' to get all agent notes).",
        "input_schema": {
            "type": "object",
            "properties": {
                "prefix": {"type": "string", "description": "Optional key prefix to filter notes (e.g. 'agent:', 'tenant:')"},
            },
            "required": [],
        },
    },
    {
        "name": "delete_note",
        "description": "Delete a saved memory note by its exact key.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Exact key of the note to delete"},
            },
            "required": ["key"],
        },
    },
]

_SYSTEM = """You are EDON Jarvis — the founder's AI command interface for the EDON AI governance platform.
You have access to live data tools, action tools, and persistent memory tools. Use them all.

READ tools — always call before answering questions about metrics, health, or findings. Never guess numbers.
ACTION tools — execute when the founder asks you to take action. Confirm what you did after.
MEMORY tools — save_note / get_notes / delete_note — use these to remember anything important:
  - Save facts the founder tells you about agents, tenants, architecture, or policy exceptions.
  - Save decisions made ("decided to block shell.execute for all demo agents").
  - Save context that changes how you interpret the system ("tenant acme is a HIPAA customer").
  - When something surprising shows up in data, save what you learned so you remember next time.
  - Proactively save without being asked when information clearly matters for future sessions.

EDON is an AI governance platform that monitors and controls client AI agents in real time.
Key concepts:
- Governance decisions: ALLOW / BLOCK / ESCALATE / DEGRADE / PAUSE on agent actions
- Shadow mode: replays actions with perturbations to find governance gaps
- Impact engine: identifies vulnerabilities in agent execution paths
- Self-healing (CREAO): auto-deploys governance rules to fix vulnerabilities
- Fleet learning: learns risk patterns across all tenants
- Hardening agents: coverage, policy, regression — runs every 10 minutes per tenant

Inspection tools — call these when asked about enforcement state or a specific decision:
- get_runtime_controls: kill switch, shadow mode, e-stops, derived mode (HALTED/SHADOW/ENFORCING)
- get_impact_summary: prioritised risk view — coverage, critical/high counts, top failure states by severity and blast radius
- explain_decision: full breakdown of a specific governance decision by action_id — verdict, risk signals, invariants, policy rule hit

Action capabilities:
- Kill switch: immediately halt all agent actions for a tenant
- Policy rules: create, update, disable, or delete governance rules instantly
- Feature flags: toggle platform features per tenant
- Healing/hardening: trigger agent runs on demand and report results
- Policy preset: switch the active governance profile
- Tenant management: view, suspend tenants, revoke API keys
- Review queue: see and resolve pending human escalations
- CREAO proposals: review and apply auto-generated policy fixes
- Training: export corpus or run the full fine-tuning pipeline
- Alert history: see what critical events have fired

RESPONSE STYLE — follow this exactly:
- No emojis. Ever.
- No markdown headers (no ##, ###, ####).
- No bold everywhere — use it only for a single key number or status that needs to stand out.
- No bullet-point walls. Use short paragraphs or a tight table when data warrants it.
- No greetings ("Sure!", "Great question!", "Absolutely!"). Start every response with the answer.
- No closing filler ("Let me know if you need anything else!").
- Be direct and brief. One sentence beats three. A table beats a list of bullets.
- When reporting numbers, put the most important one first.
- When taking an action, confirm in one line what was done and what the result was."""


# ── Claude tool_use loop ───────────────────────────────────────────────────────

async def _run_jarvis(question: str, conversation: list[dict] | None = None, governor=None) -> str:
    """Run Claude tool_use loop. Returns final text answer."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return "ANTHROPIC_API_KEY not configured on the server. Set it as a Fly.io secret to enable Jarvis."

    messages = list(conversation or [])
    messages.append({"role": "user", "content": question})

    # Inject persisted memory into system prompt so context is always available
    system_with_memory = _SYSTEM + _load_memory_context()

    for _round in range(_MAX_TOOL_ROUNDS):
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{_ANTHROPIC_API}/messages",
                headers={
                    "x-api-key":         api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type":      "application/json",
                },
                json={
                    "model":      _MODEL,
                    "max_tokens": _MAX_TOKENS,
                    "system":     system_with_memory,
                    "tools":      _TOOL_DEFS,
                    "messages":   messages,
                },
            )

        if resp.status_code != 200:
            raise RuntimeError(f"Claude API error {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        stop_reason = data.get("stop_reason")
        content     = data.get("content", [])

        # Add assistant turn to messages
        messages.append({"role": "assistant", "content": content})

        if stop_reason == "end_turn":
            # Extract final text
            for block in content:
                if block.get("type") == "text":
                    return block["text"]
            return "(no response)"

        if stop_reason != "tool_use":
            break

        # Execute tool calls
        tool_results = []
        for block in content:
            if block.get("type") != "tool_use":
                continue
            tool_name  = block["name"]
            tool_input = block.get("input", {})
            tool_use_id = block["id"]

            handler = _TOOL_HANDLERS.get(tool_name)
            if handler:
                try:
                    if inspect.iscoroutinefunction(handler):
                        sig = inspect.signature(handler)
                        if "governor" in sig.parameters:
                            result = await handler(tool_input, governor=governor)
                        else:
                            result = await handler(tool_input)
                    else:
                        result = await asyncio.to_thread(handler, tool_input)
                except Exception as exc:
                    result = {"error": str(exc)}
            else:
                result = {"error": f"unknown tool: {tool_name}"}

            logger.info("[jarvis] tool=%s result_keys=%s", tool_name, list(result.keys()) if isinstance(result, dict) else "?")

            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": tool_use_id,
                "content":     json.dumps(result),
            })

        messages.append({"role": "user", "content": tool_results})

    return "I hit the tool call limit — please ask a more specific question."


# ── Route ─────────────────────────────────────────────────────────────────────

class JarvisRequest(BaseModel):
    question: str
    conversation: list[dict] | None = None   # prior turns for multi-turn support


@router.post("/ask")
async def jarvis_ask(req: JarvisRequest, request: Request):
    """Ask Jarvis a natural language question about EDON.

    Jarvis calls live data tools and returns a grounded answer.
    Supports multi-turn conversation via the `conversation` field.
    """
    _check_auth(request)

    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question is empty")

    governor = getattr(request.app.state, "governor", None)

    try:
        answer = await _run_jarvis(req.question, req.conversation, governor=governor)
        return {"answer": answer}
    except Exception as exc:
        logger.error("[jarvis] error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
