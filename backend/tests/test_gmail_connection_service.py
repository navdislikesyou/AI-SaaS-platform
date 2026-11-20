"""Tests for the Google OAuth Gmail connection service.

These cover the three properties the connection depends on: the state nonce is
single-use, the stored credential is encrypted rather than written in the
clear, and a grant Google no longer honours is reported as "reconnect" instead
of leaking an upstream error. No test reaches the network -- the token
exchange and the Gmail client are replaced with fakes.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.services.gmail_connection as gmail_connection
from app.core.config import Settings
from app.core.exceptions import (
    AgentExecutionError,
    GmailNotConnectedError,
    GoogleOAuthNotConfiguredError,
    GoogleTokenUnavailableError,
    ValidationFailedError,
)
from app.core.token_encryption import decrypt_token
from app.models import GmailConnection, OAuthState
from app.services.gmail_connection import (
    build_authorization_url,
    build_gmail_service,
    consume_pending_state,
    create_pending_state,
    exchange_code,
    get_connection_status,
    revoke_connection,
    save_connection,
)

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"

#: Never a real address: automated tests must not reference a live mailbox.
TEST_MAILBOX = "hr@example.test"

REFRESH_SECRET = "1//test-refresh-secret-value"


@pytest.fixture
def google_settings() -> Settings:
    """Return settings in which every Google credential is present.

    Every Google field is set explicitly so a developer's local ``.env``
    cannot change what these assertions see.

    Returns:
        Settings with Google OAuth fully configured.
    """
    return Settings(
        environment="test",
        log_level="WARNING",
        google_oauth_enabled=True,
        google_client_id="client-id.apps.googleusercontent.com",
        google_client_secret="client-secret",
        google_token_encryption_key="test-encryption-passphrase",
    )


@pytest.fixture
def bind_test_sessions(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Route the service's session helper at the temporary test database.

    Args:
        session_factory: Session maker for the test database.
        monkeypatch: Fixture used to replace the session helper.
    """

    @asynccontextmanager
    async def open_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(gmail_connection, "get_session", open_session)


def _naive_utc(offset: timedelta) -> datetime:
    """Return a naive UTC timestamp, the form google-auth compares against.

    Args:
        offset: Distance from now.

    Returns:
        A naive datetime, because ``google.auth`` compares its expiry against
        a naive ``utcnow()`` and raises TypeError on a mixed comparison.
    """
    return (datetime.now(UTC) + offset).replace(tzinfo=None)


def _credential(expiry: datetime, refresh_token: str | None = REFRESH_SECRET) -> Credentials:
    """Build a Google credential in the shape the flow produces.

    Args:
        expiry: Access-token expiry, naive UTC.
        refresh_token: Refresh token to embed, or None.

    Returns:
        A credential that serializes with :meth:`Credentials.to_json`.
    """
    return Credentials(
        token="ya29.test-access-token",
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id="client-id.apps.googleusercontent.com",
        client_secret="client-secret",
        scopes=[GMAIL_SCOPE],
        expiry=expiry,
    )


async def _stored_row(
    session_factory: async_sessionmaker[AsyncSession],
    organization_id: str,
) -> GmailConnection | None:
    """Read an organization's connection row verbatim.

    Args:
        session_factory: Session maker for the test database.
        organization_id: Organization whose row to read.

    Returns:
        The row as persisted, or None when there is none.
    """
    async with session_factory() as session:
        result = await session.execute(
            select(GmailConnection).where(GmailConnection.organization_id == organization_id)
        )
        return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Pending state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_pending_state_is_consumed_exactly_once(
    make_organization: Any,
    make_user: Any,
    google_settings: Settings,
    bind_test_sessions: None,
) -> None:
    """A nonce binds the callback to one organization and then dies."""
    organization = await make_organization()
    manager = await make_user(
        "admin@example.test",
        role="admin",
        organization_id=organization.id,
    )

    state, challenge = await create_pending_state(organization.id, manager.id, google_settings)

    pending = await consume_pending_state(state, google_settings)
    assert pending.organization_id == organization.id
    assert pending.user_id == manager.id
    assert len(pending.pkce_verifier) >= 32
    assert pending.pkce_verifier not in state

    with pytest.raises(ValidationFailedError) as replay:
        await consume_pending_state(state, google_settings)

    assert replay.value.status_code == 422
    assert replay.value.details == {"reason": "invalid_oauth_state"}


@pytest.mark.asyncio
async def test_a_pending_state_issues_the_matching_pkce_challenge(
    make_organization: Any,
    make_user: Any,
    google_settings: Settings,
    bind_test_sessions: None,
) -> None:
    """The challenge is the S256 form of the stored verifier, not the verifier."""
    organization = await make_organization()
    manager = await make_user(
        "admin@example.test",
        role="admin",
        organization_id=organization.id,
    )

    state, challenge = await create_pending_state(organization.id, manager.id, google_settings)

    pending = await consume_pending_state(state, google_settings)
    digest = hashlib.sha256(pending.pkce_verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    assert challenge == expected
    assert challenge != pending.pkce_verifier


@pytest.mark.asyncio
async def test_an_unknown_state_is_rejected(
    google_settings: Settings,
    bind_test_sessions: None,
) -> None:
    """A nonce the server never issued cannot be redeemed."""
    with pytest.raises(ValidationFailedError) as exc_info:
        await consume_pending_state("not-a-real-state", google_settings)

    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_an_expired_state_is_rejected(
    make_organization: Any,
    make_user: Any,
    google_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    bind_test_sessions: None,
) -> None:
    """A nonce that outlived its TTL is no longer redeemable."""
    organization = await make_organization()
    manager = await make_user(
        "admin@example.test",
        role="admin",
        organization_id=organization.id,
    )
    state, _ = await create_pending_state(organization.id, manager.id, google_settings)

    async with session_factory() as session:
        await session.execute(
            OAuthState.__table__.update()
            .where(OAuthState.state_hash == hashlib.sha256(state.encode()).hexdigest())
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await session.commit()

    with pytest.raises(ValidationFailedError):
        await consume_pending_state(state, google_settings)


@pytest.mark.asyncio
async def test_the_state_nonce_is_stored_only_as_a_hash(
    make_organization: Any,
    make_user: Any,
    google_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    bind_test_sessions: None,
) -> None:
    """A database leak does not hand out redeemable states."""
    organization = await make_organization()
    manager = await make_user(
        "admin@example.test",
        role="admin",
        organization_id=organization.id,
    )
    state, _ = await create_pending_state(organization.id, manager.id, google_settings)

    async with session_factory() as session:
        result = await session.execute(
            select(OAuthState).where(OAuthState.organization_id == organization.id)
        )
        row = result.scalar_one()

    assert row.state_hash == hashlib.sha256(state.encode()).hexdigest()
    assert state not in row.state_hash
    assert len(row.state_hash) == 64


@pytest.mark.asyncio
async def test_creating_a_state_requires_the_oauth_credentials(
    make_organization: Any,
    make_user: Any,
    bind_test_sessions: None,
) -> None:
    """An unconfigured deployment refuses before writing anything."""
    organization = await make_organization()
    manager = await make_user(
        "admin@example.test",
        role="admin",
        organization_id=organization.id,
    )

    with pytest.raises(GoogleOAuthNotConfiguredError) as exc_info:
        await create_pending_state(
            organization.id,
            manager.id,
            # Every Google field is set explicitly so a developer's local
            # ``.env`` cannot make this deployment look configured.
            Settings(
                environment="test",
                google_oauth_enabled=True,
                google_client_id="",
                google_client_secret="",
                google_token_encryption_key="",
            ),
        )

    assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_saved_credential_is_never_written_in_the_clear(
    make_organization: Any,
    make_user: Any,
    google_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    bind_test_sessions: None,
) -> None:
    """Neither the access token nor the refresh token reaches disk readable."""
    organization = await make_organization()
    manager = await make_user(
        "admin@example.test",
        role="admin",
        organization_id=organization.id,
    )
    expiry = _naive_utc(timedelta(hours=1))

    await save_connection(
        organization.id,
        manager.id,
        _credential(expiry).to_json(),
        TEST_MAILBOX,
        google_settings,
    )

    row = await _stored_row(session_factory, organization.id)
    assert row is not None

    stored = row.credentials_encrypted
    assert REFRESH_SECRET not in stored
    assert "ya29.test-access-token" not in stored
    assert "refresh_token" not in stored
    assert row.gmail_address == TEST_MAILBOX
    assert row.token_expiry is not None
    # SQLite drops the offset it was given, so the instant is compared rather
    # than the representation.
    stored_expiry = row.token_expiry
    if stored_expiry.tzinfo is None:
        stored_expiry = stored_expiry.replace(tzinfo=UTC)
    assert stored_expiry == expiry.replace(tzinfo=UTC)


@pytest.mark.asyncio
async def test_connecting_twice_leaves_one_connection_for_the_organization(
    make_organization: Any,
    make_user: Any,
    google_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    bind_test_sessions: None,
) -> None:
    """A re-connect replaces the row rather than adding a second one."""
    organization = await make_organization()
    manager = await make_user(
        "admin@example.test",
        role="admin",
        organization_id=organization.id,
    )
    expiry = _naive_utc(timedelta(hours=1))

    await save_connection(
        organization.id, manager.id, _credential(expiry).to_json(), TEST_MAILBOX, google_settings
    )
    await save_connection(
        organization.id,
        manager.id,
        _credential(_naive_utc(timedelta(hours=2))).to_json(),
        "other@example.test",
        google_settings,
    )

    async with session_factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(GmailConnection)
            .where(GmailConnection.organization_id == organization.id)
        )

    assert count == 1
    row = await _stored_row(session_factory, organization.id)
    assert row is not None
    assert row.gmail_address == "other@example.test"
    assert row.connected_by_user_id == manager.id


@pytest.mark.asyncio
async def test_status_reports_a_disconnected_organization(
    make_organization: Any,
    bind_test_sessions: None,
) -> None:
    """An organization that never connected is reported as not connected."""
    organization = await make_organization()

    status = await get_connection_status(organization.id)

    assert status.connected is False
    assert status.gmail_address is None
    assert status.scopes == []


@pytest.mark.asyncio
async def test_status_reports_the_connected_mailbox_without_decrypting(
    make_organization: Any,
    make_user: Any,
    google_settings: Settings,
    bind_test_sessions: None,
) -> None:
    """Status answers from the plain columns, never from the blob."""
    organization = await make_organization()
    manager = await make_user(
        "admin@example.test",
        role="admin",
        organization_id=organization.id,
    )
    expiry = _naive_utc(timedelta(hours=1))

    await save_connection(
        organization.id, manager.id, _credential(expiry).to_json(), TEST_MAILBOX, google_settings
    )

    status = await get_connection_status(organization.id)

    assert status.connected is True
    assert status.gmail_address == TEST_MAILBOX
    assert status.scopes == [GMAIL_SCOPE]
    assert status.token_expires_at == expiry.replace(tzinfo=UTC)


@pytest.mark.asyncio
async def test_revoking_reports_whether_something_was_removed(
    make_organization: Any,
    make_user: Any,
    google_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    bind_test_sessions: None,
) -> None:
    """Disconnect deletes the row and a second call is honest about it."""
    organization = await make_organization()
    manager = await make_user(
        "admin@example.test",
        role="admin",
        organization_id=organization.id,
    )
    await save_connection(
        organization.id,
        manager.id,
        _credential(_naive_utc(timedelta(hours=1))).to_json(),
        TEST_MAILBOX,
        google_settings,
    )

    assert await revoke_connection(organization.id) is True
    assert await revoke_connection(organization.id) is False
    assert await _stored_row(session_factory, organization.id) is None
    assert (await get_connection_status(organization.id)).connected is False


# ---------------------------------------------------------------------------
# Building the client
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_building_a_client_without_a_connection_conflicts(
    make_organization: Any,
    google_settings: Settings,
    bind_test_sessions: None,
) -> None:
    """A permitted caller with no connection gets 409, not 500."""
    organization = await make_organization()

    with pytest.raises(GmailNotConnectedError) as exc_info:
        await build_gmail_service(organization.id, google_settings)

    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "GMAIL_NOT_CONNECTED"


@pytest.mark.asyncio
async def test_a_current_credential_is_used_without_refreshing(
    make_organization: Any,
    make_user: Any,
    google_settings: Settings,
    bind_test_sessions: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unexpired access token is not traded in for a new one."""
    organization = await make_organization()
    manager = await make_user(
        "admin@example.test",
        role="admin",
        organization_id=organization.id,
    )
    await save_connection(
        organization.id,
        manager.id,
        _credential(_naive_utc(timedelta(hours=1))).to_json(),
        TEST_MAILBOX,
        google_settings,
    )
    sentinel = object()
    monkeypatch.setattr(
        gmail_connection,
        "_refresh_credentials",
        lambda credentials: pytest.fail("refresh should not be needed"),
    )
    monkeypatch.setattr(gmail_connection, "_build_service", lambda credentials: sentinel)

    service = await build_gmail_service(organization.id, google_settings)

    assert service is sentinel


@pytest.mark.asyncio
async def test_an_expired_credential_is_refreshed_and_reencrypted(
    make_organization: Any,
    make_user: Any,
    google_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    bind_test_sessions: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refreshed token is persisted still encrypted, never in the clear."""
    organization = await make_organization()
    manager = await make_user(
        "admin@example.test",
        role="admin",
        organization_id=organization.id,
    )
    await save_connection(
        organization.id,
        manager.id,
        _credential(_naive_utc(timedelta(minutes=-10))).to_json(),
        TEST_MAILBOX,
        google_settings,
    )
    before = (await _stored_row(session_factory, organization.id)).credentials_encrypted

    def fake_refresh(credentials: Credentials) -> Credentials:
        credentials.token = "ya29.refreshed-access-token"
        credentials.expiry = _naive_utc(timedelta(hours=1))
        return credentials

    sentinel = object()
    monkeypatch.setattr(gmail_connection, "_refresh_credentials", fake_refresh)
    monkeypatch.setattr(gmail_connection, "_build_service", lambda credentials: sentinel)

    service = await build_gmail_service(organization.id, google_settings)
    assert service is sentinel

    row = await _stored_row(session_factory, organization.id)
    assert row is not None
    assert row.credentials_encrypted != before
    assert REFRESH_SECRET not in row.credentials_encrypted
    assert "ya29.refreshed-access-token" not in row.credentials_encrypted

    plaintext = json.loads(decrypt_token(row.credentials_encrypted, google_settings))
    assert plaintext["token"] == "ya29.refreshed-access-token"
    assert plaintext["refresh_token"] == REFRESH_SECRET

    assert row.token_expiry is not None
    stored_expiry = row.token_expiry
    if stored_expiry.tzinfo is None:
        stored_expiry = stored_expiry.replace(tzinfo=UTC)
    assert stored_expiry > datetime.now(UTC)


@pytest.mark.asyncio
async def test_a_grant_revoked_at_google_removes_the_connection(
    make_organization: Any,
    make_user: Any,
    google_settings: Settings,
    bind_test_sessions: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only a reconnect can fix a dead grant, so the row does not linger."""
    organization = await make_organization()
    manager = await make_user(
        "admin@example.test",
        role="admin",
        organization_id=organization.id,
    )
    await save_connection(
        organization.id,
        manager.id,
        _credential(_naive_utc(timedelta(minutes=-10))).to_json(),
        TEST_MAILBOX,
        google_settings,
    )

    def revoked(credentials: Credentials) -> Credentials:
        raise RefreshError("invalid_grant, Token has been expired or revoked.")

    monkeypatch.setattr(gmail_connection, "_refresh_credentials", revoked)

    with pytest.raises(GmailNotConnectedError) as exc_info:
        await build_gmail_service(organization.id, google_settings)

    assert exc_info.value.status_code == 409
    assert (await get_connection_status(organization.id)).connected is False


@pytest.mark.asyncio
async def test_a_transient_refresh_failure_keeps_the_connection(
    make_organization: Any,
    make_user: Any,
    google_settings: Settings,
    bind_test_sessions: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A network blip must not disconnect a mailbox that is still authorized."""
    organization = await make_organization()
    manager = await make_user(
        "admin@example.test",
        role="admin",
        organization_id=organization.id,
    )
    await save_connection(
        organization.id,
        manager.id,
        _credential(_naive_utc(timedelta(minutes=-10))).to_json(),
        TEST_MAILBOX,
        google_settings,
    )

    def timeout(credentials: Credentials) -> Credentials:
        raise RefreshError("timeout")

    monkeypatch.setattr(gmail_connection, "_refresh_credentials", timeout)

    with pytest.raises(AgentExecutionError) as exc_info:
        await build_gmail_service(organization.id, google_settings)

    assert exc_info.value.status_code == 502
    assert (await get_connection_status(organization.id)).connected is True


@pytest.mark.asyncio
async def test_a_credential_without_a_refresh_token_reports_not_connected(
    make_organization: Any,
    make_user: Any,
    google_settings: Settings,
    bind_test_sessions: None,
) -> None:
    """A credential Google stopped returning a refresh token for needs a re-connect."""
    organization = await make_organization()
    manager = await make_user(
        "admin@example.test",
        role="admin",
        organization_id=organization.id,
    )
    payload = {
        "token": "ya29.test-access-token",
        "refresh_token": None,
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "client-id.apps.googleusercontent.com",
        "client_secret": "client-secret",
        "scopes": [GMAIL_SCOPE],
        "expiry": _naive_utc(timedelta(minutes=-10)).isoformat(),
    }

    await save_connection(
        organization.id, manager.id, json.dumps(payload), TEST_MAILBOX, google_settings
    )

    with pytest.raises(GmailNotConnectedError):
        await build_gmail_service(organization.id, google_settings)


@pytest.mark.asyncio
async def test_a_credential_encrypted_with_another_key_reports_reconnect(
    make_organization: Any,
    make_user: Any,
    google_settings: Settings,
    bind_test_sessions: None,
) -> None:
    """A rotated passphrase is reported as an action to take, not a crash."""
    organization = await make_organization()
    manager = await make_user(
        "admin@example.test",
        role="admin",
        organization_id=organization.id,
    )
    await save_connection(
        organization.id,
        manager.id,
        _credential(_naive_utc(timedelta(hours=1))).to_json(),
        TEST_MAILBOX,
        google_settings,
    )
    rotated = Settings(
        environment="test",
        log_level="WARNING",
        google_oauth_enabled=True,
        google_client_id="client-id.apps.googleusercontent.com",
        google_client_secret="client-secret",
        google_token_encryption_key="a-different-passphrase",
    )

    with pytest.raises(GoogleTokenUnavailableError) as exc_info:
        await build_gmail_service(organization.id, rotated)

    assert exc_info.value.status_code == 503
    assert "reconnect" in exc_info.value.message.lower()


# ---------------------------------------------------------------------------
# Authorization URL
# ---------------------------------------------------------------------------


def test_the_authorization_url_carries_state_scope_and_pkce_challenge(
    google_settings: Settings,
) -> None:
    """Everything Google needs to return the browser safely is on the URL."""
    url = build_authorization_url("state-nonce", "challenge-value", google_settings)
    query = parse_qs(urlparse(url).query)

    assert urlparse(url).netloc == "accounts.google.com"
    assert query["response_type"] == ["code"]
    assert query["client_id"] == [google_settings.google_client_id]
    assert query["redirect_uri"] == [google_settings.google_redirect_uri]
    assert query["scope"] == [GMAIL_SCOPE]
    assert query["state"] == ["state-nonce"]
    assert query["code_challenge"] == ["challenge-value"]
    assert query["code_challenge_method"] == ["S256"]
    # Together these guarantee a refresh token on every connect.
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]


def test_authorization_is_unavailable_when_the_feature_is_off() -> None:
    """A deployment without Google credentials reports 503, not a stack trace."""
    settings = Settings(environment="test", google_oauth_enabled=False)

    with pytest.raises(GoogleOAuthNotConfiguredError) as exc_info:
        build_authorization_url("state", "challenge", settings)

    assert exc_info.value.status_code == 503


def test_a_missing_encryption_key_is_treated_as_unconfigured() -> None:
    """OAuth without an encryption passphrase is refused, never stored plain."""
    settings = Settings(
        environment="test",
        google_oauth_enabled=True,
        google_client_id="client-id",
        google_client_secret="client-secret",
        google_token_encryption_key="",
    )

    with pytest.raises(GoogleOAuthNotConfiguredError):
        build_authorization_url("state", "challenge", settings)


@pytest.mark.asyncio
async def test_exchanging_a_code_is_refused_when_unconfigured(
    make_organization: Any,
    make_user: Any,
) -> None:
    """The token exchange fails closed when any credential is missing."""
    organization = await make_organization()
    manager = await make_user(
        "admin@example.test",
        role="admin",
        organization_id=organization.id,
    )
    pending = type(
        "Pending",
        (),
        {"organization_id": organization.id, "user_id": manager.id, "pkce_verifier": "v" * 43},
    )()

    with pytest.raises(GoogleOAuthNotConfiguredError):
        await exchange_code(
            pending,
            "code-from-google",
            # Explicit empties keep the guard trip independent of any local
            # ``.env``: with no credentials the exchange must refuse before
            # it builds a flow or reaches Google.
            Settings(
                environment="test",
                google_oauth_enabled=True,
                google_client_id="",
                google_client_secret="",
                google_token_encryption_key="",
            ),
        )
