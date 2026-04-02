#!/usr/bin/env python3
"""Quick test to verify the governor fixes compile and work."""

import inspect


def test_governor_imports(monkeypatch):
    from edon_gateway.schemas import Verdict
    assert Verdict.ERROR.value == "error"

    from edon_gateway.governor import EDONGovernor
    assert hasattr(EDONGovernor, "get_intent")

    sig = inspect.signature(EDONGovernor.evaluate)
    params = list(sig.parameters.keys())
    assert "intent" in params
    assert "context" in params

    monkeypatch.setenv("EDON_AUTH_ENABLED", "false")
    from edon_gateway.main import app, governor, db  # noqa: F401
    assert governor is not None
