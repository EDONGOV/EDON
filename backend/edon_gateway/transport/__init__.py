"""Transport adapter layer — protocol-agnostic governance action framing.

Governance logic only deals with GovAction / GovResponse objects.
Adapters handle protocol-specific encoding/decoding (HTTP, MQTT, acoustic, etc.).
"""
from .base import GovAction, GovResponse, TransportAdapter
from .registry import get_adapter, register_adapter, list_protocols

__all__ = [
    "GovAction",
    "GovResponse",
    "TransportAdapter",
    "get_adapter",
    "register_adapter",
    "list_protocols",
]
