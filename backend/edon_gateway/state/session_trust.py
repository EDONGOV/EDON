"""Per-session agent trust scoring.

Tracks a rolling trust score per (tenant_id, agent_id, intent_id) triple.
Approved actions increase trust; blocks and escalations decrease it.
The governor applies the trust multiplier to risk thresholds so agents that
drift from declared intent are progressively restricted — not just event-checked.

Score range: 0.0 (fully untrusted) to 1.0 (fully trusted).
New sessions start at INITIAL_TRUST.

Storage: Redis sorted set when available, in-memory dict fallback.
Keys are namespaced as: edon:trust:<tenant>:<agent>:<intent>
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

_INITIAL_TRUST: float = float(os.getenv("EDON_SESSION_INITIAL_TRUST", "0.8"))
_ALLOW_DELTA: float = 0.02
_BLOCK_MISALIGN_DELTA: float = 0.08    # BLOCK with INTENT_MISMATCH or SCOPE_VIOLATION
_BLOCK_OTHER_DELTA: float = 0.02       # BLOCK for other reasons (rate limit, work hours) — minor
_ESCALATE_APPROVED_DELTA: float = 0.01  # ESCALATE resolved to ALLOW → slight trust gain
_MIN_TRUST: float = 0.20
_MAX_TRUST: float = 1.0
_TTL_SECONDS: int = 3600 * 8  # 8-hour session window

# Reason codes that represent confirmed intent/scope misalignment
_MISALIGN_REASON_CODES = frozenset(["INTENT_MISMATCH", "SCOPE_VIOLATION", "DATA_EXFIL"])

_REDIS_URL = (os.getenv("REDIS_URL") or os.getenv("EDON_REDIS_URL", "")).strip()

# Threshold below which risk escalation tier is tightened
RESTRICT_THRESHOLD: float = float(os.getenv("EDON_TRUST_RESTRICT_THRESHOLD", "0.55"))


class SessionTrustStore:
    """Thread-safe trust store backed by Redis or in-memory fallback."""

    def __init__(self, redis_url: Optional[str] = None):
        self._redis = None
        # In-memory fallback: maps key → (score, stored_at_timestamp)
        self._memory: dict[str, tuple[float, float]] = {}
        url = redis_url or _REDIS_URL
        if url:
            try:
                import redis as _r
                client = _r.from_url(url, socket_connect_timeout=1, socket_timeout=1, decode_responses=True)
                client.ping()
                self._redis = client
            except Exception as exc:
                logger.debug("SessionTrustStore: Redis unavailable (%s), using in-memory", exc)

    def _key(self, tenant_id: Optional[str], agent_id: Optional[str], intent_id: Optional[str]) -> str:
        t = tenant_id or "default"
        a = agent_id or "default"
        i = intent_id or "default"
        return f"edon:trust:{t}:{a}:{i}"

    def _evict_expired(self) -> None:
        """Remove in-memory entries older than _TTL_SECONDS."""
        cutoff = time.time() - _TTL_SECONDS
        expired = [k for k, (_, ts) in self._memory.items() if ts < cutoff]
        for k in expired:
            del self._memory[k]

    def get(self, tenant_id: Optional[str], agent_id: Optional[str], intent_id: Optional[str]) -> float:
        key = self._key(tenant_id, agent_id, intent_id)
        if self._redis:
            try:
                val = self._redis.get(key)
                if val is not None:
                    return max(_MIN_TRUST, min(_MAX_TRUST, float(val)))
            except Exception:
                pass
        self._evict_expired()
        entry = self._memory.get(key)
        return entry[0] if entry is not None else _INITIAL_TRUST

    def _set(self, key: str, score: float) -> None:
        score = max(_MIN_TRUST, min(_MAX_TRUST, score))
        if self._redis:
            try:
                self._redis.setex(key, _TTL_SECONDS, str(score))
                return
            except Exception:
                pass
        self._evict_expired()
        self._memory[key] = (score, time.time())

    def record_verdict(
        self,
        tenant_id: Optional[str],
        agent_id: Optional[str],
        intent_id: Optional[str],
        verdict: str,
        reason_code: Optional[str] = None,
        escalation_resolved_allow: bool = False,
    ) -> float:
        """Update trust score based on verdict and reason code. Returns new score.

        Deduction rules:
        - BLOCK + INTENT_MISMATCH / SCOPE_VIOLATION / DATA_EXFIL → full deduction
          (confirmed the agent tried to do something outside its mandate)
        - BLOCK for other reasons (rate limit, work hours, loop, risk) → minor deduction
          (the system stopped it for policy, not necessarily bad intent)
        - ESCALATE → no deduction; if it resolved to ALLOW, slight trust increase
        - ALLOW → small trust increase
        """
        key = self._key(tenant_id, agent_id, intent_id)
        current = self.get(tenant_id, agent_id, intent_id)
        verdict_upper = (verdict or "").upper()
        reason_upper = (reason_code or "").upper()

        if verdict_upper == "ALLOW":
            delta = _ALLOW_DELTA
        elif verdict_upper == "BLOCK":
            if reason_upper in _MISALIGN_REASON_CODES:
                delta = -_BLOCK_MISALIGN_DELTA
            else:
                delta = -_BLOCK_OTHER_DELTA
        elif verdict_upper == "ESCALATE":
            # No deduction for escalations — they are expected for high-risk authorized ops.
            # If the escalation resolved to ALLOW, reward slightly.
            delta = _ESCALATE_APPROVED_DELTA if escalation_resolved_allow else 0.0
        elif verdict_upper == "PAUSE":
            # Rate limit / loop — minor, infrastructure-level pause not agent misbehavior
            delta = -_BLOCK_OTHER_DELTA
        else:
            delta = 0.0

        new_score = current + delta
        self._set(key, new_score)
        logger.debug(
            "SessionTrust: verdict=%s reason=%s delta=%+.3f score %.2f→%.2f key=%s",
            verdict_upper, reason_upper, delta, current, new_score, key,
        )
        return max(_MIN_TRUST, min(_MAX_TRUST, new_score))

    def get_trust_multiplier(
        self,
        tenant_id: Optional[str],
        agent_id: Optional[str],
        intent_id: Optional[str],
    ) -> float:
        """Return 0.5–1.0 multiplier. Below RESTRICT_THRESHOLD, returns < 1.0 to tighten gates."""
        score = self.get(tenant_id, agent_id, intent_id)
        if score >= RESTRICT_THRESHOLD:
            return 1.0
        # Linear interpolation: [MIN_TRUST, RESTRICT_THRESHOLD] → [0.5, 1.0]
        span = RESTRICT_THRESHOLD - _MIN_TRUST
        if span <= 0:
            return 0.5
        return 0.5 + 0.5 * ((score - _MIN_TRUST) / span)


# Singleton used by governor — lazy-initialized to avoid import-time side effects
_store: Optional[SessionTrustStore] = None


def get_store() -> SessionTrustStore:
    global _store
    if _store is None:
        _store = SessionTrustStore()
    return _store
