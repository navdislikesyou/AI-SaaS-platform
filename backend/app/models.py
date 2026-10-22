"""SQLAlchemy 2.x database models for the AI SaaS Platform.

Maps to Organizations, Users, and RefreshTokens. Uses async-capable
declarative base. Model definitions are deliberately free of ASGI/WSGI
lifecycle logic so they can be used by tests with an in-memory SQLite
database or a production PostgreSQL instance.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from argon2 import PasswordHasher
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

from app.core.exceptions import ValidationFailedError

password_hasher = PasswordHasher()


class Base(DeclarativeBase):
    """Declarative base for the platform's models.

    Declared as a class rather than through ``declarative_base()`` so that a
    type checker understands the model attributes: with the function form the
    base is a plain variable, every model is reported as an invalid base
    class, and every attribute is seen as a ``Column`` instead of a ``str``.
    """


class Organization(Base):
    """Organization / tenant within the SaaS platform.

    Each user belongs to one organization. Organizations own resources
    and enforce isolation.
    """

    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(191), nullable=False)
    slug: Mapped[str] = mapped_column(String(191), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda now: datetime.now(UTC),
    )

    # Relationships. The targets are named rather than imported because
    # ``User`` and ``RefreshToken`` are defined below and reference this
    # class back. Without these two the mapper cannot be configured, and
    # every database query fails before it runs.
    users: Mapped[list[User]] = relationship("User", back_populates="organization")
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        "RefreshToken", back_populates="organization"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class UserRole:
    """Role constants for the application."""

    EMPLOYEE = "employee"
    MANAGER = "manager"
    ADMIN = "admin"

    choices = [EMPLOYEE, MANAGER, ADMIN]


class User(Base):
    """User account, one per employee.

    Belongs to one organization. Has an optional manager hierarchy.
    Password is stored as an Argon2 hash. Token version enables revocation.
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(191), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(191), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=UserRole.EMPLOYEE,
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    token_version: Mapped[int] = mapped_column(default=0, nullable=False)
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    manager_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda now: datetime.now(UTC),
    )

    # Relationships
    organization: Mapped[Organization] = relationship("Organization", back_populates="users")
    manager: Mapped[User | None] = relationship(
        "User",
        remote_side=[id],
        back_populates="subordinates",
    )
    subordinates: Mapped[list[User]] = relationship(
        "User",
        back_populates="manager",
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_users_email", "email", unique=True),
        Index("ix_users_organization_id", "organization_id"),
    )

    def verify_password(self, plain_text: str) -> bool:
        """Verify a plain-text password against the stored hash.

        Args:
            plain_text: The password to check.

        Returns:
            True if the password matches, False otherwise.
        """
        try:
            password_hasher.verify(self.hashed_password, plain_text)
            return True
        except Exception:
            return False

    def check_password(self, plain_text: str) -> bool:
        """Alias for verify_password for consistency with auth flow."""
        return self.verify_password(plain_text)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "is_active": self.is_active,
            "organization_id": self.organization_id,
            "token_version": self.token_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @property
    def is_disabled(self) -> bool:
        """Return True when the user account is inactive."""
        return not self.is_active


class RefreshToken(Base):
    """Opaque refresh token stored only as a SHA-256 hash.

    Never stores the plaintext token. Supports rotation and revocation.
    A new token replaces any previous one; old hashes are checked on
    submit to detect reuse.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="refresh_tokens")
    organization: Mapped[Organization | None] = relationship(
        "Organization", back_populates="refresh_tokens"
    )

    __table_args__ = (Index("ix_refresh_tokens_hash", "token_hash", unique=True),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "organization_id": self.organization_id,
            "expires_at": self.expires_at,
            "revoked_at": self.revoked_at,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------


def hash_password(plain_text: str) -> str:
    """Hash a plain-text password using Argon2.

    Args:
        plain_text: The password to hash.

    Returns:
        The Argon2 hash string.
    """
    return password_hasher.hash(plain_text)


def check_password_hash(hashed: str, plain_text: str) -> bool:
    """Verify a password against its Argon2 hash.

    Args:
        hashed: The stored hash.
        plain_text: The password to check.

    Returns:
        True if the password matches, False otherwise.
    """
    try:
        password_hasher.verify(hashed, plain_text)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Model validation helpers
# ---------------------------------------------------------------------------


def validate_role(role: str) -> str:
    """Validate that a role is one of the allowed values.

    Args:
        role: The role string to validate.

    Returns:
        The validated role.

    Raises:
        ValidationFailedError: If the role is not allowed.
    """
    if role not in {UserRole.EMPLOYEE, UserRole.MANAGER, UserRole.ADMIN}:
        raise ValidationFailedError(
            f"Invalid role '{role}'. Must be one of: {UserRole.EMPLOYEE}, "
            f"{UserRole.MANAGER}, {UserRole.ADMIN}.",
            details={"field": "role"},
        )
    return role
