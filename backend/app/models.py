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
    Text,
    UniqueConstraint,
    func,
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


class Feedback(Base):
    """Employee feedback record, scoped to one organization.

    Stores one piece of feedback attributed to an employee, with its RoBERTa
    sentiment classification and the source it came from. Dedup is enforced by
    a unique constraint on (organization_id, source, source_message_id,
    employee_id, feedback_hash) so the same email/feedback is never stored
    twice for the same organization.
    """

    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[str] = mapped_column(String(191), nullable=False, index=True)
    employee_name: Mapped[str] = mapped_column(String(191), nullable=False)
    employee_email: Mapped[str | None] = mapped_column(String(191), nullable=True)
    feedback_text: Mapped[str] = mapped_column(String, nullable=False)
    sentiment: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual", index=True)
    source_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    feedback_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source",
            "source_message_id",
            "employee_id",
            "feedback_hash",
            name="uq_feedback_dedup",
        ),
        Index("ix_feedback_created_at", "created_at"),
    )

    def to_dict(self) -> dict:
        created_at = self.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "employee_id": self.employee_id,
            "employee_name": self.employee_name,
            "employee_email": self.employee_email,
            "feedback": self.feedback_text,
            "sentiment": self.sentiment,
            "confidence": self.confidence,
            "source": self.source,
            "source_message_id": self.source_message_id,
            "created_at": created_at.astimezone(UTC).isoformat(),
        }


class GmailConnection(Base):
    """One organization's authorized Gmail mailbox.

    Exactly one row per organization, enforced by a unique constraint, because
    the connection belongs to the tenant rather than to whichever member
    clicked Connect. The mailbox address is read from Google's profile at
    consent time and is never configured.

    The Google credential is stored as a single encrypted blob:
    ``credentials_encrypted`` holds ``Fernet(Credentials.to_json())``, so both
    the short-lived access token and the long-lived refresh token are out of
    reach at rest. ``token_expiry`` is duplicated outside the blob only because
    it is not sensitive and the status endpoint displays it.

    No relationships are declared. Callers query by ``organization_id``
    directly, which keeps the mapper independent of ``Organization``.
    """

    __tablename__ = "gmail_connections"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connected_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    gmail_address: Mapped[str] = mapped_column(String(191), nullable=False)
    scopes: Mapped[str] = mapped_column(String(512), nullable=False)
    credentials_encrypted: Mapped[str] = mapped_column(String(8192), nullable=False)
    token_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            name="uq_gmail_connections_organization_id",
        ),
    )


class EmailSend(Base):
    """One audited, idempotent email send attempt.

    One row per idempotency key per organization. The row is claimed (status
    ``sending``) before any Google call so that concurrent requests and
    retries after a timeout cannot trigger a second send. The HTML body is
    never stored: only the metadata needed for audit and replay is kept.
    """

    __tablename__ = "email_sends"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    sender_mailbox: Mapped[str] = mapped_column(String(191), nullable=False)
    recipients: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="sending")
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    gmail_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_email_sends_organization_idempotency_key",
        ),
        Index("ix_email_sends_organization_id", "organization_id"),
        Index("ix_email_sends_status", "status"),
    )


class OAuthState(Base):
    """Single-use pending Google OAuth authorization.

    Bound to one organization and one user because the callback that consumes
    it is a bare browser navigation carrying no access token, so the binding
    has to come from the server side rather than from a credential.

    The nonce is stored only as a SHA-256 hash, mirroring how refresh tokens
    are stored, so a database leak does not hand out usable states. The PKCE
    verifier is stored in plaintext: it must be readable to complete the
    exchange, and it is worthless once the state is consumed or expired.
    """

    __tablename__ = "oauth_states"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    pkce_verifier: Mapped[str] = mapped_column(String(256), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Meeting(Base):
    """One organization-scoped meeting record.

    Meetings are AXON records owned by an organization, created and managed
    through the Automation Agent's scheduling workflow. The Automation Agent
    package itself stays draft-only: it parses and drafts meeting invitations
    but never creates, edits, or cancels a meeting record.

    Timestamps are stored in UTC. ``timezone`` holds the IANA time zone the
    organizer chose so clients can render local times correctly.
    """

    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organizer_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    venue: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled", index=True)
    #: Schedule generation. Incremented on every reschedule so reminders from
    #: previous generations can be cancelled without deleting their history.
    schedule_generation: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    attendees: Mapped[list[MeetingAttendee]] = relationship(
        "MeetingAttendee",
        back_populates="meeting",
        cascade="all, delete-orphan",
    )
    reminders: Mapped[list[MeetingReminder]] = relationship(
        "MeetingReminder",
        back_populates="meeting",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_meetings_organization_status", "organization_id", "status"),
        Index("ix_meetings_starts_at", "starts_at"),
    )

    def to_dict(self) -> dict:
        starts_at = self.starts_at
        ends_at = self.ends_at
        if starts_at.tzinfo is None:
            starts_at = starts_at.replace(tzinfo=UTC)
        if ends_at.tzinfo is None:
            ends_at = ends_at.replace(tzinfo=UTC)
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "organizer_user_id": self.organizer_user_id,
            "title": self.title,
            "description": self.description,
            "starts_at": starts_at.astimezone(UTC).isoformat(),
            "ends_at": ends_at.astimezone(UTC).isoformat(),
            "timezone": self.timezone,
            "venue": self.venue,
            "status": self.status,
            "schedule_generation": self.schedule_generation,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class MeetingAttendee(Base):
    """One attendee of a meeting.

    Attendees are resolved against verified AXON users where possible, with an
    email address fallback for external invitees. Either ``user_id`` or ``email``
    identifies the attendee; both may be present when the attendee is an org
    user.
    """

    __tablename__ = "meeting_attendees"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(191), nullable=True)

    meeting: Mapped[Meeting] = relationship("Meeting", back_populates="attendees")

    __table_args__ = (
        UniqueConstraint(
            "meeting_id",
            "email",
            name="uq_meeting_attendees_meeting_email",
        ),
        Index("ix_meeting_attendees_user_id", "user_id"),
    )


class MeetingReminder(Base):
    """One reminder delivery for a meeting schedule generation.

    Reminders are durable database records, not in-memory job entries. The
    scheduler claims and processes them row by row. Historical reminders are
    never deleted: when a meeting is rescheduled, reminders belonging to the
    previous schedule generation are marked ``cancelled`` and new reminders are
    created for the new generation, each with its own idempotency key.

    Statuses:
        pending    - waiting to be sent
        sending    - claimed by the scheduler, delivery in progress
        sent       - Gmail accepted the email
        failed     - conclusive Gmail failure
        uncertain  - outcome unknown (network/timeout); requires investigation
        cancelled  - superseded by a reschedule or meeting cancellation
    """

    __tablename__ = "meeting_reminders"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    reminder_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    email_send_id: Mapped[str | None] = mapped_column(
        ForeignKey("email_sends.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    schedule_generation: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    meeting: Mapped[Meeting] = relationship("Meeting", back_populates="reminders")

    __table_args__ = (
        UniqueConstraint(
            "meeting_id",
            "reminder_type",
            "schedule_generation",
            name="uq_meeting_reminders_meeting_type_generation",
        ),
        Index("ix_meeting_reminders_status_scheduled", "status", "scheduled_for"),
        Index("ix_meeting_reminders_meeting_status", "meeting_id", "status"),
    )

    def to_dict(self) -> dict:
        scheduled_for = self.scheduled_for
        if scheduled_for.tzinfo is None:
            scheduled_for = scheduled_for.replace(tzinfo=UTC)
        return {
            "id": self.id,
            "meeting_id": self.meeting_id,
            "reminder_type": self.reminder_type,
            "scheduled_for": scheduled_for.astimezone(UTC).isoformat(),
            "status": self.status,
            "schedule_generation": self.schedule_generation,
            "email_send_id": self.email_send_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
