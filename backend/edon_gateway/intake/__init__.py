"""EDON Intent Normalization Layer.

Reconciles the three intent signals on every agent action:
  - stated_intent: what the agent claims it is doing
  - user_message:  what the user actually requested
  - action_type:   what the agent is actually executing

Exposes normalize_intent() for use in the /v1/action pipeline.
"""

from .normalizer import normalize_intent, NormalizedIntent, MISALIGNMENT_THRESHOLD

__all__ = ["normalize_intent", "NormalizedIntent", "MISALIGNMENT_THRESHOLD"]
