"""Transport adapter registry.

Adapters are registered by protocol name at import time.
The gateway (and tests) call get_adapter("mqtt") / get_adapter("acoustic")
to obtain the appropriate encoder/decoder.
"""
from __future__ import annotations

from typing import Dict, List
from .base import TransportAdapter

_registry: Dict[str, TransportAdapter] = {}


def register_adapter(adapter: TransportAdapter) -> None:
    """Register a transport adapter instance by its protocol name."""
    _registry[adapter.protocol] = adapter


def get_adapter(protocol: str) -> TransportAdapter:
    """Return the adapter for *protocol*.  Raises KeyError if not registered."""
    if protocol not in _registry:
        raise KeyError(
            f"No adapter registered for protocol '{protocol}'. "
            f"Available: {list(_registry.keys())}"
        )
    return _registry[protocol]


def list_protocols() -> List[str]:
    """Return a sorted list of all registered protocol names."""
    return sorted(_registry.keys())


def _bootstrap() -> None:
    """Pre-register built-in adapters.  Called once at module import."""
    from .mqtt_adapter import MQTTAdapter
    from .acoustic_adapter import AcousticAdapter

    register_adapter(MQTTAdapter())
    register_adapter(AcousticAdapter())


_bootstrap()
