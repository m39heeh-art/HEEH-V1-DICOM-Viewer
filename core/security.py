"""Authenticated encryption helpers for medical-image bytes.

This module protects data confidentiality and integrity at rest or in transit.
It does not anonymize DICOM metadata and does not replace access controls,
key rotation, audit logging, or a regulated clinical security program.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken


class EncryptionConfigurationError(ValueError):
    """Raised when the application encryption key is absent or malformed."""


def generate_key() -> str:
    """Generate a URL-safe Fernet key suitable for a secret manager."""
    return Fernet.generate_key().decode("ascii")


def _fernet(key: str | bytes) -> Fernet:
    if isinstance(key, str):
        key = key.encode("ascii")
    try:
        return Fernet(key)
    except (TypeError, ValueError) as exc:
        raise EncryptionConfigurationError(
            "Encryption key must be a valid Fernet key."
        ) from exc


def encrypt_bytes(data: bytes, key: str | bytes) -> bytes:
    """Encrypt and authenticate bytes using Fernet (AES-128-CBC + HMAC)."""
    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    return _fernet(key).encrypt(data)


def decrypt_bytes(token: bytes, key: str | bytes) -> bytes:
    """Decrypt authenticated bytes and reject tampering or wrong keys."""
    if not isinstance(token, bytes):
        raise TypeError("token must be bytes")
    try:
        return _fernet(key).decrypt(token)
    except InvalidToken as exc:
        raise ValueError("Encrypted data is invalid or the key is incorrect.") from exc


def encryption_key_from_environment(
    variable: str = "NEUROPROJECT_ENCRYPTION_KEY",
) -> str:
    """Load a required encryption key without providing an insecure default."""
    key = os.environ.get(variable)
    if not key:
        raise EncryptionConfigurationError(
            f"{variable} is not set; refusing to use an implicit encryption key."
        )
    _fernet(key)
    return key
