"""
Root pytest configuration for the EDON backend test suite.

Markers:
  live_server — tests that require a running gateway at EDON_GATEWAY_URL.
                Skipped automatically unless EDON_RUN_LIVE_TESTS=true is set.

Usage:
  # Run only unit/integration tests (default in CI):
  pytest tests/ edon_gateway/test/

  # Run live-server tests (requires gateway running):
  EDON_RUN_LIVE_TESTS=true EDON_GATEWAY_URL=http://localhost:8000 pytest tests/
"""
import os
import sys
from pathlib import Path

import pytest


_BACKEND_ROOT = Path(__file__).resolve().parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def pytest_collection_modifyitems(config, items):
    """Auto-skip live_server tests unless EDON_RUN_LIVE_TESTS=true."""
    run_live = os.getenv("EDON_RUN_LIVE_TESTS", "").lower() == "true"
    skip_live = pytest.mark.skip(reason="requires live server — set EDON_RUN_LIVE_TESTS=true to enable")
    for item in items:
        if "live_server" in item.keywords:
            if not run_live:
                item.add_marker(skip_live)
