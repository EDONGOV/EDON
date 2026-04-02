"""
Behavioral CAV — derives Context-Aware Vector scores from agent action telemetry.
Used when no physiological wearable data is available (software agents).
Feeds into the same governance signal layer as the physical CAV engine.

Score range:  0–10000
States:       restorative (<3000) | balanced (3000–5999) | focus (6000–7999) | overload (8000+)
"""

import threading
import time
from collections import deque
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------

_WINDOW_SIZE = 60          # max actions in the rolling window
_WINDOW_SECS = 600         # 10-minute sliding window (seconds)
_EWMA_ALPHA = 0.1          # slow-adapting baseline (physiological analogy)


class _ActionRecord:
    """Lightweight record of a single observed action."""
    __slots__ = ("tool", "op", "verdict", "risk_level", "ts")

    def __init__(self, tool: str, op: str, verdict: str, risk_level: str, ts: float):
        self.tool = tool
        self.op = op
        self.verdict = verdict.upper()
        self.risk_level = risk_level.lower()
        self.ts = ts


# ---------------------------------------------------------------------------
# BehavioralCAVEngine
# ---------------------------------------------------------------------------

class BehavioralCAVEngine:
    """
    Computes behavioral CAV scores for software agents from their action stream.

    Thread-safe: all state is guarded by a single reentrant lock.
    Uses only Python stdlib — no numpy, no external deps.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # Per-agent rolling window:  agent_id -> deque[_ActionRecord]
        self._windows: Dict[str, deque] = {}
        # Per-agent EWMA baseline:  agent_id -> {"mean": float, "var": float, "n": int}
        self._baselines: Dict[str, Dict[str, float]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_action(
        self,
        agent_id: str,
        tool: str,
        op: str,
        verdict: str,
        risk_level: str,
        timestamp: Optional[float] = None,
    ) -> None:
        """Record a single agent action into the rolling window.

        Args:
            agent_id:   Unique agent identifier.
            tool:       Tool name (e.g. "email", "shell").
            op:         Operation (e.g. "send", "execute").
            verdict:    Governance verdict: ALLOW | BLOCK | ESCALATE | DEGRADE | ERROR.
            risk_level: Estimated risk: low | medium | high | critical.
            timestamp:  Unix epoch float; defaults to now.
        """
        ts = timestamp if timestamp is not None else time.time()
        record = _ActionRecord(tool, op, verdict, risk_level, ts)

        with self._lock:
            if agent_id not in self._windows:
                self._windows[agent_id] = deque(maxlen=_WINDOW_SIZE)
            window = self._windows[agent_id]
            window.append(record)
            # Evict records older than _WINDOW_SECS
            cutoff = ts - _WINDOW_SECS
            while window and window[0].ts < cutoff:
                window.popleft()

    def compute_score(self, agent_id: str) -> Dict[str, Any]:
        """Compute the behavioral CAV score for an agent.

        Returns a dict with:
            cav_score   float  0–10000
            cav_state   str    restorative | balanced | focus | overload
            signals     dict   raw signal values
            z_score     float  deviation from learned baseline
        """
        with self._lock:
            window: List[_ActionRecord] = list(self._windows.get(agent_id, []))

        if not window:
            return {
                "cav_score": 0.0,
                "cav_state": "restorative",
                "signals": self._empty_signals(),
                "z_score": 0.0,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        now_ts = time.time()
        signals = self._extract_signals(window, now_ts)
        raw_score = self._weighted_score(signals)
        cav_score = max(0.0, min(10000.0, raw_score))
        cav_state = self._state_from_score(cav_score)
        z_score = self._compute_z(agent_id, cav_score)

        return {
            "cav_score": round(cav_score, 2),
            "cav_state": cav_state,
            "signals": signals,
            "z_score": round(z_score, 3),
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def update_baseline(self, agent_id: str) -> None:
        """EWMA-update the learned baseline for this agent using the current score.

        Should be called after compute_score to adapt the baseline slowly over time.
        """
        result = self.compute_score(agent_id)
        score = result["cav_score"]
        with self._lock:
            if agent_id not in self._baselines:
                self._baselines[agent_id] = {"mean": score, "var": 0.0, "n": 1}
                return
            bl = self._baselines[agent_id]
            old_mean = bl["mean"]
            # EWMA mean
            new_mean = _EWMA_ALPHA * score + (1 - _EWMA_ALPHA) * old_mean
            # EWMA variance (Welford-style approximation adapted for EWMA)
            diff = score - old_mean
            new_var = (1 - _EWMA_ALPHA) * (bl["var"] + _EWMA_ALPHA * diff * diff)
            bl["mean"] = new_mean
            bl["var"] = new_var
            bl["n"] = bl["n"] + 1

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_signals(
        self, window: List[_ActionRecord], now_ts: float
    ) -> Dict[str, Any]:
        """Derive normalized signal values from the action window."""
        n = len(window)
        if n == 0:
            return self._empty_signals()

        # --- actions_per_min ---
        oldest_ts = window[0].ts
        elapsed_mins = max((now_ts - oldest_ts) / 60.0, 1 / 60.0)
        actions_per_min = n / elapsed_mins

        # --- error_rate --- (BLOCK + ERROR verdicts / total)
        error_verdicts = {"BLOCK", "ERROR"}
        errors = sum(1 for r in window if r.verdict in error_verdicts)
        error_rate = errors / n

        # --- tool_switch_rate --- (how often the tool changes, normalised 0-1)
        switches = sum(
            1 for i in range(1, n) if window[i].tool != window[i - 1].tool
        )
        tool_switch_rate = switches / max(n - 1, 1)

        # --- risk_trend --- (slope-like: compare first half vs second half risk scores)
        risk_map = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        scores_raw = [risk_map.get(r.risk_level, 1) for r in window]
        mid = n // 2
        first_half_avg = sum(scores_raw[:mid]) / max(mid, 1)
        second_half_avg = sum(scores_raw[mid:]) / max(n - mid, 1)
        if second_half_avg > first_half_avg + 0.3:
            risk_trend = "rising"
            risk_trend_score = 1.0
        elif second_half_avg < first_half_avg - 0.3:
            risk_trend = "falling"
            risk_trend_score = 0.0
        else:
            risk_trend = "flat"
            risk_trend_score = 0.5

        # --- retry_rate --- (consecutive same tool+op pairs = retries)
        retries = sum(
            1 for i in range(1, n)
            if window[i].tool == window[i - 1].tool
            and window[i].op == window[i - 1].op
        )
        retry_rate = retries / max(n - 1, 1)

        # --- session_duration_mins ---
        session_duration_mins = elapsed_mins

        return {
            "actions_per_min": round(actions_per_min, 3),
            "error_rate": round(error_rate, 4),
            "tool_switch_rate": round(tool_switch_rate, 4),
            "risk_trend": risk_trend,
            "risk_trend_score": risk_trend_score,
            "retry_rate": round(retry_rate, 4),
            "session_duration_mins": round(session_duration_mins, 3),
            "window_size": n,
        }

    @staticmethod
    def _empty_signals() -> Dict[str, Any]:
        return {
            "actions_per_min": 0.0,
            "error_rate": 0.0,
            "tool_switch_rate": 0.0,
            "risk_trend": "flat",
            "risk_trend_score": 0.5,
            "retry_rate": 0.0,
            "session_duration_mins": 0.0,
            "window_size": 0,
        }

    @staticmethod
    def _weighted_score(signals: Dict[str, Any]) -> float:
        """Weighted sum of normalised signals → raw CAV score 0–10000.

        Weights:
            error_rate            * 3000  (high: errors = operational stress)
            actions_per_min_norm  * 1500  (deviation from comfortable pace)
            tool_switch_rate      * 2000  (context switching = cognitive load)
            risk_trend_score      * 2500  (0=falling risk, 0.5=flat, 1=rising)
            retry_rate            * 1000  (retries = friction / failures)
        """
        # Normalise actions_per_min to 0-1 using a soft cap of 20 apm as 'max comfortable'
        _APM_SOFT_CAP = 20.0
        apm_norm = min(signals["actions_per_min"] / _APM_SOFT_CAP, 1.0)

        score = (
            signals["error_rate"] * 3000.0
            + apm_norm * 1500.0
            + signals["tool_switch_rate"] * 2000.0
            + signals["risk_trend_score"] * 2500.0
            + signals["retry_rate"] * 1000.0
        )
        return score

    @staticmethod
    def _state_from_score(score: float) -> str:
        if score < 3000:
            return "restorative"
        if score < 6000:
            return "balanced"
        if score < 8000:
            return "focus"
        return "overload"

    def _compute_z(self, agent_id: str, current_score: float) -> float:
        """Return z-score: (current - baseline_mean) / max(baseline_std, 1.0)."""
        with self._lock:
            bl = self._baselines.get(agent_id)
        if bl is None:
            return 0.0
        std = bl["var"] ** 0.5
        return (current_score - bl["mean"]) / max(std, 1.0)


# ---------------------------------------------------------------------------
# Module-level singleton and convenience functions
# ---------------------------------------------------------------------------

behavioral_cav = BehavioralCAVEngine()


def record_action(
    agent_id: str,
    tool: str,
    op: str,
    verdict: str,
    risk_level: str,
    timestamp: Optional[float] = None,
) -> None:
    """Module-level convenience: record an action on the singleton engine."""
    behavioral_cav.record_action(agent_id, tool, op, verdict, risk_level, timestamp)


def compute_score(agent_id: str) -> Dict[str, Any]:
    """Module-level convenience: compute CAV score from the singleton engine."""
    return behavioral_cav.compute_score(agent_id)
