"""Self-healing rule canary deployment — safe rollout with automatic rollback.

When self-healing deploys a new governance rule, it can be deployed in canary
mode: applied to only `fraction` of requests (default 10%) while the watchdog
monitors the block rate. If the block rate under the canary rule exceeds the
baseline by more than `rollback_multiplier` (default 2.0x), the rule is
automatically disabled and an alert fires.

Canary lifecycle:
  CANARY → (block_rate OK for `graduation_window_s`) → GRADUATED (applied 100%)
  CANARY → (block_rate too high)                     → ROLLED_BACK (rule disabled)

The governor calls `should_apply_canary(rule_id)` to decide whether to include
a canary rule in the evaluation for a given request. The outcome is recorded
via `record_canary_outcome(rule_id, blocked)`.
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from ..logging_config import get_logger

logger = get_logger(__name__)

# ── Defaults ───────────────────────────────────────────────────────────────────
DEFAULT_FRACTION       = 0.10   # 10% of requests use the canary rule
DEFAULT_ROLLBACK_MUL   = 2.0    # rollback if block rate >= 2x baseline
DEFAULT_MIN_SAMPLES    = 50     # don't evaluate until at least this many samples
DEFAULT_GRADUATION_S   = 300    # graduate after 5 min of healthy block rate
DEFAULT_BASELINE_RATE  = 0.05   # fallback assumed baseline if no real data (5%)


class CanaryStatus(str, Enum):
    CANARY      = "canary"
    GRADUATED   = "graduated"
    ROLLED_BACK = "rolled_back"


@dataclass
class CanaryState:
    rule_id: str
    tenant_id: str
    fraction: float = DEFAULT_FRACTION
    rollback_multiplier: float = DEFAULT_ROLLBACK_MUL
    min_samples: int = DEFAULT_MIN_SAMPLES
    graduation_window_s: float = DEFAULT_GRADUATION_S
    baseline_block_rate: float = DEFAULT_BASELINE_RATE
    status: CanaryStatus = CanaryStatus.CANARY
    created_at: float = field(default_factory=time.monotonic)
    # Counters
    total_evaluated: int = 0
    total_blocked: int = 0
    healthy_since: Optional[float] = None  # monotonic time when block rate went healthy

    @property
    def block_rate(self) -> float:
        if self.total_evaluated == 0:
            return 0.0
        return self.total_blocked / self.total_evaluated

    @property
    def is_active(self) -> bool:
        return self.status == CanaryStatus.CANARY

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "tenant_id": self.tenant_id,
            "status": self.status.value,
            "fraction": self.fraction,
            "total_evaluated": self.total_evaluated,
            "total_blocked": self.total_blocked,
            "block_rate": round(self.block_rate, 4),
            "baseline_block_rate": self.baseline_block_rate,
            "rollback_multiplier": self.rollback_multiplier,
            "age_s": round(time.monotonic() - self.created_at, 1),
        }


_lock = threading.Lock()
_canaries: dict[str, CanaryState] = {}  # rule_id → CanaryState
_watchdog_thread: Optional[threading.Thread] = None
_watchdog_running = False


# ── Public API ─────────────────────────────────────────────────────────────────

def register_canary(
    rule_id: str,
    tenant_id: str,
    fraction: float = DEFAULT_FRACTION,
    rollback_multiplier: float = DEFAULT_ROLLBACK_MUL,
    baseline_block_rate: float = DEFAULT_BASELINE_RATE,
) -> CanaryState:
    """Register a newly deployed rule for canary monitoring."""
    state = CanaryState(
        rule_id=rule_id,
        tenant_id=tenant_id,
        fraction=max(0.01, min(1.0, fraction)),
        rollback_multiplier=rollback_multiplier,
        baseline_block_rate=baseline_block_rate,
    )
    with _lock:
        _canaries[rule_id] = state
    logger.info(
        "[canary] registered rule=%s tenant=%s fraction=%.0f%%",
        rule_id, tenant_id, fraction * 100,
    )
    _ensure_watchdog()
    return state


def should_apply_canary(rule_id: str) -> bool:
    """Return True if this canary rule should be applied to the current request.

    Called by the governor for each canary rule in the tenant rule set.
    Thread-safe O(1).
    """
    with _lock:
        state = _canaries.get(rule_id)
    if state is None or not state.is_active:
        return False
    return random.random() < state.fraction


def record_canary_outcome(rule_id: str, blocked: bool) -> None:
    """Record whether the canary rule would have blocked the request."""
    with _lock:
        state = _canaries.get(rule_id)
        if state is None or not state.is_active:
            return
        state.total_evaluated += 1
        if blocked:
            state.total_blocked += 1


def get_canary(rule_id: str) -> Optional[CanaryState]:
    with _lock:
        return _canaries.get(rule_id)


def list_canaries(tenant_id: Optional[str] = None) -> list[dict]:
    with _lock:
        states = list(_canaries.values())
    if tenant_id:
        states = [s for s in states if s.tenant_id == tenant_id]
    return [s.to_dict() for s in states]


def graduate_canary(rule_id: str) -> bool:
    """Manually graduate a canary to full deployment."""
    with _lock:
        state = _canaries.get(rule_id)
        if state and state.is_active:
            state.status = CanaryStatus.GRADUATED
            logger.info("[canary] graduated rule=%s", rule_id)
            return True
    return False


# ── Watchdog ───────────────────────────────────────────────────────────────────

def _ensure_watchdog() -> None:
    global _watchdog_thread, _watchdog_running
    if _watchdog_running and _watchdog_thread and _watchdog_thread.is_alive():
        return
    _watchdog_running = True
    _watchdog_thread = threading.Thread(
        target=_watchdog_loop, daemon=True, name="edon-canary-watchdog"
    )
    _watchdog_thread.start()


def _watchdog_loop() -> None:
    while _watchdog_running:
        try:
            _check_canaries()
        except Exception as exc:
            logger.debug("[canary] watchdog error: %s", exc)
        time.sleep(30)


def _check_canaries() -> None:
    now = time.monotonic()
    with _lock:
        active = [s for s in _canaries.values() if s.is_active]

    for state in active:
        if state.total_evaluated < state.min_samples:
            continue

        rollback_threshold = state.baseline_block_rate * state.rollback_multiplier

        if state.block_rate >= rollback_threshold:
            _rollback(state)
        else:
            # Block rate is healthy — track graduation window
            if state.healthy_since is None:
                with _lock:
                    state.healthy_since = now
            elif now - state.healthy_since >= state.graduation_window_s:
                with _lock:
                    state.status = CanaryStatus.GRADUATED
                logger.info(
                    "[canary] GRADUATED rule=%s block_rate=%.1f%% (baseline=%.1f%%)",
                    state.rule_id, state.block_rate * 100, state.baseline_block_rate * 100,
                )


def _rollback(state: CanaryState) -> None:
    """Disable the rule and fire an alert."""
    with _lock:
        state.status = CanaryStatus.ROLLED_BACK

    logger.warning(
        "[canary] ROLLBACK rule=%s block_rate=%.1f%% threshold=%.1f%% samples=%d",
        state.rule_id,
        state.block_rate * 100,
        state.baseline_block_rate * state.rollback_multiplier * 100,
        state.total_evaluated,
    )

    # Disable the rule in the DB
    try:
        from ..persistence import get_db
        db = get_db()
        db.update_policy_rule(state.rule_id, state.tenant_id, enabled=False)
        logger.warning("[canary] rule=%s disabled in DB", state.rule_id)
    except Exception as exc:
        logger.warning("[canary] could not disable rule in DB: %s", exc)

    # Fire alert
    try:
        from ..alerts.dispatcher import _dispatch
        _dispatch("healing.canary_rollback", {
            "rule_id": state.rule_id,
            "tenant_id": state.tenant_id,
            "block_rate": round(state.block_rate, 4),
            "baseline": state.baseline_block_rate,
            "samples": state.total_evaluated,
            "message": (
                f"Auto-hardening rule '{state.rule_id}' rolled back: "
                f"block rate {state.block_rate:.1%} exceeded "
                f"{state.rollback_multiplier}x baseline ({state.baseline_block_rate:.1%})."
            ),
        })
    except Exception:
        pass
