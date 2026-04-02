"""Compat shim to expose inner edon_gateway package."""

from __future__ import annotations

import os
import sys
from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)  # type: ignore[name-defined]

_inner = os.path.join(os.path.dirname(__file__), "edon_gateway")
if os.path.isdir(_inner):
    if _inner not in __path__:
        __path__.append(_inner)  # type: ignore[attr-defined]
    if _inner not in sys.path:
        sys.path.insert(0, _inner)
