"""Swarm coordination package.

SwarmCoordinator evaluates collective-action policies across a named group
of agents/bots: action budget caps, quorum rules, and dosage limits.
"""
from .coordinator import SwarmCoordinator, SwarmEvalContext, SwarmVerdict

__all__ = ["SwarmCoordinator", "SwarmEvalContext", "SwarmVerdict"]
