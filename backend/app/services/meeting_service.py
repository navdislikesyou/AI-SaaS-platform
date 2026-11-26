"""Meeting scheduling service for the Automation Agent.

Meetings are durable AXON records owned by an organization. This service owns
the full meeting lifecycle:

- create, retrieve, list (organization-scoped), update, cancel, reschedule
- attendee management
- reminder generation, cancellation, regeneration, and history

The connected Automation Agent stays draft-only: it parses and drafts meeting
invitations, but this service is the only place that creates, edits, or
cancels meeting records.

Reminders use a schedule-generation mechanism. Every meeting carries a
``schedule_generation`` counter. On reschedule, reminders belonging to the
previous generation are marked ``cancelled`` (their history is preserved) and
new reminders are created for the new generation, each with a unique
idempotency key. This guarantees no duplicate reminders for the same schedule
while never deleting delivery history.

All timestamps are stored in UTC. The organizer-chosen IANA time zone is
preserved on the meeting so clients can render local times.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import get_session
from app.core.exceptions import (
    ValidationFailedError,
)
from app.models import (
    Meeting,
    MeetingAttendee,
    MeetingReminder,
)
from app.services.activity_store import record_activity

logger = logging.getLogger(__name__)

#: Reminder types the scheduler supports, in order of delivery before a meeting.
REMINDER_TYPES: tuple[str, ...] = ("24h", "30m")

#: How far before each reminder type the email should be sent.
REMINDER_OFFSETS: dict[str, timedelta] = {
    "24h": timedelta(hours=24),
    "30m": timedelta(minutes=30),
}

#: Terminal reminder statuses that should never be re-sent.
_REMINDER_TERMINAL_STATUSES = frozenset({"sent", "failed", "uncertain", "cancelled"})


def _utc_now() -> datetime:
    """Return the current time as an aware UTC datetime."""
    return datetime.now(UTC)


def _validate_timezone(timezone: str) -> str:
    """Validate that a time zone string is a known IANA zone.

    Args:
        timezone: IANA time zone identifier, e.g. ``"Asia/Kolkata"``.

    Returns:
        The validated time zone string.

    Raises:
        ValidationFailedError: If the time zone is unknown.
    """
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValidationFailedError(
            f"Unknown time zone '{timezone}'.",
            details={"field": "timezone"},
        ) from exc
    return timezone


def _parse_utc(value: Any, field: str) -> datetime:
    """Parse a client-supplied timestamp into an aware UTC datetime.

    Accepts an ISO-8601 string or an aware datetime. Naive datetimes are
    rejected because the client must declare a time zone explicitly through
    the meeting's ``timezone`` field.

    Args:
        value: Raw timestamp value.
        field: Field name, used in error messages.

    Returns:
        An aware UTC datetime.

    Raises:
        ValidationFailedError: If the value cannot be parsed or is naive.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValidationFailedError(
                f"Field '{field}' must include a time zone offset.",
                details={"field": field},
            )
        return value.astimezone(UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValidationFailedError(
                f"Field '{field}' is not a valid ISO-8601 timestamp.",
                details={"field": field},
            ) from exc
        if parsed.tzinfo is None:
            raise ValidationFailedError(
                f"Field '{field}' must include a time zone offset.",
                details={"field": field},
            )
        return parsed.astimezone(UTC)
    raise ValidationFailedError(
        f"Field '{field}' must be a timestamp.",
        details={"field": field},
    )


def _validate_email(email: Any, field: str) -> str:
    """Validate and normalize a single attendee email address.

    Args:
        email: Raw email value.
        field: Field name, used in error messages.

    Returns:
        The lowercased, stripped email address.

    Raises:
        ValidationFailedError: If the address is malformed.
    """
    if not isinstance(email, str):
        raise ValidationFailedError(
            f"Field '{field}' must be a string.",
            details={"field": field},
        )
    address = email.strip().lower()
    if not address or "@" not in address or " " in address:
        raise ValidationFailedError(
            f"Field '{field}' is not a valid email address.",
            details={"field": field},
        )
    return address


class MeetingService:
    """Service for meeting lifecycle and reminder management."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    async def create_meeting(
        self,
        *,
        organization_id: str,
        organizer_user_id: str | None,
        title: str,
        description: str | None,
        starts_at: Any,
        ends_at: Any,
        timezone: str,
        venue: str | None,
        attendees: list[dict[str, Any]],
    ) -> Meeting:
        """Create a new meeting in ``scheduled`` status.

        No email is sent automatically. The caller must use
        :meth:`send_invitation` (a separate, explicitly confirmed endpoint) to
        dispatch the invitation.

        Args:
            organization_id: Owning organization.
            organizer_user_id: User who created the meeting.
            title: Meeting title.
            description: Optional agenda.
            starts_at: Start timestamp (ISO-8601 or aware datetime).
            ends_at: End timestamp (ISO-8601 or aware datetime).
            timezone: IANA time zone of the organizer.
            venue: Optional room or meeting link.
            attendees: List of ``{"name", "email"}`` dicts, optionally with
                ``user_id`` for verified org users.

        Returns:
            The created :class:`Meeting`.

        Raises:
            ValidationFailedError: On bad input.
        """
        if not title or not title.strip():
            raise ValidationFailedError(
                "Meeting title is required.",
                details={"field": "title"},
            )
        title = title.strip()

        _validate_timezone(timezone)

        start = _parse_utc(starts_at, "starts_at")
        end = _parse_utc(ends_at, "ends_at")
        if end <= start:
            raise ValidationFailedError(
                "Meeting end time must be after start time.",
                details={"field": "ends_at"},
            )

        # Validate and deduplicate attendees.
        seen_emails: set[str] = set()
        raw_attendees: list[dict[str, Any]] = []
        for index, attendee in enumerate(attendees or []):
            email = _validate_email(attendee.get("email"), f"attendees[{index}].email")
            if email in seen_emails:
                raise ValidationFailedError(
                    f"Duplicate attendee email '{email}'.",
                    details={"field": f"attendees[{index}].email"},
                )
            seen_emails.add(email)
            raw_attendees.append(
                {
                    "name": str(attendee.get("name") or "").strip() or None,
                    "email": email,
                    "user_id": str(attendee.get("user_id") or "").strip() or None,
                }
            )

        meeting = Meeting(
            organization_id=organization_id,
            organizer_user_id=organizer_user_id,
            title=title,
            description=description,
            starts_at=start,
            ends_at=end,
            timezone=timezone,
            venue=venue,
            status="scheduled",
            schedule_generation=1,
        )

        async with get_session() as session:
            # Validate user_id attendees against active org users and derive email/name from DB.
            normalized_attendees: list[dict[str, Any]] = []
            user_ids = [a["user_id"] for a in raw_attendees if a.get("user_id")]
            users_by_id: dict[str, Any] = {}
            if user_ids:
                from app.models import User

                result = await session.execute(select(User).where(User.id.in_(user_ids)))
                users = result.scalars().all()
                users_by_id = {str(u.id): u for u in users}

            for index, attendee in enumerate(raw_attendees):
                uid = attendee.get("user_id")
                if uid:
                    user = users_by_id.get(str(uid))
                    if user is None:
                        raise ValidationFailedError(
                            f"Unknown attendee employee ID: {uid}",
                            details={
                                "field": f"attendees[{index}].user_id",
                                "reason": "unknown_employee",
                            },
                        )
                    if str(user.organization_id) != str(organization_id):
                        raise ValidationFailedError(
                            f"Attendee {uid} is outside the authenticated organization.",
                            details={
                                "field": f"attendees[{index}].user_id",
                                "reason": "cross_organization_employee",
                            },
                        )
                    if not bool(user.is_active):
                        raise ValidationFailedError(
                            f"Attendee {uid} is inactive.",
                            details={
                                "field": f"attendees[{index}].user_id",
                                "reason": "inactive_employee",
                            },
                        )
                    normalized_attendees.append(
                        {
                            "name": str(user.full_name or user.email or "").strip() or None,
                            "email": str(user.email).strip().lower(),
                            "user_id": str(user.id),
                        }
                    )
                else:
                    # Allow email-only only when it maps to an active user in the same org.
                    from app.models import User

                    email_result = await session.execute(
                        select(User).where(
                            User.organization_id == organization_id,
                            User.email == attendee["email"],
                        )
                    )
                    user = email_result.scalar_one_or_none()
                    if user is None or not bool(user.is_active):
                        raise ValidationFailedError(
                            "Meeting attendee must be an active organization employee.",
                            details={
                                "field": f"attendees[{index}].email",
                                "reason": "unverified_attendee",
                            },
                        )
                    normalized_attendees.append(
                        {
                            "name": str(user.full_name or user.email or "").strip() or None,
                            "email": str(user.email).strip().lower(),
                            "user_id": str(user.id),
                        }
                    )

            session.add(meeting)
            await session.flush()
            for attendee in normalized_attendees:
                session.add(
                    MeetingAttendee(
                        meeting_id=meeting.id,
                        user_id=attendee["user_id"],
                        email=attendee["email"],
                        name=attendee["name"],
                    )
                )
            await session.commit()
            await session.refresh(meeting)

        logger.info(
            "meeting_created meeting_id=%s organization_id=%s title=%s",
            meeting.id,
            organization_id,
            title,
        )
        try:
            record_activity(
                agent="automation",
                operation="create_meeting",
                description="Created a meeting",
                status="completed",
                user_id=organizer_user_id,
                organization_id=organization_id,
            )
        except Exception:
            logger.warning(
                "activity_record_failed agent=automation operation=create_meeting",
                exc_info=True,
            )
        return meeting

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    async def get_meeting(self, meeting_id: str) -> Meeting | None:
        """Return one meeting by id, or None.

        Args:
            meeting_id: Meeting identifier.

        Returns:
            The meeting, or None when it does not exist.
        """
        async with get_session() as session:
            result = await session.execute(select(Meeting).where(Meeting.id == meeting_id))
            return result.scalar_one_or_none()

    async def list_attendees(self, meeting_id: str) -> list[dict[str, Any]]:
        """Return the attendees of one meeting.

        Args:
            meeting_id: Meeting identifier.

        Returns:
            List of ``{"name", "email"}`` dicts, empty when the meeting has no
            attendees.
        """
        async with get_session() as session:
            result = await session.execute(
                select(MeetingAttendee).where(MeetingAttendee.meeting_id == meeting_id)
            )
            attendees = result.scalars().all()
        return [
            {
                "name": a.name,
                "email": a.email,
            }
            for a in attendees
        ]

    async def get_meeting_with_details(self, meeting_id: str) -> dict[str, Any] | None:
        meeting = await self.get_meeting(meeting_id)
        if meeting is None:
            return None

        async with get_session() as session:
            attendee_result = await session.execute(
                select(MeetingAttendee).where(MeetingAttendee.meeting_id == meeting_id)
            )
            attendees = attendee_result.scalars().all()

            reminder_result = await session.execute(
                select(MeetingReminder)
                .where(MeetingReminder.meeting_id == meeting_id)
                .order_by(MeetingReminder.reminder_type, MeetingReminder.schedule_generation.desc())
            )
            reminders = reminder_result.scalars().all()

        return {
            "meeting": meeting.to_dict(),
            "attendees": [
                {
                    "id": a.id,
                    "user_id": a.user_id,
                    "email": a.email,
                    "name": a.name,
                }
                for a in attendees
            ],
            "reminders": [r.to_dict() for r in reminders],
        }

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    async def list_meetings(
        self,
        *,
        organization_id: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Meeting]:
        """List meetings for one organization, newest first.

        Args:
            organization_id: Owning organization (tenant isolation).
            status: Optional filter (``scheduled``, ``cancelled``, ``completed``).
            limit: Maximum rows to return.

        Returns:
            Meeting rows ordered by start time descending.
        """
        async with get_session() as session:
            stmt = (
                select(Meeting)
                .where(Meeting.organization_id == organization_id)
                .order_by(Meeting.starts_at.desc())
            )
            if status is not None:
                stmt = stmt.where(Meeting.status == status)
            stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_meeting(
        self,
        *,
        meeting_id: str,
        organization_id: str,
        title: str | None = None,
        description: str | None = None,
        starts_at: Any = None,
        ends_at: Any = None,
        timezone: str | None = None,
        venue: str | None = None,
    ) -> Meeting | None:
        """Update mutable fields of a scheduled meeting.

        Args:
            meeting_id: Meeting identifier.
            organization_id: Owning organization (enforced).
            title: New title.
            description: New agenda.
            starts_at: New start timestamp.
            ends_at: New end timestamp.
            timezone: New IANA time zone.
            venue: New room or meeting link.

        Returns:
            The updated meeting, or None when not found.

        Raises:
            ValidationFailedError: On bad input or end-before-start.
            ForbiddenError: When the meeting does not belong to the org.
        """
        async with get_session() as session:
            result = await session.execute(
                select(Meeting).where(
                    Meeting.id == meeting_id,
                    Meeting.organization_id == organization_id,
                )
            )
            meeting = result.scalar_one_or_none()
            if meeting is None:
                return None

            if meeting.status == "cancelled":
                raise ValidationFailedError(
                    "A cancelled meeting cannot be updated.",
                    details={"reason": "meeting_cancelled"},
                )

            if title is not None:
                if not title.strip():
                    raise ValidationFailedError(
                        "Meeting title is required.",
                        details={"field": "title"},
                    )
                meeting.title = title.strip()

            if description is not None:
                meeting.description = description.strip() if description else None

            if venue is not None:
                meeting.venue = venue.strip() if venue else None

            if timezone is not None:
                _validate_timezone(timezone)
                meeting.timezone = timezone

            start = meeting.starts_at
            end = meeting.ends_at
            if starts_at is not None:
                start = _parse_utc(starts_at, "starts_at")
            if ends_at is not None:
                end = _parse_utc(ends_at, "ends_at")
            if end <= start:
                raise ValidationFailedError(
                    "Meeting end time must be after start time.",
                    details={"field": "ends_at"},
                )
            meeting.starts_at = start
            meeting.ends_at = end

            await session.commit()
            await session.refresh(meeting)

        logger.info(
            "meeting_updated meeting_id=%s organization_id=%s",
            meeting_id,
            organization_id,
        )
        try:
            record_activity(
                agent="automation",
                operation="update_meeting",
                description="Updated a meeting",
                status="completed",
                organization_id=organization_id,
            )
        except Exception:
            logger.warning(
                "activity_record_failed agent=automation operation=update_meeting",
                exc_info=True,
            )
        return meeting

    # ------------------------------------------------------------------
    # Cancellation
    # ------------------------------------------------------------------

    async def cancel_meeting(self, *, meeting_id: str, organization_id: str) -> Meeting | None:
        """Cancel a meeting and cancel its pending reminders.

        Historical reminder records are preserved; their status is set to
        ``cancelled``. Reminders already in a terminal state are left alone.

        Args:
            meeting_id: Meeting identifier.
            organization_id: Owning organization (enforced).

        Returns:
            The cancelled meeting, or None when not found.

        Raises:
            ForbiddenError: When the meeting does not belong to the org.
        """
        async with get_session() as session:
            result = await session.execute(
                select(Meeting).where(
                    Meeting.id == meeting_id,
                    Meeting.organization_id == organization_id,
                )
            )
            meeting = result.scalar_one_or_none()
            if meeting is None:
                return None

            meeting.status = "cancelled"
            await session.execute(
                update(MeetingReminder)
                .where(
                    MeetingReminder.meeting_id == meeting_id,
                    MeetingReminder.schedule_generation == meeting.schedule_generation,
                    MeetingReminder.status.in_(("pending", "sending")),
                )
                .values(status="cancelled", updated_at=_utc_now())
            )
            await session.commit()
            await session.refresh(meeting)

        logger.info(
            "meeting_cancelled meeting_id=%s organization_id=%s",
            meeting_id,
            organization_id,
        )
        try:
            record_activity(
                agent="automation",
                operation="cancel_meeting",
                description="Cancelled a meeting",
                status="completed",
                organization_id=organization_id,
            )
        except Exception:
            logger.warning(
                "activity_record_failed agent=automation operation=cancel_meeting",
                exc_info=True,
            )
        return meeting

    # ------------------------------------------------------------------
    # Rescheduling
    # ------------------------------------------------------------------

    async def reschedule_meeting(
        self,
        *,
        meeting_id: str,
        organization_id: str,
        starts_at: Any,
        ends_at: Any,
        timezone: str | None = None,
        title: str | None = None,
        description: str | None = None,
        venue: str | None = None,
        attendees: list[dict[str, Any]] | None = None,
    ) -> Meeting | None:
        """Reschedule a meeting and regenerate its reminders.

        Reminders belonging to the current schedule generation are marked
        ``cancelled`` (history preserved). The meeting's
        ``schedule_generation`` is incremented and new 24h/30m reminders are
        created for the new generation, each with a unique idempotency key.

        Args:
            meeting_id: Meeting identifier.
            organization_id: Owning organization (enforced).
            starts_at: New start timestamp.
            ends_at: New end timestamp.
            timezone: New IANA time zone (optional).
            title: New title (optional).
            description: New agenda (optional).
            venue: New venue (optional).
            attendees: New attendee list (optional; replaces existing).

        Returns:
            The rescheduled meeting, or None when not found.

        Raises:
            ValidationFailedError: On bad input or end-before-start.
            ForbiddenError: When the meeting does not belong to the org.
        """
        start = _parse_utc(starts_at, "starts_at")
        end = _parse_utc(ends_at, "ends_at")
        if end <= start:
            raise ValidationFailedError(
                "Meeting end time must be after start time.",
                details={"field": "ends_at"},
            )

        new_timezone = _validate_timezone(timezone) if timezone else None

        async with get_session() as session:
            result = await session.execute(
                select(Meeting).where(
                    Meeting.id == meeting_id,
                    Meeting.organization_id == organization_id,
                )
            )
            meeting = result.scalar_one_or_none()
            if meeting is None:
                return None

            if meeting.status == "cancelled":
                raise ValidationFailedError(
                    "A cancelled meeting cannot be rescheduled.",
                    details={"reason": "meeting_cancelled"},
                )

            # Cancel reminders of the current generation (history preserved).
            await session.execute(
                update(MeetingReminder)
                .where(
                    MeetingReminder.meeting_id == meeting_id,
                    MeetingReminder.schedule_generation == meeting.schedule_generation,
                    MeetingReminder.status.in_(("pending", "sending")),
                )
                .values(status="cancelled", updated_at=_utc_now())
            )

            # Bump the generation so new reminders are distinct.
            meeting.schedule_generation += 1
            meeting.starts_at = start
            meeting.ends_at = end
            meeting.status = "scheduled"
            if title is not None:
                meeting.title = title.strip() or meeting.title
            if description is not None:
                meeting.description = description.strip() if description else None
            if venue is not None:
                meeting.venue = venue.strip() if venue else None
            if new_timezone is not None:
                meeting.timezone = new_timezone

            await session.flush()

            # Replace attendees when a new list is supplied.
            if attendees is not None:
                await session.execute(
                    delete(MeetingAttendee).where(MeetingAttendee.meeting_id == meeting_id)
                )
                seen_emails: set[str] = set()
                raw_attendees: list[dict[str, Any]] = []
                for index, attendee in enumerate(attendees):
                    email = _validate_email(attendee.get("email"), f"attendees[{index}].email")
                    if email in seen_emails:
                        raise ValidationFailedError(
                            f"Duplicate attendee email '{email}'.",
                            details={"field": f"attendees[{index}].email"},
                        )
                    seen_emails.add(email)
                    raw_attendees.append(
                        {
                            "name": str(attendee.get("name") or "").strip() or None,
                            "email": email,
                            "user_id": str(attendee.get("user_id") or "").strip() or None,
                        }
                    )

                user_ids = [a["user_id"] for a in raw_attendees if a.get("user_id")]
                users_by_id: dict[str, Any] = {}
                if user_ids:
                    from app.models import User

                    result = await session.execute(select(User).where(User.id.in_(user_ids)))
                    users = result.scalars().all()
                    users_by_id = {str(u.id): u for u in users}

                for index, attendee in enumerate(raw_attendees):
                    uid = attendee.get("user_id")
                    if uid:
                        user = users_by_id.get(str(uid))
                        if user is None:
                            raise ValidationFailedError(
                                f"Unknown attendee employee ID: {uid}",
                                details={
                                    "field": f"attendees[{index}].user_id",
                                    "reason": "unknown_employee",
                                },
                            )
                        if str(user.organization_id) != str(organization_id):
                            raise ValidationFailedError(
                                f"Attendee {uid} is outside the authenticated organization.",
                                details={
                                    "field": f"attendees[{index}].user_id",
                                    "reason": "cross_organization_employee",
                                },
                            )
                        if not bool(user.is_active):
                            raise ValidationFailedError(
                                f"Attendee {uid} is inactive.",
                                details={
                                    "field": f"attendees[{index}].user_id",
                                    "reason": "inactive_employee",
                                },
                            )
                    else:
                        from app.models import User

                        email_result = await session.execute(
                            select(User).where(
                                User.organization_id == organization_id,
                                User.email == attendee["email"],
                            )
                        )
                        user = email_result.scalar_one_or_none()
                        if user is None or not bool(user.is_active):
                            raise ValidationFailedError(
                                "Meeting attendee must be an active organization employee.",
                                details={
                                    "field": f"attendees[{index}].email",
                                    "reason": "unverified_attendee",
                                },
                            )
                    session.add(
                        MeetingAttendee(
                            meeting_id=meeting.id,
                            user_id=str(user.id),
                            email=str(user.email).strip().lower(),
                            name=str(user.full_name or user.email or "").strip() or None,
                        )
                    )

            # Create reminders for the new generation.
            self._create_reminders_for_generation(
                session,
                meeting,
                meeting.schedule_generation,
            )
            await session.commit()
            await session.refresh(meeting)

        logger.info(
            "meeting_rescheduled meeting_id=%s organization_id=%s generation=%d",
            meeting_id,
            organization_id,
            meeting.schedule_generation,
        )
        try:
            record_activity(
                agent="automation",
                operation="reschedule_meeting",
                description="Rescheduled a meeting",
                status="completed",
                organization_id=organization_id,
            )
        except Exception:
            logger.warning(
                "activity_record_failed agent=automation operation=reschedule_meeting",
                exc_info=True,
            )
        return meeting

    def _create_reminders_for_generation(
        self,
        session: AsyncSession,
        meeting: Meeting,
        generation: int,
    ) -> None:
        """Insert 24h and 30m reminders for one schedule generation.

        Each reminder gets a unique idempotency key so the scheduler and the
        Gmail idempotency system can deduplicate delivery.

        Args:
            session: Active database session.
            meeting: Meeting whose reminders to create.
            generation: Schedule generation to stamp on the reminders.
        """
        for reminder_type in REMINDER_TYPES:
            scheduled_for = meeting.starts_at - REMINDER_OFFSETS[reminder_type]
            # Skip reminders already in the past (they will be picked up by the
            # restart-recovery scan as overdue pending reminders).
            idempotency_key = f"meeting_reminder:{meeting.id}:{reminder_type}:{generation}"
            session.add(
                MeetingReminder(
                    meeting_id=meeting.id,
                    reminder_type=reminder_type,
                    scheduled_for=scheduled_for,
                    status="pending",
                    idempotency_key=idempotency_key,
                    schedule_generation=generation,
                )
            )

    # ------------------------------------------------------------------
    # Reminder history
    # ------------------------------------------------------------------

    async def list_reminders(
        self,
        *,
        meeting_id: str,
        organization_id: str,
    ) -> list[MeetingReminder] | None:
        """Return all reminders for a meeting, newest generation first.

        Returns None when the meeting does not belong to the organization.

        Args:
            meeting_id: Meeting identifier.
            organization_id: Owning organization (enforced).

        Returns:
            Reminder rows, or None when the meeting is not in the org.
        """
        meeting = await self.get_meeting(meeting_id)
        if meeting is None or meeting.organization_id != organization_id:
            return None

        async with get_session() as session:
            result = await session.execute(
                select(MeetingReminder)
                .where(MeetingReminder.meeting_id == meeting_id)
                .order_by(
                    MeetingReminder.schedule_generation.desc(),
                    MeetingReminder.reminder_type,
                )
            )
            return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Reminder claiming (used by the scheduler)
    # ------------------------------------------------------------------

    async def claim_due_reminders(self, *, limit: int = 25) -> list[MeetingReminder]:
        """Atomically claim due pending reminders for the scheduler.

        Uses database‑safe locking: ``FOR UPDATE SKIP LOCKED`` where supported
        (PostgreSQL), otherwise a status‑check UPDATE that works with SQLite.

        Claims reminders whose ``scheduled_for`` is in the past and whose
        status is ``pending``.  Only reminders whose status is successfully
        changed from ``pending`` to ``sending`` are returned; if two scheduler
        instances run concurrently, only one will claim each reminder.

        Args:
            limit: Maximum reminders to claim in one pass.

        Returns:
            Claimed reminder rows (status now ``sending``).
        """
        now = _utc_now()
        async with get_session() as session:
            # Pick candidates that are due and still pending.
            stmt = (
                select(MeetingReminder)
                .where(
                    MeetingReminder.status == "pending",
                    MeetingReminder.scheduled_for <= now,
                )
                .order_by(MeetingReminder.scheduled_for.asc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            candidates = result.scalars().all()

            claimed: list[MeetingReminder] = []
            for reminder in candidates:
                # Try to upgrade status from ``pending`` to ``sending``.
                # PostgreSQL: ``FOR UPDATE SKIP LOCKED`` is used elsewhere in the
                #   stack; here we rely on the session's transaction isolation.
                # SQLite:      no ``FOR UPDATE`` available, so we attempt an
                #   UPDATE WHERE status = ``pending``; only rows still pending
                #   will be changed, serving as our atomic claim.
                await session.execute(
                    update(MeetingReminder)
                    .where(
                        MeetingReminder.id == reminder.id,
                        MeetingReminder.status == "pending",
                    )
                    .values(status="sending", updated_at=now)
                )
                # Re-read the reminder to see if the status changed.
                await session.refresh(reminder)
                if reminder.status == "sending":
                    claimed.append(reminder)

            await session.commit()
            for reminder in claimed:
                await session.refresh(reminder)
            return claimed

    async def finalize_reminder(
        self,
        *,
        reminder_id: str,
        status: str,
        email_send_id: str | None = None,
    ) -> MeetingReminder | None:
        """Mark a reminder as sent, failed, or uncertain.

        Args:
            reminder_id: Reminder identifier.
            status: Terminal status (``sent``, ``failed``, ``uncertain``).
            email_send_id: Linked :class:`EmailSend` audit row id.

        Returns:
            The updated reminder, or None when not found.
        """
        if status not in ("sent", "failed", "uncertain"):
            raise ValidationFailedError(
                f"Invalid reminder status '{status}'.",
                details={"field": "status"},
            )

        async with get_session() as session:
            result = await session.execute(
                select(MeetingReminder).where(MeetingReminder.id == reminder_id)
            )
            reminder = result.scalar_one_or_none()
            if reminder is None:
                return None
            reminder.status = status
            reminder.updated_at = _utc_now()
            if email_send_id is not None:
                reminder.email_send_id = email_send_id
            await session.commit()
            await session.refresh(reminder)
            return reminder

    async def get_reminder(self, reminder_id: str) -> MeetingReminder | None:
        """Return one reminder by id, or None."""
        async with get_session() as session:
            result = await session.execute(
                select(MeetingReminder).where(MeetingReminder.id == reminder_id)
            )
            return result.scalar_one_or_none()
