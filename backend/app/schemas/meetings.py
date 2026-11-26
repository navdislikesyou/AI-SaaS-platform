"""Pydantic schemas for the Meeting scheduling API.

Meeting records are AXON records owned by an organization. The Automation Agent
stays draft-only: it parses and drafts invitations, but meeting creation,
editing, cancellation, and reminder scheduling are backend-owned operations.

All timestamps cross the API boundary as ISO-8601 strings and are stored in UTC.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AttendeeCreate(BaseModel):
    """One attendee supplied when creating or rescheduling a meeting."""

    name: str | None = None
    email: str
    user_id: str | None = None


class MeetingCreate(BaseModel):
    """Payload for creating a meeting.

    No email is sent automatically. Use ``POST /meetings/{id}/send-invitation``
    to dispatch the invitation after explicit confirmation.
    """

    model_config = ConfigDict(populate_by_name=True)

    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    starts_at: datetime
    ends_at: datetime
    timezone: str
    venue: str | None = None
    attendees: list[AttendeeCreate] = Field(default_factory=list)


class MeetingUpdate(BaseModel):
    """Payload for updating a meeting."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    timezone: str | None = None
    venue: str | None = None


class AttendeeResponse(BaseModel):
    """One meeting attendee as returned to the client."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    user_id: str | None = None
    email: str
    name: str | None = None


class MeetingResponse(BaseModel):
    """One meeting record as returned to the client."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    organization_id: str
    organizer_user_id: str | None = None
    title: str
    description: str | None = None
    starts_at: datetime
    ends_at: datetime
    timezone: str
    venue: str | None = None
    status: str
    schedule_generation: int
    created_at: datetime
    updated_at: datetime


class ReminderResponse(BaseModel):
    """One reminder delivery record as returned to the client."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    meeting_id: str
    reminder_type: str
    scheduled_for: datetime
    status: str
    schedule_generation: int
    email_send_id: str | None = None
    created_at: datetime
    updated_at: datetime


class MeetingDetailResponse(BaseModel):
    """One meeting with its attendees and reminder history."""

    model_config = ConfigDict(populate_by_name=True)

    meeting: MeetingResponse
    attendees: list[AttendeeResponse] = Field(default_factory=list)
    reminders: list[ReminderResponse] = Field(default_factory=list)


class MeetingListResponse(BaseModel):
    """Payload for the meeting list endpoint."""

    model_config = ConfigDict(populate_by_name=True)

    meetings: list[MeetingResponse] = Field(default_factory=list)
    total: int = 0


class RescheduleRequest(BaseModel):
    """Payload for rescheduling a meeting."""

    starts_at: datetime
    ends_at: datetime
    timezone: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    venue: str | None = None
    attendees: list[AttendeeCreate] | None = None


class SendInvitationRequest(BaseModel):
    """Payload for sending a meeting invitation email.

    ``confirm`` must be exactly ``true`` (truthy strings do not count).
    ``idempotency_key`` makes retries after a timeout replay the recorded
    outcome instead of resending.
    """

    subject: str = Field(min_length=1, max_length=1000)
    html_body: str = Field(min_length=1)
    confirm: bool
    idempotency_key: str = Field(min_length=1)


class ReminderListResponse(BaseModel):
    """Payload for the reminder history endpoint."""

    model_config = ConfigDict(populate_by_name=True)

    reminders: list[ReminderResponse] = Field(default_factory=list)
    total: int = 0


def meeting_to_response(meeting: Any) -> MeetingResponse:
    """Convert a SQLAlchemy Meeting to a :class:`MeetingResponse`."""
    return MeetingResponse(
        id=meeting.id,
        organization_id=meeting.organization_id,
        organizer_user_id=meeting.organizer_user_id,
        title=meeting.title,
        description=meeting.description,
        starts_at=meeting.starts_at,
        ends_at=meeting.ends_at,
        timezone=meeting.timezone,
        venue=meeting.venue,
        status=meeting.status,
        schedule_generation=meeting.schedule_generation,
        created_at=meeting.created_at,
        updated_at=meeting.updated_at,
    )


def attendee_to_response(attendee: Any) -> AttendeeResponse:
    """Convert a SQLAlchemy MeetingAttendee to a :class:`AttendeeResponse`."""
    return AttendeeResponse(
        id=attendee.id,
        user_id=attendee.user_id,
        email=attendee.email,
        name=attendee.name,
    )


def reminder_to_response(reminder: Any) -> ReminderResponse:
    """Convert a SQLAlchemy MeetingReminder to a :class:`ReminderResponse`."""
    return ReminderResponse(
        id=reminder.id,
        meeting_id=reminder.meeting_id,
        reminder_type=reminder.reminder_type,
        scheduled_for=reminder.scheduled_for,
        status=reminder.status,
        schedule_generation=reminder.schedule_generation,
        email_send_id=reminder.email_send_id,
        created_at=reminder.created_at,
        updated_at=reminder.updated_at,
    )
