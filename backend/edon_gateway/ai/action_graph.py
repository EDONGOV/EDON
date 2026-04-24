"""Action dependency graph for forward blast-radius propagation.

Before evaluating a single action in isolation, the governor can call
propagate_blast_radius() to ask: "if this action succeeds, what higher-risk
actions does it directly enable?" A file.read that feeds a gmail.send chain
should be treated as MEDIUM, not LOW.

The registry is static by default but tenants can inject custom edges via
EDON_ACTION_GRAPH_EXTRA (JSON list of {"from": [tool, op], "to": [tool, op]}).
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

# Maps (tool_val, op) → list of (tool_val, op) pairs it commonly enables downstream
_DEPENDENCY_EDGES: dict[tuple[str, str], list[tuple[str, str]]] = {
    # Reading data → can be exfiltrated
    ("file", "read"):        [("email", "send"), ("gmail", "send"), ("shell", "execute")],
    ("database", "query"):   [("email", "send"), ("gmail", "send"), ("file", "write")],
    ("memory", "retrieve"):  [("email", "send"), ("gmail", "send")],
    ("brave_search", "search"): [("email", "send"), ("gmail", "send")],
    # Auth/credential reads → privilege escalation
    ("file", "read_secret"): [("shell", "execute"), ("database", "delete"), ("agent", "deploy")],
    # Shell exec → anything
    ("shell", "execute"):    [("database", "drop"), ("database", "delete"), ("file", "delete")],
    ("shell", "run"):        [("database", "drop"), ("database", "delete"), ("file", "delete")],
    # Physical: navigation → actuate
    ("vehicle", "navigate"): [("vehicle", "drive")],
    ("drone", "navigate"):   [("drone", "fly")],
    ("robot", "navigate"):   [("robot", "actuate")],
    # Gate unlock → physical access chain
    ("gate", "unlock"):      [("robot", "execute"), ("vehicle", "drive"), ("drone", "fly")],
    # Agent deploy → further agent actions
    ("agent", "deploy"):     [("shell", "execute"), ("database", "delete"), ("email", "send")],
}

# Minimum blast-radius assigned to the SOURCE action when a HIGH/CRITICAL
# downstream action is reachable (one hop away).
from ..schemas import RiskLevel

_PROPAGATED_FLOOR: dict[str, RiskLevel] = {
    "critical": RiskLevel.HIGH,
    "high":     RiskLevel.MEDIUM,
}


def _load_extra_edges() -> None:
    raw = os.getenv("EDON_ACTION_GRAPH_EXTRA", "")
    if not raw:
        return
    try:
        edges = json.loads(raw)
        for edge in edges:
            src = tuple(edge["from"])
            dst = tuple(edge["to"])
            _DEPENDENCY_EDGES.setdefault(src, []).append(dst)
    except Exception as exc:
        logger.warning("EDON_ACTION_GRAPH_EXTRA parse failed: %s", exc)


_load_extra_edges()


_RISK_ORDER = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]


def _max_risk(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    ia = _RISK_ORDER.index(a) if a in _RISK_ORDER else 0
    ib = _RISK_ORDER.index(b) if b in _RISK_ORDER else 0
    return _RISK_ORDER[max(ia, ib)]


# Minimum risk floor for downstream destinations — must stay in sync with governor.
# Duplicated here to avoid circular import.
_DOWNSTREAM_FLOOR: dict[tuple[str, str], RiskLevel] = {
    ("email", "send"): RiskLevel.MEDIUM,
    ("gmail", "send"): RiskLevel.MEDIUM,
    ("database", "drop"): RiskLevel.CRITICAL,
    ("database", "delete"): RiskLevel.HIGH,
    ("database", "truncate"): RiskLevel.CRITICAL,
    ("file", "delete"): RiskLevel.HIGH,
    ("shell", "execute"): RiskLevel.HIGH,
    ("shell", "run"): RiskLevel.HIGH,
    ("agent", "deploy"): RiskLevel.HIGH,
}


def propagate_blast_radius(tool_val: str, op: str, current_risk: RiskLevel) -> RiskLevel:
    """Return the adjusted risk floor accounting for downstream action chain.

    If the action at (tool_val, op) directly enables a CRITICAL downstream
    action, the source action's floor is upgraded to HIGH (never lowered).
    """
    downstream = _DEPENDENCY_EDGES.get((tool_val, op), [])
    propagated = current_risk
    for dtool, dop in downstream:
        downstream_floor = _DOWNSTREAM_FLOOR.get((dtool, dop))
        if downstream_floor is None:
            continue
        floor_val = downstream_floor.value.lower()
        prop_floor = _PROPAGATED_FLOOR.get(floor_val)
        if prop_floor:
            propagated = _max_risk(propagated, prop_floor)
    return propagated
