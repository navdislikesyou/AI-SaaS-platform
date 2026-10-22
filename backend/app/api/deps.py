"""Shared FastAPI dependencies.

Provides singletons for settings, the agent registry, the orchestrator, the
performance job manager, and auth dependencies. Auth is added here as the seam
so that routers do not need to change when auth is enabled/disabled.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import AgentRegistry
from app.core.config import Settings, get_settings
from app.core.database import get_async_session
from app.models import User, UserRole

#: Global singletons (initialized during app startup).
_registry: AgentRegistry | None = None
_orchestrator: Any = None  # Orchestrator type; kept here for process-wide access.
_job_manager: Any = None  # JobManager type; kept here for process-wide access.

#: OAuth2 scheme for access JWT. Points at login endpoint for FastAPI docs.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


#: OAuth2 scheme that returns the token if present, None otherwise.
#: Used by endpoints that support both authenticated and unauthenticated access.
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def user_context_for(user: User | None) -> dict[str, Any] | None:
    """Build the execution principal handed to an agent adapter.

    The context carries the caller's identity and organisation so an agent can
    scope what it reads and writes to one tenant. It is passed per request
    rather than kept in module state, so two concurrent requests can never see
    each other's principal.

    Args:
        user: The authenticated user, or None for an anonymous caller.

    Returns:
        A dictionary with ``user_id``, ``organization_id``, and ``role``, or
        None when the request carries no principal.
    """
    if user is None:
        return None

    return {
        "user_id": user.id,
        "organization_id": user.organization_id,
        "role": user.role,
    }


async def get_current_user_from_token_optional_principal(
    token: str = Depends(oauth2_scheme_optional),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> User | None:
    """Return the authenticated user if a valid token is present, otherwise None.

    Unlike ``get_current_user_from_token`` this never raises 401; it simply
    returns ``None`` when no valid token is supplied.  This is intended for
    endpoints that wish to support both authenticated and unauthenticated access.
    """
    if not token:
        return None

    try:
        payload = await _verify_jwt_token(token, settings)
    except HTTPException:
        return None

    user_id: str | None = payload.get("sub")
    token_version: int = payload.get("token_version", 0) or 0

    if not user_id:
        return None

    # Look up the user
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        return None

    # Check token version for revocation
    if user.token_version != token_version:
        return None

    return user


def init_registry(registry: AgentRegistry) -> None:
    """Install the process-wide agent registry.

    Args:
        registry: The registry to share across requests.
    """
    global _registry
    _registry = registry


def init_orchestrator(orchestrator: Any) -> None:
    """Install the process-wide orchestrator.

    Args:
        orchestrator: The orchestrator to share across requests.
    """
    global _orchestrator
    _orchestrator = orchestrator


def get_registry() -> AgentRegistry:
    """Return the process-wide agent registry.

    Returns:
        The registry built during application startup.

    Raises:
        RuntimeError: If the registry is not initialized.
    """
    if _registry is None:
        raise RuntimeError(
            "Agent registry is not initialized. Call init_registry() during startup."
        )
    return _registry


def get_orchestrator() -> Any:
    """Return the process-wide orchestrator.

    Returns:
        The orchestrator built during application startup.

    Raises:
        RuntimeError: If the orchestrator is not initialized.
    """
    if _orchestrator is None:
        raise RuntimeError(
            "Orchestrator is not initialized. Call init_orchestrator() during startup."
        )
    return _orchestrator


def get_job_manager() -> Any:
    """Return the process-wide performance job manager.

    Returns:
        The shared job manager.
    """
    global _job_manager
    if _job_manager is None:
        from app.services.job_manager import JobManager

        _job_manager = JobManager()
    return _job_manager


def init_job_manager(manager: Any) -> None:
    """Install the process-wide performance job manager.

    Args:
        manager: The job manager to share across requests.
    """
    global _job_manager

    _job_manager = manager


def get_settings_dep() -> Settings:
    """Return application settings.

    Returns:
        The cached settings instance.
    """
    return get_settings()


def get_dataset_upload_service(settings: Settings = Depends(get_settings_dep)) -> Any:
    """Return the process-wide Performance dataset upload service.

    The Performance dataset API accepts structured datasets (CSV and XLSX) and
    resolves a dataset id to a trusted path, so it needs the dataset uploader
    from ``app.services.dataset_upload``.

    This is deliberately not the Knowledge document uploader. The two have
    different allowlists -- documents are ``.pdf``, ``.docx``, and ``.txt``,
    datasets are ``.csv`` and ``.xlsx`` -- and different storage, so handing a
    browser upload to the wrong one rejects every CSV with a message about
    document types.

    Args:
        settings: Application settings, used for the upload directory and the
            size limit. Injected rather than read from the module so a test can
            point the service at a temporary directory.
    """
    from app.services.dataset_upload import get_dataset_service

    return get_dataset_service(settings)


def get_document_upload_service(settings: Settings = Depends(get_settings_dep)) -> Any:
    """Return the process-wide Knowledge document upload service.

    The Knowledge Agent ingests documents, so it keeps the document allowlist
    (``.pdf``, ``.docx``, ``.txt``) and the knowledge upload directory.

    Args:
        settings: Application settings, used for the upload directory and the
            size limit.
    """
    from app.services.document_upload import get_upload_service

    return get_upload_service(settings)


def get_dataset_manifest(settings: Settings = Depends(get_settings_dep)) -> Any:
    """Return the process-wide Performance dataset manifest store.

    Args:
        settings: Application settings, used for the manifest path.
    """
    from app.services.dataset_upload import get_manifest

    return get_manifest(settings)


def get_document_manifest() -> Any:
    """Return the process-wide knowledge document manifest."""
    from app.services.document_manifest import DocumentManifest

    return DocumentManifest(get_settings().resolved_knowledge_upload_manifest_path)


def get_employee_directory_service() -> Any:
    """Return the process-wide employee directory service."""
    from app.services.employee_directory import get_directory_service

    return get_directory_service(get_settings())


def get_employee_directory_manifest() -> Any:
    """Return the process-wide employee directory manifest."""
    from app.services.employee_directory import get_manifest

    return get_manifest(get_settings())


def resource_is_visible_to(
    resource_organization_id: str | None,
    current_user: User | None,
) -> bool:
    """Return whether a caller may read a resource that belongs to an organisation.

    A resource that carries no organisation belongs to no tenant. It holds no
    tenant data, so it stays readable by anyone who can name it.

    A resource that carries an organisation belongs to that tenant and is
    visible to that tenant only. A caller with no authenticated organisation
    -- no token, an expired token, or a revoked one -- owns nothing, so it
    cannot read another tenant's resource. Skipping the comparison for such a
    caller would turn an expired token into a way around the check.

    Args:
        resource_organization_id: The organisation that owns the resource, or
            None when it belongs to no tenant.
        current_user: The authenticated user, or None for an anonymous caller.

    Returns:
        True when the caller may read the resource.
    """
    if resource_organization_id is None:
        return True

    caller_organization_id = current_user.organization_id if current_user else None

    return caller_organization_id is not None and caller_organization_id == resource_organization_id


def reset_state() -> None:
    """Clear the shared singletons. Intended for test isolation."""
    global _registry, _orchestrator, _job_manager
    _registry = None
    _orchestrator = None
    _job_manager = None
    from app.services.dataset_upload import set_dataset_service
    from app.services.dataset_upload import set_manifest as set_dataset_manifest
    from app.services.document_upload import reset_upload_service
    from app.services.employee_directory import set_directory_service
    from app.services.employee_directory import set_manifest as set_employee_manifest

    reset_upload_service()
    set_dataset_service(None)
    set_directory_service(None)
    set_employee_manifest(None)
    set_dataset_manifest(None)


# ---------------------------------------------------------------------------
# Authentication dependencies
# ---------------------------------------------------------------------------


async def _verify_jwt_token(token: str, settings: Settings) -> dict[str, Any]:
    """Verify and decode a JWT access token.

    The expiry is enforced here: the ``exp`` claim is required, so a token
    that carries none is refused, and a token whose expiry has passed is
    refused with 401. The client answers that with a single refresh attempt.

    Returns:
        The payload dict if valid.
    Raises HTTPException 401 on failure.
    """
    # PyJWT 2.x installs the module as ``jwt``; ``pyjwt`` was the 1.x name.
    import jwt

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=["HS256"],
            options={"require": ["exp", "sub"]},
        )
        return payload
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def get_current_user_from_token(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> User:
    """Dependency that resolves the current authenticated user from an access JWT.

    - Extracts user ID from the access token payload
    - Looks up the user in the database
    - Checks that the user is active and the token version matches (revocation)
    - Raises 401 with WWW-Authenticate: Bearer if not authenticated

    Returns:
        The User model instance.

    Raises:
        HTTPException 401: If no valid token or user not found/inactive.
    """
    payload = await _verify_jwt_token(token, settings)
    user_id: str | None = payload.get("sub")
    token_version: int = payload.get("token_version", 0) or 0

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Look up the user
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check token version for revocation
    if user.token_version != token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked (token version mismatch)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def require_employee(current_user: User = Depends(get_current_user_from_token)) -> User:
    """Dependency that requires the user to have the 'employee' role or higher.

    Returns the current user if they have employee, manager, or admin role.
    Raises 403 if the user does not have sufficient role.
    """
    if current_user.role not in {UserRole.EMPLOYEE, UserRole.MANAGER, UserRole.ADMIN}:
        from app.core.exceptions import ForbiddenError

        raise ForbiddenError(
            "Insufficient role: employee required.",
            details={"field": "role"},
        )
    return current_user


def require_manager(current_user: User = Depends(get_current_user_from_token)) -> User:
    """Dependency that requires the user to have the 'manager' role or higher.

    Returns the current user if they have manager or admin role.
    Raises 403 if the user does not have sufficient role.
    """
    if current_user.role not in {UserRole.MANAGER, UserRole.ADMIN}:
        from app.core.exceptions import ForbiddenError

        raise ForbiddenError(
            "Insufficient role: manager required.",
            details={"field": "role"},
        )
    return current_user


def require_admin(current_user: User = Depends(get_current_user_from_token)) -> User:
    """Dependency that requires the user to have the 'admin' role.

    Returns the current user only if they have admin role.
    Raises 403 if the user does not have admin role.
    """
    if current_user.role != UserRole.ADMIN:
        from app.core.exceptions import ForbiddenError

        raise ForbiddenError(
            "Insufficient role: admin required.",
            details={"field": "role"},
        )
    return current_user


async def get_refresh_token_from_cookie(request: Request) -> str | None:
    """Read refresh token from the HttpOnly cookie.

    Used by the refresh and logout endpoints.
    """
    cookies = request.cookies
    return cookies.get("refresh_token")


async def get_current_user_from_token_optional(
    token: str = Depends(oauth2_scheme_optional),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> User | None:
    """Return the authenticated user if a valid token is present, otherwise None.

    Unlike ``get_current_user_from_token`` this never raises 401; it simply
    returns ``None`` when no valid token is supplied.  This is intended for
    endpoints that wish to support both authenticated and unauthenticated access.
    """
    try:
        payload = await _verify_jwt_token(token, settings)
    except HTTPException:
        return None

    user_id: str | None = payload.get("sub")
    token_version: int = payload.get("token_version", 0) or 0

    if not user_id:
        return None

    # Look up the user
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        return None

    # Check token version for revocation
    if user.token_version != token_version:
        return None

    return user
