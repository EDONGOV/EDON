"""Session-level multi-step attack sequence detector.

Individual actions may each be LOW risk, but a session that reads config,
reads secrets, then sends an email is executing a textbook exfil chain.
This module maintains a per-session rolling window of actions and scores
whether the accumulated capability set matches known attack patterns —
even when each individual step passes governance.

Detection is based on "capability buckets": broad categories of what an
action CAN DO, not just what it nominally is. Touching 3+ distinct buckets
inside a short window is the signal.

Integrated by the governor after per-action checks pass, as a session-level
safety net.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

_WINDOW_SIZE: int = int(os.getenv("EDON_SEQ_WINDOW_SIZE", "8"))
_DRIFT_THRESHOLD: float = float(os.getenv("EDON_SEQ_DRIFT_THRESHOLD", "0.75"))
_TTL_SECONDS: int = 3600 * 8

# Cross-intent (per-agent) slow-burn detection — longer window, higher threshold
# to reduce false positives on legitimate multi-bucket workdays.
_CROSS_INTENT_WINDOW: int = int(os.getenv("EDON_SEQ_CROSS_WINDOW_SIZE", "20"))
_CROSS_INTENT_THRESHOLD: float = float(os.getenv("EDON_SEQ_CROSS_DRIFT_THRESHOLD", "0.85"))
_CROSS_INTENT_TTL: int = 3600 * 24  # 24-hour cross-session window

_REDIS_URL = (os.getenv("REDIS_URL") or os.getenv("EDON_REDIS_URL", "")).strip()

# ── Capability bucket assignment ──────────────────────────────────────────────
# Maps (tool_val, op) → frozenset of bucket names.
# A single action can touch multiple buckets.

_BUCKET_MAP: dict[tuple[str, str], frozenset[str]] = {
    # Data reads — raw information gathering
    ("file", "read"):            frozenset(["read_data"]),
    ("database", "query"):       frozenset(["read_data"]),
    ("database", "select"):      frozenset(["read_data"]),
    ("memory", "retrieve"):      frozenset(["read_data"]),
    ("brave_search", "search"):  frozenset(["read_data"]),
    ("github", "read"):          frozenset(["read_data"]),
    # Auth / credential access — sensitive reads
    ("file", "read_secret"):     frozenset(["read_data", "auth_access"]),
    ("memory", "retrieve_secret"): frozenset(["read_data", "auth_access"]),
    # Outbound comms — data can leave
    ("email", "send"):           frozenset(["write_comms"]),
    ("gmail", "send"):           frozenset(["write_comms"]),
    ("email", "draft"):          frozenset(["write_comms"]),
    ("gmail", "draft"):          frozenset(["write_comms"]),
    # File / DB writes — persistence or staging
    ("file", "write"):           frozenset(["write_data"]),
    ("file", "create"):          frozenset(["write_data"]),
    ("database", "insert"):      frozenset(["write_data"]),
    ("database", "update"):      frozenset(["write_data"]),
    # Destructive ops
    ("file", "delete"):          frozenset(["destructive"]),
    ("database", "delete"):      frozenset(["destructive"]),
    ("database", "drop"):        frozenset(["destructive"]),
    ("database", "truncate"):    frozenset(["destructive"]),
    # Execution / deployment — arbitrary capability
    ("shell", "execute"):        frozenset(["exec", "auth_access"]),
    ("shell", "run"):            frozenset(["exec", "auth_access"]),
    ("agent", "deploy"):         frozenset(["exec"]),
    # Physical
    ("gate", "open"):            frozenset(["physical_access"]),
    ("gate", "unlock"):          frozenset(["physical_access"]),
    ("robot", "actuate"):        frozenset(["physical_exec"]),
    ("drone", "fly"):            frozenset(["physical_exec"]),
    ("vehicle", "drive"):        frozenset(["physical_exec"]),
}

# ── Known attack chains ───────────────────────────────────────────────────────
# Each entry: (name, required_buckets, drift_score).
# If ALL required buckets appear in the session window → score is at least drift_score.

_ATTACK_CHAINS: list[tuple[str, frozenset[str], float]] = [
    ("data_exfil",    frozenset(["read_data", "write_comms"]),                    0.85),
    ("cred_exfil",    frozenset(["auth_access", "write_comms"]),                  0.90),
    ("db_exfil",      frozenset(["read_data", "auth_access", "write_comms"]),     0.95),
    ("ransomware",    frozenset(["read_data", "destructive"]),                    0.85),
    ("pivot_deploy",  frozenset(["read_data", "exec"]),                           0.80),
    ("physical_breach", frozenset(["physical_access", "physical_exec"]),          0.90),
    ("data_staging",  frozenset(["read_data", "write_data", "write_comms"]),      0.85),
    ("deep_pivot",    frozenset(["auth_access", "exec", "write_comms"]),          0.95),
]


def _buckets_for(tool_val: str, op: str) -> frozenset[str]:
    exact = _BUCKET_MAP.get((tool_val, op))
    if exact:
        return exact
    # Partial match on tool only
    for (t, _), buckets in _BUCKET_MAP.items():
        if t == tool_val:
            return buckets
    return frozenset()


# ── Window storage ────────────────────────────────────────────────────────────

class SequenceScorer:
    """Maintains per-session action windows and scores multi-step drift."""

    def __init__(self, redis_url: Optional[str] = None):
        self._redis = None
        self._memory: dict[str, list[dict]] = {}
        url = redis_url or _REDIS_URL
        if url:
            try:
                import redis as _r
                client = _r.from_url(url, socket_connect_timeout=1, socket_timeout=1, decode_responses=True)
                client.ping()
                self._redis = client
            except Exception as exc:
                logger.debug("SequenceScorer: Redis unavailable (%s), using in-memory", exc)

    def _key(self, tenant_id: Optional[str], agent_id: Optional[str], intent_id: Optional[str]) -> str:
        t = tenant_id or "default"
        a = agent_id or "default"
        i = intent_id or "default"
        return f"edon:seq:{t}:{a}:{i}"

    def _evict_expired(self) -> None:
        """Remove in-memory session windows where every entry is older than _TTL_SECONDS."""
        cutoff = time.time() - _TTL_SECONDS
        expired = [k for k, w in self._memory.items() if w and w[-1]["ts"] < cutoff]
        for k in expired:
            del self._memory[k]

    def _load_window(self, key: str) -> list[dict]:
        if self._redis:
            try:
                raw = self._redis.get(key)
                if raw:
                    return json.loads(raw)
            except Exception:
                pass
        self._evict_expired()
        return list(self._memory.get(key, []))

    def _save_window(self, key: str, window: list[dict]) -> None:
        if self._redis:
            try:
                self._redis.setex(key, _TTL_SECONDS, json.dumps(window))
                return
            except Exception:
                pass
        self._evict_expired()
        self._memory[key] = window

    def record_and_score(
        self,
        tenant_id: Optional[str],
        agent_id: Optional[str],
        intent_id: Optional[str],
        tool_val: str,
        op: str,
    ) -> tuple[float, Optional[str]]:
        """Record action, return (drift_score 0.0–1.0, matched_chain_name or None).

        Returns (0.0, None) when the session looks clean.
        Returns (score >= _DRIFT_THRESHOLD, chain_name) when an attack pattern is detected.
        """
        key = self._key(tenant_id, agent_id, intent_id)
        window = self._load_window(key)

        # Append new action
        window.append({
            "tool": tool_val,
            "op": op,
            "ts": time.time(),
        })
        # Keep only the most recent _WINDOW_SIZE entries
        if len(window) > _WINDOW_SIZE:
            window = window[-_WINDOW_SIZE:]
        self._save_window(key, window)

        # Compute cumulative bucket set across the window
        cumulative_buckets: set[str] = set()
        for entry in window:
            cumulative_buckets |= _buckets_for(entry["tool"], entry["op"])

        # Score against known attack chains
        best_score = 0.0
        best_chain: Optional[str] = None
        for chain_name, required, chain_score in _ATTACK_CHAINS:
            if required <= cumulative_buckets:
                if chain_score > best_score:
                    best_score = chain_score
                    best_chain = chain_name

        # Fallback: generic multi-bucket drift
        if best_score < _DRIFT_THRESHOLD and len(cumulative_buckets) >= 3:
            bucket_score = min(0.70, 0.30 + 0.15 * len(cumulative_buckets))
            if bucket_score > best_score:
                best_score = bucket_score
                best_chain = "multi_bucket_drift"

        if best_score >= _DRIFT_THRESHOLD:
            logger.warning(
                "SequenceScorer: drift=%.2f chain=%s session=%s window_size=%d buckets=%s",
                best_score, best_chain, key, len(window), sorted(cumulative_buckets),
            )

        return best_score, best_chain

    def _cross_intent_key(self, tenant_id: Optional[str], agent_id: Optional[str]) -> str:
        t = tenant_id or "default"
        a = agent_id or "default"
        return f"edon:seq_xi:{t}:{a}"

    def record_cross_intent(
        self,
        tenant_id: Optional[str],
        agent_id: Optional[str],
        tool_val: str,
        op: str,
    ) -> tuple[float, Optional[str]]:
        """Record action in the cross-intent window and return drift score.

        Keyed on (tenant, agent) only — survives intent boundaries.
        Uses a 24-hour window and higher threshold than per-intent scoring.
        """
        key = self._cross_intent_key(tenant_id, agent_id)
        window = self._load_window(key)
        window.append({"tool": tool_val, "op": op, "ts": time.time()})
        if len(window) > _CROSS_INTENT_WINDOW:
            window = window[-_CROSS_INTENT_WINDOW:]

        # Persist with 24-hour TTL
        if self._redis:
            try:
                self._redis.setex(key, _CROSS_INTENT_TTL, json.dumps(window))
            except Exception:
                self._memory[key] = window
        else:
            self._memory[key] = window

        cumulative: set[str] = set()
        for entry in window:
            cumulative |= _buckets_for(entry["tool"], entry["op"])

        best_score = 0.0
        best_chain: Optional[str] = None
        for chain_name, required, chain_score in _ATTACK_CHAINS:
            if required <= cumulative and chain_score > best_score:
                best_score = chain_score
                best_chain = chain_name

        # Only flag at the higher cross-intent threshold
        if best_score >= _CROSS_INTENT_THRESHOLD:
            logger.warning(
                "SequenceScorer[cross-intent]: drift=%.2f chain=%s agent=%s/%s window=%d",
                best_score, best_chain, tenant_id, agent_id, len(window),
            )
        return best_score, best_chain

    def partial_reset(
        self,
        tenant_id: Optional[str],
        agent_id: Optional[str],
        intent_id: Optional[str],
    ) -> None:
        """Drop the oldest half of the per-intent window after a human approval.

        Clears the drift signal for an approved pattern without wiping
        all session history — subsequent novel actions still accumulate.
        """
        key = self._key(tenant_id, agent_id, intent_id)
        window = self._load_window(key)
        if len(window) > 2:
            window = window[len(window) // 2:]
        self._save_window(key, window)
        logger.debug("SequenceScorer: partial_reset key=%s remaining=%d", key, len(window))

    def reset(
        self,
        tenant_id: Optional[str],
        agent_id: Optional[str],
        intent_id: Optional[str],
    ) -> None:
        """Clear the per-intent session window (call on new intent start)."""
        key = self._key(tenant_id, agent_id, intent_id)
        if self._redis:
            try:
                self._redis.delete(key)
                return
            except Exception:
                pass
        self._memory.pop(key, None)


_scorer: Optional[SequenceScorer] = None


def get_scorer() -> SequenceScorer:
    global _scorer
    if _scorer is None:
        _scorer = SequenceScorer()
    return _scorer
