"""
Symmetric encryption helpers for broker credentials.

Uses Fernet (AES-128-CBC + HMAC-SHA256) keyed by the BROKER_ENCRYPTION_KEY env var.
Generate a key with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import os
from cryptography.fernet import Fernet, InvalidToken


_cached_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _cached_fernet
    if _cached_fernet is not None:
        return _cached_fernet

    key = os.environ.get("BROKER_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "BROKER_ENCRYPTION_KEY is not set. Generate one with "
            "`python -c 'from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())'` and add it to your environment."
        )

    try:
        _cached_fernet = Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as e:
        raise RuntimeError(
            f"BROKER_ENCRYPTION_KEY is not a valid Fernet key: {e}"
        ) from e

    return _cached_fernet


def encrypt_str(plaintext: str) -> str:
    """Encrypt a string and return a urlsafe-b64 ciphertext string."""
    if plaintext is None:
        raise ValueError("Cannot encrypt None")
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_str(ciphertext: str) -> str:
    """Decrypt a Fernet ciphertext string back to plaintext."""
    if ciphertext is None:
        raise ValueError("Cannot decrypt None")
    try:
        return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as e:
        raise ValueError("Failed to decrypt — token invalid or key mismatch") from e


def mask_secret(value: str, visible: int = 4) -> str:
    """Return a masked preview of a secret, e.g. 'XXX-…-A1B2'."""
    if not value:
        return ""
    if len(value) <= visible * 2:
        return "•" * len(value)
    return f"{value[:visible]}…{value[-visible:]}"
