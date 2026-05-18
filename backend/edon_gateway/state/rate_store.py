"""Redis-backed sliding-window state for rate limiting and loop detection.

Uses Redis sorted sets: score = unix timestamp (float), member = unique event ID.
ZADD + ZREMRANGEBYSCORE + ZCARD gives an O(log N) exact sliding window.

Falls back to in-memory dict-of-lists if Redis is unavailable, which is
correct for single-replica deployments but resets on restart and doesn't
cross replicas.
"""
import os
import time
import uuid
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_REDIS_URL = (os.getenv("REDIS_URL") or os.getenv("EDON_REDIS_URL", "")).strip()


_EVICT_INTERVAL = 1000   # sweep stale in-memory keys every N writes
_MAX_KEY_AGE = 7200.0    # keys whose newest entry is older than this are dropped


class RateStore:
    """Sliding-window event store backed by Redis (or in-memory fallback).

    All public methods are synchronous; call them from the governor's
    synchronous evaluation path without an event loop.
    """

    def __init__(self, redis_url: Optional[str] = None):
        self._redis = None
        self._memory: dict = {}  # key -> [(timestamp_float, member_str)]
        self._write_count: int = 0
        url = redis_url or _REDIS_URL
        if url:
            try:
                import redis as _redis_lib
                client = _redis_lib.from_url(
                    url,
                    socket_connect_timeout=1,
                    socket_timeout=1,
                    decode_responses=True,
                )
                client.ping()
                self._redis = client
                logger.info("RateStore: connected to Redis")
            except Exception as exc:
                logger.warning("RateStore: Redis unavailable (%s) — using in-memory fallback", exc)

    @property
    def backend(self) -> str:
        return "redis" if self._redis else "memory"

    # ── core primitive ────────────────────────────────────────────────────────

    def add_and_count(self, key: str, window_seconds: float) -> int:
        """Add one event to the sliding window and return the window count (including this event)."""
        now = time.time()
        cutoff = now - window_seconds
        member = str(uuid.uuid4())
        if self._redis:
            try:
                pipe = self._redis.pipeline()
                pipe.zadd(key, {member: now})
                pipe.zremrangebyscore(key, "-inf", cutoff)
                pipe.zcard(key)
                pipe.expire(key, int(window_seconds) + 60)
                results = pipe.execute()
                return int(results[2])
            except Exception as exc:
                logger.warning("RateStore Redis write error (%s) — falling back to memory", exc)
        # In-memory path
        entries = self._memory.get(key, [])
        entries = [(ts, m) for ts, m in entries if ts > cutoff]
        entries.append((now, member))
        self._memory[key] = entries
        self._write_count += 1
        if self._write_count % _EVICT_INTERVAL == 0:
            self._evict_stale_keys()
        return len(entries)

    def count_in_window(self, key: str, window_seconds: float) -> int:
        """Return count of events in the sliding window without adding."""
        now = time.time()
        cutoff = now - window_seconds
        if self._redis:
            try:
                self._redis.zremrangebyscore(key, "-inf", cutoff)
                return int(self._redis.zcard(key))
            except Exception as exc:
                logger.warning("RateStore Redis read error (%s) — falling back to memory", exc)
        entries = self._memory.get(key, [])
        return sum(1 for ts, _ in entries if ts > cutoff)

    def _evict_stale_keys(self) -> None:
        """Remove in-memory keys whose newest entry is older than _MAX_KEY_AGE."""
        cutoff = time.time() - _MAX_KEY_AGE
        stale = [k for k, entries in self._memory.items()
                 if not entries or entries[-1][0] < cutoff]
        for k in stale:
            del self._memory[k]

    # ── key builders ─────────────────────────────────────────────────────────

    @staticmethod
    def rate_key(tenant_id: Optional[str], agent_id: Optional[str]) -> str:
        t = tenant_id or "default"
        a = agent_id or "default"
        return f"edon:rate:{t}:{a}"

    @staticmethod
    def loop_key(
        tenant_id: Optional[str],
        agent_id: Optional[str],
        tool: str,
        op: str,
        params_hash: str,
    ) -> str:
        t = tenant_id or "default"
        a = agent_id or "default"
        # Truncate params_hash to keep key length sane
        ph = params_hash[:24]
        return f"edon:loop:{t}:{a}:{tool}:{op}:{ph}"

    @staticmethod
    def intent_rate_key(tenant_id: Optional[str], intent_id: Optional[str]) -> str:
        """Shared budget key across ALL agents operating under the same intent.

        Used by the governor to enforce a cross-agent action cap so that a
        swarm cannot collectively exceed the intent's action budget even if
        individual per-agent rate limits are not yet hit.

        tenant_id is required in the key — without it, two tenants sharing an
        intent_id name (e.g. "default") would consume from the same rate bucket.
        """
        t = tenant_id or "default"
        i = intent_id or "default"
        return f"edon:intent_rate:{t}:{i}"
