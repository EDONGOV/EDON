"""Field-level encryption for sensitive database columns.

Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).
Key source: EDON_DB_ENCRYPTION_KEY env var (base64-encoded Fernet key).
In production, raises if key not set.
In dev/test, generates ephemeral key with WARNING.
"""

import os
import logging

logger = logging.getLogger(__name__)

try:
    from cryptography.fernet import Fernet, InvalidToken
    FERNET_AVAILABLE = True
except ImportError:
    FERNET_AVAILABLE = False
    logger.warning("cryptography not installed. Field encryption unavailable. "
                   "Install with: pip install cryptography>=41.0.0")

_fernet_instance = None


def _get_env() -> str:
    return os.getenv("EDON_ENV", "production").strip().lower()


def _get_fernet():
    """Get or create the Fernet instance."""
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance

    if not FERNET_AVAILABLE:
        raise RuntimeError(
            "cryptography not installed. Run: pip install cryptography>=41.0.0"
        )

    raw_key = os.getenv("EDON_DB_ENCRYPTION_KEY", "").strip()
    if raw_key:
        try:
            _fernet_instance = Fernet(raw_key.encode())
            logger.info("Loaded field encryption key from EDON_DB_ENCRYPTION_KEY")
            return _fernet_instance
        except Exception as exc:
            raise RuntimeError(f"Invalid EDON_DB_ENCRYPTION_KEY: {exc}") from exc

    env = _get_env()
    if env not in ("development", "test", "dev"):
        raise RuntimeError(
            "CRITICAL: EDON_DB_ENCRYPTION_KEY not set in production. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )

    # Dev/test: ephemeral key (data lost on restart)
    ephemeral_key = Fernet.generate_key()
    _fernet_instance = Fernet(ephemeral_key)
    logger.warning(
        "Using EPHEMERAL encryption key (dev/test only). "
        "Data encrypted with this key will be unrecoverable after restart. "
        "Set EDON_DB_ENCRYPTION_KEY for persistent encryption."
    )
    return _fernet_instance


def encrypt_field(plaintext: str) -> str:
    """Encrypt a string field value.

    Args:
        plaintext: The value to encrypt.

    Returns:
        Encrypted ciphertext as a UTF-8 string.
    """
    if not plaintext:
        return plaintext
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_field(ciphertext: str) -> str:
    """Decrypt a previously encrypted field value.

    Args:
        ciphertext: The encrypted value (output of encrypt_field).

    Returns:
        Original plaintext string.

    Raises:
        ValueError: If decryption fails (wrong key or corrupted data).
    """
    if not ciphertext:
        return ciphertext
    try:
        return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (Exception if not FERNET_AVAILABLE else InvalidToken) as exc:
        raise ValueError("Failed to decrypt field: invalid token or wrong key.") from exc


def validate_encryption_setup() -> None:
    """Validate encryption is properly configured. Call at startup."""
    if not FERNET_AVAILABLE:
        env = _get_env()
        if env not in ("development", "test", "dev"):
            raise RuntimeError(
                "cryptography library not installed in production. "
                "Run: pip install cryptography>=41.0.0"
            )
        logger.warning("cryptography not installed in dev/test. Field encryption disabled.")
        return

    _get_fernet()  # triggers key validation / ephemeral generation

    # Round-trip test
    test_value = "edon-encryption-validation-test"
    encrypted = encrypt_field(test_value)
    decrypted = decrypt_field(encrypted)
    if decrypted != test_value:
        raise RuntimeError("Encryption round-trip validation failed.")

    logger.info("Field-level encryption setup validated.")
