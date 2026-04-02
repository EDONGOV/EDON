"""Transport adapter base classes and shared data types.

GovAction and GovResponse are the protocol-agnostic currency for all
governance decisions — regardless of whether the action arrived via HTTP,
MQTT, acoustic framing, or any future protocol.
"""
from __future__ import annotations

import abc
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class GovAction:
    """Transport-agnostic representation of a governance action.

    Maps 1:1 to the Action schema used by the governor, but carries the
    raw bytes/frame from the originating transport layer so adapters can
    re-encode responses correctly.
    """
    action_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    tool: str = ""
    op: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    estimated_risk: str = "low"
    source: str = "agent"
    intent_id: Optional[str] = None
    tenant_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    raw_frame: Optional[bytes] = None  # original bytes from transport layer

    def to_action_dict(self) -> Dict[str, Any]:
        """Convert to the dict format consumed by EDONGovernor."""
        return {
            "action_id": self.action_id,
            "agent_id": self.agent_id,
            "tool": self.tool,
            "op": self.op,
            "params": self.params,
            "estimated_risk": self.estimated_risk,
            "source": self.source,
            "intent_id": self.intent_id,
            "tenant_id": self.tenant_id,
            "tags": self.tags,
        }

    @classmethod
    def from_action_dict(cls, d: Dict[str, Any]) -> "GovAction":
        """Construct from a dict (e.g. decoded from JSON/CBOR payload)."""
        return cls(
            action_id=d.get("action_id") or str(uuid.uuid4()),
            agent_id=d.get("agent_id", ""),
            tool=d.get("tool", ""),
            op=d.get("op", ""),
            params=d.get("params", {}),
            estimated_risk=d.get("estimated_risk", "low"),
            source=d.get("source", "agent"),
            intent_id=d.get("intent_id"),
            tenant_id=d.get("tenant_id"),
            tags=d.get("tags", []),
        )


@dataclass
class GovResponse:
    """Transport-agnostic governance verdict."""
    action_id: str
    verdict: str          # ALLOW | BLOCK | ESCALATE | DEGRADE | PAUSE
    reason_code: str
    explanation: str
    encoded_frame: Optional[bytes] = None  # populated by adapter.send()


class TransportAdapter(abc.ABC):
    """Abstract base for all transport protocol adapters.

    Concrete adapters implement decode() and encode(). The gateway core
    only touches GovAction / GovResponse; adapters own all wire-format details.
    """

    @property
    @abc.abstractmethod
    def protocol(self) -> str:
        """Protocol identifier string, e.g. 'http', 'mqtt', 'acoustic'."""
        ...

    @abc.abstractmethod
    def decode(self, raw: bytes) -> GovAction:
        """Decode raw bytes into a GovAction. No I/O — pure transformation."""
        ...

    @abc.abstractmethod
    def encode(self, response: GovResponse) -> bytes:
        """Encode a GovResponse into raw bytes. No I/O — pure transformation."""
        ...

    def receive(self, raw: bytes) -> GovAction:
        """Decode and attach the original frame bytes for traceability."""
        action = self.decode(raw)
        action.raw_frame = raw
        return action

    def send(self, response: GovResponse) -> bytes:
        """Encode response and attach to the response object."""
        frame = self.encode(response)
        response.encoded_frame = frame
        return frame
