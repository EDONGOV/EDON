"""Fleet learning engine for cross-agent safety intelligence.

This module provides:
1) Per-agent pre-action out-of-bounds (OOB) risk prediction.
2) Feedback labeling for blocked/incidents and human-reviewed outcomes.
3) Tenant-controlled federated sharing to improve global OOB priors.

The model is intentionally simple and auditable (rule + statistics based),
so operators can reason about why a prediction happened.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class RiskPrediction:
    score: float
    reasons: List[str]
    signal_breakdown: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "reasons": self.reasons,
            "signal_breakdown": {k: round(v, 4) for k, v in self.signal_breakdown.items()},
        }


class FleetLearningEngine:
    """Simple, deterministic fleet learning engine."""

    def __init__(self, db_path: str = "data/fleet_learning.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback_labels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at REAL NOT NULL,
                    tenant_id TEXT,
                    agent_id TEXT,
                    action_tool TEXT NOT NULL,
                    action_op TEXT NOT NULL,
                    predicted_risk REAL,
                    label TEXT NOT NULL,
                    oob_type TEXT,
                    notes TEXT,
                    source TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_feedback_tool_op
                ON feedback_labels(action_tool, action_op)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_feedback_tenant_created
                ON feedback_labels(tenant_id, created_at)
                """
            )
            conn.commit()

    @staticmethod
    def _safe_ts(event: Dict[str, Any]) -> float:
        raw = event.get("timestamp") or event.get("created_at") or ""
        if isinstance(raw, (int, float)):
            return float(raw)
        if isinstance(raw, str):
            try:
                # Fast path: unix timestamp encoded as string
                return float(raw)
            except Exception:
                pass
            # ISO path
            try:
                from datetime import datetime

                return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
            except Exception:
                return 0.0
        return 0.0

    @staticmethod
    def _is_negative_verdict(verdict: str) -> bool:
        v = (verdict or "").upper()
        return v in {"BLOCK", "ERROR", "ESCALATE", "PAUSE"}

    def is_federated_opt_in(self, db: Any, tenant_id: Optional[str]) -> bool:
        if not tenant_id:
            return False
        try:
            prefs = db.read_preferences(tenant_id, keys=["federated_learning_opt_in"])
            value = str(prefs.get("federated_learning_opt_in", "false")).strip().lower()
            return value in {"1", "true", "yes", "on"}
        except Exception:
            return False

    def set_federated_opt_in(self, db: Any, tenant_id: str, opt_in: bool) -> None:
        db.write_preference(tenant_id, "federated_learning_opt_in", "true" if opt_in else "false")

    def _tool_op_prior(self, action_tool: str, action_op: str) -> float:
        with self._lock, self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN label IN ('oob', 'incident', 'blocked') THEN 1 ELSE 0 END) AS negatives
                FROM feedback_labels
                WHERE action_tool = ? AND action_op = ?
                """,
                (action_tool, action_op),
            )
            row = cur.fetchone()
            total = int(row["total"] or 0)
            negatives = int(row["negatives"] or 0)
            # Bayesian-ish smoothing to avoid extreme early priors.
            return (negatives + 1.0) / (total + 6.0)

    def record_feedback(
        self,
        *,
        tenant_id: Optional[str],
        agent_id: Optional[str],
        action_tool: str,
        action_op: str,
        label: str,
        predicted_risk: Optional[float] = None,
        oob_type: Optional[str] = None,
        notes: Optional[str] = None,
        source: str = "operator",
    ) -> None:
        with self._lock, self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO feedback_labels (
                    created_at, tenant_id, agent_id, action_tool, action_op,
                    predicted_risk, label, oob_type, notes, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    time.time(),
                    tenant_id,
                    agent_id,
                    action_tool,
                    action_op,
                    predicted_risk,
                    label,
                    oob_type,
                    notes,
                    source,
                ),
            )
            conn.commit()

    def predict_action(
        self,
        *,
        db: Any,
        tenant_id: Optional[str],
        agent_id: str,
        action_tool: str,
        action_op: str,
        estimated_risk: str = "low",
    ) -> RiskPrediction:
        """Predict OOB risk using agent + fleet signals."""
        # Pull enough history to compute rolling agent baselines.
        events = db.query_audit_events(agent_id=agent_id, customer_id=tenant_id, limit=1500)
        now = time.time()
        hour_ago = now - 3600
        month_ago = now - 30 * 24 * 3600

        recent = [e for e in events if self._safe_ts(e) >= hour_ago]
        baseline = [e for e in events if month_ago <= self._safe_ts(e) < hour_ago]

        recent_total = len(recent)
        base_total = max(len(baseline), 1)

        recent_bad = sum(1 for e in recent if self._is_negative_verdict(e.get("verdict", "")))
        base_bad = sum(1 for e in baseline if self._is_negative_verdict(e.get("verdict", "")))

        recent_bad_rate = recent_bad / max(recent_total, 1)
        base_bad_rate = base_bad / base_total

        action_rate_recent = recent_total
        action_rate_baseline = len(baseline) / 720.0  # 30d * 24h

        seen_tool_before = any(
            ((e.get("action") or {}).get("tool") == action_tool and (e.get("action") or {}).get("op") == action_op)
            for e in baseline
        )
        novelty_signal = 1.0 if not seen_tool_before else 0.0

        # Tenant-controlled federated prior.
        if self.is_federated_opt_in(db, tenant_id):
            fleet_prior = self._tool_op_prior(action_tool=action_tool, action_op=action_op)
        else:
            fleet_prior = 0.18

        risk_weight = {"low": 0.05, "medium": 0.18, "high": 0.38, "critical": 0.62}.get(
            (estimated_risk or "low").lower(), 0.05
        )

        rate_spike = 0.0
        if action_rate_baseline > 0:
            multiple = action_rate_recent / action_rate_baseline
            if multiple > 2.0:
                rate_spike = min((multiple - 2.0) / 4.0, 1.0)

        bad_spike = 0.0
        if recent_bad_rate > base_bad_rate + 0.15:
            bad_spike = min((recent_bad_rate - base_bad_rate) / 0.5, 1.0)

        # Weighted, explainable risk score.
        components = {
            "fleet_prior": 0.28 * fleet_prior,
            "estimated_risk": 0.20 * risk_weight,
            "novelty": 0.20 * novelty_signal,
            "rate_spike": 0.16 * rate_spike,
            "negative_verdict_spike": 0.16 * bad_spike,
        }
        score = max(0.0, min(sum(components.values()), 1.0))

        reasons: List[str] = []
        if novelty_signal > 0:
            reasons.append("tool/op not seen in agent 30-day baseline")
        if rate_spike > 0:
            reasons.append("agent action-rate spike vs 30-day baseline")
        if bad_spike > 0:
            reasons.append("negative-verdict spike vs 30-day baseline")
        if fleet_prior >= 0.35:
            reasons.append("fleet feedback indicates elevated tool/op incident rate")
        if not reasons:
            reasons.append("no elevated anomaly signals; baseline behavior")

        return RiskPrediction(score=score, reasons=reasons, signal_breakdown=components)

    def get_tool_incident_rate(self, action_tool: str, action_op: str) -> float:
        """Public wrapper: historical incident rate for a tool/op pair (0.0–1.0).

        Uses Bayesian smoothing to avoid extreme priors from small sample sizes.
        Values > 0.4 indicate the fleet has seen elevated incidents for this pair.
        """
        return self._tool_op_prior(action_tool=action_tool, action_op=action_op)

    def model_summary(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        with self._lock, self._conn() as conn:
            cur = conn.cursor()
            if tenant_id:
                cur.execute(
                    """
                    SELECT COUNT(*) AS total,
                           SUM(CASE WHEN label IN ('oob', 'incident', 'blocked') THEN 1 ELSE 0 END) AS negatives
                    FROM feedback_labels
                    WHERE tenant_id = ?
                    """,
                    (tenant_id,),
                )
            else:
                cur.execute(
                    """
                    SELECT COUNT(*) AS total,
                           SUM(CASE WHEN label IN ('oob', 'incident', 'blocked') THEN 1 ELSE 0 END) AS negatives
                    FROM feedback_labels
                    """
                )
            row = cur.fetchone()
            total = int(row["total"] or 0)
            negatives = int(row["negatives"] or 0)

            cur.execute(
                """
                SELECT action_tool, action_op, COUNT(*) AS cnt
                FROM feedback_labels
                GROUP BY action_tool, action_op
                ORDER BY cnt DESC
                LIMIT 20
                """
            )
            top_pairs = [
                {"action_tool": r["action_tool"], "action_op": r["action_op"], "samples": int(r["cnt"])}
                for r in cur.fetchall()
            ]

        return {
            "tenant_id": tenant_id,
            "feedback_samples": total,
            "negative_labels": negatives,
            "negative_rate": round((negatives / total), 4) if total else 0.0,
            "top_labeled_tool_ops": top_pairs,
        }


_engine: Optional[FleetLearningEngine] = None


def get_fleet_learning_engine() -> FleetLearningEngine:
    global _engine
    if _engine is None:
        _engine = FleetLearningEngine()
    return _engine

