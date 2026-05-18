"""EDON Proof Engine — 3 levels of exploit proof.

  Level 1   (logical)    — deterministic step-by-step chain, no AI, always available
  Level 2   (simulated)  — sandbox governor replay, proves exploit passes real policy
  Level 2.5 (sandbox)    — mock execution trace, shows exactly what data is touched
  Level 3   (controlled) — staging environment replay (future)

Entry points:
    from .engine import get_proof_engine, ProofMode, ProofResult
    from .logical import generate_logical_proof, LogicalProof
    from .simulated import generate_simulated_proof, SimulatedProof
    from .sandbox import execute_sandbox, SandboxExecution
"""

from .engine import ProofEngine, ProofMode, ProofResult, get_proof_engine
from .logical import generate_logical_proof, LogicalProof
from .simulated import generate_simulated_proof, SimulatedProof
from .sandbox import execute_sandbox, SandboxExecution

__all__ = [
    "ProofEngine", "ProofMode", "ProofResult", "get_proof_engine",
    "generate_logical_proof", "LogicalProof",
    "generate_simulated_proof", "SimulatedProof",
    "execute_sandbox", "SandboxExecution",
]
