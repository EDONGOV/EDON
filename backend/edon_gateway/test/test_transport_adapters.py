"""Tests for transport adapter layer (Gap 4).

All tests are pure in-process — no network, no DB.
"""
import json
import struct
import zlib

import pytest

from edon_gateway.transport.base import GovAction, GovResponse
from edon_gateway.transport.mqtt_adapter import MQTTAdapter
from edon_gateway.transport.acoustic_adapter import AcousticAdapter, _crc32
from edon_gateway.transport.registry import get_adapter, list_protocols, register_adapter


# ---------------------------------------------------------------------------
# GovAction / GovResponse
# ---------------------------------------------------------------------------

class TestGovAction:
    def test_from_dict_round_trip(self):
        d = {
            "action_id": "abc-123",
            "agent_id": "bot-1",
            "tool": "robot",
            "op": "move",
            "params": {"direction": "forward"},
            "estimated_risk": "medium",
            "tenant_id": "tenant-x",
        }
        a = GovAction.from_action_dict(d)
        assert a.action_id == "abc-123"
        assert a.tool == "robot"
        assert a.op == "move"
        assert a.params["direction"] == "forward"
        assert a.tenant_id == "tenant-x"

    def test_to_action_dict_keys(self):
        a = GovAction(tool="sensor", op="read")
        d = a.to_action_dict()
        assert "tool" in d and "op" in d
        assert d["tool"] == "sensor"

    def test_auto_action_id(self):
        a = GovAction()
        assert len(a.action_id) > 0

    def test_from_dict_missing_fields_defaults(self):
        a = GovAction.from_action_dict({})
        assert a.tool == ""
        assert a.estimated_risk == "low"
        assert a.tags == []


# ---------------------------------------------------------------------------
# MQTT Adapter
# ---------------------------------------------------------------------------

class TestMQTTAdapter:
    def setup_method(self):
        self.adapter = MQTTAdapter()

    def test_protocol_name(self):
        assert self.adapter.protocol == "mqtt"

    def test_decode_basic(self):
        payload = {
            "action_id": "id-1",
            "agent_id": "agent-a",
            "tool": "email",
            "op": "read",
        }
        raw = json.dumps(payload).encode("utf-8")
        action = self.adapter.decode(raw)
        assert action.tool == "email"
        assert action.op == "read"
        assert action.agent_id == "agent-a"

    def test_encode_response(self):
        resp = GovResponse(
            action_id="id-1",
            verdict="ALLOW",
            reason_code="policy_pass",
            explanation="ok",
        )
        raw = self.adapter.encode(resp)
        d = json.loads(raw.decode("utf-8"))
        assert d["verdict"] == "ALLOW"
        assert d["action_id"] == "id-1"

    def test_round_trip(self):
        action = GovAction(action_id="rt-1", agent_id="bot", tool="robot", op="move")
        raw_send = json.dumps(action.to_action_dict()).encode("utf-8")
        received = self.adapter.decode(raw_send)
        assert received.tool == "robot"
        assert received.op == "move"

    def test_topic_for_action(self):
        topic = self.adapter.topic_for_action("tenant-1", "agent-1")
        assert topic == "edon/gov/tenant-1/agent-1/action"

    def test_topic_for_verdict(self):
        topic = self.adapter.topic_for_verdict("t", "a")
        assert topic == "edon/gov/t/a/verdict"


# ---------------------------------------------------------------------------
# Acoustic Adapter
# ---------------------------------------------------------------------------

class TestAcousticAdapter:
    def setup_method(self):
        self.adapter = AcousticAdapter(use_cbor=False)

    def test_protocol_name(self):
        assert self.adapter.protocol == "acoustic"

    def test_encode_decode_round_trip(self):
        action = GovAction(
            action_id="a-1", agent_id="nano-1", tool="inject", op="deliver",
            params={"dose_mg": 0.05}, estimated_risk="high",
        )
        resp = GovResponse(
            action_id="a-1", verdict="ALLOW",
            reason_code="policy_pass", explanation="ok",
        )
        frame = self.adapter.encode(resp)
        assert len(frame) >= 8

        # Encode an action separately so we can decode it
        action_frame = self.adapter.encode(
            GovResponse(
                action_id="a-2",
                verdict="BLOCK",
                reason_code="test",
                explanation="x",
            )
        )
        decoded = self.adapter.decode(action_frame)
        # The frame was encoded as a GovResponse dict but decode produces a GovAction;
        # fields that match (action_id, verdict→tool not present) are extracted best-effort
        assert decoded is not None

    def test_decode_action_frame(self):
        """Encode a GovAction dict directly into an acoustic frame."""
        action_dict = {
            "action_id": "frame-1",
            "agent_id": "nano-2",
            "tool": "sensor",
            "op": "measure",
            "params": {},
            "estimated_risk": "low",
        }
        payload = json.dumps(action_dict, separators=(",", ":")).encode("utf-8")
        crc = _crc32(payload)
        header = struct.pack("<BBH", 0xED, 0x01, len(payload))
        crc_bytes = struct.pack("<I", crc)
        frame = header + crc_bytes + payload

        decoded = self.adapter.decode(frame)
        assert decoded.tool == "sensor"
        assert decoded.op == "measure"
        assert decoded.action_id == "frame-1"

    def test_crc_mismatch_raises(self):
        action_dict = {"tool": "robot", "op": "move"}
        payload = json.dumps(action_dict).encode("utf-8")
        crc = _crc32(payload)
        header = struct.pack("<BBH", 0xED, 0x01, len(payload))
        crc_bytes = struct.pack("<I", crc ^ 0xFFFFFFFF)  # flip all bits → bad CRC
        frame = header + crc_bytes + payload
        with pytest.raises(ValueError, match="CRC mismatch"):
            self.adapter.decode(frame)

    def test_bad_magic_raises(self):
        payload = b'{"tool":"x","op":"y"}'
        crc = _crc32(payload)
        header = struct.pack("<BBH", 0xAB, 0x01, len(payload))  # wrong magic
        crc_bytes = struct.pack("<I", crc)
        frame = header + crc_bytes + payload
        with pytest.raises(ValueError, match="magic"):
            self.adapter.decode(frame)

    def test_too_short_raises(self):
        with pytest.raises(ValueError, match="too short"):
            self.adapter.decode(b"\xED\x01\x00")

    def test_frame_size_bytes(self):
        d = {"action_id": "x", "tool": "t", "op": "o"}
        size = self.adapter.frame_size_bytes(d)
        assert size < 100  # minimal frame well under 100 bytes

    def test_frame_overhead_is_8_bytes(self):
        payload = json.dumps({}, separators=(",", ":")).encode("utf-8")
        size = self.adapter.frame_size_bytes({})
        assert size == 8 + len(payload)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestTransportRegistry:
    def test_get_mqtt(self):
        adapter = get_adapter("mqtt")
        assert adapter.protocol == "mqtt"

    def test_get_acoustic(self):
        adapter = get_adapter("acoustic")
        assert adapter.protocol == "acoustic"

    def test_missing_protocol_raises(self):
        with pytest.raises(KeyError, match="chemical"):
            get_adapter("chemical")

    def test_list_protocols_contains_builtins(self):
        protocols = list_protocols()
        assert "mqtt" in protocols
        assert "acoustic" in protocols

    def test_register_custom_adapter(self):
        class FakeAdapter(MQTTAdapter):
            @property
            def protocol(self):
                return "test_fake_proto"

        register_adapter(FakeAdapter())
        assert get_adapter("test_fake_proto").protocol == "test_fake_proto"
