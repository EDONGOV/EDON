"""Swarm-level collective action policy coordinator.

Evaluates whether an individual agent's action is permitted given the
collective state of its swarm.  Policies include:

  - **Action budgets**: max N actions of type X per minute across all swarm members.
  - **Quorum rules**: M of N members must submit the same action before it executes.
  - **Dosage caps**: total payload delivered by the swarm cannot exceed a limit
    within a rolling time window (critical for nanobot drug delivery).

All persistent state is in the DB (swarm_action_log).  The decision logic
runs in Python so it stays fast and testable without a running HTTP server.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class SwarmEvalContext:
    """Input to SwarmCoordinator.evaluate()."""
    swarm_id: str
    agent_id: str
    action_type: str           # "tool.op" e.g. "drone.spray"
    payload: Dict[str, Any]
    timestamp: str             # ISO-8601


@dataclass
class SwarmVerdict:
    """Result from SwarmCoordinator.evaluate()."""
    verdict: str               # ALLOW | BLOCK | ESCALATE | QUORUM_PENDING
    reason: str
    quorum_votes: int = 0
    quorum_required: int = 0
    budget_remaining: Optional[int] = None
    dosage_remaining: Optional[float] = None


class SwarmCoordinator:
    """Collective-action policy evaluator for a named swarm.

    One instance is created per request; all persistent state lives in the DB.

    Usage::

        coord = SwarmCoordinator(db)
        verdict = coord.evaluate(SwarmEvalContext(
            swarm_id="swarm-001",
            agent_id="nanobot-42",
            action_type="drone.spray",
            payload={"volume_ml": 25.0},
            timestamp=datetime.now(UTC).isoformat(),
        ))
    """

    def __init__(self, db) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self, ctx: SwarmEvalContext) -> SwarmVerdict:
        """Evaluate *ctx* against swarm-level policies stored in the DB."""
        policy = self._load_policy(ctx.swarm_id)

        # 1. Action budgets
        budget_rules: Dict[str, Dict] = policy.get("action_budgets", {})
        if ctx.action_type in budget_rules:
            rule = budget_rules[ctx.action_type]
            max_per_min = int(rule.get("max_per_minute", 0))
            within, remaining = self._check_budget(ctx.swarm_id, ctx.action_type, max_per_min, 60)
            if not within:
                self._record(ctx, "BLOCK")
                return SwarmVerdict(
                    verdict="BLOCK",
                    reason=f"Swarm budget exhausted: max {max_per_min}/min for '{ctx.action_type}'",
                    budget_remaining=0,
                )

        # 2. Quorum rules
        quorum_rules: Dict[str, Dict] = policy.get("quorum_rules", {})
        if ctx.action_type in quorum_rules:
            qrule = quorum_rules[ctx.action_type]
            required = int(qrule.get("required_votes", 2))
            ttl = int(qrule.get("ttl_seconds", 30))
            met, votes = self._check_quorum(ctx.swarm_id, ctx.action_type, required, ttl)
            if not met:
                # Record the pending vote (don't block permanently — it may reach quorum)
                self._record(ctx, "QUORUM_PENDING")
                return SwarmVerdict(
                    verdict="QUORUM_PENDING",
                    reason=f"Quorum not reached: {votes}/{required} votes for '{ctx.action_type}'",
                    quorum_votes=votes,
                    quorum_required=required,
                )

        # 3. Dosage caps
        dosage_rules: Dict[str, Dict] = policy.get("dosage_caps", {})
        if ctx.action_type in dosage_rules:
            drule = dosage_rules[ctx.action_type]
            max_amount = float(drule.get("max_amount_per_hour", 0.0))
            amount_field = drule.get("amount_field", "amount")
            window_sec = int(drule.get("window_seconds", 3600))
            within, remaining = self._check_dosage(
                ctx.swarm_id, ctx.action_type, ctx.payload,
                max_amount, amount_field, window_sec,
            )
            if not within:
                self._record(ctx, "BLOCK")
                return SwarmVerdict(
                    verdict="BLOCK",
                    reason=(
                        f"Swarm dosage cap reached: max {max_amount} "
                        f"'{amount_field}' per {window_sec}s for '{ctx.action_type}'"
                    ),
                    dosage_remaining=0.0,
                )

        # 4. All checks passed — record before querying remaining so dosage_remaining is accurate
        self._record(ctx, "ALLOW")
        budget_rem = self._budget_remaining(ctx.swarm_id, ctx.action_type, budget_rules, 60)
        dosage_rem = self._dosage_remaining(ctx.swarm_id, ctx.action_type, dosage_rules)
        return SwarmVerdict(
            verdict="ALLOW",
            reason="Action passes all swarm-level policies.",
            budget_remaining=budget_rem,
            dosage_remaining=dosage_rem,
        )

    def get_swarm_state(self, swarm_id: str, tenant_id: str) -> Dict[str, Any]:
        """Return real-time swarm state: members, action counts, dosage consumed."""
        with self._db._get_connection() as conn:
            # Member count
            row = conn.execute(
                "SELECT COUNT(*) FROM swarm_members WHERE swarm_id = ?", (swarm_id,)
            ).fetchone()
            member_count = row[0] if row else 0

            # Action counts (last 60s)
            rows = conn.execute(
                """
                SELECT action_type, verdict, COUNT(*) as cnt
                FROM swarm_action_log
                WHERE swarm_id = ?
                  AND timestamp >= datetime('now', '-60 seconds')
                GROUP BY action_type, verdict
                """,
                (swarm_id,),
            ).fetchall()
            action_counts: Dict[str, Dict[str, int]] = {}
            for r in rows:
                at = r[0]
                if at not in action_counts:
                    action_counts[at] = {}
                action_counts[at][r[1]] = r[2]

            # Dosage consumed (last 1h)
            dosage_rows = conn.execute(
                """
                SELECT action_type, SUM(amount) as total
                FROM swarm_action_log
                WHERE swarm_id = ?
                  AND timestamp >= datetime('now', '-3600 seconds')
                  AND amount IS NOT NULL
                GROUP BY action_type
                """,
                (swarm_id,),
            ).fetchall()
            dosage_consumed = {r[0]: r[1] for r in dosage_rows}

            # Pending quorum proposals
            pending_rows = conn.execute(
                """
                SELECT action_type, COUNT(*) as votes
                FROM swarm_action_log
                WHERE swarm_id = ?
                  AND verdict = 'QUORUM_PENDING'
                  AND timestamp >= datetime('now', '-60 seconds')
                GROUP BY action_type
                """,
                (swarm_id,),
            ).fetchall()
            pending_quorum = {r[0]: r[1] for r in pending_rows}

        return {
            "swarm_id": swarm_id,
            "member_count": member_count,
            "action_counts_last_60s": action_counts,
            "dosage_consumed_last_1h": dosage_consumed,
            "pending_quorum": pending_quorum,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_policy(self, swarm_id: str) -> Dict[str, Any]:
        with self._db._get_connection() as conn:
            row = conn.execute(
                "SELECT policy_json FROM swarms WHERE id = ?", (swarm_id,)
            ).fetchone()
        if row is None:
            return {}
        try:
            return json.loads(row[0]) if row[0] else {}
        except json.JSONDecodeError:
            return {}

    def _check_budget(
        self, swarm_id: str, action_type: str, max_per_min: int, window_sec: int
    ) -> Tuple[bool, int]:
        """Return (within_budget, remaining)."""
        with self._db._get_connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM swarm_action_log
                WHERE swarm_id = ? AND action_type = ?
                  AND verdict NOT IN ('BLOCK')
                  AND timestamp >= datetime('now', ? || ' seconds')
                """,
                (swarm_id, action_type, f"-{window_sec}"),
            ).fetchone()
        used = row[0] if row else 0
        remaining = max(0, max_per_min - used)
        return remaining > 0, remaining

    def _budget_remaining(
        self,
        swarm_id: str,
        action_type: str,
        budget_rules: Dict[str, Dict],
        window_sec: int,
    ) -> Optional[int]:
        if action_type not in budget_rules:
            return None
        max_per_min = int(budget_rules[action_type].get("max_per_minute", 0))
        _, remaining = self._check_budget(swarm_id, action_type, max_per_min, window_sec)
        return remaining

    def _check_quorum(
        self, swarm_id: str, action_type: str, required: int, ttl_seconds: int
    ) -> Tuple[bool, int]:
        """Return (quorum_met, current_vote_count).

        A 'vote' is any QUORUM_PENDING entry for this (swarm_id, action_type)
        within the TTL window.  Once quorum is met we count the current pending
        votes and consider it met.
        """
        with self._db._get_connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM swarm_action_log
                WHERE swarm_id = ? AND action_type = ? AND verdict = 'QUORUM_PENDING'
                  AND timestamp >= datetime('now', ? || ' seconds')
                """,
                (swarm_id, action_type, f"-{ttl_seconds}"),
            ).fetchone()
        votes = (row[0] if row else 0) + 1  # +1 for the current incoming vote
        return votes >= required, votes

    def _check_dosage(
        self,
        swarm_id: str,
        action_type: str,
        payload: Dict[str, Any],
        max_amount: float,
        amount_field: str,
        window_sec: int,
    ) -> Tuple[bool, float]:
        """Return (within_cap, remaining_capacity)."""
        with self._db._get_connection() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(amount), 0.0) FROM swarm_action_log
                WHERE swarm_id = ? AND action_type = ?
                  AND timestamp >= datetime('now', ? || ' seconds')
                  AND amount IS NOT NULL
                """,
                (swarm_id, action_type, f"-{window_sec}"),
            ).fetchone()
        consumed = row[0] if row else 0.0
        this_amount = float(payload.get(amount_field, 0.0))
        remaining = max(0.0, max_amount - consumed - this_amount)
        return (consumed + this_amount) <= max_amount, remaining

    def _dosage_remaining(
        self,
        swarm_id: str,
        action_type: str,
        dosage_rules: Dict[str, Dict],
    ) -> Optional[float]:
        if action_type not in dosage_rules:
            return None
        drule = dosage_rules[action_type]
        max_amount = float(drule.get("max_amount_per_hour", 0.0))
        amount_field = drule.get("amount_field", "amount")
        window_sec = int(drule.get("window_seconds", 3600))
        _, remaining = self._check_dosage(
            swarm_id, action_type, {}, max_amount, amount_field, window_sec
        )
        return remaining

    def _record(self, ctx: SwarmEvalContext, verdict: str) -> None:
        """Insert into swarm_action_log for budget/dosage accounting."""
        amount_val: Optional[float] = None
        for key in ("amount", "volume_ml", "dose_mg", "quantity"):
            if key in ctx.payload:
                try:
                    amount_val = float(ctx.payload[key])
                    break
                except (TypeError, ValueError):
                    pass

        with self._db._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO swarm_action_log
                    (swarm_id, agent_id, tenant_id, action_type, payload_json, verdict, timestamp, amount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ctx.swarm_id,
                    ctx.agent_id,
                    "",   # tenant_id populated by caller if available
                    ctx.action_type,
                    json.dumps(ctx.payload),
                    verdict,
                    ctx.timestamp,
                    amount_val,
                ),
            )
            conn.commit()
