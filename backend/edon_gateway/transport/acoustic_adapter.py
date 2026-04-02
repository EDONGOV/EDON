"""Acoustic channel transport adapter for nanobot-scale communication.

Frame layout (little-endian, 8-byte header):
  [0]     magic   : 0xED
  [1]     version : 0x01 (JSON) | 0x02 (CBOR, requires cbor2)
  [2-3]   payload_length : uint16
  [4-7]   crc32   : uint32 over payload bytes only
  [8...]  payload : compact JSON or CBOR bytes

Rationale for the wire format:
  - Acoustic channels in fluid (blood, industrial coolant) support ~10–1000 bps.
  - 8-byte overhead = ~0.08 s at 100 bps per governance frame — acceptable.
  - CRC-32 detects single-bit errors common in acoustic channels.
  - CBOR (RFC 7049) reduces payload size ~30 % vs compact JSON for numeric params.
"""
from __future__ import annotations

import json
import struct
import zlib
from typing import Any, Dict

from .base import TransportAdapter, GovAction, GovResponse

_MAGIC = 0xED
_VERSION_JSON = 0x01
_VERSION_CBOR = 0x02


def _crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


class AcousticAdapter(TransportAdapter):
    """Acoustic-channel framing adapter with optional CBOR payload encoding."""

    def __init__(self, use_cbor: bool = False) -> None:
        self._use_cbor = use_cbor
        self._cbor = None
        if use_cbor:
            try:
                import cbor2  # type: ignore
                self._cbor = cbor2
            except ImportError as exc:
                raise ImportError(
                    "cbor2 package required for AcousticAdapter CBOR mode. "
                    "Install with: pip install cbor2"
                ) from exc

    @property
    def protocol(self) -> str:
        return "acoustic"

    def decode(self, raw: bytes) -> GovAction:
        """Validate frame header + CRC, then deserialise payload."""
        if len(raw) < 8:
            raise ValueError(f"Frame too short: {len(raw)} bytes (minimum 8)")

        magic, version, payload_len = struct.unpack_from("<BBH", raw, 0)
        if magic != _MAGIC:
            raise ValueError(f"Bad magic byte: 0x{magic:02X} (expected 0xED)")

        crc_received = struct.unpack_from("<I", raw, 4)[0]
        payload = raw[8 : 8 + payload_len]

        if len(payload) != payload_len:
            raise ValueError(
                f"Truncated payload: got {len(payload)} bytes, expected {payload_len}"
            )

        crc_computed = _crc32(payload)
        if crc_received != crc_computed:
            raise ValueError(
                f"CRC mismatch: received {crc_received:#010x}, "
                f"computed {crc_computed:#010x} — frame corrupted"
            )

        if version == _VERSION_CBOR:
            if self._cbor is None:
                raise ValueError("CBOR frame received but cbor2 not installed")
            d: Dict[str, Any] = self._cbor.loads(payload)
        else:
            d = json.loads(payload.decode("utf-8"))

        return GovAction.from_action_dict(d)

    def encode(self, response: GovResponse) -> bytes:
        """Encode a GovResponse into a framed byte sequence."""
        payload_dict = {
            "action_id": response.action_id,
            "verdict": response.verdict,
            "reason_code": response.reason_code,
        }

        if self._use_cbor and self._cbor is not None:
            payload = self._cbor.dumps(payload_dict)
            version = _VERSION_CBOR
        else:
            payload = json.dumps(payload_dict, separators=(",", ":")).encode("utf-8")
            version = _VERSION_JSON

        crc = _crc32(payload)
        header = struct.pack("<BBH", _MAGIC, version, len(payload))
        crc_bytes = struct.pack("<I", crc)
        return header + crc_bytes + payload

    def frame_size_bytes(self, action_dict: Dict[str, Any]) -> int:
        """Estimate encoded frame size for channel capacity planning."""
        if self._use_cbor and self._cbor is not None:
            payload = self._cbor.dumps(action_dict)
        else:
            payload = json.dumps(action_dict, separators=(",", ":")).encode("utf-8")
        return 8 + len(payload)
