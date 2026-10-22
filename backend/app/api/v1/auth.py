"""Authentication endpoints for the AI SaaS Platform.

POST /api/v1/auth/login - authenticate user and issue tokens
POST /api/v1/auth/refresh - rotate refresh token (from HttpOnly cookie)
POST /api/v1/auth/logout - revoke refresh token and clear cookie
GET /api/v1/auth/me - return authenticated user profile
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_from_token
from app.core.config import Settings, get_settings
from app.core.database import get_async_session
from app.models import RefreshToken, User
from app.schemas import UserPublic

router = APIRouter(prefix="/auth", tags=["auth"])

#: Path the refresh cookie is scoped to. It has to cover every route that
#: reads the cookie, logout included: a cookie scoped to the refresh route
#: alone is never sent to logout, so logout would leave the token valid.
_COOKIE_PATH = "/api/v1/auth"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def _get_refresh_token_from_cookie(request: Request) -> str | None:
    """Read refresh token from the HttpOnly cookie set during login."""
    cookies = request.cookies
    return cookies.get("refresh_token")


def _issue_access_token(
    user_id: str,
    token_version: int,
    settings: Settings,
) -> str:
    """Return a signed access token for a user.

    The token carries the token version, so a session can be revoked by
    bumping it, and an expiry, so a token that was copied out of the browser
    stops working on its own. The refresh token is the long-lived credential;
    this one is deliberately short-lived.

    Args:
        user_id: The user the token belongs to.
        token_version: The token version the user currently holds.
        settings: Application settings, for the signing key and the lifetime.

    Returns:
        The signed access token.
    """
    import jwt as pyjwt

    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(minutes=settings.jwt_access_token_expire_minutes)

    return pyjwt.encode(
        {
            "sub": str(user_id),
            "token_version": token_version,
            "iat": issued_at,
            "exp": expires_at,
        },
        settings.jwt_secret_key,
        algorithm="HS256",
    )


@router.post("/login", response_model=UserPublic, status_code=status.HTTP_200_OK)
async def login(
    email: str,
    password: str,
    response: Response,
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> UserPublic:
    """Authenticate user and issue access JWT + refresh token cookie.

    - Access JWT is returned in response body (HS256, 15 min effective lifetime)
    - Refresh token is set in HttpOnly cookie (30 days, rotation on each use)
    """
    # Find user by normalized email
    result = await session.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        from app.core.exceptions import InvalidCredentialsError

        raise InvalidCredentialsError()

    # Verify password with Argon2
    password_hasher = PasswordHasher()
    try:
        password_hasher.verify(user.hashed_password, password)
    except Exception as exc:
        from app.core.exceptions import InvalidCredentialsError

        raise InvalidCredentialsError() from exc

    # Issue access JWT.
    #
    # The token carries the *new* token version. Signing in increments the
    # version to invalidate any refresh token issued earlier, so signing the
    # token with the old value would issue a token the server immediately
    # rejects as revoked.
    new_token_version = user.token_version + 1

    access_token = _issue_access_token(user.id, new_token_version, settings)

    # Issue refresh token (opaque, hashed with SHA-256, stored in DB)
    refresh_token_raw = secrets.token_urlsafe(64)
    refresh_token_hash = hashlib.sha256(refresh_token_raw.encode()).hexdigest()

    expires_at = datetime.now(UTC) + timedelta(days=30)

    new_refresh_token = RefreshToken(
        token_hash=refresh_token_hash,
        user_id=user.id,
        organization_id=user.organization_id,
        expires_at=expires_at,
        created_at=datetime.now(UTC),
    )

    session.add(new_refresh_token)
    await session.flush()

    # Set refresh token in HttpOnly cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token_raw,
        httponly=True,
        secure=settings.environment == "production",
        samesite=settings.samesite,
        max_age=30 * 24 * 60 * 60,  # 30 days
        path=_COOKIE_PATH,
    )

    # Increment token version to invalidate any old refresh tokens
    await session.execute(
        update(User).where(User.id == user.id).values(token_version=new_token_version)
    )
    await session.commit()

    return UserPublic(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        organization_id=user.organization_id,
        is_active=user.is_active,
        token_version=new_token_version,
        access_token=access_token,
    )


@router.post("/refresh", response_model=UserPublic, status_code=status.HTTP_200_OK)
async def refresh(
    response: Response,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> UserPublic:
    """Rotate refresh token: validate current token from cookie, issue new tokens.

    - Uses an atomic conditional database update so that only one concurrent
      request can successfully consume a given refresh token.
    - The losing request receives 401 "Invalid refresh token" and must retry
      with the new token issued by the winning request.
    - Rejects revoked/expired/reused refresh tokens
    - Old refresh token is invalidated (revoked_at set in DB) atomically
    - New refresh token is set in HttpOnly cookie
    - Access JWT is returned in response body
    """
    # Read refresh token from cookie
    refresh_token_raw = await _get_refresh_token_from_cookie(request)
    # Validate origin for CSRF protection.
    origin = request.headers.get("origin")
    trusted = settings.trusted_origins or []
    origin_allowed = origin in trusted or (
        origin is not None
        and settings.environment == "development"
        and any(origin.startswith(u) for u in trusted)
    )
    if not origin_allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid origin for refresh token operation",
        )

    if not refresh_token_raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Compute hash and atomically consume/validate the refresh token.
    # The UPDATE succeeds only if the token has not been revoked yet (revoked_at IS NULL).
    provided_hash = hashlib.sha256(refresh_token_raw.encode()).hexdigest()

    now = datetime.now(UTC)
    consumed_result = await session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == provided_hash)
        .where(RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
        .returning(RefreshToken.user_id, RefreshToken.organization_id)
    )
    # ``first()`` returns the row. ``scalar_one_or_none()`` would return only
    # the first column, so indexing it would take the first character of the
    # user id rather than the id itself.
    consumed = consumed_result.first()

    if consumed is None:
        # The token was already consumed (revoked_at was already set) by a
        # concurrent request.  Refresh the cookie with the latest state so the
        # client can re-present a valid token.
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token (already consumed)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = consumed[0]
    org_id = consumed[1]

    # Get the user
    user_result = await session.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()

    if not user or not user.is_active:
        # Invalidate the already-consumed token and fail cleanly
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == provided_hash)
            .values(revoked_at=now)
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Increment token version to invalidate any other old refresh tokens.
    #
    # The new value is computed before the update and reused afterwards. The
    # update synchronises the loaded user with the stored value, so reading
    # ``user.token_version`` after it would yield a version one higher than
    # the one the database holds, and the access token signed with it would
    # be refused as revoked.
    new_token_version = user.token_version + 1

    await session.execute(
        update(User).where(User.id == user.id).values(token_version=new_token_version)
    )

    # Issue new refresh token
    new_refresh_token_raw = secrets.token_urlsafe(64)
    new_refresh_token_hash = hashlib.sha256(new_refresh_token_raw.encode()).hexdigest()

    new_expires_at = now + timedelta(days=30)

    new_refresh_token = RefreshToken(
        token_hash=new_refresh_token_hash,
        user_id=user.id,
        organization_id=org_id,
        expires_at=new_expires_at,
        created_at=now,
    )

    session.add(new_refresh_token)

    # Commit the rotation. The consumed token, the new token, and the bumped
    # token version are all discarded when the session closes unless they are
    # committed here, which would leave the consumed token usable and the new
    # access token immediately invalid.
    await session.commit()

    # Set new refresh token in HttpOnly cookie
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token_raw,
        httponly=True,
        secure=settings.environment == "production",
        samesite=settings.samesite,
        max_age=30 * 24 * 60 * 60,
        path=_COOKIE_PATH,
    )

    # Issue new access JWT
    access_token = _issue_access_token(user.id, new_token_version, settings)

    return UserPublic(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        organization_id=org_id,
        is_active=user.is_active,
        token_version=new_token_version,
        access_token=access_token,
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    response: Response,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """Revoke current refresh token and clear the cookie."""
    # Read refresh token from cookie
    refresh_token_raw = await _get_refresh_token_from_cookie(request)
    # Validate origin for CSRF protection.
    origin = request.headers.get("origin")
    trusted = settings.trusted_origins or []
    origin_allowed = origin in trusted or (
        origin is not None
        and settings.environment == "development"
        and any(origin.startswith(u) for u in trusted)
    )
    if not origin_allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid origin for refresh token operation",
        )

    if refresh_token_raw:
        provided_hash = hashlib.sha256(refresh_token_raw.encode()).hexdigest()

        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == provided_hash)
            .values(revoked_at=datetime.now(UTC))
        )
        await session.commit()

    # Clear the refresh token cookie
    response.delete_cookie(
        key="refresh_token",
        path=_COOKIE_PATH,
    )

    return {"detail": "Successfully logged out"}


@router.get("/me", response_model=UserPublic, status_code=status.HTTP_200_OK)
async def me(
    current_user: User = Depends(get_current_user_from_token),
) -> UserPublic:
    """Return the authenticated user profile.

    - Requires valid access JWT in Authorization header
    - Returns 401 with WWW-Authenticate: Bearer if no valid token
    """
    return UserPublic(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        organization_id=current_user.organization_id,
        is_active=current_user.is_active,
        token_version=current_user.token_version,
    )
