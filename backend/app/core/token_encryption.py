"""Encryption for stored third-party OAuth credentials.

A refresh token is a long-lived credential: anyone holding it keeps reading the
mailbox it was issued for, so it is never written to the database in plaintext.
The passphrase comes from settings and is stretched into a Fernet key with
SHA-256, which lets any non-empty secret be used without requiring a
base64-encoded key.

Rotating the passphrase invalidates every stored credential. A value encrypted
under the old key cannot be decrypted under the new one, and the caller is told
to reconnect rather than being shown a decryption error, because that is the
only action that fixes it.
"""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings
from app.core.exceptions import (
    GoogleOAuthNotConfiguredError,
    GoogleTokenUnavailableError,
)

logger = logging.getLogger(__name__)


def _fernet(settings: Settings) -> Fernet:
    """Build the Fernet instance keyed by the configured passphrase.

    Args:
        settings: Application settings, read for the encryption passphrase.

    Returns:
        A Fernet instance derived from the passphrase.

    Raises:
        GoogleOAuthNotConfiguredError: If no passphrase is configured. There
            is deliberately no unencrypted fallback.
    """
    secret = settings.google_token_encryption_key
    if not secret:
        raise GoogleOAuthNotConfiguredError(GoogleOAuthNotConfiguredError.DEFAULT_MESSAGE)

    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_token(plaintext: str, settings: Settings) -> str:
    """Encrypt a credential so it can be stored.

    Args:
        plaintext: The credential text, typically ``Credentials.to_json()``.
        settings: Application settings, read for the encryption passphrase.

    Returns:
        An ASCII ciphertext safe to store in a text column.

    Raises:
        GoogleOAuthNotConfiguredError: If no passphrase is configured.
    """
    return _fernet(settings).encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_token(ciphertext: str, settings: Settings) -> str:
    """Decrypt a credential previously produced by :func:`encrypt_token`.

    Args:
        ciphertext: The stored ciphertext.
        settings: Application settings, read for the encryption passphrase.

    Returns:
        The original credential text.

    Raises:
        GoogleOAuthNotConfiguredError: If no passphrase is configured.
        GoogleTokenUnavailableError: If the ciphertext cannot be decrypted,
            which means the passphrase changed since it was stored.
    """
    fernet = _fernet(settings)

    try:
        return fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError) as exc:
        # Fernet's message describes the ciphertext internals, so it is logged
        # and replaced with a fixed, actionable message.
        logger.warning("google_token_decrypt_failed")
        raise GoogleTokenUnavailableError(GoogleTokenUnavailableError.DEFAULT_MESSAGE) from exc
