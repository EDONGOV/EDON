"""EDON Proof Engine — orchestrates Level 1 / Level 2 / Level 3 proof generation.

ProofMode:
  LOGICAL    (Level 1) — deterministic step-by-step chain. No AI, no governor needed.
                          Fast, always available, good enough to close deals.

  SIMULATED  (Level 2) — replay exploit steps through the live governor in sandbox mode.
                          Proves the exploit passes your actual policy engine.
                          Requires a live governor instance.

  CONTROLLED (Level 3) — replay against a staging environment (future / Shannon slot).
                          Not yet implemented.

Usage:
    engine = get_proof_engine()

    # Level 1 — always works, even during bootstrap (no governor needed)
    result = engine.prove(failure_state, mode=ProofMode.LOGICAL)

    # Level 2 — requires live governor
    result = await engine.prove_async(failure_state, mode=ProofMode.SIMULATED, governor=gov)

    # Both levels together (Level 1 always, Level 2 if governor available)
    result = await engine.prove_full(failure_state, governor=gov, tenant_id="acme")
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from enum import Enum
from typing import Optional

from .logical import generate_logical_proof, LogicalProof
from .simulated import generate_simulated_proof, SimulatedProof
from ..logging_config import get_logger

logger = get_logger(__name__)


class ProofMode(str, Enum):
    LOGICAL    = "logical"     # Level 1 — deterministic, no governor needed
    SIMULATED  = "simulated"   # Level 2 — sandbox governor replay
    SANDBOX    = "sandbox"     # Level 2.5 — mock execution trace (no governor needed)
    CONTROLLED = "controlled"  # Level 3 — staging environment (future)


@dataclass
class ProofResult:
    """Unified proof result — contains whichever levels were generated."""
    failure_state_id: str
    vulnerability_class: str
    requested_mode: str

    # Level 1 — always present when mode includes LOGICAL
    logical_proof: Optional[dict] = None

    # Level 2 — present when mode includes SIMULATED and governor available
    simulated_proof: Optional[dict] = None

    # Level 2.5 — sandbox mock execution trace (always included, no governor needed)
    sandbox_proof: Optional[dict] = None

    # Headline for UI
    exploit_confirmed: bool = False   # True = Level 2 confirmed exploit succeeds
    highest_confidence: float = 0.0   # best confidence across levels
    proof_summary: str = ""           # one-line summary for display

    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


# ── Engine ────────────────────────────────────────────────────────────────────

class ProofEngine:

    def prove(self, failure_state: dict) -> ProofResult:
        """Generate Level 1 Logical Proof + Level 2.5 Sandbox (synchronous, always available)."""
        vuln  = failure_state.get("vulnerability_class", "unknown")
        fsid  = failure_state.get("failure_state_id", "unknown")

        logical = generate_logical_proof(failure_state)

        # Level 2.5 — sandbox mock execution (always runs, no governor needed)
        sandbox_dict = None
        try:
            from .sandbox import execute_sandbox
            sandbox_exec = execute_sandbox(logical, failure_state)
            sandbox_dict = sandbox_exec.to_dict()
        except Exception as exc:
            logger.debug("[proof/engine] sandbox execution failed (non-blocking): %s", exc)

        summary = (
            f"Level 1 — {len(logical.steps)}-step exploit chain identified. "
            f"Rules violated: {len(logical.rules_violated)}. "
            f"Outcome: {logical.final_outcome[:80]}"
        )

        return ProofResult(
            failure_state_id=fsid,
            vulnerability_class=vuln,
            requested_mode=ProofMode.LOGICAL.value,
            logical_proof=logical.to_dict(),
            sandbox_proof=sandbox_dict,
            highest_confidence=logical.confidence,
            proof_summary=summary,
        )

    async def prove_async(
        self,
        failure_state: dict,
        mode: ProofMode = ProofMode.SIMULATED,
        governor=None,
        tenant_id: Optional[str] = None,
    ) -> ProofResult:
        """Generate Level 2 Simulated Proof (async, requires governor).

        Always generates Level 1 first, then runs Level 2 if governor available.
        """
        vuln = failure_state.get("vulnerability_class", "unknown")
        fsid = failure_state.get("failure_state_id", "unknown")

        # Level 1 is always generated (fast, deterministic)
        logical = generate_logical_proof(failure_state)

        # Level 2.5 — sandbox mock execution (always runs, no governor needed)
        sandbox_dict = None
        try:
            from .sandbox import execute_sandbox
            sandbox_exec = execute_sandbox(logical, failure_state, governor=governor, tenant_id=tenant_id)
            sandbox_dict = sandbox_exec.to_dict()
        except Exception as exc:
            logger.debug("[proof/engine] sandbox execution failed (non-blocking): %s", exc)

        result = ProofResult(
            failure_state_id=fsid,
            vulnerability_class=vuln,
            requested_mode=mode.value,
            logical_proof=logical.to_dict(),
            sandbox_proof=sandbox_dict,
            highest_confidence=logical.confidence,
        )

        if mode == ProofMode.SIMULATED and governor is not None:
            try:
                sim = await generate_simulated_proof(
                    logical_proof=logical,
                    failure_state=failure_state,
                    governor=governor,
                    tenant_id=tenant_id,
                )
                result.simulated_proof = sim.to_dict()
                result.exploit_confirmed = sim.exploit_succeeded
                result.highest_confidence = max(logical.confidence, sim.confidence)
            except Exception as exc:
                logger.warning("[proof/engine] simulated proof failed (non-blocking): %s", exc)

        elif mode == ProofMode.CONTROLLED:
            logger.info("[proof/engine] Level 3 (controlled replay) not yet implemented")

        result.proof_summary = _build_summary(result, logical)
        return result

    async def prove_full(
        self,
        failure_state: dict,
        governor=None,
        tenant_id: Optional[str] = None,
    ) -> ProofResult:
        """Generate the highest proof level available given current resources.

        With governor: Level 1 + Level 2.
        Without governor: Level 1 only.
        """
        mode = ProofMode.SIMULATED if governor is not None else ProofMode.LOGICAL
        return await self.prove_async(
            failure_state,
            mode=mode,
            governor=governor,
            tenant_id=tenant_id,
        )

    async def prove_batch(
        self,
        failure_states: list[dict],
        governor=None,
        tenant_id: Optional[str] = None,
        max_concurrent: int = 5,
    ) -> list[ProofResult]:
        """Generate proofs for multiple failure states concurrently.

        Used by the bootstrap engine to prove all top findings in parallel.
        """
        sem = asyncio.Semaphore(max_concurrent)

        async def _one(fs: dict) -> ProofResult:
            async with sem:
                return await self.prove_full(fs, governor=governor, tenant_id=tenant_id)

        return list(await asyncio.gather(*[_one(fs) for fs in failure_states]))


def _build_summary(result: ProofResult, logical: LogicalProof) -> str:
    parts = []

    if result.simulated_proof:
        sim = result.simulated_proof
        if result.exploit_confirmed:
            parts.append(
                f"CONFIRMED (Level 2): exploit passes the live policy engine — "
                f"{len(logical.steps)} steps, all critical steps allowed."
            )
        elif sim.get("blocked_at_step"):
            parts.append(
                f"BLOCKED at Step {sim['blocked_at_step']} by governor — "
                f"existing policy partially mitigates this path."
            )
        else:
            parts.append(
                f"Simulated: {len(logical.steps)} steps evaluated against governor."
            )
    else:
        parts.append(
            f"Logical proof: {len(logical.steps)}-step exploit chain. "
            f"{len(logical.rules_violated)} governance rule(s) absent."
        )

    parts.append(f"Entry: {logical.entry_point}.")
    parts.append(f"Outcome: {logical.final_outcome}.")
    return " ".join(parts)


# ── Singleton ──────────────────────────────────────────────────────────────────

_engine: Optional[ProofEngine] = None


def get_proof_engine() -> ProofEngine:
    global _engine
    if _engine is None:
        _engine = ProofEngine()
    return _engine
