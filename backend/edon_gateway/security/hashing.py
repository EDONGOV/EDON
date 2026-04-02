"""Secure hashing utilities for API keys, tokens, and passwords.

This module provides bcrypt-based hashing for sensitive credentials.
SHA256 is ONLY used for legacy compatibility during migration.

Security Requirements:
- API keys MUST be hashed with bcrypt (cost factor 12)
- Passwords MUST be hashed with bcrypt (cost factor 12)
- Audit chain hashing uses SHA256 (appropriate for hash chains)
"""

import hashlib
import logging
from typing import Tuple

try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False
    logging.warning("bcrypt not installed. Falling back to SHA256 (INSECURE for production)")

logger = logging.getLogger(__name__)

# Bcrypt cost factor (12 = ~250ms per hash, good balance of security and UX)
BCRYPT_COST_FACTOR = 12


def hash_api_key(api_key: str) -> Tuple[str, str]:
    """Hash an API key securely with bcrypt.

    Args:
        api_key: The plaintext API key

    Returns:
        Tuple of (hash_value, hash_type) where hash_type is "bcrypt" or "sha256"

    Security Note:
        In production, this MUST use bcrypt. SHA256 fallback is for
        development/testing only when bcrypt is not installed.
    """
    if not BCRYPT_AVAILABLE:
        logger.error("bcrypt not available! Using insecure SHA256 fallback")
        hash_value = hashlib.sha256(api_key.encode()).hexdigest()
        return hash_value, "sha256"

    # Generate salt and hash with bcrypt
    salt = bcrypt.gensalt(rounds=BCRYPT_COST_FACTOR)
    hash_bytes = bcrypt.hashpw(api_key.encode('utf-8'), salt)
    hash_value = hash_bytes.decode('utf-8')

    return hash_value, "bcrypt"


def verify_api_key(api_key: str, stored_hash: str, hash_type: str = "bcrypt") -> bool:
    """Verify an API key against its stored hash.

    Args:
        api_key: The plaintext API key to verify
        stored_hash: The stored hash value
        hash_type: Type of hash ("bcrypt" or "sha256")

    Returns:
        True if the API key matches the hash, False otherwise

    Security Note:
        SHA256 verification is supported ONLY for legacy keys during migration.
        New keys MUST use bcrypt.
    """
    try:
        if hash_type == "bcrypt":
            if not BCRYPT_AVAILABLE:
                logger.error("bcrypt not available for verification!")
                return False

            # bcrypt.checkpw handles timing-attack-safe comparison
            return bcrypt.checkpw(api_key.encode('utf-8'), stored_hash.encode('utf-8'))

        elif hash_type == "sha256":
            # Legacy verification (timing attack vulnerable, but for migration only)
            logger.warning(f"Using legacy SHA256 verification (insecure)")
            computed_hash = hashlib.sha256(api_key.encode()).hexdigest()

            # Constant-time comparison
            return compare_digest_safe(computed_hash, stored_hash)

        else:
            logger.error(f"Unknown hash type: {hash_type}")
            return False

    except Exception as e:
        logger.error(f"Error verifying API key: {e}")
        return False


def compare_digest_safe(a: str, b: str) -> bool:
    """Timing-attack-safe string comparison.

    Uses secrets.compare_digest for constant-time comparison.
    """
    import secrets
    return secrets.compare_digest(a, b)


def hash_for_audit_chain(data: str) -> str:
    """Hash data for audit trail cryptographic chaining.

    SHA256 is appropriate here because:
    - Not hashing passwords/keys (hashing audit data)
    - Need fast computation
    - Need deterministic output for chain verification

    Args:
        data: The data to hash

    Returns:
        SHA256 hex digest
    """
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def rehash_needed(hash_type: str) -> bool:
    """Check if a hash needs to be upgraded from SHA256 to bcrypt.

    Args:
        hash_type: Current hash type

    Returns:
        True if the hash should be upgraded to bcrypt
    """
    return hash_type == "sha256" and BCRYPT_AVAILABLE


# Migration helpers

def create_api_key_with_secure_hash(raw_key: str) -> Tuple[str, str]:
    """Create a new API key with secure hashing.

    This is the function to use when generating new API keys.

    Args:
        raw_key: The raw API key (e.g., from secrets.token_urlsafe)

    Returns:
        Tuple of (key_hash, hash_type)
    """
    return hash_api_key(raw_key)


def migrate_legacy_hash(raw_key: str, old_hash: str) -> Tuple[str, str, bool]:
    """Migrate a legacy SHA256 hash to bcrypt.

    Call this when a user successfully authenticates with a legacy SHA256 hash.
    This opportunistically upgrades their hash to bcrypt.

    Args:
        raw_key: The plaintext API key (from successful authentication)
        old_hash: The old SHA256 hash (for verification)

    Returns:
        Tuple of (new_hash, new_hash_type, migrated)
        where migrated=True if upgrade was performed
    """
    # Verify the old hash first
    if not verify_api_key(raw_key, old_hash, "sha256"):
        logger.error("Legacy hash verification failed during migration")
        return old_hash, "sha256", False

    # Generate new bcrypt hash
    if not BCRYPT_AVAILABLE:
        logger.warning("bcrypt not available, cannot migrate hash")
        return old_hash, "sha256", False

    new_hash, hash_type = hash_api_key(raw_key)
    logger.info("Successfully migrated API key hash from SHA256 to bcrypt")

    return new_hash, hash_type, True


def hash_api_key_fast(api_key: str) -> str:
    """SHA256 hash of an API key for fast DB lookup.

    SHA256 is appropriate here (not bcrypt) because:
    - API keys are cryptographically random (256-bit entropy via secrets.token_hex(32))
    - High-entropy keys do not benefit from bcrypt's key-stretching
    - At 230+ req/sec, bcrypt (250ms/hash) would require 57x available CPU
    - Use bcrypt only for low-entropy inputs (passwords)

    Args:
        api_key: The raw API key string

    Returns:
        SHA256 hex digest (64 chars) for DB lookup
    """
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def validate_hash_security():
    """Validate that secure hashing is available.

    Call this at application startup to ensure bcrypt is installed.
    Raises RuntimeError in production if bcrypt is not available.
    """
    import os

    if not BCRYPT_AVAILABLE:
        env = os.getenv("EDON_ENV", "production").lower()
        if env == "production":
            raise RuntimeError(
                "CRITICAL SECURITY ERROR: bcrypt is not installed in production! "
                "API key hashing is insecure. Install bcrypt immediately: pip install bcrypt"
            )
        else:
            logger.warning(
                "bcrypt not installed in non-production environment. "
                "Using insecure SHA256 fallback. Install bcrypt for proper security."
            )
    else:
        logger.info(f"Secure hashing initialized with bcrypt (cost factor {BCRYPT_COST_FACTOR})")
