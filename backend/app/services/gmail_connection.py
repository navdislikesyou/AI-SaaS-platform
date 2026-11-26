"""Google OAuth connection backing the Employee Insights Gmail source.

One Gmail mailbox per organization. A manager starts the flow, Google returns
the browser to a callback that carries no access token, and the binding between
the two therefore lives server-side in a single-use state row keyed by a hash
of the nonce.

Three properties are load bearing:

- **Nothing is stored in plaintext.** The Google credential blob is encrypted
  by :mod:`app.core.token_encryption` before it is written, so the long-lived
  refresh token is out of reach at rest. The state nonce is likewise stored
  only as a SHA-256 hash.
- **One connection per organization**, enforced by a unique constraint rather
  than by application logic, so a race cannot produce two.
- **Google is only ever reached on a worker thread.** The token exchange, the
  profile lookup, the token refresh, and building the Gmail client are all
  blocking and synchronous.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import anyio
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import get_session
from app.core.exceptions import (
    AgentExecutionError,
    GmailNotConnectedError,
    GoogleOAuthNotConfiguredError,
    GoogleTokenUnavailableError,
    ValidationFailedError,
)
from app.core.token_encryption import decrypt_token, encrypt_token
from app.models import GmailConnection, OAuthState
from app.schemas.google import GoogleConnectionStatus

logger = logging.getLogger(__name__)

#: Gmail API binding used by :func:`googleapiclient.discovery.build`.
GMAIL_API_NAME = "gmail"
GMAIL_API_VERSION = "v1"

#: Endpoints Google's web client configuration requires. These are public,
#: documented constants, not secrets; only the client id and secret vary.
_GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
_GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"


@dataclass(frozen=True)
class PendingState:
    """A consumed OAuth state, carrying everything the callback still needs.

    Attributes:
        id: The state row identifier.
        organization_id: Organization the connection will belong to.
        user_id: User who initiated the flow.
        pkce_verifier: PKCE verifier to redeem the authorization code with.
            Short-lived and single-use, so it is safe to hold in memory for the
            duration of the exchange.
    """

    id: str
    organization_id: str
    user_id: str
    pkce_verifier: str


def _require_configured(settings: Settings) -> None:
    """Refuse to build a Google flow when any credential is missing.

    Args:
        settings: Application settings.

    Raises:
        GoogleOAuthNotConfiguredError: If the feature is off or a credential,
            including the encryption passphrase, is absent.
    """
    if not settings.google_oauth_configured:
        raise GoogleOAuthNotConfiguredError(GoogleOAuthNotConfiguredError.DEFAULT_MESSAGE)


def requested_gmail_scopes(settings: Settings) -> list[str]:
    """Return the scopes every new authorization requests.

    ``gmail.readonly`` (Employee Insights) and ``gmail.send`` (Automation
    Agent sending) are both requested so a single connected mailbox serves
    both features. The order is stable so tests and log lines can compare.

    Args:
        settings: Application settings.

    Returns:
        The de-duplicated list of requested Gmail scopes.
    """
    scopes: list[str] = []
    for scope in (settings.gmail_readonly_scope, settings.gmail_send_scope):
        if scope and scope not in scopes:
            scopes.append(scope)
    return scopes


def _granted_scopes(credentials_json: str, settings: Settings) -> str:
    """Return the scopes actually granted by Google for this credential.

    Google's serialized credential carries the ``scopes`` list it issued.
    Persisting those (rather than assuming the requested set) keeps the
    stored row honest when a user unchecks a scope on the consent screen.
    Falls back to the requested scopes only when the credential does not
    advertise them.

    Args:
        credentials_json: Serialized Google credential.
        settings: Application settings.

    Returns:
        Space-delimited granted scopes.
    """
    granted: list[str] = []
    try:
        parsed = json.loads(credentials_json)
        raw = parsed.get("scopes") if isinstance(parsed, dict) else None
        if isinstance(raw, list):
            granted = [str(item) for item in raw if str(item).strip()]
    except (json.JSONDecodeError, TypeError, ValueError):
        granted = []
    if not granted:
        granted = requested_gmail_scopes(settings)
    return " ".join(granted)


def _client_config(settings: Settings) -> dict[str, Any]:
    """Build Google's web client configuration from settings.

    Built from settings rather than read from a ``credentials.json`` file so
    the deployment has exactly one source of configuration and no client
    secret is ever read from the repository.

    Args:
        settings: Application settings.

    Returns:
        A client configuration dict in Google's ``web`` shape.
    """
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": _GOOGLE_AUTH_URI,
            "token_uri": _GOOGLE_TOKEN_URI,
            "redirect_uri": settings.google_redirect_uri,
        }
    }


def _state_hash(state: str) -> str:
    """Hash a state nonce for storage.

    Args:
        state: The nonce handed to the browser.

    Returns:
        Its SHA-256 hex digest.
    """
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def _pkce_pair() -> tuple[str, str]:
    """Generate a PKCE verifier and its S256 challenge.

    Returns:
        The ``(verifier, challenge)`` pair. The verifier is stored server-side
        and the challenge is sent to Google.
    """
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def build_authorization_url(state: str, code_challenge: str, settings: Settings) -> str:
    """Build the Google consent URL for a pending authorization.

    Args:
        state: The nonce that binds the callback back to this attempt.
        code_challenge: The PKCE S256 challenge matching the stored verifier.
        settings: Application settings.

    Returns:
        The URL the browser should navigate to. No network call is made here.

    Raises:
        GoogleOAuthNotConfiguredError: If any credential is missing.
    """
    _require_configured(settings)

    flow = Flow.from_client_config(
        _client_config(settings),
        scopes=requested_gmail_scopes(settings),
    )
    flow.redirect_uri = settings.google_redirect_uri

    # access_type=offline plus prompt=consent together guarantee a refresh
    # token on every connect, including a re-connect after a disconnect.
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
        code_challenge=code_challenge,
        code_challenge_method="S256",
    )
    return authorization_url


async def create_pending_state(
    organization_id: str,
    user_id: str,
    settings: Settings,
) -> tuple[str, str]:
    """Record a pending authorization and return its challenge pair.

    Expired states are swept here rather than by a scheduled job: the volume
    is one row per connect attempt, so cleaning up on write is enough to keep
    the table bounded.

    Args:
        organization_id: Organization the resulting connection belongs to.
        user_id: User starting the flow.
        settings: Application settings, read for the state lifetime.

    Returns:
        The ``(state, code_challenge)`` pair. The state goes to Google, the
        challenge accompanies it, and the verifier stays in the database.

    Raises:
        ValidationFailedError: If the state cannot be persisted (422).
    """
    _require_configured(settings)

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(32)
    now = datetime.now(UTC)

    try:
        async with get_session() as session:
            await session.execute(delete(OAuthState).where(OAuthState.expires_at < now))
            session.add(
                OAuthState(
                    state_hash=_state_hash(state),
                    organization_id=organization_id,
                    user_id=user_id,
                    pkce_verifier=verifier,
                    expires_at=now + timedelta(seconds=settings.google_oauth_state_ttl_seconds),
                )
            )
            await session.commit()
    except Exception as exc:
        logger.exception("oauth_state_create_failed organization_id=%s", organization_id)
        raise ValidationFailedError(
            "The sign-in attempt could not be started. Please try again.",
            details={"reason": "oauth_state_store_failed"},
        ) from exc

    return state, challenge


async def consume_pending_state(state: str, settings: Settings) -> PendingState:
    """Consume a state nonce, so it can be used exactly once.

    The ``UPDATE ... WHERE consumed_at IS NULL`` is atomic, so two callbacks
    racing on the same nonce cannot both win: the loser sees no row. Unknown,
    expired, and already-consumed states are deliberately indistinguishable,
    because telling them apart would confirm which nonces ever existed.

    Args:
        state: The nonce returned by Google on the callback.
        settings: Unused; accepted so every state helper takes settings.

    Returns:
        The binding the callback needs to finish the exchange.

    Raises:
        ValidationFailedError: If the state is unknown, expired, or replayed.
    """
    now = datetime.now(UTC)

    async with get_session() as session:
        result = await session.execute(
            update(OAuthState)
            .where(OAuthState.state_hash == _state_hash(state))
            .where(OAuthState.consumed_at.is_(None))
            .where(OAuthState.expires_at > now)
            .values(consumed_at=now)
            .returning(
                OAuthState.id,
                OAuthState.organization_id,
                OAuthState.user_id,
                OAuthState.pkce_verifier,
            )
        )
        row = result.first()
        await session.commit()

    if row is None:
        logger.warning("oauth_state_rejected")
        raise ValidationFailedError(
            "The sign-in attempt could not be verified. Please try again.",
            details={"reason": "invalid_oauth_state"},
        )

    return PendingState(
        id=row.id,
        organization_id=row.organization_id,
        user_id=row.user_id,
        pkce_verifier=row.pkce_verifier,
    )


def _exchange_for_credential(
    client_config: dict[str, Any],
    scopes: list[str],
    redirect_uri: str,
    code: str,
    code_verifier: str,
) -> tuple[str, str]:
    """Redeem an authorization code and read the mailbox address.

    Blocking: performs the token exchange and one Gmail profile call.

    Args:
        client_config: Google web client configuration.
        scopes: Requested scopes.
        redirect_uri: Redirect URI registered on the client.
        code: The authorization code from Google.
        code_verifier: The PKCE verifier matching the sent challenge.

    Returns:
        The serialized credential and the authorized mailbox address. The
        address always comes from Google, never from configuration.

    Raises:
        Exception: If Google refuses the code or the profile cannot be read.
    """
    flow = Flow.from_client_config(client_config, scopes=scopes)
    flow.redirect_uri = redirect_uri
    flow.fetch_token(code=code, code_verifier=code_verifier)

    credentials = flow.credentials
    service = build(GMAIL_API_NAME, GMAIL_API_VERSION, credentials=credentials)
    profile = service.users().getProfile(userId="me").execute()

    address = profile.get("emailAddress") or ""
    if not address:
        raise ValueError("Google returned no mailbox address.")

    return credentials.to_json(), address


async def exchange_code(
    pending: PendingState,
    code: str,
    settings: Settings,
) -> tuple[str, str]:
    """Exchange an authorization code for a credential and mailbox address.

    Args:
        pending: The consumed state supplying the PKCE verifier.
        code: The authorization code from Google.
        settings: Application settings.

    Returns:
        The serialized credential and the authorized mailbox address.

    Raises:
        AgentExecutionError: If Google refuses the exchange. The upstream
            message is logged server-side and never returned.
    """
    _require_configured(settings)

    try:
        return await anyio.to_thread.run_sync(
            _exchange_for_credential,
            _client_config(settings),
            requested_gmail_scopes(settings),
            settings.google_redirect_uri,
            code,
            pending.pkce_verifier,
        )
    except Exception as exc:
        # Google's message can echo request details, so only a fixed
        # description reaches the client.
        logger.warning("google_oauth_exchange_failed organization_id=%s", pending.organization_id)
        raise AgentExecutionError(
            "Google could not complete the sign-in. Please try again.",
            details={"reason": "oauth_exchange_failed"},
        ) from exc


async def save_connection(
    organization_id: str,
    user_id: str,
    credentials_json: str,
    gmail_address: str,
    settings: Settings,
) -> None:
    """Store or replace an organization's Gmail connection.

    The credential is encrypted before it reaches the session, so no code path
    outside :mod:`app.core.token_encryption` ever holds a plaintext refresh
    token it could accidentally persist.

    Args:
        organization_id: Organization the connection belongs to.
        user_id: User who completed the consent.
        credentials_json: Serialized Google credential from :func:`exchange_code`.
        gmail_address: Authorized mailbox address.
        settings: Application settings, read for the encryption passphrase.

    Raises:
        ValidationFailedError: If the connection cannot be persisted (422).
    """
    encrypted = encrypt_token(credentials_json, settings)
    expiry = _expiry_from_json(credentials_json)

    try:
        async with get_session() as session:
            row = await _fetch_connection(session, organization_id)

            if row is None:
                session.add(
                    GmailConnection(
                        organization_id=organization_id,
                        connected_by_user_id=user_id,
                        gmail_address=gmail_address,
                        scopes=_granted_scopes(credentials_json, settings),
                        credentials_encrypted=encrypted,
                        token_expiry=expiry,
                    )
                )
            else:
                row.connected_by_user_id = user_id
                row.gmail_address = gmail_address
                row.scopes = _granted_scopes(credentials_json, settings)
                row.credentials_encrypted = encrypted
                row.token_expiry = expiry

            await session.commit()
    except Exception as exc:
        logger.exception("gmail_connection_save_failed organization_id=%s", organization_id)
        raise ValidationFailedError(
            "The Gmail connection could not be saved. Please try again.",
            details={"reason": "gmail_connection_store_failed"},
        ) from exc

    logger.info("gmail_connection_saved organization_id=%s", organization_id)


async def get_connection_status(organization_id: str) -> GoogleConnectionStatus:
    """Read an organization's connection status.

    The expiry is displayed from the column stored beside the encrypted blob,
    so this never has to decrypt anything to answer.

    Args:
        organization_id: Organization whose connection to report.

    Returns:
        The connection status. A missing row reports ``connected=False``.
    """
    async with get_session() as session:
        row = await _fetch_connection(session, organization_id)
        if row is None:
            return GoogleConnectionStatus(connected=False)

        return GoogleConnectionStatus(
            connected=True,
            gmail_address=row.gmail_address,
            scopes=[scope for scope in row.scopes.split() if scope],
            connected_at=_as_utc(row.created_at),
            token_expires_at=_as_utc(row.token_expiry),
        )


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalize a stored timestamp to an aware UTC datetime.

    SQLite has no timezone type, so a column declared ``timezone=True`` still
    reads back naive there while PostgreSQL returns aware. Normalizing once
    here keeps the API response identical on both backends, and never makes a
    caller guess which one it is talking to.

    Args:
        value: A timestamp read from the database, aware or naive.

    Returns:
        The same instant in UTC, or None when there is no value.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def revoke_connection(organization_id: str) -> bool:
    """Delete an organization's Gmail connection.

    Args:
        organization_id: Organization whose connection to remove.

    Returns:
        True when a connection existed and was removed.
    """
    async with get_session() as session:
        row = await _fetch_connection(session, organization_id)
        if row is None:
            return False
        await session.delete(row)
        await session.commit()

    logger.info("gmail_connection_revoked organization_id=%s", organization_id)
    return True


async def build_gmail_service(organization_id: str, settings: Settings) -> Any:
    """Build an authorized Gmail client for an organization.

    Decrypts the stored credential, refreshes it when it has expired, and
    builds the client. Every step that can touch the network runs on a worker
    thread.

    Args:
        organization_id: Organization whose mailbox to authorize against.
        settings: Application settings.

    Returns:
        A ``googleapiclient`` Gmail service bound to the stored credential.

    Raises:
        GmailNotConnectedError: If no connection exists, or if the stored
            grant has been revoked at Google and can no longer be refreshed.
        GoogleTokenUnavailableError: If the stored credential cannot be
            decrypted with the current passphrase.
        AgentExecutionError: If the refresh fails for a transient reason.
    """
    async with get_session() as session:
        row = await _fetch_connection(session, organization_id)
        if row is None:
            ciphertext, scopes = None, ""
        else:
            ciphertext, scopes = row.credentials_encrypted, row.scopes

    if ciphertext is None:
        raise GmailNotConnectedError(GmailNotConnectedError.DEFAULT_MESSAGE)

    credentials = _decode_credentials(ciphertext, scopes, settings)

    if not credentials.valid:
        credentials = await _refresh(organization_id, credentials, settings)

    return await anyio.to_thread.run_sync(_build_service, credentials)


async def _refresh(
    organization_id: str,
    credentials: Any,
    settings: Settings,
) -> Any:
    """Refresh an expired credential and persist the result.

    Args:
        organization_id: Organization whose connection to update.
        credentials: The credential to refresh.
        settings: Application settings, read for the encryption passphrase.

    Returns:
        The refreshed credential.

    Raises:
        GmailNotConnectedError: If Google reports the grant is gone, which
            only reconnecting can fix.
        AgentExecutionError: If the refresh failed for any other reason.
    """
    if not credentials.refresh_token:
        logger.warning("gmail_refresh_token_missing organization_id=%s", organization_id)
        raise GmailNotConnectedError(GmailNotConnectedError.DEFAULT_MESSAGE)

    try:
        refreshed = await anyio.to_thread.run_sync(_refresh_credentials, credentials)
    except RefreshError as exc:
        if "invalid_grant" in str(exc):
            # The user revoked access, or the grant expired. Only reconnecting
            # can restore it, so the dead connection is removed rather than
            # left in place to fail every future sync.
            logger.warning("gmail_grant_revoked organization_id=%s", organization_id)
            await revoke_connection(organization_id)
            raise GmailNotConnectedError(GmailNotConnectedError.DEFAULT_MESSAGE) from exc

        logger.warning("gmail_token_refresh_failed organization_id=%s", organization_id)
        raise AgentExecutionError(
            "The Gmail mailbox could not be refreshed. Please try again.",
            details={"reason": "gmail_refresh_failed"},
        ) from exc
    except Exception as exc:
        logger.warning("gmail_token_refresh_failed organization_id=%s", organization_id)
        raise AgentExecutionError(
            "The Gmail mailbox could not be refreshed. Please try again.",
            details={"reason": "gmail_refresh_failed"},
        ) from exc

    await _store_refreshed(organization_id, refreshed, settings)
    return refreshed


def _refresh_credentials(credentials: Any) -> Any:
    """Refresh a credential in place. Blocking.

    Args:
        credentials: The credential to refresh.

    Returns:
        The same credential object, refreshed.
    """
    credentials.refresh(Request())
    return credentials


def _build_service(credentials: Any) -> Any:
    """Build the Gmail client. Blocking.

    Args:
        credentials: The credential to bind.

    Returns:
        A ``googleapiclient`` Gmail service.
    """
    return build(GMAIL_API_NAME, GMAIL_API_VERSION, credentials=credentials)


async def _store_refreshed(
    organization_id: str,
    credentials: Any,
    settings: Settings,
) -> None:
    """Persist a refreshed credential back onto the connection.

    Args:
        organization_id: Organization whose connection to update.
        credentials: The refreshed credential.
        settings: Application settings, read for the encryption passphrase.
    """
    async with get_session() as session:
        row = await _fetch_connection(session, organization_id)
        if row is None:
            return
        row.credentials_encrypted = encrypt_token(credentials.to_json(), settings)
        row.token_expiry = _expiry(credentials)
        await session.commit()


async def _fetch_connection(session: AsyncSession, organization_id: str) -> GmailConnection | None:
    """Load an organization's connection row.

    Args:
        session: Active database session.
        organization_id: Organization whose connection to load.

    Returns:
        The row, or None when the organization has no connection.
    """
    result = await session.execute(
        select(GmailConnection).where(GmailConnection.organization_id == organization_id)
    )
    return result.scalar_one_or_none()


def _decode_credentials(ciphertext: str, scopes: str, settings: Settings) -> Any:
    """Rebuild a Google credential from its encrypted stored form.

    Args:
        ciphertext: The stored encrypted blob.
        scopes: Space-delimited scopes the credential was granted.
        settings: Application settings, read for the encryption passphrase.

    Returns:
        A credential object ready to use.

    Raises:
        GoogleTokenUnavailableError: If the blob cannot be decrypted or is not
            the JSON Google produced.
    """
    plaintext = decrypt_token(ciphertext, settings)

    try:
        info = json.loads(plaintext)
        return Credentials.from_authorized_user_info(info, scopes=scopes.split())
    except (ValueError, TypeError, AttributeError) as exc:
        # The blob decrypted but is not what Google wrote. Both causes have
        # the same fix, so they share one message.
        logger.warning("google_token_malformed")
        raise GoogleTokenUnavailableError(GoogleTokenUnavailableError.DEFAULT_MESSAGE) from exc


def _expiry_from_json(credentials_json: str) -> datetime | None:
    """Read the expiry out of a serialized credential.

    Google writes it as an RFC 3339 string with a literal ``Z`` suffix, for
    example ``2026-11-18T09:36:38.675008+00:00Z``. ``fromisoformat`` rejects
    that trailing ``Z`` once an offset is already present, so it is stripped
    and the offset is left to speak for itself.

    Args:
        credentials_json: The serialized credential.

    Returns:
        The expiry in UTC, or None when Google did not send one.
    """
    try:
        raw = json.loads(credentials_json).get("expiry")
    except (ValueError, TypeError):
        return None

    if not raw:
        return None

    try:
        text = str(raw).strip()
        if text.endswith(("Z", "z")):
            text = text[:-1]
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _expiry(credentials: Any) -> datetime | None:
    """Normalize a credential's expiry to an aware UTC datetime.

    Args:
        credentials: The credential to read.

    Returns:
        The expiry in UTC, or None when it is unknown.
    """
    expiry = getattr(credentials, "expiry", None)
    if expiry is None:
        return None
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=UTC)
    return expiry.astimezone(UTC)
