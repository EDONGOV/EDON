"""Ed25519 decision signing for EDON Governor.

Set EDON_SIGNING_KEY_HEX to a 32-byte hex-encoded Ed25519 private key for
persistent, cross-restart verification. If unset an ephemeral key is generated
and a warning is logged.

Customers retrieve the gateway public key at GET /v1/pubkey to verify decisions
offline.
"""
import os
import base64
import json
import logging
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

logger = logging.getLogger(__name__)

_SIGNING_KEY: Optional[Ed25519PrivateKey] = None
_PUBLIC_KEY_HEX: Optional[str] = None
_KEY_ID: Optional[str] = None

# Fields excluded from the signed payload (mutable metadata / internal signals)
_EXCLUDED_FROM_SIGNATURE = frozenset({"meta", "invariant_results", "policy_snapshot_hash"})


def _load_or_generate_key() -> Ed25519PrivateKey:
    key_hex = os.getenv("EDON_SIGNING_KEY_HEX", "").strip()
    if key_hex:
        try:
            return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(key_hex))
        except Exception as exc:
            logger.error("EDON_SIGNING_KEY_HEX is invalid: %s — generating ephemeral key", exc)
    logger.warning(
        "EDON_SIGNING_KEY_HEX not set — generating ephemeral signing key. "
        "Decisions will not verify across restarts. Set the env var in production."
    )
    return Ed25519PrivateKey.generate()


def _get_signing_key() -> Ed25519PrivateKey:
    global _SIGNING_KEY, _PUBLIC_KEY_HEX, _KEY_ID
    if _SIGNING_KEY is None:
        _SIGNING_KEY = _load_or_generate_key()
        raw_pub = _SIGNING_KEY.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        _PUBLIC_KEY_HEX = raw_pub.hex()
        _KEY_ID = _PUBLIC_KEY_HEX[:16]
    return _SIGNING_KEY


def get_public_key_hex() -> str:
    """Return the Ed25519 public key as a hex string."""
    _get_signing_key()
    return _PUBLIC_KEY_HEX  # type: ignore[return-value]


def get_key_id() -> str:
    """Return a short identifier for the current public key (first 16 hex chars)."""
    _get_signing_key()
    return _KEY_ID  # type: ignore[return-value]


def _canonical_payload(decision_dict: dict) -> bytes:
    payload = {k: v for k, v in decision_dict.items() if k not in _EXCLUDED_FROM_SIGNATURE}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def sign_decision(decision_dict: dict) -> str:
    """Sign a canonical representation of the decision. Returns base64url signature."""
    key = _get_signing_key()
    sig_bytes = key.sign(_canonical_payload(decision_dict))
    return base64.urlsafe_b64encode(sig_bytes).decode()


def sign_canonical_payload(payload_dict: dict) -> str:
    """Sign the full canonical payload without excluding any fields."""
    key = _get_signing_key()
    sig_bytes = key.sign(json.dumps(payload_dict, sort_keys=True, separators=(",", ":")).encode())
    return base64.urlsafe_b64encode(sig_bytes).decode()


def verify_decision(decision_dict: dict, signature_b64url: str, pubkey_hex: str) -> bool:
    """Verify a decision signature against the given public key. Returns True if valid."""
    try:
        raw_pub = bytes.fromhex(pubkey_hex)
        pub = Ed25519PublicKey.from_public_bytes(raw_pub)
        sig_bytes = base64.urlsafe_b64decode(signature_b64url + "==")
        pub.verify(sig_bytes, _canonical_payload(decision_dict))
        return True
    except Exception:
        return False


def verify_canonical_payload(payload_dict: dict, signature_b64url: str, pubkey_hex: str) -> bool:
    """Verify a full canonical payload signature against the given public key."""
    try:
        raw_pub = bytes.fromhex(pubkey_hex)
        pub = Ed25519PublicKey.from_public_bytes(raw_pub)
        sig_bytes = base64.urlsafe_b64decode(signature_b64url + "==")
        pub.verify(sig_bytes, json.dumps(payload_dict, sort_keys=True, separators=(",", ":")).encode())
        return True
    except Exception:
        return False
