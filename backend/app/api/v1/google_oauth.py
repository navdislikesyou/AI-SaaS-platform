"""Google OAuth routes for the Employee Insights Gmail connection.

Endpoints:

- ``GET /google/oauth/authorize`` -- return Google's consent URL (PKCE + state).
- ``GET /google/oauth/callback`` -- consume Google's redirect, store the
  encrypted credential, and redirect back to the frontend.
- ``GET /google/connection`` -- whether the organisation has a connected
  Gmail mailbox.
- ``DELETE /google/connection`` -- remove the stored connection.

The connection service in :mod:`app.services.gmail_connection` owns the
state nonce, the token exchange, the encrypted storage, and the Gmail client.
These routes only translate HTTP into service calls and always answer the
browser with a redirect, never with a stack trace.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import RedirectResponse

from app.api.deps import get_settings_dep, require_manager
from app.core.config import Settings
from app.core.exceptions import (
    AgentExecutionError,
    ForbiddenError,
    GoogleOAuthNotConfiguredError,
    ValidationFailedError,
)
from app.models import User
from app.schemas.common import APIResponse
from app.schemas.google import GoogleAuthorizeResponse, GoogleConnectionStatus
from app.services import gmail_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/google", tags=["google-oauth"])

#: Every reason the callback may hand the browser. The test suite asserts the
#: callback always answers with one of these, never an unguessed value.
CALLBACK_REASONS = frozenset(
    {
        "success",
        "invalid_state",
        "denied",
        "not_configured",
        "exchange_failed",
    }
)

_CALLBACK_PATH = "/insights"


def _redirect(settings: Settings, reason: str) -> RedirectResponse:
    """Send the browser back to the frontend with a single opaque reason."""
    return RedirectResponse(
        url=f"{settings.frontend_base_url}{_CALLBACK_PATH}?gmail={reason}",
        status_code=status.HTTP_302_FOUND,
    )


def _require_manager_and_organization(
    current_user: User,
) -> None:
    """Require the caller to be a manager+ in an organisation."""
    if not current_user.organization_id:
        raise ForbiddenError(
            "Google OAuth requires an authenticated organisation.",
            details={"reason": "missing_organization"},
        )


@router.get(
    "/oauth/authorize",
    response_model=APIResponse[GoogleAuthorizeResponse],
    status_code=status.HTTP_200_OK,
    summary="Start Google OAuth authorization",
    description="Return Google's consent URL for granting gmail.readonly access.",
)
async def authorize(
    current_user: User = Depends(require_manager),
    settings: Settings = Depends(get_settings_dep),
) -> APIResponse[GoogleAuthorizeResponse]:
    """Begin the OAuth flow for the caller's organisation."""
    _require_manager_and_organization(current_user)
    organization_id = current_user.organization_id
    assert organization_id is not None

    state, code_challenge = await gmail_connection.create_pending_state(
        organization_id,
        current_user.id,
        settings,
    )
    authorization_url = gmail_connection.build_authorization_url(state, code_challenge, settings)

    return APIResponse(
        data=GoogleAuthorizeResponse(
            authorization_url=authorization_url,
            expires_in_seconds=settings.google_oauth_state_ttl_seconds,
        ),
        message="Google consent URL issued.",
    )


@router.get(
    "/oauth/callback",
    summary="OAuth callback",
    description="Consume Google's authorization redirect and return to the frontend.",
)
async def callback(
    code: str | None = Query(None, description="Authorization code from Google."),
    state: str | None = Query(None, description="State nonce returned by /authorize."),
    error: str | None = Query(
        None, description="Error Google returned when the user declined consent."
    ),
    settings: Settings = Depends(get_settings_dep),
) -> RedirectResponse:
    """Complete the OAuth flow and redirect the browser back to the frontend."""
    # The user declined consent at Google: report it without a code.
    if error:
        return _redirect(settings, "denied")

    if not settings.google_oauth_configured:
        return _redirect(settings, "not_configured")

    if not state or not code:
        return _redirect(settings, "invalid_state")

    try:
        pending = await gmail_connection.consume_pending_state(state, settings)
    except ValidationFailedError:
        return _redirect(settings, "invalid_state")
    except Exception:  # pragma: no cover - defensive boundary
        logger.exception("oauth_state_consume_failed")
        return _redirect(settings, "invalid_state")

    try:
        credentials_json, gmail_address = await gmail_connection.exchange_code(
            pending, code, settings
        )
    except GoogleOAuthNotConfiguredError:
        return _redirect(settings, "not_configured")
    except AgentExecutionError:
        return _redirect(settings, "exchange_failed")
    except Exception:  # pragma: no cover - defensive boundary
        logger.exception("oauth_exchange_failed organization_id=%s", pending.organization_id)
        return _redirect(settings, "exchange_failed")

    try:
        await gmail_connection.save_connection(
            pending.organization_id,
            pending.user_id,
            credentials_json,
            gmail_address,
            settings,
        )
    except ValidationFailedError:
        return _redirect(settings, "exchange_failed")
    except Exception:  # pragma: no cover - defensive boundary
        logger.exception("gmail_connection_save_failed organization_id=%s", pending.organization_id)
        return _redirect(settings, "exchange_failed")

    return _redirect(settings, "success")


@router.get(
    "/connection",
    response_model=APIResponse[GoogleConnectionStatus],
    status_code=status.HTTP_200_OK,
    summary="Gmail connection status",
    description="Whether the caller's organisation has a connected Gmail mailbox.",
)
async def connection_status(
    current_user: User = Depends(require_manager),
    settings: Settings = Depends(get_settings_dep),
) -> APIResponse[GoogleConnectionStatus]:
    """Return the connection status for the caller's organisation."""
    _require_manager_and_organization(current_user)
    organization_id = current_user.organization_id
    assert organization_id is not None

    status_value = await gmail_connection.get_connection_status(organization_id)
    return APIResponse(
        data=status_value,
        message="Gmail connection status retrieved.",
    )


@router.delete(
    "/connection",
    response_model=APIResponse[dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="Disconnect Gmail",
    description="Remove the stored Gmail connection for the caller's organisation.",
)
async def disconnect(
    current_user: User = Depends(require_manager),
    settings: Settings = Depends(get_settings_dep),
) -> APIResponse[dict[str, Any]]:
    """Remove the organisation's stored Gmail connection."""
    _require_manager_and_organization(current_user)
    organization_id = current_user.organization_id
    assert organization_id is not None

    removed = await gmail_connection.revoke_connection(organization_id)
    return APIResponse(
        data={"removed": removed},
        message="Gmail connection removed." if removed else "No connection to remove.",
    )
