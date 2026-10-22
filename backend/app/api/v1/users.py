"""User management API.

Provides admin-protected create, list, update, activate, deactivate, and
manager-assignment operations.  Endpoints are scoped to the authenticated
user's organisation so that users can only manage colleagues in their own
tenant.
"""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    require_admin,
    require_employee,
    require_manager,
)
from app.core.database import get_async_session
from app.models import User, UserRole, hash_password
from app.schemas import UserCreated, UserPublic, UserSummary
from app.schemas.common import APIResponse

router = APIRouter(prefix="/users", tags=["user-management"])

logger = logging.getLogger(__name__)

#: Length of the temporary password generated for a new user. The value is
#: shown to the administrator once and never stored in plain text.
TEMPORARY_PASSWORD_LENGTH = 16


def _generate_temporary_password() -> str:
    """Return a random password for a newly created user.

    The account is created with a password nobody has seen yet. The value is
    returned to the administrator once, in the creation response, so it can
    be delivered to the new user. It is never persisted in plain text and
    never appears in a log.

    Returns:
        A random password.
    """
    alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(TEMPORARY_PASSWORD_LENGTH))


def _normalize_role(role: str) -> str:
    """Normalize a role string to its canonical form.

    Args:
        role: The role string from the API request.

    Returns:
        The canonical role string.

    Raises:
        ValidationFailedError: If the role is not valid.
    """
    valid_roles = {"employee", "manager", "admin"}
    normalized = role.lower().strip()
    if normalized not in valid_roles:
        from app.core.exceptions import ValidationFailedError

        raise ValidationFailedError(
            f"Invalid role '{role}'. Must be one of: {', '.join(valid_roles)}.",
            details={"field": "role"},
        )
    return normalized


@router.post(
    "/",
    response_model=APIResponse[UserCreated],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user (admin only)",
    description="Create a new user account in the authenticated user's organisation.",
)
async def create_user(
    email: str,
    full_name: str,
    role: str = Query(
        default="employee",
        description="Initial role: employee, manager, or admin.",
    ),
    manager_id: str | None = Query(
        default=None,
        description="Optional UUID of the user's manager.",
    ),
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_async_session),
) -> APIResponse[UserPublic]:
    """Admin-create a new user.

    Args:
        email: User's email address (must be unique within the organisation).
        full_name: User's full name.
        role: Initial role (employee, manager, or admin).
        manager_id: Optional UUID of the user's manager.
        current_user: The authenticated admin user.
        session: Database session.

    Returns:
        The created user profile.
    """
    role = _normalize_role(role)
    normalized_email = email.lower().strip()
    temporary_password = _generate_temporary_password()

    result = await session.execute(select(User).where(User.email == normalized_email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email '{email}' already exists.",
        )

    # Validate manager_id if provided
    if manager_id:
        result = await session.execute(select(User).where(User.id == manager_id))
        manager = result.scalar_one_or_none()
        if not manager:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Manager not found.",
            )
        if manager.organization_id != current_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Manager must belong to the same organisation.",
            )

    new_user = User(
        email=normalized_email,
        full_name=full_name,
        role=role,
        manager_id=manager_id,
        organization_id=current_user.organization_id,
        is_active=True,
        hashed_password=hash_password(temporary_password),
    )
    session.add(new_user)
    await session.flush()
    await session.refresh(new_user)

    # A brand new account has no tokens to invalidate, and the acting admin
    # keeps their own session.
    await session.commit()

    logger.info("user_created user_id=%s by_admin_id=%s", new_user.id, current_user.id)

    return APIResponse(
        data=UserCreated(
            id=new_user.id,
            email=new_user.email,
            full_name=new_user.full_name,
            role=new_user.role,
            organization_id=new_user.organization_id,
            is_active=new_user.is_active,
            token_version=new_user.token_version,
            temporary_password=temporary_password,
        ),
        message="User created successfully.",
    )


@router.get(
    "/",
    response_model=APIResponse[list[UserSummary]],
    summary="List users in your organisation",
    description="List all active users in the authenticated user's organisation. "
    "Employees see all colleagues; managers and admins see their team.",
)
async def list_users(
    current_user: User = Depends(require_employee),
    session: AsyncSession = Depends(get_async_session),
) -> APIResponse[list[UserSummary]]:
    """List users in the authenticated user's organisation.

    Args:
        current_user: The authenticated user (employee, manager, or admin).
        session: Database session.

    Returns:
        Envelope containing user profiles in the organisation.
    """
    org_id = current_user.organization_id

    result = await session.execute(
        select(User).where(User.organization_id == org_id, User.is_active.is_(True))
    )
    users = result.scalars().all()

    return APIResponse(
        data=[
            UserSummary(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                role=user.role,
                organization_id=user.organization_id,
                is_active=user.is_active,
            )
            for user in users
        ],
        message=f"{len(users)} users.",
    )


@router.patch(
    "/{user_id}",
    response_model=APIResponse[UserPublic],
    summary="Change user role (admin only)",
    description="Update a user's role. Only admins may change roles.",
)
async def change_user_role(
    user_id: str,
    new_role: str = Query(
        ...,
        description="The new role for the user: employee, manager, or admin.",
    ),
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_async_session),
) -> APIResponse[UserPublic]:
    """Admin-change a user's role.

    Args:
        user_id: UUID of the user whose role to update.
        new_role: The new role value.
        current_user: The authenticated admin user.
        session: Database session.

    Returns:
        The updated user profile.
    """
    new_role = _normalize_role(new_role)

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    if user.organization_id != current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot modify users outside your organisation.",
        )

    # Prevent demoting the last active administrator in the organisation.
    #
    # The target counts as one of the active administrators, so the guard
    # covers the case where an administrator demotes themselves as well. With
    # the target excluded from the count, an organisation's only
    # administrator could demote themselves and leave nobody able to administer
    # it.
    if user.role == UserRole.ADMIN and new_role != UserRole.ADMIN:
        active_admins = await session.execute(
            select(User).where(
                User.organization_id == current_user.organization_id,
                User.role == UserRole.ADMIN,
                User.is_active.is_(True),
            )
        )
        if len(active_admins.scalars().all()) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the last active organization administrator.",
            )

    user.role = new_role

    # Invalidate the changed user's outstanding access tokens. Their role or
    # activation state moved, so any token they already hold must stop
    # working. The acting admin keeps their own session.
    user.token_version = user.token_version + 1
    await session.execute(
        update(User).where(User.id == user.id).values(token_version=user.token_version)
    )
    await session.commit()

    logger.info(
        "user_role_changed user_id=%s old_role=%s new_role=%s by_admin_id=%s",
        user.id,
        user.role if hasattr(user, "role") else "unknown",
        user.role,
        current_user.id,
    )

    return APIResponse(
        data=UserPublic(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            organization_id=user.organization_id,
            is_active=user.is_active,
            token_version=user.token_version,
        ),
        message="User role updated successfully.",
    )


@router.post(
    "/{user_id}/activate",
    response_model=APIResponse[UserPublic],
    summary="Activate a user (admin only)",
    description="Reactivate a disabled user account.",
)
async def activate_user(
    user_id: str,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_async_session),
) -> APIResponse[UserPublic]:
    """Admin-activate a user.

    Args:
        user_id: UUID of the user to activate.
        current_user: The authenticated admin user.
        session: Database session.

    Returns:
        The activated user profile.
    """
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    if user.organization_id != current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot activate users outside your organisation.",
        )

    # Activating an administrator never reduces the number of active
    # administrators, so there is nothing to protect here. An earlier version
    # of this route refused the activation whenever the organisation had a
    # single active administrator, which made it impossible for an
    # organisation to ever have two.
    user.is_active = True

    # Invalidate the changed user's outstanding access tokens. Their role or
    # activation state moved, so any token they already hold must stop
    # working. The acting admin keeps their own session.
    user.token_version = user.token_version + 1
    await session.execute(
        update(User).where(User.id == user.id).values(token_version=user.token_version)
    )
    await session.commit()

    logger.info("user_activated user_id=%s by_admin_id=%s", user.id, current_user.id)

    return APIResponse(
        data=UserPublic(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            organization_id=user.organization_id,
            is_active=user.is_active,
            token_version=user.token_version,
        ),
        message="User activated successfully.",
    )


@router.post(
    "/{user_id}/deactivate",
    response_model=APIResponse[UserPublic],
    summary="Deactivate a user (admin only)",
    description="Deactivate a user account. Self-deactivation is not allowed.",
)
async def deactivate_user(
    user_id: str,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_async_session),
) -> APIResponse[UserPublic]:
    """Admin-deactivate a user.

    Args:
        user_id: UUID of the user to deactivate.
        current_user: The authenticated admin user.
        session: Database session.

    Returns:
        The deactivated user profile.
    """
    # Prevent self-deactivation
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account.",
        )

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    if user.organization_id != current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot deactivate users outside your organisation.",
        )

    # Prevent deactivating the last active administrator in the organisation.
    #
    # Only an active administrator is protected: deactivating an account that
    # is already inactive changes nothing about who can administer the
    # organisation.
    if user.role == UserRole.ADMIN and user.is_active:
        active_admins = await session.execute(
            select(User).where(
                User.organization_id == current_user.organization_id,
                User.role == UserRole.ADMIN,
                User.is_active.is_(True),
            )
        )
        if len(active_admins.scalars().all()) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate the last active organization administrator.",
            )

    user.is_active = False

    # Invalidate the changed user's outstanding access tokens. Their role or
    # activation state moved, so any token they already hold must stop
    # working. The acting admin keeps their own session.
    user.token_version = user.token_version + 1
    await session.execute(
        update(User).where(User.id == user.id).values(token_version=user.token_version)
    )
    await session.commit()

    logger.info("user_deactivated user_id=%s by_admin_id=%s", user.id, current_user.id)

    return APIResponse(
        data=UserPublic(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            organization_id=user.organization_id,
            is_active=user.is_active,
            token_version=user.token_version,
        ),
        message="User deactivated successfully.",
    )


@router.patch(
    "/{user_id}/manager",
    response_model=APIResponse[UserPublic],
    summary="Assign or remove a user's manager (manager or admin only)",
    description="Set or clear a user's manager. The manager must belong to "
    "the same organisation.  Only users with manager or admin role may "
    "perform this operation.",
)
async def set_user_manager(
    user_id: str,
    manager_id: str | None = Query(
        default=None,
        description="UUID of the new manager, or null to remove the manager.",
    ),
    current_user: User = Depends(require_manager),
    session: AsyncSession = Depends(get_async_session),
) -> APIResponse[UserPublic]:
    """Manager-or-admin-set a user's manager.

    Args:
        user_id: UUID of the user whose manager to set.
        manager_id: UUID of the manager, or null to remove.
        current_user: The authenticated manager or admin user.
        session: Database session.

    Returns:
        The updated user profile.
    """
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    if user.organization_id != current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot modify users outside your organisation.",
        )

    if manager_id:
        # Validate the manager exists and belongs to the same organisation
        m_result = await session.execute(select(User).where(User.id == manager_id))
        manager = m_result.scalar_one_or_none()

        if not manager:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Manager not found.",
            )

        if manager.organization_id != current_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Manager must belong to the same organisation.",
            )

        # Prevent circular reference: a user cannot have themselves as manager
        if manager.id == user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user cannot be their own manager.",
            )

        user.manager_id = manager_id
    else:
        user.manager_id = None

    # Invalidate the changed user's outstanding access tokens. Their role or
    # activation state moved, so any token they already hold must stop
    # working. The acting admin keeps their own session.
    user.token_version = user.token_version + 1
    await session.execute(
        update(User).where(User.id == user.id).values(token_version=user.token_version)
    )
    await session.commit()

    logger.info(
        "user_manager_set user_id=%s manager_id=%s by_manager_id=%s",
        user.id,
        manager_id,
        current_user.id,
    )

    return APIResponse(
        data=UserPublic(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            organization_id=user.organization_id,
            is_active=user.is_active,
            token_version=user.token_version,
        ),
        message="Manager updated successfully.",
    )
