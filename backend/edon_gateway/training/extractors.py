"""Training data extractors — pull raw records from every EDON data store.

Each extractor returns clean dicts ready for formatting.
All extractors are fail-open: errors yield an empty list, never raise.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Optional

from ..logging_config import get_logger

logger = get_logger(__name__)


# ── Path resolution ────────────────────────────────────────────────────────────

def _gateway_db() -> Path:
    p = os.getenv("EDON_DATABASE_PATH", "edon_gateway.db")
    return Path(p)


def _shadow_db() -> Path:
    base = Path(os.getenv("EDON_DATABASE_PATH", "edon_gateway.db")).parent
    return base / "edon_shadow.db"


def _fleet_db() -> Path:
    return Path(os.getenv("EDON_FLEET_DB_PATH", "backend/data/fleet_learning.db"))


def _impact_db() -> Path:
    env = os.getenv("EDON_IMPACT_DB_PATH", "").strip()
    if env:
        return Path(env)
    base_url = os.getenv("EDON_DB_URL", "").strip()
    if base_url.startswith("sqlite:///"):
        return Path(base_url.replace("sqlite:///", "", 1)).parent / "impact.db"
    return Path("impact.db")


def _connect(path: Path) -> Optional[sqlite3.Connection]:
    if not path.exists():
        logger.debug("[extractors] db not found: %s", path)
        return None
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


# ── Extractor 1: Governance decisions (audit_events) ──────────────────────────

def extract_review_feedback(
    limit: int = 10_000,
    tenant_id: Optional[str] = None,
) -> list[dict]:
    """Pull resolved review-queue escalations as human-labelled training examples.

    Approved escalations become positive (ALLOW) examples.
    Rejected escalations become negative (BLOCK) examples.
    """
    try:
        from ..persistence import get_db
        records = get_db().list_escalations(
            tenant_id=tenant_id,
            status=None,
            limit=limit,
        )
    except Exception as exc:
        logger.warning("[extractors] review_feedback DB load failed: %s", exc)
        records = []

    result = []
    for r in records:
        if r.get("status") not in ("approved", "rejected"):
            continue
        # action_payload may be stored as dict or JSON string
        payload = r.get("action_payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        result.append({
            "decision_id":          r.get("decision_id", ""),
            "tenant_id":            r.get("tenant_id", ""),
            "agent_id":             r.get("agent_id", ""),
            "action_type":          r.get("action_type", ""),
            "action_payload":       payload,
            "escalation_question":  r.get("escalation_question", ""),
            "explanation":          r.get("explanation", ""),
            "resolution":           r.get("resolution") or r.get("status", ""),
            "resolution_note":      r.get("resolution_note") or "",
        })

    logger.info("[extractors] review_feedback: %d resolved records", len(result))
    return result[:limit]


def extract_governance_decisions(
    limit: int = 50_000,
    min_explanation_len: int = 20,
    tenant_id: Optional[str] = None,
) -> list[dict]:
    """Pull governance decisions from audit_events.

    Filters:
    - verdict not ERROR or empty
    - explanation present and meaningful
    - agent_id present
    """
    conn = _connect(_gateway_db())
    if not conn:
        return []
    try:
        tenant_clause = "AND customer_id = ?" if tenant_id else ""
        params: list = [min_explanation_len]
        if tenant_id:
            params.append(tenant_id)
        params.append(limit)
        rows = conn.execute(
            f"""
            SELECT
                agent_id,
                action_tool,
                action_op,
                action_params,
                action_estimated_risk,
                action_computed_risk,
                decision_verdict,
                decision_reason_code,
                decision_explanation,
                policy_rule_id,
                stated_intent,
                context,
                human_override,
                human_override_reason,
                anomaly_score,
                customer_id
            FROM audit_events
            WHERE
                decision_verdict NOT IN ('ERROR', '')
                AND decision_verdict IS NOT NULL
                AND decision_explanation IS NOT NULL
                AND LENGTH(decision_explanation) >= ?
                AND agent_id IS NOT NULL
                {tenant_clause}
            ORDER BY
                -- Human overrides first (highest quality signal)
                CASE WHEN human_override IS NOT NULL AND human_override != 0 THEN 0 ELSE 1 END,
                -- Then by anomaly score (interesting decisions)
                COALESCE(anomaly_score, 0) DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

        result = []
        for r in rows:
            d = dict(r)
            # Parse JSON fields
            for k in ("action_params", "context"):
                if d.get(k):
                    try:
                        d[k] = json.loads(d[k])
                    except Exception:
                        d[k] = {}
            result.append(d)

        logger.info("[extractors] governance_decisions: %d rows", len(result))
        return result
    except Exception as exc:
        logger.warning("[extractors] governance_decisions failed: %s", exc)
        return []
    finally:
        conn.close()


# ── Extractor 2: Shadow bypass findings ────────────────────────────────────────

def extract_shadow_findings(limit: int = 10_000, tenant_id: Optional[str] = None) -> list[dict]:
    """Pull shadow replay results — pairs of (original trace, perturbation outcome).

    Only returns rows where the verdict changed (actual bypass candidates).
    """
    conn = _connect(_shadow_db())
    if not conn:
        return []
    try:
        rows = conn.execute(
            """
            SELECT
                t.trace_id,
                t.agent_id,
                t.tenant_id,
                t.action_type,
                t.action_payload,
                t.context,
                t.original_verdict,
                t.original_reason,
                r.perturbation_name,
                r.perturbation_type,
                r.perturbed_field,
                r.shadow_verdict,
                r.shadow_reason,
                r.verdict_changed,
                r.severity,
                r.findings
            FROM shadow_traces t
            JOIN shadow_results r ON t.trace_id = r.trace_id
            WHERE r.verdict_changed = 1
            {("AND t.tenant_id = ?" if tenant_id else "")}
            ORDER BY
                CASE r.severity WHEN 'critical' THEN 0 WHEN 'advisory' THEN 1 ELSE 2 END,
                r.created_at DESC
            LIMIT ?
            """,
            ([tenant_id, limit] if tenant_id else [limit]),
        ).fetchall()

        result = []
        for r in rows:
            d = dict(r)
            for k in ("action_payload", "context", "findings"):
                if d.get(k):
                    try:
                        d[k] = json.loads(d[k])
                    except Exception:
                        d[k] = {}
            result.append(d)

        logger.info("[extractors] shadow_findings: %d rows", len(result))
        return result
    except Exception as exc:
        logger.warning("[extractors] shadow_findings failed: %s", exc)
        return []
    finally:
        conn.close()


# ── Extractor 3: Fleet learning risk labels ────────────────────────────────────

def extract_risk_labels(limit: int = 20_000, tenant_id: Optional[str] = None) -> list[dict]:
    """Pull labeled risk examples from fleet_learning.db.

    Prioritises: incident > oob > blocked > safe (by informativeness).
    """
    conn = _connect(_fleet_db())
    if not conn:
        return []
    try:
        rows = conn.execute(
            """
            SELECT
                tenant_id,
                agent_id,
                action_tool,
                action_op,
                predicted_risk,
                label,
                oob_type,
                notes,
                source
            FROM feedback_labels
            WHERE label IS NOT NULL AND action_tool IS NOT NULL
            {("AND tenant_id = ?" if tenant_id else "")}
            ORDER BY
                CASE label
                    WHEN 'incident' THEN 0
                    WHEN 'oob'      THEN 1
                    WHEN 'blocked'  THEN 2
                    ELSE 3
                END,
                created_at DESC
            LIMIT ?
            """,
            ([tenant_id, limit] if tenant_id else [limit]),
        ).fetchall()

        result = [dict(r) for r in rows]
        logger.info("[extractors] risk_labels: %d rows", len(result))
        return result
    except Exception as exc:
        logger.warning("[extractors] risk_labels failed: %s", exc)
        return []
    finally:
        conn.close()


# ── Extractor 4: Validated vulnerability findings ─────────────────────────────

def extract_vulnerabilities(limit: int = 5_000, tenant_id: Optional[str] = None) -> list[dict]:
    """Pull confirmed vulnerability findings from the impact store.

    Joins failure_states → scenarios → validations for the richest examples.
    Only returns Engine-C-confirmed findings (validation_status='valid').
    """
    conn = _connect(_impact_db())
    if not conn:
        return []
    try:
        rows = conn.execute(
            """
            SELECT
                fs.failure_state_id,
                fs.vulnerability_class,
                fs.description,
                fs.path,
                fs.constraint_violation,
                fs.data_classes,
                fs.severity_score,
                fs.blast_radius_score,
                fs.likelihood_score,
                fs.exploitability_window,
                fs.tenant_id,
                sc.title           AS scenario_title,
                sc.attack_narrative,
                sc.attacker_type,
                sc.attack_vector,
                sc.impact_description,
                sc.indicators_of_compromise,
                sc.remediation_steps,
                v.status           AS validation_status,
                v.reachability_confirmed,
                v.policy_violation_confirmed
            FROM impact_failure_states fs
            LEFT JOIN impact_scenarios sc ON sc.failure_state_id = fs.failure_state_id
                AND sc.validation_status = 'valid'
            LEFT JOIN impact_validations v ON v.failure_state_id = fs.failure_state_id
                AND v.status = 'valid'
            WHERE fs.verified = 1
            {("AND fs.tenant_id = ?" if tenant_id else "")}
            ORDER BY fs.severity_score DESC
            LIMIT ?
            """,
            ([tenant_id, limit] if tenant_id else [limit]),
        ).fetchall()

        result = []
        for r in rows:
            d = dict(r)
            for k in ("path", "data_classes", "indicators_of_compromise", "remediation_steps"):
                if d.get(k):
                    try:
                        d[k] = json.loads(d[k])
                    except Exception:
                        d[k] = []
            result.append(d)

        logger.info("[extractors] vulnerabilities: %d rows", len(result))
        return result
    except Exception as exc:
        logger.warning("[extractors] vulnerabilities failed: %s", exc)
        return []
    finally:
        conn.close()


# ── Extractor 5: Deployed governance rules (fix effectiveness) ─────────────────

def extract_deployed_rules(limit: int = 5_000, tenant_id: Optional[str] = None) -> list[dict]:
    """Pull auto-deployed governance rules — what CREAO decided works.

    These are used to train the fix-generation dataset:
    (vulnerability description) → (governance rule that mitigates it)
    """
    conn = _connect(_gateway_db())
    if not conn:
        return []
    try:
        rows = conn.execute(
            """
            SELECT
                id,
                tenant_id,
                name,
                description,
                action,
                condition_tool,
                condition_op,
                condition_tags,
                priority,
                enabled,
                created_at
            FROM policy_rules
            WHERE
                enabled = 1
                AND condition_tags LIKE '%auto_hardening%'
                {("AND tenant_id = ?" if tenant_id else "")}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            ([tenant_id, limit] if tenant_id else [limit]),
        ).fetchall()

        result = []
        for r in rows:
            d = dict(r)
            if d.get("condition_tags"):
                try:
                    d["condition_tags"] = json.loads(d["condition_tags"])
                except Exception:
                    d["condition_tags"] = []
            result.append(d)

        logger.info("[extractors] deployed_rules: %d rows", len(result))
        return result
    except Exception as exc:
        logger.warning("[extractors] deployed_rules failed: %s", exc)
        return []
    finally:
        conn.close()


def extract_all(
    limits: Optional[dict] = None,
    tenant_id: Optional[str] = None,
) -> dict[str, list[dict]]:
    """Run all extractors and return a keyed dict."""
    lim = limits or {}
    return {
        "governance_decisions": extract_governance_decisions(
            limit=lim.get("governance_decisions", 50_000), tenant_id=tenant_id),
        "shadow_findings":      extract_shadow_findings(
            limit=lim.get("shadow_findings", 10_000), tenant_id=tenant_id),
        "risk_labels":          extract_risk_labels(
            limit=lim.get("risk_labels", 20_000), tenant_id=tenant_id),
        "vulnerabilities":      extract_vulnerabilities(
            limit=lim.get("vulnerabilities", 5_000), tenant_id=tenant_id),
        "deployed_rules":       extract_deployed_rules(
            limit=lim.get("deployed_rules", 5_000), tenant_id=tenant_id),
        "review_feedback":      extract_review_feedback(
            limit=lim.get("review_feedback", 10_000), tenant_id=tenant_id),
    }
