"""EDON Hardening Agents — Evolution Loop.

Three narrow, bounded agents that continuously improve EDON's coverage,
policy precision, and regression safety:

  coverage_agent   — probes unscenarioed Impact failure states with synthetic shadow traces
  policy_agent     — converts approved fix proposals into deployable rule deltas
  regression_agent — validates rule_ready rules against trace history before deployment

Orchestrated by runner.run(), which chains them: coverage → policy → regression.
"""

from . import coverage_agent, policy_agent, regression_agent
from .runner import run, start_background_scheduler, stop_background_scheduler

__all__ = [
    "coverage_agent",
    "policy_agent",
    "regression_agent",
    "run",
    "start_background_scheduler",
    "stop_background_scheduler",
]
