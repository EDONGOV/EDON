"""Edge deployment package — offline policy evaluation for swarm controllers.

EmbeddedGovernor runs on edge nodes (e.g. Raspberry Pi swarm controllers)
with no DB or network access.  It evaluates actions against a pre-compiled
PolicyBundle received from the gateway's /edge/{id}/policy-bundle endpoint.
"""
from .embedded_governor import EmbeddedGovernor, PolicyBundle, EmbeddedVerdict

__all__ = ["EmbeddedGovernor", "PolicyBundle", "EmbeddedVerdict"]
