"""HTTP tests for the Google OAuth Gmail connection routes.

These exercise the routes through the real application: dependency overrides
stand in for the authenticated caller and for the settings, and the Google
network calls are replaced, so nothing here reaches Google or a developer's
local database.

The behaviour under test is the routes': role gating, the shape of the
envelope, and the guarantee that the callback always answers with a redirect
carrying one of a fixed set of reasons.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from google.oauth2.credentials import Credentials
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.api.v1.google_oauth as google_oauth_api
import app.services.gmail_connection as gmail_connection
from app.api.deps import get_current_user_from_token, get_settings_dep
from app.core.config import Settings
from app.core.exceptions import AgentExecutionError
from app.models import GmailConnection, OAuthState
from app.services.gmail_connection import save_connection
from tests.fakes import FakePrincipal

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"

#: Never a real address: automated tests must not reference a live mailbox.
TEST_MAILBOX = "hr@example.test"

CALLBACK_URL = "/api/v1/google/oauth/callback"


@pytest.fixture
def google_settings() -> Settings:
    """Return settings in which every Google credential is present.

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
        frontend_base_url="http://frontend.test",
    )


@pytest.fixture
def bind_test_sessions(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Route the connection service's session helper at the test database.

    Args:
        session_factory: Session maker for the test database.
        monkeypatch: Fixture used to replace the session helper.
    """

    @asynccontextmanager
    async def open_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(gmail_connection, "get_session", open_session)


@pytest.fixture
def google_client(
    app: Any,
    client: AsyncClient,
    google_settings: Settings,
    bind_test_sessions: None,
) -> AsyncIterator[AsyncClient]:
    """Return a client whose settings carry Google OAuth configuration.

    Args:
        app: The application under test.
        client: The shared HTTP client.
        google_settings: Settings with Google OAuth configured.
        bind_test_sessions: Routes the service at the test database.

    Yields:
        The same HTTP client, after the settings override is in place.
    """
    app.dependency_overrides[get_settings_dep] = lambda: google_settings
    yield client


def _sign_in_as(
    app: Any,
    organization_id: str | None,
    user_id: str,
    role: str,
) -> None:
    """Authenticate as one user with a chosen role.

    Args:
        app: The application under test.
        organization_id: Organization the caller belongs to, or None for a
            user outside any organization.
        user_id: User identifier the caller authenticates as.
        role: Role the caller holds.
    """
    app.dependency_overrides[get_current_user_from_token] = lambda: FakePrincipal(
        user_id=user_id,
        organization_id=organization_id,
        role=role,
    )


def _credentials_json(expiry_offset: timedelta) -> str:
    """Serialize a Google credential in the shape the flow produces.

    Args:
        expiry_offset: Distance of the access-token expiry from now.

    Returns:
        The credential as JSON.
    """
    credentials = Credentials(
        token="ya29.test-access-token",
        refresh_token="1//test-refresh-secret-value",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="client-id.apps.googleusercontent.com",
        client_secret="client-secret",
        scopes=[GMAIL_SCOPE],
        expiry=(datetime.now(UTC) + expiry_offset).replace(tzinfo=None),
    )
    return credentials.to_json()


async def _connect(
    session_factory: async_sessionmaker[AsyncSession],
    organization_id: str,
    user_id: str,
) -> None:
    """Store a connection for an organization, as a completed consent would.

    Args:
        session_factory: Session maker for the test database.
        organization_id: Organization that owns the connection.
        user_id: User who completed the consent.
    """
    settings = Settings(
        environment="test",
        log_level="WARNING",
        google_oauth_enabled=True,
        google_client_id="client-id.apps.googleusercontent.com",
        google_client_secret="client-secret",
        google_token_encryption_key="test-encryption-passphrase",
    )
    await save_connection(
        organization_id,
        user_id,
        _credentials_json(timedelta(hours=1)),
        TEST_MAILBOX,
        settings,
    )


# ---------------------------------------------------------------------------
# authorize
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_starting_a_connection_requires_the_manager_role(
    app: Any,
    google_client: AsyncClient,
    make_organization: Any,
    make_user: Any,
) -> None:
    """An employee cannot start an authorization for the shared mailbox."""
    organization = await make_organization()
    employee = await make_user(
        "employee@example.test",
        role="employee",
        organization_id=organization.id,
    )
    _sign_in_as(app, organization.id, employee.id, "employee")

    response = await google_client.get("/api/v1/google/oauth/authorize")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_starting_a_connection_returns_the_google_consent_url(
    app: Any,
    google_client: AsyncClient,
    make_organization: Any,
    make_user: Any,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A manager receives a consent URL, and a state is recorded behind it."""
    organization = await make_organization()
    manager = await make_user(
        "admin@example.test",
        role="manager",
        organization_id=organization.id,
    )
    _sign_in_as(app, organization.id, manager.id, "manager")

    response = await google_client.get("/api/v1/google/oauth/authorize")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True

    url = urlparse(body["data"]["authorization_url"])
    query = parse_qs(url.query)
    assert url.netloc == "accounts.google.com"
    assert query["scope"] == [GMAIL_SCOPE]
    assert query["access_type"] == ["offline"]
    assert query["code_challenge_method"] == ["S256"]
    assert body["data"]["expires_in_seconds"] > 0

    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(OAuthState).where(OAuthState.organization_id == organization.id)
                )
            )
            .scalars()
            .all()
        )

    assert len(rows) == 1
    assert rows[0].user_id == manager.id
    # The nonce itself is never stored, only its hash.
    assert rows[0].state_hash != query["state"][0]
    assert len(rows[0].state_hash) == 64


@pytest.mark.asyncio
async def test_starting_a_connection_requires_an_organization(
    app: Any,
    google_client: AsyncClient,
) -> None:
    """A manager outside any organization has no mailbox to connect."""
    _sign_in_as(app, None, "root-user", "admin")

    response = await google_client.get("/api/v1/google/oauth/authorize")

    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "missing_organization"


@pytest.mark.asyncio
async def test_starting_a_connection_reports_an_unconfigured_deployment(
    app: Any,
    client: AsyncClient,
    make_organization: Any,
    make_user: Any,
) -> None:
    """Without Google credentials the route answers 503, not a stack trace."""
    organization = await make_organization()
    admin = await make_user(
        "admin@example.test",
        role="admin",
        organization_id=organization.id,
    )
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="test",
        log_level="WARNING",
        google_oauth_enabled=False,
    )
    _sign_in_as(app, organization.id, admin.id, "admin")

    response = await client.get("/api/v1/google/oauth/authorize")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "GOOGLE_OAUTH_NOT_CONFIGURED"


# ---------------------------------------------------------------------------
# connection status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reading_the_connection_requires_the_manager_role(
    app: Any,
    google_client: AsyncClient,
    make_organization: Any,
    make_user: Any,
) -> None:
    """An employee cannot inspect the organization's mailbox."""
    organization = await make_organization()
    employee = await make_user(
        "employee@example.test",
        role="employee",
        organization_id=organization.id,
    )
    _sign_in_as(app, organization.id, employee.id, "employee")

    response = await google_client.get("/api/v1/google/connection")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_connection_status_reports_the_connected_mailbox(
    app: Any,
    google_client: AsyncClient,
    make_organization: Any,
    make_user: Any,
    session_factory: async_sessionmaker[AsyncSession],
    bind_test_sessions: None,
) -> None:
    """A connected organization sees its address and never its credential."""
    organization = await make_organization()
    admin = await make_user(
        "admin@example.test",
        role="admin",
        organization_id=organization.id,
    )
    _sign_in_as(app, organization.id, admin.id, "admin")
    await _connect(session_factory, organization.id, admin.id)

    response = await google_client.get("/api/v1/google/connection")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["connected"] is True
    assert data["gmail_address"] == TEST_MAILBOX
    assert data["scopes"] == [GMAIL_SCOPE]

    raw = response.text
    assert "refresh" not in raw.lower()
    assert "1//test-refresh-secret-value" not in raw
    assert "ya29.test-access-token" not in raw


@pytest.mark.asyncio
async def test_connection_status_reports_a_disconnected_organization(
    app: Any,
    google_client: AsyncClient,
    make_organization: Any,
    make_user: Any,
) -> None:
    """An organization that never connected is not an error."""
    organization = await make_organization()
    admin = await make_user(
        "admin@example.test",
        role="admin",
        organization_id=organization.id,
    )
    _sign_in_as(app, organization.id, admin.id, "admin")

    response = await google_client.get("/api/v1/google/connection")

    assert response.status_code == 200
    assert response.json()["data"]["connected"] is False


@pytest.mark.asyncio
async def test_connection_status_is_scoped_to_the_callers_organization(
    app: Any,
    google_client: AsyncClient,
    make_organization: Any,
    make_user: Any,
    session_factory: async_sessionmaker[AsyncSession],
    bind_test_sessions: None,
) -> None:
    """One tenant's connection is invisible to another tenant."""
    first = await make_organization("First", "first")
    second = await make_organization("Second", "second")
    first_admin = await make_user(
        "first-admin@example.test",
        role="admin",
        organization_id=first.id,
    )
    second_admin = await make_user(
        "second-admin@example.test",
        role="admin",
        organization_id=second.id,
    )
    await _connect(session_factory, first.id, first_admin.id)
    _sign_in_as(app, second.id, second_admin.id, "admin")

    response = await google_client.get("/api/v1/google/connection")

    assert response.status_code == 200
    assert response.json()["data"]["connected"] is False


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disconnecting_requires_the_manager_role(
    app: Any,
    google_client: AsyncClient,
    make_organization: Any,
    make_user: Any,
) -> None:
    """An employee cannot disconnect the organization's mailbox."""
    organization = await make_organization()
    employee = await make_user(
        "employee@example.test",
        role="employee",
        organization_id=organization.id,
    )
    _sign_in_as(app, organization.id, employee.id, "employee")

    response = await google_client.delete("/api/v1/google/connection")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_disconnecting_removes_the_connection_and_is_truthful_about_it(
    app: Any,
    google_client: AsyncClient,
    make_organization: Any,
    make_user: Any,
    session_factory: async_sessionmaker[AsyncSession],
    bind_test_sessions: None,
) -> None:
    """The first call removes the row; the second admits there was none."""
    organization = await make_organization()
    admin = await make_user(
        "admin@example.test",
        role="admin",
        organization_id=organization.id,
    )
    _sign_in_as(app, organization.id, admin.id, "admin")
    await _connect(session_factory, organization.id, admin.id)

    first = await google_client.delete("/api/v1/google/connection")
    second = await google_client.delete("/api/v1/google/connection")
    status = await google_client.get("/api/v1/google/connection")

    assert first.status_code == 200
    assert first.json()["data"] == {"removed": True}
    assert second.json()["data"] == {"removed": False}
    assert status.json()["data"]["connected"] is False


# ---------------------------------------------------------------------------
# callback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_callback_redirects_to_the_frontend_on_success(
    app: Any,
    google_client: AsyncClient,
    make_organization: Any,
    make_user: Any,
    session_factory: async_sessionmaker[AsyncSession],
    bind_test_sessions: None,
    monkeypatch: pytest.MonkeyPatch,
    google_settings: Settings,
) -> None:
    """A completed consent lands on the frontend reporting success."""
    organization = await make_organization()
    manager = await make_user(
        "admin@example.test",
        role="manager",
        organization_id=organization.id,
    )
    state, _ = await gmail_connection.create_pending_state(
        organization.id, manager.id, google_settings
    )

    async def fake_exchange(pending: Any, code: str, settings: Settings) -> tuple[str, str]:
        return _credentials_json(timedelta(hours=1)), TEST_MAILBOX

    monkeypatch.setattr(gmail_connection, "exchange_code", fake_exchange)

    response = await google_client.get(
        CALLBACK_URL, params={"state": state, "code": "code-from-google"}
    )

    assert response.status_code == 302
    location = urlparse(str(response.headers["location"]))
    assert f"{location.scheme}://{location.netloc}" == google_settings.frontend_base_url
    assert location.path == "/insights"
    assert parse_qs(location.query) == {"gmail": ["success"]}

    # The mailbox is now visible to the manager who connected it.
    _sign_in_as(app, organization.id, manager.id, "manager")
    status = await google_client.get("/api/v1/google/connection")
    assert status.status_code == 200
    assert status.json()["data"]["gmail_address"] == TEST_MAILBOX


@pytest.mark.asyncio
async def test_the_callback_redirects_for_an_unknown_state(
    google_client: AsyncClient,
    google_settings: Settings,
    bind_test_sessions: None,
) -> None:
    """A forged or stale nonce is refused with a redirect, not a 500."""
    response = await google_client.get(
        CALLBACK_URL, params={"state": "forged-nonce", "code": "code-from-google"}
    )

    assert response.status_code == 302
    query = parse_qs(urlparse(str(response.headers["location"])).query)
    assert query == {"gmail": ["invalid_state"]}


@pytest.mark.asyncio
async def test_the_callback_redirects_when_the_user_declines(
    google_client: AsyncClient,
    bind_test_sessions: None,
) -> None:
    """Consent refused at Google is reported as denied, with no code needed."""
    response = await google_client.get(
        CALLBACK_URL, params={"error": "access_denied", "state": "anything"}
    )

    assert response.status_code == 302
    query = parse_qs(urlparse(str(response.headers["location"])).query)
    assert query == {"gmail": ["denied"]}


@pytest.mark.asyncio
async def test_the_callback_redirects_when_the_feature_is_not_configured(
    app: Any,
    client: AsyncClient,
    bind_test_sessions: None,
) -> None:
    """An unconfigured deployment still answers the browser with a redirect."""
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="test",
        log_level="WARNING",
        google_oauth_enabled=False,
        frontend_base_url="http://frontend.test",
    )

    response = await client.get(CALLBACK_URL, params={"state": "state", "code": "code"})

    assert response.status_code == 302
    query = parse_qs(urlparse(str(response.headers["location"])).query)
    assert query == {"gmail": ["not_configured"]}


@pytest.mark.asyncio
async def test_the_callback_redirects_when_google_refuses_the_code(
    google_client: AsyncClient,
    make_organization: Any,
    make_user: Any,
    bind_test_sessions: None,
    monkeypatch: pytest.MonkeyPatch,
    google_settings: Settings,
) -> None:
    """An upstream failure becomes a reason; it never reaches the browser."""
    organization = await make_organization()
    manager = await make_user(
        "admin@example.test",
        role="manager",
        organization_id=organization.id,
    )
    state, _ = await gmail_connection.create_pending_state(
        organization.id, manager.id, google_settings
    )

    async def refuse(pending: Any, code: str, settings: Settings) -> tuple[str, str]:
        raise AgentExecutionError(
            "Google could not complete the sign-in. Please try again.",
            details={"reason": "oauth_exchange_failed"},
        )

    monkeypatch.setattr(gmail_connection, "exchange_code", refuse)

    response = await google_client.get(CALLBACK_URL, params={"state": state, "code": "bad-code"})

    assert response.status_code == 302
    query = parse_qs(urlparse(str(response.headers["location"])).query)
    assert query == {"gmail": ["exchange_failed"]}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("params"),
    [
        {},
        {"state": "", "code": ""},
        {"state": "only-state"},
        {"code": "only-code"},
    ],
)
async def test_the_callback_always_answers_with_a_redirect(
    google_client: AsyncClient,
    bind_test_sessions: None,
    params: dict[str, str],
) -> None:
    """Whatever the browser arrives with, the response is a usable redirect."""
    response = await google_client.get(CALLBACK_URL, params=params)

    assert response.status_code == 302
    location = str(response.headers["location"])
    query = parse_qs(urlparse(location).query)
    assert set(query) == {"gmail"}
    assert query["gmail"][0] in google_oauth_api.CALLBACK_REASONS


@pytest.mark.asyncio
async def test_the_callback_never_echoes_upstream_text(
    google_client: AsyncClient,
    make_organization: Any,
    make_user: Any,
    bind_test_sessions: None,
    monkeypatch: pytest.MonkeyPatch,
    google_settings: Settings,
) -> None:
    """An upstream message carrying a path cannot travel back in the URL."""
    organization = await make_organization()
    manager = await make_user(
        "admin@example.test",
        role="manager",
        organization_id=organization.id,
    )
    state, _ = await gmail_connection.create_pending_state(
        organization.id, manager.id, google_settings
    )

    async def refuse(pending: Any, code: str, settings: Settings) -> tuple[str, str]:
        raise AgentExecutionError(
            "token exchange failed for C:\\saas platform\\secrets\\client_secret.json",
            details={"reason": "oauth_exchange_failed"},
        )

    monkeypatch.setattr(gmail_connection, "exchange_code", refuse)

    response = await google_client.get(CALLBACK_URL, params={"state": state, "code": "code"})

    location = str(response.headers["location"])
    assert "saas" not in location.lower()
    assert "client_secret" not in location
    assert "%5C" not in location


@pytest.mark.asyncio
async def test_saving_the_exchanged_credential_is_encrypted(
    google_client: AsyncClient,
    make_organization: Any,
    make_user: Any,
    session_factory: async_sessionmaker[AsyncSession],
    bind_test_sessions: None,
    monkeypatch: pytest.MonkeyPatch,
    google_settings: Settings,
) -> None:
    """The credential the callback persists is unreadable in the database."""
    organization = await make_organization()
    manager = await make_user(
        "admin@example.test",
        role="manager",
        organization_id=organization.id,
    )
    state, _ = await gmail_connection.create_pending_state(
        organization.id, manager.id, google_settings
    )

    async def fake_exchange(pending: Any, code: str, settings: Settings) -> tuple[str, str]:
        return _credentials_json(timedelta(hours=1)), TEST_MAILBOX

    monkeypatch.setattr(gmail_connection, "exchange_code", fake_exchange)

    response = await google_client.get(CALLBACK_URL, params={"state": state, "code": "code"})
    assert response.status_code == 302

    async with session_factory() as session:
        row = (
            await session.execute(
                select(GmailConnection).where(GmailConnection.organization_id == organization.id)
            )
        ).scalar_one()

    stored = row.credentials_encrypted
    assert "1//test-refresh-secret-value" not in stored
    assert "ya29.test-access-token" not in stored
    assert "refresh_token" not in stored
    assert row.gmail_address == TEST_MAILBOX
