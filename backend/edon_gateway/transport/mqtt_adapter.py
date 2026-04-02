"""MQTT transport adapter.

Wire format: UTF-8 JSON on topic edon/gov/{tenant_id}/{agent_id}/action.
Verdicts published to edon/gov/{tenant_id}/{agent_id}/verdict.

paho-mqtt is optional — encode/decode work on plain bytes regardless.
The subscribe/publish loop is the caller's responsibility; this class
handles only framing.
"""
from __future__ import annotations

import json
from .base import TransportAdapter, GovAction, GovResponse


class MQTTAdapter(TransportAdapter):
    """MQTT JSON framing adapter."""

    @property
    def protocol(self) -> str:
        return "mqtt"

    def decode(self, raw: bytes) -> GovAction:
        d = json.loads(raw.decode("utf-8"))
        return GovAction.from_action_dict(d)

    def encode(self, response: GovResponse) -> bytes:
        payload = {
            "action_id": response.action_id,
            "verdict": response.verdict,
            "reason_code": response.reason_code,
            "explanation": response.explanation,
        }
        return json.dumps(payload, separators=(",", ":")).encode("utf-8")

    def topic_for_action(self, tenant_id: str, agent_id: str) -> str:
        return f"edon/gov/{tenant_id}/{agent_id}/action"

    def topic_for_verdict(self, tenant_id: str, agent_id: str) -> str:
        return f"edon/gov/{tenant_id}/{agent_id}/verdict"
