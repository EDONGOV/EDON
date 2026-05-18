"""Session-level risk accumulation for multi-step attack detection.

Groups actions by (tenant_id, session_id) and accumulates a decaying risk
score across the session window. Individual actions may each be ALLOW, but
a pattern of escalating-risk actions triggers ESCALATE or BLOCK.
"""

import os
import time
import threading
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

_WINDOW_SEC = int(os.getenv("EDON_SESSION_WINDOW_SEC", "3600"))       # 1-hour window
_ESCALATE_THRESHOLD = float(os.getenv("EDON_SESSION_ESCALATE_THRESHOLD", "0.65"))
_BLOCK_THRESHOLD = float(os.getenv("EDON_SESSION_BLOCK_THRESHOLD", "0.90"))
_MAX_ENTRIES = int(os.getenv("EDON_SESSION_MAX_ACTIONS", "200"))

# Base risk contribution per risk level
_RISK_WEIGHTS: Dict[str, float] = {
    "low": 0.05,
    "medium": 0.15,
    "high": 0.35,
    "critical": 0.65,
}

# Additional contribution from a prior action's verdict
_VERDICT_WEIGHTS: Dict[str, float] = {
    "BLOCK": 0.30,
    "ESCALATE": 0.20,
    "ERROR": 0.25,
    "PAUSE": 0.10,
    "DEGRADE": 0.05,
    "ALLOW": 0.00,
}

# Decay half-life in seconds (score halves every 15 minutes)
_HALF_LIFE_SEC = 900.0


class _SessionEntry:
    __slots__ = ("ts", "tool", "op", "risk_level", "verdict", "action_id")

    def __init__(
        self,
        ts: float,
        tool: str,
        op: str,
        risk_level: str,
        verdict: str,
        action_id: str,
    ) -> None:
        self.ts = ts
        self.tool = tool
        self.op = op
        self.risk_level = risk_level.lower()
        self.verdict = verdict.upper()
        self.action_id = action_id


class SessionRiskResult:
    __slots__ = ("session_score", "action_count", "escalate", "block", "reasons")

    def __init__(
        self,
        session_score: float,
        action_count: int,
        escalate: bool,
        block: bool,
        reasons: List[str],
    ) -> None:
        self.session_score = session_score
        self.action_count = action_count
        self.escalate = escalate
        self.block = block
        self.reasons = reasons

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_score": round(self.session_score, 4),
            "action_count": self.action_count,
            "escalate": self.escalate,
            "block": self.block,
            "reasons": self.reasons,
        }


def _compute_score(entries: List[_SessionEntry]) -> float:
    """Decaying cumulative risk score capped at 1.0."""
    if not entries:
        return 0.0
    now = time.time()
    total = 0.0
    for e in entries:
        age = max(0.0, now - e.ts)
        decay = 0.5 ** (age / _HALF_LIFE_SEC)
        risk_w = _RISK_WEIGHTS.get(e.risk_level, 0.05)
        verdict_w = _VERDICT_WEIGHTS.get(e.verdict, 0.0)
        total += (risk_w + verdict_w) * decay
    return min(total, 1.0)


_EVICT_INTERVAL = 500   # sweep expired session keys every N records


class SessionRiskTracker:
    """Thread-safe session-level risk accumulator."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: Dict[Tuple[str, str], List[_SessionEntry]] = defaultdict(list)
        self._record_count: int = 0

    def _key(self, tenant_id: Optional[str], session_id: str) -> Tuple[str, str]:
        return (tenant_id or "default", session_id)

    def _prune(self, entries: List[_SessionEntry]) -> List[_SessionEntry]:
        cutoff = time.time() - _WINDOW_SEC
        return [e for e in entries if e.ts >= cutoff]

    def check(
        self,
        tenant_id: Optional[str],
        session_id: str,
        current_tool: str,
        current_op: str,
        current_risk: str,
    ) -> SessionRiskResult:
        """Project what the session score will be if this action is ALLOW.

        Call BEFORE recording the action.  Returns whether the accumulated
        session risk warrants ESCALATE or BLOCK.
        """
        key = self._key(tenant_id, session_id)
        with self._lock:
            existing = self._prune(self._sessions.get(key, []))

        # Simulate the current action with an optimistic ALLOW verdict
        simulated = _SessionEntry(
            ts=time.time(),
            tool=current_tool,
            op=current_op,
            risk_level=current_risk,
            verdict="ALLOW",
            action_id="__pending__",
        )
        projected = existing + [simulated]
        score = _compute_score(projected)

        reasons: List[str] = []
        block = score >= _BLOCK_THRESHOLD
        escalate = (not block) and score >= _ESCALATE_THRESHOLD

        if block or escalate:
            reasons.append(
                f"Session risk {score:.2f} >= "
                f"{'block' if block else 'escalate'} threshold "
                f"({_BLOCK_THRESHOLD if block else _ESCALATE_THRESHOLD})"
            )

        recent_high = sum(1 for e in existing if e.risk_level in ("high", "critical"))
        if recent_high >= 3:
            reasons.append(f"{recent_high} high/critical actions in session")

        bad_verdicts = sum(
            1 for e in existing if e.verdict in ("BLOCK", "ESCALATE", "ERROR")
        )
        if bad_verdicts >= 2:
            reasons.append(f"{bad_verdicts} BLOCK/ESCALATE verdicts in session")

        return SessionRiskResult(
            session_score=score,
            action_count=len(existing),
            escalate=escalate,
            block=block,
            reasons=reasons,
        )

    def _evict_expired_sessions(self) -> None:
        """Remove session keys whose entries have all expired."""
        cutoff = time.time() - _WINDOW_SEC
        stale = [k for k, entries in self._sessions.items()
                 if not entries or entries[-1].ts < cutoff]
        for k in stale:
            del self._sessions[k]

    def record(
        self,
        tenant_id: Optional[str],
        session_id: str,
        action_id: str,
        tool: str,
        op: str,
        risk_level: str,
        verdict: str,
    ) -> None:
        """Record a completed action (with its final verdict) into the session."""
        key = self._key(tenant_id, session_id)
        entry = _SessionEntry(
            ts=time.time(),
            tool=tool,
            op=op,
            risk_level=risk_level,
            verdict=verdict,
            action_id=action_id,
        )
        with self._lock:
            pruned = self._prune(self._sessions[key])
            if len(pruned) >= _MAX_ENTRIES:
                pruned.pop(0)
            pruned.append(entry)
            self._sessions[key] = pruned
            self._record_count += 1
            if self._record_count % _EVICT_INTERVAL == 0:
                self._evict_expired_sessions()

    def get_summary(self, tenant_id: Optional[str], session_id: str) -> Dict[str, Any]:
        key = self._key(tenant_id, session_id)
        with self._lock:
            entries = self._prune(self._sessions.get(key, []))
        return {
            "session_id": session_id,
            "action_count": len(entries),
            "session_score": round(_compute_score(entries), 4),
            "window_seconds": _WINDOW_SEC,
        }

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "status": "healthy",
                "active_sessions": len(self._sessions),
                "escalate_threshold": _ESCALATE_THRESHOLD,
                "block_threshold": _BLOCK_THRESHOLD,
                "window_seconds": _WINDOW_SEC,
            }


_tracker: Optional[SessionRiskTracker] = None


def get_session_tracker() -> SessionRiskTracker:
    global _tracker
    if _tracker is None:
        _tracker = SessionRiskTracker()
    return _tracker
