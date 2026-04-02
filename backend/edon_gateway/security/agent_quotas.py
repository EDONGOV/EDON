"""Per-agent resource quota enforcement.

Allows tenants to set custom call-rate limits and payload-size caps per agent,
overriding the global defaults from the rate limiter.

Quota configs are stored in DB preferences (key: "agent_quota:<agent_id>")
and cached in memory with a 30-second TTL.
"""

import json
import os
import time
import threading
from typing import Any, Dict, Optional, Tuple

from ..middleware.rate_limit import check_rate_limit, increment_rate_limit, DEFAULT_LIMITS

# Max bytes for action_payload (default: 1 MB)
_DEFAULT_MAX_PAYLOAD_BYTES = int(os.getenv("EDON_DEFAULT_MAX_PAYLOAD_BYTES", str(1024 * 1024)))
_QUOTA_CACHE_TTL_SEC = 30.0
_PREF_KEY_PREFIX = "agent_quota:"


class AgentQuotaConfig:
    """Resource limits for a single agent."""

    __slots__ = (
        "max_calls_per_minute",
        "max_calls_per_hour",
        "max_calls_per_day",
        "max_payload_bytes",
        "enabled",
    )

    def __init__(
        self,
        max_calls_per_minute: int = DEFAULT_LIMITS["per_minute"],
        max_calls_per_hour: int = DEFAULT_LIMITS["per_hour"],
        max_calls_per_day: int = DEFAULT_LIMITS["per_day"],
        max_payload_bytes: int = _DEFAULT_MAX_PAYLOAD_BYTES,
        enabled: bool = True,
    ) -> None:
        self.max_calls_per_minute = max_calls_per_minute
        self.max_calls_per_hour = max_calls_per_hour
        self.max_calls_per_day = max_calls_per_day
        self.max_payload_bytes = max_payload_bytes
        self.enabled = enabled

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_calls_per_minute": self.max_calls_per_minute,
            "max_calls_per_hour": self.max_calls_per_hour,
            "max_calls_per_day": self.max_calls_per_day,
            "max_payload_bytes": self.max_payload_bytes,
            "enabled": self.enabled,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "AgentQuotaConfig":
        return AgentQuotaConfig(
            max_calls_per_minute=int(d.get("max_calls_per_minute", DEFAULT_LIMITS["per_minute"])),
            max_calls_per_hour=int(d.get("max_calls_per_hour", DEFAULT_LIMITS["per_hour"])),
            max_calls_per_day=int(d.get("max_calls_per_day", DEFAULT_LIMITS["per_day"])),
            max_payload_bytes=int(d.get("max_payload_bytes", _DEFAULT_MAX_PAYLOAD_BYTES)),
            enabled=bool(d.get("enabled", True)),
        )


class AgentQuotaStore:
    """Thread-safe per-agent quota store with DB persistence and in-memory cache."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # (tenant_id, agent_id) -> (AgentQuotaConfig, expires_at)
        self._cache: Dict[Tuple[str, str], Tuple[AgentQuotaConfig, float]] = {}

    def _cache_key(self, tenant_id: Optional[str], agent_id: str) -> Tuple[str, str]:
        return (tenant_id or "default", agent_id)

    def get(self, db: Any, tenant_id: Optional[str], agent_id: str) -> AgentQuotaConfig:
        """Get quota config for agent. Returns defaults if not configured."""
        key = self._cache_key(tenant_id, agent_id)
        now = time.time()

        with self._lock:
            cached = self._cache.get(key)
            if cached and cached[1] > now:
                return cached[0]

        # Load from DB
        config = AgentQuotaConfig()
        if db is not None and tenant_id:
            try:
                pref_key = f"{_PREF_KEY_PREFIX}{agent_id}"
                prefs = db.read_preferences(tenant_id, keys=[pref_key])
                raw = prefs.get(pref_key)
                if raw:
                    data = json.loads(raw) if isinstance(raw, str) else raw
                    config = AgentQuotaConfig.from_dict(data)
            except Exception:
                pass

        with self._lock:
            self._cache[key] = (config, now + _QUOTA_CACHE_TTL_SEC)

        return config

    def set(self, db: Any, tenant_id: str, agent_id: str, quota: AgentQuotaConfig) -> None:
        """Persist quota config for agent."""
        pref_key = f"{_PREF_KEY_PREFIX}{agent_id}"
        db.write_preference(tenant_id, pref_key, json.dumps(quota.to_dict()))
        key = self._cache_key(tenant_id, agent_id)
        with self._lock:
            self._cache[key] = (quota, time.time() + _QUOTA_CACHE_TTL_SEC)

    def delete(self, db: Any, tenant_id: str, agent_id: str) -> None:
        """Remove custom quota config (reverts to defaults)."""
        pref_key = f"{_PREF_KEY_PREFIX}{agent_id}"
        try:
            db.write_preference(tenant_id, pref_key, "")
        except Exception:
            pass
        key = self._cache_key(tenant_id, agent_id)
        with self._lock:
            self._cache.pop(key, None)


_store: Optional[AgentQuotaStore] = None


def get_quota_store() -> AgentQuotaStore:
    global _store
    if _store is None:
        _store = AgentQuotaStore()
    return _store


def check_agent_quota(
    db: Any,
    tenant_id: Optional[str],
    agent_id: str,
    payload_bytes: int = 0,
) -> Tuple[bool, Optional[str]]:
    """Check per-agent quotas: payload size + custom call-rate limits.

    Returns (allowed, error_message). error_message is None if allowed.
    """
    quota = get_quota_store().get(db, tenant_id, agent_id)
    if not quota.enabled:
        return True, None

    # Payload size check
    if payload_bytes > quota.max_payload_bytes:
        return False, (
            f"Payload size {payload_bytes} bytes exceeds agent quota "
            f"({quota.max_payload_bytes} bytes max)"
        )

    # Call-rate check using existing rate limiter infrastructure
    custom_limits = {
        "per_minute": quota.max_calls_per_minute,
        "per_hour": quota.max_calls_per_hour,
        "per_day": quota.max_calls_per_day,
    }
    rate_key = f"quota:{tenant_id or 'default'}:{agent_id}"
    allowed, msg = check_rate_limit(rate_key, custom_limits)
    return allowed, msg


def record_agent_call(tenant_id: Optional[str], agent_id: str) -> None:
    """Increment call counters for agent quota tracking."""
    rate_key = f"quota:{tenant_id or 'default'}:{agent_id}"
    try:
        increment_rate_limit(rate_key)
    except Exception:
        pass
