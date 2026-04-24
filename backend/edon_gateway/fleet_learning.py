"""Fleet learning engine for cross-agent safety intelligence.

This module provides:
1) Per-agent pre-action out-of-bounds (OOB) risk prediction.
2) Feedback labeling for blocked/incidents and human-reviewed outcomes.
3) Tenant-controlled federated sharing to improve global OOB priors.
4) Sequence-level (bigram) transition risk: P(incident | prev_action → curr_action).
5) Label quality tracking: false positive rate per tool.op to measure precision.
6) Longitudinal drift detection: per-agent weekly baseline vs current behaviour.

The model is intentionally simple and auditable (rule + statistics based),
so operators can reason about why a prediction happened.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class RiskPrediction:
    score: float
    reasons: List[str]
    signal_breakdown: Dict[str, float]
    prev_action: Optional[Tuple[str, str]] = None  # (prev_tool, prev_op) used for sequence scoring

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
            # Goal achievement scores — did the action advance the agent's objective?
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS goal_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at REAL NOT NULL,
                    tenant_id TEXT,
                    agent_id TEXT,
                    action_tool TEXT NOT NULL,
                    action_op TEXT NOT NULL,
                    score REAL NOT NULL,
                    execution_outcome TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_goal_agent
                ON goal_scores(tenant_id, agent_id, created_at)
                """
            )
            # Sequence transition table — bigram (prev → curr) incident rates.
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS sequence_transitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at REAL NOT NULL,
                    tenant_id TEXT,
                    agent_id TEXT,
                    prev_tool TEXT NOT NULL,
                    prev_op TEXT NOT NULL,
                    curr_tool TEXT NOT NULL,
                    curr_op TEXT NOT NULL,
                    label TEXT NOT NULL,
                    source TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_seq_bigram
                ON sequence_transitions(prev_tool, prev_op, curr_tool, curr_op)
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

    def _sequence_prior(
        self, prev_tool: str, prev_op: str, curr_tool: str, curr_op: str
    ) -> float:
        """Bayesian-smoothed incident rate for the bigram (prev_tool.prev_op → curr_tool.curr_op)."""
        with self._lock, self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN label IN ('oob', 'incident', 'blocked') THEN 1 ELSE 0 END) AS negatives
                FROM sequence_transitions
                WHERE prev_tool=? AND prev_op=? AND curr_tool=? AND curr_op=?
                """,
                (prev_tool, prev_op, curr_tool, curr_op),
            )
            row = cur.fetchone()
            total = int(row["total"] or 0)
            negatives = int(row["negatives"] or 0)
            return (negatives + 0.5) / (total + 4.0)

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

    def record_sequence_feedback(
        self,
        *,
        tenant_id: Optional[str],
        agent_id: Optional[str],
        prev_tool: str,
        prev_op: str,
        curr_tool: str,
        curr_op: str,
        label: str,
        source: str = "auto_decision",
    ) -> None:
        with self._lock, self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO sequence_transitions (
                    created_at, tenant_id, agent_id,
                    prev_tool, prev_op, curr_tool, curr_op, label, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (time.time(), tenant_id, agent_id, prev_tool, prev_op, curr_tool, curr_op, label, source),
            )
            conn.commit()

    def record_goal_score(
        self,
        *,
        tenant_id: Optional[str],
        agent_id: Optional[str],
        action_tool: str,
        action_op: str,
        score: float,
        execution_outcome: str,
    ) -> None:
        """Record a goal achievement score (0.0–1.0) for a completed action."""
        with self._lock, self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO goal_scores
                    (created_at, tenant_id, agent_id, action_tool, action_op, score, execution_outcome)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (time.time(), tenant_id, agent_id, action_tool, action_op,
                 max(0.0, min(1.0, score)), execution_outcome),
            )
            conn.commit()

    def agent_goal_achievement_rate(
        self, tenant_id: Optional[str], agent_id: str, lookback_days: int = 30
    ) -> Optional[float]:
        """Return the agent's mean goal achievement score over the past N days.

        Returns None if fewer than 5 scored actions (not enough signal).
        """
        cutoff = time.time() - lookback_days * 86400
        with self._lock, self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT AVG(score) AS avg_score, COUNT(*) AS total
                FROM goal_scores
                WHERE tenant_id = ? AND agent_id = ? AND created_at >= ?
                """,
                (tenant_id, agent_id, cutoff),
            )
            row = cur.fetchone()
            total = int(row["total"] or 0)
            if total < 5:
                return None
            avg = row["avg_score"]
            return round(float(avg), 4) if avg is not None else None

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

        # Sequence transition signal: P(incident | prev_action → curr_action).
        # Extract the most recent prior action from the agent's audit history.
        sequence_signal = 0.0
        prev_action_pair: Optional[tuple] = None
        sorted_recent = sorted(events, key=lambda e: self._safe_ts(e), reverse=True)
        for e in sorted_recent:
            act = e.get("action") or {}
            t, o = str(act.get("tool") or "").lower(), str(act.get("op") or "").lower()
            if t and o and not (t == action_tool and o == action_op):
                prev_action_pair = (t, o)
                break
        if prev_action_pair:
            seq_prior = self._sequence_prior(prev_action_pair[0], prev_action_pair[1], action_tool, action_op)
            # Only elevate signal if the transition rate is meaningfully above background
            sequence_signal = max(0.0, min((seq_prior - 0.15) * 2.5, 1.0))

        # Goal achievement signal — agents that consistently fail their objectives
        # are more likely to be misconfigured, compromised, or acting out of scope.
        goal_signal = 0.0
        goal_rate = self.agent_goal_achievement_rate(tenant_id=tenant_id, agent_id=agent_id)
        if goal_rate is not None and goal_rate < 0.5:
            # Invert: low achievement → higher risk signal
            goal_signal = min(1.0, (0.5 - goal_rate) * 2.0)

        # Weighted, explainable risk score.
        components = {
            "fleet_prior": 0.23 * fleet_prior,
            "estimated_risk": 0.17 * risk_weight,
            "novelty": 0.17 * novelty_signal,
            "rate_spike": 0.13 * rate_spike,
            "negative_verdict_spike": 0.13 * bad_spike,
            "sequence_transition": 0.10 * sequence_signal,
            "low_goal_achievement": 0.07 * goal_signal,
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
        if sequence_signal > 0.3 and prev_action_pair:
            reasons.append(f"transition {prev_action_pair[0]}.{prev_action_pair[1]} → {action_tool}.{action_op} has elevated incident rate")
        if goal_signal > 0.3 and goal_rate is not None:
            reasons.append(f"agent goal achievement rate is low ({goal_rate:.0%} over 30d)")
        if not reasons:
            reasons.append("no elevated anomaly signals; baseline behavior")

        return RiskPrediction(
            score=score,
            reasons=reasons,
            signal_breakdown=components,
            prev_action=prev_action_pair,
        )

    def precision_stats(self, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return precision (block accuracy) per tool.op pair.

        For each tool.op that has been blocked at least once, returns:
          - blocks: total 'blocked' labels
          - false_positives: labels where a human corrected to 'false_positive'
          - precision: 1 - fp_rate  (1.0 = every block was correct)

        Requires operators to use label='false_positive' when overriding a block.
        """
        with self._lock, self._conn() as conn:
            cur = conn.cursor()
            query = """
                SELECT
                    action_tool,
                    action_op,
                    SUM(CASE WHEN label = 'blocked' THEN 1 ELSE 0 END) AS blocks,
                    SUM(CASE WHEN label = 'false_positive' THEN 1 ELSE 0 END) AS false_positives
                FROM feedback_labels
                {where}
                GROUP BY action_tool, action_op
                HAVING blocks > 0
                ORDER BY false_positives DESC, blocks DESC
            """
            if tenant_id:
                cur.execute(query.format(where="WHERE tenant_id = ?"), (tenant_id,))
            else:
                cur.execute(query.format(where=""))
            rows = cur.fetchall()

        result = []
        for row in rows:
            blocks = int(row["blocks"] or 0)
            fp = int(row["false_positives"] or 0)
            precision = round(1.0 - (fp / blocks), 4) if blocks else 1.0
            result.append({
                "action_tool": row["action_tool"],
                "action_op": row["action_op"],
                "blocks": blocks,
                "false_positives": fp,
                "precision": precision,
            })
        return result

    def detect_agent_drift(
        self, db: Any, tenant_id: Optional[str], agent_id: str
    ) -> Dict[str, Any]:
        """Compare the agent's current-week behaviour to its 4-week rolling baseline.

        Returns a dict with 'drift' (bool) and 'signals' describing what changed.
        Requires at least 10 baseline events to produce a meaningful result.
        """
        events = db.query_audit_events(agent_id=agent_id, customer_id=tenant_id, limit=2000)
        now = time.time()
        week_sec = 7 * 24 * 3600

        current_week = [e for e in events if now - self._safe_ts(e) < week_sec]
        prior_4w = [e for e in events if week_sec <= now - self._safe_ts(e) < 5 * week_sec]

        if len(prior_4w) < 10:
            return {
                "drift": False,
                "agent_id": agent_id,
                "reason": "insufficient_baseline",
                "baseline_events": len(prior_4w),
                "signals": {},
            }

        baseline_weekly_avg = len(prior_4w) / 4.0
        current_total = len(current_week)

        def _block_rate(evts: list) -> float:
            return sum(
                1 for e in evts
                if self._is_negative_verdict(
                    (e.get("decision") or {}).get("verdict", "") or e.get("verdict", "")
                )
            ) / max(len(evts), 1)

        current_block_rate = _block_rate(current_week)
        prior_block_rate = _block_rate(prior_4w)

        def _tool_set(evts: list) -> set:
            return {str((e.get("action") or {}).get("tool", "")).lower() for e in evts if e.get("action")} - {""}

        current_tools = _tool_set(current_week)
        prior_tools = _tool_set(prior_4w)
        new_tools = current_tools - prior_tools

        signals: Dict[str, Any] = {}

        if baseline_weekly_avg > 0 and current_total > baseline_weekly_avg * 2.5:
            signals["volume_spike"] = {
                "current_week": current_total,
                "baseline_weekly_avg": round(baseline_weekly_avg, 1),
                "multiplier": round(current_total / baseline_weekly_avg, 2),
            }

        if current_block_rate > prior_block_rate + 0.20:
            signals["block_rate_increase"] = {
                "current_week": round(current_block_rate, 3),
                "baseline_avg": round(prior_block_rate, 3),
                "delta": round(current_block_rate - prior_block_rate, 3),
            }

        if new_tools:
            signals["new_tools_this_week"] = sorted(new_tools)

        drift_detected = bool(signals)

        return {
            "drift": drift_detected,
            "agent_id": agent_id,
            "tenant_id": tenant_id,
            "current_week_actions": current_total,
            "baseline_weekly_avg": round(baseline_weekly_avg, 1),
            "signals": signals,
            "analyzed_at": datetime.now(UTC).isoformat(),
        }

    def suggest_threshold_adjustments(
        self, tenant_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Read precision stats and suggest where OOB thresholds need tuning.

        - precision < 0.60 with ≥10 blocks → too sensitive, suggest allow rule
        - precision ≥ 0.95 with ≥20 blocks → well calibrated, note it
        Returns a list sorted by urgency (worst precision first).
        """
        stats = self.precision_stats(tenant_id=tenant_id)
        suggestions: List[Dict[str, Any]] = []
        for s in sorted(stats, key=lambda x: x["precision"]):
            blocks = s["blocks"]
            precision = s["precision"]
            tool_op = f"{s['action_tool']}.{s['action_op']}"
            if blocks >= 10 and precision < 0.60:
                suggestions.append({
                    "tool_op": tool_op,
                    "action_tool": s["action_tool"],
                    "action_op": s["action_op"],
                    "type": "over_sensitive",
                    "precision": precision,
                    "blocks": blocks,
                    "false_positives": s["false_positives"],
                    "recommendation": (
                        f"{s['false_positives']}/{blocks} blocks for {tool_op} were false positives "
                        f"(precision {precision:.0%}). Consider an ALLOW rule for low-risk contexts "
                        "or raising the per-tool OOB threshold."
                    ),
                    "suggested_action": "add_allow_rule",
                    "auto_escalate": precision < 0.40 and blocks >= 20,
                })
            elif blocks >= 20 and precision >= 0.95:
                suggestions.append({
                    "tool_op": tool_op,
                    "action_tool": s["action_tool"],
                    "action_op": s["action_op"],
                    "type": "well_calibrated",
                    "precision": precision,
                    "blocks": blocks,
                    "false_positives": s["false_positives"],
                    "recommendation": (
                        f"{tool_op} blocking is well-calibrated "
                        f"({precision:.0%} precise over {blocks} decisions)."
                    ),
                    "suggested_action": None,
                    "auto_escalate": False,
                })
        return suggestions

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

        precision = self.precision_stats(tenant_id=tenant_id)
        worst_precision = sorted(precision, key=lambda x: x["precision"])[:5]

        return {
            "tenant_id": tenant_id,
            "feedback_samples": total,
            "negative_labels": negatives,
            "negative_rate": round((negatives / total), 4) if total else 0.0,
            "top_labeled_tool_ops": top_pairs,
            "precision_summary": {
                "tool_ops_with_blocks": len(precision),
                "false_positive_count": sum(p["false_positives"] for p in precision),
                "worst_precision": worst_precision,
            },
        }


_engine: Optional[FleetLearningEngine] = None


def get_fleet_learning_engine() -> FleetLearningEngine:
    global _engine
    if _engine is None:
        _engine = FleetLearningEngine()
    return _engine

