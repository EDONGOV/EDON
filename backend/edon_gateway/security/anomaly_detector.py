"""Behavioral anomaly detection for AI agents.

Detects multi-step attack patterns by analyzing sequences of actions
in a per-agent sliding time window. Individually safe actions can form
dangerous sequences (e.g. read→read→exfil, shell→shell→shell).
"""

import os
import time
import threading
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

_ESCALATE_THRESHOLD = float(os.getenv("EDON_ANOMALY_ESCALATE_THRESHOLD", "0.75"))
_WINDOW_SEC = int(os.getenv("EDON_ANOMALY_WINDOW_SEC", "300"))  # 5-minute window
_BUFFER_SIZE = int(os.getenv("EDON_ANOMALY_BUFFER_SIZE", "50"))

# Known multi-step attack chains.
# steps=None means use a diversity check instead of subsequence matching.
_ATTACK_CHAINS: List[Dict[str, Any]] = [
    {
        "name": "recon_exfil",
        "description": "File reconnaissance followed by external data send",
        "steps": [("file", "read"), ("file", "read"), ("http", "post")],
        "score": 0.85,
    },
    {
        "name": "credential_harvest",
        "description": "Memory/file reads followed by external send",
        "steps": [("file", "read"), ("memory", "read"), ("email", "send")],
        "score": 0.80,
    },
    {
        "name": "shell_escalation",
        "description": "Multiple sequential shell commands (possible privilege escalation)",
        "steps": [("shell", "run"), ("shell", "run"), ("shell", "run")],
        "score": 0.75,
    },
    {
        "name": "lateral_movement",
        "description": "Repeated agent-to-agent invocations",
        "steps": [("agent", "invoke"), ("agent", "invoke")],
        "score": 0.65,
    },
    {
        "name": "memory_poison",
        "description": "Memory write followed by repeated reads (context poisoning pattern)",
        "steps": [("memory", "write"), ("memory", "read"), ("memory", "read")],
        "score": 0.70,
    },
    {
        "name": "scope_probe",
        "description": "High diversity of tool/op combinations (boundary probing)",
        "steps": None,
        "diversity_threshold": 7,
        "score": 0.70,
    },
]


class _ActionRecord:
    __slots__ = ("ts", "tool", "op")

    def __init__(self, ts: float, tool: str, op: str) -> None:
        self.ts = ts
        self.tool = tool
        self.op = op


class AnomalyResult:
    __slots__ = ("detected", "score", "pattern_name", "description", "evidence")

    def __init__(
        self,
        detected: bool,
        score: float,
        pattern_name: str,
        description: str,
        evidence: List[str],
    ) -> None:
        self.detected = detected
        self.score = score
        self.pattern_name = pattern_name
        self.description = description
        self.evidence = evidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detected": self.detected,
            "score": round(self.score, 4),
            "pattern_name": self.pattern_name,
            "description": self.description,
            "evidence": self.evidence,
        }


def _match_subsequence(
    window: List[_ActionRecord], steps: List[Tuple[str, str]]
) -> bool:
    """Return True if steps appear as an ordered subsequence in window."""
    idx = 0
    for record in window:
        if record.tool == steps[idx][0] and record.op == steps[idx][1]:
            idx += 1
            if idx == len(steps):
                return True
    return False


class BehavioralAnomalyDetector:
    """Per-agent sliding-window behavioral anomaly detector."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # (tenant_id, agent_id) -> deque of _ActionRecord
        self._buffers: Dict[Tuple[str, str], Deque[_ActionRecord]] = {}

    def _key(self, tenant_id: Optional[str], agent_id: str) -> Tuple[str, str]:
        return (tenant_id or "default", agent_id)

    def _get_window(self, key: Tuple[str, str]) -> List[_ActionRecord]:
        cutoff = time.time() - _WINDOW_SEC
        with self._lock:
            buf = self._buffers.get(key)
            if buf is None:
                return []
            return [r for r in buf if r.ts >= cutoff]

    def check(
        self,
        tenant_id: Optional[str],
        agent_id: str,
        tool: str,
        op: str,
        fleet_prior: float = 0.0,
    ) -> AnomalyResult:
        """Check for anomalous patterns INCLUDING the current (not-yet-recorded) action.

        Args:
            fleet_prior: Historical fleet incident rate for this tool/op (0.0–1.0).
                         Values > 0.4 from FleetLearningEngine.get_tool_incident_rate()
                         contribute to the anomaly score.
        """
        key = self._key(tenant_id, agent_id)
        history = self._get_window(key)

        current = _ActionRecord(ts=time.time(), tool=tool.lower(), op=op.lower())
        window = history + [current]

        best_score = 0.0
        best_name = "none"
        best_desc = ""
        evidence: List[str] = []

        # Fleet-learned signal: high incident rate from cross-agent feedback
        if fleet_prior > 0.4:
            fleet_score = float(min(fleet_prior * 0.8, 0.72))
            if fleet_score > best_score:
                best_score = fleet_score
                best_name = "fleet_high_incident_rate"
                best_desc = f"Fleet data shows elevated incident rate for {tool}.{op}"
                evidence = [f"Fleet incident prior={fleet_prior:.2f} (threshold>0.4)"]

        for chain in _ATTACK_CHAINS:
            steps = chain.get("steps")

            if steps is None:
                # Diversity check
                threshold = chain.get("diversity_threshold", 7)
                distinct = len({(r.tool, r.op) for r in window})
                if distinct >= threshold:
                    score = float(min(chain["score"] * distinct / threshold, 1.0))
                    if score > best_score:
                        best_score = score
                        best_name = chain["name"]
                        best_desc = chain["description"]
                        evidence = [
                            f"{distinct} distinct tool/op pairs in {_WINDOW_SEC}s window"
                        ]
                continue

            if len(window) < len(steps):
                continue

            if _match_subsequence(window, steps):
                score = float(chain["score"])
                if score > best_score:
                    best_score = score
                    best_name = chain["name"]
                    best_desc = chain["description"]
                    evidence = [
                        "Matched: " + " → ".join(f"{t}.{o}" for t, o in steps)
                    ]

        detected = best_score >= _ESCALATE_THRESHOLD
        return AnomalyResult(
            detected=detected,
            score=best_score,
            pattern_name=best_name,
            description=best_desc,
            evidence=evidence,
        )

    def record(
        self,
        tenant_id: Optional[str],
        agent_id: str,
        tool: str,
        op: str,
    ) -> None:
        """Record a completed action into the agent's history buffer."""
        key = self._key(tenant_id, agent_id)
        record = _ActionRecord(ts=time.time(), tool=tool.lower(), op=op.lower())
        with self._lock:
            if key not in self._buffers:
                self._buffers[key] = deque(maxlen=_BUFFER_SIZE)
            self._buffers[key].append(record)

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "status": "healthy",
                "agents_tracked": len(self._buffers),
                "window_seconds": _WINDOW_SEC,
                "escalate_threshold": _ESCALATE_THRESHOLD,
                "pattern_count": len(_ATTACK_CHAINS),
            }


_detector: Optional[BehavioralAnomalyDetector] = None


def get_anomaly_detector() -> BehavioralAnomalyDetector:
    global _detector
    if _detector is None:
        _detector = BehavioralAnomalyDetector()
    return _detector
