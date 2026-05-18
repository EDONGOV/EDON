"""
CAV Engine client — fetches operator cognitive state and robot stability signals.
Used as a governance signal in the governor decision flow.
Fails open: if CAV is unreachable, governance continues without it.
"""

import logging
import threading
import time
from typing import Optional

import requests

from .config import config

logger = logging.getLogger(__name__)

_OPERATOR_CACHE_TTL = 30  # seconds
_ROBOT_CACHE_TTL = 5      # seconds
_REQUEST_TIMEOUT = 2      # seconds


class CAVClient:
    """Client for the CAV (Cognitive/Autonomy Verification) Engine.

    Thread-safe in-memory cache with per-resource TTLs:
      - operator state: 30 s
      - robot stability: 5 s

    All network calls fail open — if CAV is unreachable, ``None`` is returned
    and governance continues normally.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Cache entries: { cache_key: (value, expires_at_float) }
        self._cache: dict = {}

    # ──────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────

    def _cache_get(self, key: str) -> Optional[dict]:
        """Return cached value if it exists and has not expired."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if time.monotonic() > expires_at:
                del self._cache[key]
                return None
            return value

    def _cache_set(self, key: str, value: dict, ttl: float) -> None:
        """Store a value in the cache with the given TTL (seconds)."""
        with self._lock:
            self._cache[key] = (value, time.monotonic() + ttl)

    def _cache_invalidate(self, key: str) -> None:
        """Remove a single entry from the cache."""
        with self._lock:
            self._cache.pop(key, None)

    def _cav_get(self, url: str) -> Optional[dict]:
        """Perform a GET against CAV and return parsed JSON, or None on any error."""
        if not config.CAV_ENABLED:
            return None
        try:
            resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.debug("CAV GET %s failed (fail-open): %s", url, exc)
            return None

    def _cav_post(self, url: str, payload: dict) -> bool:
        """Perform a POST against CAV and return True on 2xx, False otherwise."""
        if not config.CAV_ENABLED:
            return False
        try:
            resp = requests.post(url, json=payload, timeout=_REQUEST_TIMEOUT)
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.debug("CAV POST %s failed (fail-open): %s", url, exc)
            return False

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    def get_operator_state(self, operator_id: str) -> Optional[dict]:
        """Fetch the cognitive state for an operator.

        Returns a dict with keys ``cav_score`` (int), ``cav_state`` (str),
        and ``z_score`` (float), or ``None`` if CAV is unavailable or disabled.

        Result is cached for 30 seconds per operator_id.

        Args:
            operator_id: Unique identifier for the human operator.

        Returns:
            Operator state dict or None.
        """
        cache_key = f"operator_state:{operator_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        url = f"{config.CAV_URL}/v1/state/{operator_id}"
        data = self._cav_get(url)
        if data is not None:
            self._cache_set(cache_key, data, _OPERATOR_CACHE_TTL)
        return data

    def get_robot_stability(self, robot_id: str) -> Optional[dict]:
        """Fetch the stability signal for an autonomous robot or vehicle.

        Returns a dict with keys ``stable`` (bool), ``stability_score`` (float),
        and ``warning`` (str), or ``None`` if CAV is unavailable or disabled.

        Result is cached for 5 seconds per robot_id (robot state changes fast).

        Args:
            robot_id: Unique identifier for the robot / autonomous system.

        Returns:
            Robot stability dict or None.
        """
        cache_key = f"robot_stability:{robot_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        url = f"{config.CAV_URL}/v1/robot/{robot_id}/stability"
        data = self._cav_get(url)
        if data is not None:
            self._cache_set(cache_key, data, _ROBOT_CACHE_TTL)
        return data

    def get_humanoid_stability(self, robot_id: str) -> Optional[dict]:
        """Fetch rich stability telemetry for a humanoid robot.

        Returns a dict with keys:
          stable (bool), stability_score (float 0-1),
          balance_margin (float — how far CoM is from tipping, metres),
          payload_kg (float — current payload),
          payload_limit_kg (float — max allowed payload),
          terrain_confidence (float 0-1 — how well terrain is understood),
          center_of_mass_offset (float — CoM offset from nominal, metres),
          joint_torques (dict[str, float] — per-joint Nm readings),
          warning (str — human-readable safety note if any).

        Falls back to basic ``get_robot_stability`` if the CAV endpoint is not
        available (older CAV versions).  Result cached for 5 seconds.

        Args:
            robot_id: Unique identifier for the humanoid robot.

        Returns:
            Humanoid stability dict or None.
        """
        cache_key = f"humanoid_stability:{robot_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        url = f"{config.CAV_URL}/v1/humanoid/{robot_id}/stability"
        data = self._cav_get(url)
        if data is not None:
            self._cache_set(cache_key, data, _ROBOT_CACHE_TTL)
            return data

        # Fallback: basic robot stability endpoint (older CAV versions)
        basic = self.get_robot_stability(robot_id)
        if basic is not None:
            # Normalise to the richer schema so callers don't need to branch
            normalised = {
                "stable": basic.get("stable", True),
                "stability_score": basic.get("stability_score", 1.0),
                "balance_margin": None,
                "payload_kg": None,
                "payload_limit_kg": None,
                "terrain_confidence": None,
                "center_of_mass_offset": None,
                "joint_torques": {},
                "warning": basic.get("warning", ""),
            }
            self._cache_set(cache_key, normalised, _ROBOT_CACHE_TTL)
            return normalised
        return None

    def ingest_operator_telemetry(self, operator_id: str, payload: dict) -> bool:
        """Forward wearable telemetry for an operator to the CAV engine.

        Invalidates any cached operator state for this operator_id so the
        next governance call fetches fresh data.

        Args:
            operator_id: Unique identifier for the human operator.
            payload: Telemetry payload dict (EDA, BVP, TEMP, ACC_*, etc.).

        Returns:
            True if CAV accepted the data (HTTP 2xx), False otherwise.
        """
        url = f"{config.CAV_URL}/v1/telemetry/operator/{operator_id}"
        success = self._cav_post(url, payload)
        if success:
            # Invalidate stale operator state so next evaluate() fetches fresh data
            self._cache_invalidate(f"operator_state:{operator_id}")
        return success


# Module-level singleton used throughout the gateway
cav_client = CAVClient()
