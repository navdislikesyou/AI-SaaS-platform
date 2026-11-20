"""Schemas for the Google OAuth Gmail connection.

Only the shapes that cross a router boundary live here. The counters produced
by a Gmail sync travel through the generic ``POST /agents/execute`` envelope as
an untyped object, so they are documented on the service method instead of
being modelled twice.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GoogleAuthorizeResponse(BaseModel):
    """Authorization URL the browser should navigate to.

    Attributes:
        authorization_url: Google's consent URL, already carrying the ``state``
            nonce and the PKCE challenge.
        expires_in_seconds: How long the pending state behind it survives.
            After that the client has to request a fresh URL.
    """

    model_config = ConfigDict(populate_by_name=True)

    authorization_url: str
    expires_in_seconds: int


class GoogleConnectionStatus(BaseModel):
    """Whether the caller's organization has a Gmail mailbox connected.

    Attributes:
        connected: True when a usable connection exists.
        gmail_address: The authorized mailbox address, or None. Always read
            from Google's profile at consent time, never configured.
        scopes: Granted OAuth scopes.
        connected_at: When the connection was last established.
        token_expires_at: Expiry of the stored access token, when known. The
            access token is refreshed on demand, so this is informational.
    """

    model_config = ConfigDict(populate_by_name=True)

    connected: bool
    gmail_address: str | None = None
    scopes: list[str] = Field(default_factory=list)
    connected_at: datetime | None = None
    token_expires_at: datetime | None = None
