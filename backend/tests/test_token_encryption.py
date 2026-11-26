"""Tests for encryption of stored Google OAuth credentials.

A refresh token grants ongoing access to a mailbox, so the properties that
matter are: it round-trips, it never appears in plaintext, and a wrong or
missing passphrase fails loudly instead of falling back to unencrypted storage.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.exceptions import GoogleOAuthNotConfiguredError, GoogleTokenUnavailableError
from app.core.token_encryption import decrypt_token, encrypt_token

PLAINTEXT = '{"token": "ya29.example", "refresh_token": "1//secret-value"}'

PASSPHRASE = "correct horse battery staple"


def _settings(key: str = PASSPHRASE) -> Settings:
    """Return settings carrying an explicit encryption passphrase.

    Args:
        key: The passphrase to configure.

    Returns:
        Settings that do not depend on the developer's local ``.env``.
    """
    return Settings(google_token_encryption_key=key)


def test_round_trip_returns_the_original_credential() -> None:
    """Encrypting then decrypting reproduces the credential exactly."""
    settings = _settings()

    assert decrypt_token(encrypt_token(PLAINTEXT, settings), settings) == PLAINTEXT


def test_stored_value_never_contains_the_credential() -> None:
    """The ciphertext carries no fragment of what was encrypted."""
    ciphertext = encrypt_token(PLAINTEXT, _settings())

    assert PLAINTEXT not in ciphertext
    assert "refresh_token" not in ciphertext
    assert "ya29.example" not in ciphertext
    assert "secret-value" not in ciphertext


def test_encrypting_the_same_value_twice_produces_different_ciphertext() -> None:
    """Each encryption uses a fresh IV, so identical secrets do not correlate."""
    settings = _settings()

    assert encrypt_token(PLAINTEXT, settings) != encrypt_token(PLAINTEXT, settings)


def test_a_different_passphrase_cannot_decrypt() -> None:
    """A rotated passphrase reports an actionable 503 rather than garbage."""
    ciphertext = encrypt_token(PLAINTEXT, _settings("key-one"))

    with pytest.raises(GoogleTokenUnavailableError) as exc_info:
        decrypt_token(ciphertext, _settings("key-two"))

    assert exc_info.value.status_code == 503
    assert exc_info.value.error_code == "GOOGLE_TOKEN_UNAVAILABLE"


def test_decrypt_failure_does_not_leak_ciphertext_or_library_text() -> None:
    """The returned message is fixed; internals stay in the server log."""
    with pytest.raises(GoogleTokenUnavailableError) as exc_info:
        decrypt_token("definitely-not-a-fernet-token", _settings())

    message = exc_info.value.message.lower()
    assert "fernet" not in message
    assert "invalid token" not in message
    assert "definitely-not" not in message


def test_missing_passphrase_refuses_to_encrypt() -> None:
    """There is no unencrypted fallback when the key is absent."""
    with pytest.raises(GoogleOAuthNotConfiguredError):
        encrypt_token(PLAINTEXT, Settings(google_token_encryption_key=""))


def test_missing_passphrase_refuses_to_decrypt() -> None:
    """Decryption fails the same way rather than treating the value as plain."""
    with pytest.raises(GoogleOAuthNotConfiguredError):
        decrypt_token("stored-value", Settings(google_token_encryption_key=""))


def test_oauth_is_configured_only_when_every_credential_is_present() -> None:
    """The encryption passphrase is a precondition, not an optional extra."""
    base: dict[str, object] = {
        "google_oauth_enabled": True,
        "google_client_id": "client-id",
        "google_client_secret": "client-secret",
        "google_token_encryption_key": PASSPHRASE,
    }
    # Every Google field is set explicitly so a developer's local .env cannot
    # change what these assertions see.
    empty = {
        "google_oauth_enabled": False,
        "google_client_id": "",
        "google_client_secret": "",
        "google_token_encryption_key": "",
    }

    assert Settings(**base).google_oauth_configured is True
    assert Settings(**{**base, "google_token_encryption_key": ""}).google_oauth_configured is False
    assert Settings(**{**base, "google_client_secret": ""}).google_oauth_configured is False
    assert Settings(**{**base, "google_client_id": ""}).google_oauth_configured is False
    assert Settings(**{**base, "google_oauth_enabled": False}).google_oauth_configured is False
    assert Settings(**empty).google_oauth_configured is False
