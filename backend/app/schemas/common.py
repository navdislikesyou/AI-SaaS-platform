"""Shared response schemas.

Every endpoint returns one of these envelopes so clients can parse responses
uniformly. Agent-specific data is carried as a generic object rather than a
typed model, because the shapes of the future agent results are not yet known.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field

DataT = TypeVar("DataT")


def utc_now() -> datetime:
    """Return the current UTC time.

    Returns:
        A timezone-aware datetime in UTC.
    """
    return datetime.now(UTC)


class ErrorDetail(BaseModel):
    """Structured error information.

    Attributes:
        code: Stable machine-readable error code.
        message: Human-readable description safe to show a user.
        details: Optional structured context.
    """

    code: str
    message: str
    details: Any | None = None


class APIResponse[DataT](BaseModel):
    """Standard success envelope.

    Attributes:
        success: Always true on success.
        data: The endpoint payload.
        message: Optional human-readable summary.
        request_id: Correlation id matching the response header.
    """

    model_config = ConfigDict(populate_by_name=True)

    success: bool = True
    data: DataT | None = None
    message: str | None = None
    request_id: str | None = None


class ErrorResponse(BaseModel):
    """Standard error envelope.

    Attributes:
        success: Always false on error.
        error: Structured error information.
        request_id: Correlation id matching the response header.
    """

    success: bool = False
    error: ErrorDetail
    request_id: str | None = None


class HealthResponse(BaseModel):
    """Liveness payload.

    Attributes:
        status: ``ok`` when the process is serving requests.
        app_name: Configured application name.
        version: Configured application version.
        environment: Deployment environment.
        timestamp: Server time in UTC.
    """

    status: str
    app_name: str
    version: str
    environment: str
    timestamp: datetime = Field(default_factory=utc_now)


class ReadCheck(BaseModel):
    """One named readiness check.

    Attributes:
        name: The component being checked.
        ready: Whether the component passed.
        detail: Optional explanation, especially for failures.
    """

    name: str
    ready: bool
    detail: str | None = None


class ReadinessResponse(BaseModel):
    """Readiness payload.

    Attributes:
        status: ``ready`` or ``not_ready``.
        checks: Individual component results.
        timestamp: Server time in UTC.
    """

    status: str
    checks: list[ReadCheck]
    timestamp: datetime = Field(default_factory=utc_now)


class UserPublic(BaseModel):
    """Public user profile returned by auth endpoints.

    Attributes:
        id: User UUID.
        email: User email (normalized).
        full_name: User's full name.
        role: User role (employee/manager/admin).
        organization_id: UUID of the owning organization, or ``None``.
        is_active: Whether the account is active.
        token_version: Current token version for revocation tracking.
        access_token: Access JWT, returned only by the auth endpoints. ``None``
            everywhere else, because a token is never part of a user listing.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str
    email: str
    full_name: str
    role: str
    organization_id: str | None = None
    is_active: bool
    token_version: int
    access_token: str | None = None


class UserCreated(UserPublic):
    """A newly created user, with the one-time password shown to the admin.

    The account is created with a random password that is returned here once
    so it can be delivered to the new user. Only the hash is stored, and the
    value is never included in any other response.

    Attributes:
        temporary_password: The generated password, shown once.
    """

    temporary_password: str | None = None


class UserSummary(BaseModel):
    """Summary user profile for listing endpoints.

    Omits ``token_version`` and other sensitive fields for bulk listings.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str
    email: str
    full_name: str
    role: str
    organization_id: str | None = None
    is_active: bool
