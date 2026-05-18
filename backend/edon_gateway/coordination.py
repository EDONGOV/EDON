"""Multi-agent coordination graph for EDON.

Tracks within-session action flow across multiple agents and scores
composite risk when agents hand off data to each other.

Architecture note: this is a heuristic layer, not a game-theoretic causal
graph. It covers the observable cases — agent A reads credentials, agent B
sends to external endpoint in the same session. Full causal graph scoring
requires agents to declare data lineage explicitly (derived_from field),
which is a future protocol change.

Composite risk formula:
    base_risk
  + 0.15 * (unique_agents - 1)          [multi-agent multiplier]
  + 0.20 * data_flow_connections         [hand-off count]
  + 0.25 * if credential in flow         [privilege escalation path]
  cap at 1.0

Thread-safe. In-memory (resets on restart). TTL prunes sessions > 90 min.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional

_SESSION_TTL_SEC = 5400  # 90 minutes
_MULTI_AGENT_PENALTY  = 0.15
_DATA_FLOW_PENALTY    = 0.20
_CREDENTIAL_PENALTY   = 0.25
_MAX_RISK             = 1.0

# Output type inference from action_type string
_OUTPUT_SIGNALS: dict[str, str] = {
    "read":       "data",
    "get":        "data",
    "query":      "data",
    "list":       "data",
    "fetch":      "data",
    "search":     "data",
    "credential": "credential",
    "auth":       "credential",
    "token":      "credential",
    "secret":     "credential",
    "key":        "credential",
    "password":   "credential",
    "login":      "credential",
}

_CONSUMER_SIGNALS = {"write", "send", "post", "put", "patch", "create",
                      "delete", "call", "invoke", "execute", "upload", "emit"}


def _infer_output_type(action_type: str) -> Optional[str]:
    # Split on "." and check each component; credential signals take priority over generic data signals.
    parts = action_type.lower().split(".")
    # First pass: credential-class signals (highest specificity)
    _credential_signals = {"credential", "auth", "token", "secret", "key", "password", "login"}
    for part in parts:
        if part in _credential_signals:
            return "credential"
    # Second pass: generic data signals
    for part in parts:
        if part in _OUTPUT_SIGNALS and _OUTPUT_SIGNALS[part] == "data":
            return "data"
    # Substring fallback for compound parts like "getCredential"
    full = action_type.lower()
    for signal, output in _OUTPUT_SIGNALS.items():
        if signal in full:
            return output
    return None


def _is_consumer(action_type: str) -> bool:
    lower = action_type.lower()
    return any(sig in lower for sig in _CONSUMER_SIGNALS)


@dataclass
class ActionRecord:
    action_id:   str
    agent_id:    str
    action_type: str
    output_type: Optional[str]   # "data" | "credential" | None
    is_consumer: bool
    ts:          float           # time.time()


@dataclass
class SessionState:
    tenant_id:   str
    session_id:  str
    records:     list[ActionRecord] = field(default_factory=list)
    created_at:  float             = field(default_factory=time.time)
    last_active: float             = field(default_factory=time.time)


@dataclass
class CoordinationRisk:
    composite_score:       float
    unique_agents:         int
    data_flow_connections: int
    credential_in_flow:    bool
    multi_agent:           bool
    reason:                str


class CoordinationGraph:
    """Session-scoped action tracker for multi-agent composite risk scoring."""

    def __init__(self) -> None:
        self._lock    = threading.Lock()
        self._sessions: dict[tuple[str, str], SessionState] = {}  # (tenant_id, session_id)
        self._last_prune = time.time()

    def record_action(
        self,
        tenant_id:   str,
        session_id:  str,
        agent_id:    str,
        action_id:   str,
        action_type: str,
    ) -> None:
        """Register an action in the session graph."""
        key = (tenant_id or "", session_id)
        record = ActionRecord(
            action_id=action_id,
            agent_id=agent_id,
            action_type=action_type,
            output_type=_infer_output_type(action_type),
            is_consumer=_is_consumer(action_type),
            ts=time.time(),
        )
        with self._lock:
            if key not in self._sessions:
                self._sessions[key] = SessionState(
                    tenant_id=tenant_id or "",
                    session_id=session_id,
                )
            sess = self._sessions[key]
            sess.records.append(record)
            sess.last_active = time.time()
            self._maybe_prune()

    def evaluate_composite_risk(
        self,
        tenant_id:  str,
        session_id: str,
        agent_id:   str,
        action_type: str,
    ) -> CoordinationRisk:
        """Score composite risk for this action in the context of its session.

        Called BEFORE the action executes, so action_type is the proposed action.
        The session history is the accumulated context.
        """
        key = (tenant_id or "", session_id)
        with self._lock:
            sess = self._sessions.get(key)

        if not sess or len(sess.records) == 0:
            return CoordinationRisk(
                composite_score=0.0, unique_agents=1, data_flow_connections=0,
                credential_in_flow=False, multi_agent=False, reason="single_agent_no_history",
            )

        records = sess.records
        unique_agents = len({r.agent_id for r in records} | {agent_id})
        multi_agent   = unique_agents > 1

        # Data flow: count how many prior records produced output that this
        # action type could consume (different agent + compatible type)
        proposed_consumer = _is_consumer(action_type)
        data_flow = 0
        credential_in_flow = False

        for r in records:
            if r.agent_id == agent_id:
                continue
            if r.output_type is not None and proposed_consumer:
                data_flow += 1
            if r.output_type == "credential":
                credential_in_flow = True
            # Also flag if this action produces credentials and there are consumers
            if _infer_output_type(action_type) == "credential":
                credential_in_flow = True

        composite = 0.0
        reasons: list[str] = []

        if multi_agent:
            penalty = _MULTI_AGENT_PENALTY * (unique_agents - 1)
            composite += penalty
            reasons.append(f"multi_agent({unique_agents})+{penalty:.2f}")

        if data_flow > 0:
            penalty = _DATA_FLOW_PENALTY * data_flow
            composite += penalty
            reasons.append(f"data_flow({data_flow})+{penalty:.2f}")

        if credential_in_flow:
            composite += _CREDENTIAL_PENALTY
            reasons.append(f"credential_in_flow+{_CREDENTIAL_PENALTY:.2f}")

        composite = round(min(composite, _MAX_RISK), 4)

        return CoordinationRisk(
            composite_score=composite,
            unique_agents=unique_agents,
            data_flow_connections=data_flow,
            credential_in_flow=credential_in_flow,
            multi_agent=multi_agent,
            reason=" ".join(reasons) or "ok",
        )

    def _maybe_prune(self) -> None:
        now = time.time()
        if now - self._last_prune < 300:
            return
        cutoff = now - _SESSION_TTL_SEC
        expired = [k for k, s in self._sessions.items() if s.last_active < cutoff]
        for k in expired:
            del self._sessions[k]
        self._last_prune = now


# ── Singleton ──────────────────────────────────────────────────────────────────

_graph: Optional[CoordinationGraph] = None
_graph_lock = threading.Lock()


def get_coordination_graph() -> CoordinationGraph:
    global _graph
    if _graph is None:
        with _graph_lock:
            if _graph is None:
                _graph = CoordinationGraph()
    return _graph
