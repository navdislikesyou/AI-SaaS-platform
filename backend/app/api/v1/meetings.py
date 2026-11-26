"""Meeting scheduling API for the Automation Agent.

Endpoints:

- ``POST /meetings`` -- create a meeting (no email sent automatically)
- ``GET /meetings`` -- list organization-scoped meetings
- ``GET /meetings/{meeting_id}`` -- get meeting details with attendees and reminders
- ``PATCH /meetings/{meeting_id}`` -- update a meeting
- ``DELETE /meetings/{meeting_id}`` -- cancel a meeting (cancels pending reminders)
- ``POST /meetings/{meeting_id}/reschedule`` -- reschedule and regenerate reminders
- ``GET /meetings/{meeting_id}/reminders`` -- list reminder delivery history
- ``POST /meetings/{meeting_id}/send-invitation`` -- send the invitation email
  (explicitly confirmed, idempotent)

Meeting creation never sends email. Invitation sending is a separate, explicitly
confirmed operation that reuses the existing Gmail send infrastructure
(``app/services/gmail_send.py``) with idempotency keys and audit rows.

The Automation Agent package stays draft-only: it parses and drafts
invitations, but this router is the only place that creates, edits, cancels,
or schedules meeting records.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    get_current_user_from_token,
    get_settings_dep,
    require_manager,
)
from app.core.config import Settings
from app.core.exceptions import (
    AppError,
    ForbiddenError,
)
from app.models import User
from app.schemas.common import APIResponse
from app.schemas.meetings import (
    MeetingCreate,
    MeetingDetailResponse,
    MeetingListResponse,
    MeetingResponse,
    MeetingUpdate,
    ReminderListResponse,
    RescheduleRequest,
    SendInvitationRequest,
    attendee_to_response,
    meeting_to_response,
    reminder_to_response,
)
from app.services.gmail_send import send_html_email
from app.services.meeting_service import MeetingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/meetings", tags=["meetings"])


def _service() -> MeetingService:
    """Build a per-request meeting service."""
    return MeetingService()


def _require_organization(current_user: User) -> str:
    """Return the caller's organization id, raising 403 if missing."""
    if not current_user.organization_id:
        raise ForbiddenError(
            "Meetings require an authenticated organisation.",
            details={"reason": "missing_organization"},
        )
    return current_user.organization_id


@router.post(
    "",
    response_model=APIResponse[MeetingResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a meeting",
    description="Create a new meeting. No email is sent automatically.",
)
async def create_meeting(
    payload: MeetingCreate,
    current_user: User = Depends(require_manager),
    settings: Settings = Depends(get_settings_dep),
    service: MeetingService = Depends(_service),
) -> APIResponse[MeetingResponse]:
    """Create a meeting in ``scheduled`` status.

    Only manager/administrator users may create meetings. Invitation sending is
    a separate endpoint.
    """
    organization_id = _require_organization(current_user)

    meeting = await service.create_meeting(
        organization_id=organization_id,
        organizer_user_id=current_user.id,
        title=payload.title,
        description=payload.description,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        timezone=payload.timezone,
        venue=payload.venue,
        attendees=[
            {
                "name": a.name,
                "email": a.email,
                "user_id": a.user_id,
            }
            for a in payload.attendees
        ],
    )
    return APIResponse(
        data=meeting_to_response(meeting),
        message="Meeting created.",
    )


@router.get(
    "",
    response_model=APIResponse[MeetingListResponse],
    status_code=status.HTTP_200_OK,
    summary="List meetings",
    description="List organization-scoped meetings, newest first.",
)
async def list_meetings(
    status: str | None = Query(
        None, description="Filter by meeting status (scheduled, cancelled, completed)."
    ),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user_from_token),
    service: MeetingService = Depends(_service),
) -> APIResponse[MeetingListResponse]:
    """List meetings for the caller's organization."""
    organization_id = _require_organization(current_user)
    meetings = await service.list_meetings(
        organization_id=organization_id, status=status, limit=limit
    )
    return APIResponse(
        data=MeetingListResponse(
            meetings=[meeting_to_response(m) for m in meetings],
            total=len(meetings),
        ),
        message="Meetings retrieved.",
    )


@router.get(
    "/{meeting_id}",
    response_model=APIResponse[MeetingDetailResponse],
    status_code=status.HTTP_200_OK,
    summary="Get meeting details",
    description="Get one meeting with its attendees and reminder history.",
)
async def get_meeting(
    meeting_id: str,
    current_user: User = Depends(get_current_user_from_token),
    service: MeetingService = Depends(_service),
) -> APIResponse[MeetingDetailResponse]:
    """Get meeting details, scoped to the caller's organization."""
    organization_id = _require_organization(current_user)
    detail = await service.get_meeting_with_details(meeting_id)
    if detail is None:
        raise AppError(
            f"Meeting '{meeting_id}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="MEETING_NOT_FOUND",
        )
    if detail["meeting"]["organization_id"] != organization_id:
        raise ForbiddenError(
            "Meeting belongs to another organisation.",
            details={"reason": "cross_organization"},
        )
    return APIResponse(
        data=MeetingDetailResponse(
            meeting=meeting_to_response(detail["meeting"]),
            attendees=[attendee_to_response(a) for a in detail["attendees"]],
            reminders=[reminder_to_response(r) for r in detail["reminders"]],
        ),
        message="Meeting retrieved.",
    )


@router.patch(
    "/{meeting_id}",
    response_model=APIResponse[MeetingResponse],
    status_code=status.HTTP_200_OK,
    summary="Update a meeting",
    description="Update mutable fields of a scheduled meeting.",
)
async def update_meeting(
    meeting_id: str,
    payload: MeetingUpdate,
    current_user: User = Depends(require_manager),
    service: MeetingService = Depends(_service),
) -> APIResponse[MeetingResponse]:
    """Update a meeting. Manager/administrator only."""
    organization_id = _require_organization(current_user)
    meeting = await service.update_meeting(
        meeting_id=meeting_id,
        organization_id=organization_id,
        title=payload.title,
        description=payload.description,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        timezone=payload.timezone,
        venue=payload.venue,
    )
    if meeting is None:
        raise AppError(
            f"Meeting '{meeting_id}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="MEETING_NOT_FOUND",
        )
    return APIResponse(
        data=meeting_to_response(meeting),
        message="Meeting updated.",
    )


@router.delete(
    "/{meeting_id}",
    response_model=APIResponse[MeetingResponse],
    status_code=status.HTTP_200_OK,
    summary="Cancel a meeting",
    description="Cancel a meeting and cancel its pending reminders.",
)
async def cancel_meeting(
    meeting_id: str,
    current_user: User = Depends(require_manager),
    service: MeetingService = Depends(_service),
) -> APIResponse[MeetingResponse]:
    """Cancel a meeting. Manager/administrator only."""
    organization_id = _require_organization(current_user)
    meeting = await service.cancel_meeting(meeting_id=meeting_id, organization_id=organization_id)
    if meeting is None:
        raise AppError(
            f"Meeting '{meeting_id}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="MEETING_NOT_FOUND",
        )
    return APIResponse(
        data=meeting_to_response(meeting),
        message="Meeting cancelled.",
    )


@router.post(
    "/{meeting_id}/reschedule",
    response_model=APIResponse[MeetingResponse],
    status_code=status.HTTP_200_OK,
    summary="Reschedule a meeting",
    description="Reschedule a meeting and regenerate its reminders.",
)
async def reschedule_meeting(
    meeting_id: str,
    payload: RescheduleRequest,
    current_user: User = Depends(require_manager),
    service: MeetingService = Depends(_service),
) -> APIResponse[MeetingResponse]:
    """Reschedule a meeting. Manager/administrator only."""
    organization_id = _require_organization(current_user)
    meeting = await service.reschedule_meeting(
        meeting_id=meeting_id,
        organization_id=organization_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        timezone=payload.timezone,
        title=payload.title,
        description=payload.description,
        venue=payload.venue,
        attendees=[
            {
                "name": a.name,
                "email": a.email,
                "user_id": a.user_id,
            }
            for a in (payload.attendees or [])
        ],
    )
    if meeting is None:
        raise AppError(
            f"Meeting '{meeting_id}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="MEETING_NOT_FOUND",
        )
    return APIResponse(
        data=meeting_to_response(meeting),
        message="Meeting rescheduled.",
    )


@router.get(
    "/{meeting_id}/reminders",
    response_model=APIResponse[ReminderListResponse],
    status_code=status.HTTP_200_OK,
    summary="List reminder history",
    description="List reminder delivery history for a meeting.",
)
async def list_reminders(
    meeting_id: str,
    current_user: User = Depends(get_current_user_from_token),
    service: MeetingService = Depends(_service),
) -> APIResponse[ReminderListResponse]:
    """List reminders for a meeting, scoped to the caller's organization."""
    organization_id = _require_organization(current_user)
    reminders = await service.list_reminders(meeting_id=meeting_id, organization_id=organization_id)
    if reminders is None:
        raise AppError(
            f"Meeting '{meeting_id}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="MEETING_NOT_FOUND",
        )
    return APIResponse(
        data=ReminderListResponse(
            reminders=[reminder_to_response(r) for r in reminders],
            total=len(reminders),
        ),
        message="Reminder history retrieved.",
    )


@router.post(
    "/{meeting_id}/send-invitation",
    response_model=APIResponse[dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="Send meeting invitation",
    description="Send the meeting invitation email (explicitly confirmed, idempotent).",
)
async def send_invitation(
    meeting_id: str,
    payload: SendInvitationRequest,
    current_user: User = Depends(require_manager),
    settings: Settings = Depends(get_settings_dep),
    service: MeetingService = Depends(_service),
) -> APIResponse[dict[str, Any]]:
    """Send the meeting invitation through the organization's Gmail mailbox.

    Requires manager/administrator, ``confirm is True``, valid attendees, a
    non-empty subject and HTML body, and an idempotency key. Reuses the
    existing Gmail send infrastructure with audit and idempotency.
    """
    if payload.confirm is not True:
        from app.core.exceptions import ValidationFailedError

        raise ValidationFailedError(
            "Send invitation requires confirm to be true.",
            details={"reason": "confirmation_required"},
        )

    organization_id = _require_organization(current_user)
    detail = await service.get_meeting_with_details(meeting_id)
    if detail is None:
        raise AppError(
            f"Meeting '{meeting_id}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="MEETING_NOT_FOUND",
        )
    if detail["meeting"]["organization_id"] != organization_id:
        raise ForbiddenError(
            "Meeting belongs to another organisation.",
            details={"reason": "cross_organization"},
        )
    if detail["meeting"]["status"] == "cancelled":
        from app.core.exceptions import ValidationFailedError

        raise ValidationFailedError(
            "Cannot send an invitation for a cancelled meeting.",
            details={"reason": "meeting_cancelled"},
        )

    attendees = detail["attendees"]
    if not attendees:
        from app.core.exceptions import ValidationFailedError

        raise ValidationFailedError(
            "Meeting has no attendees to invite.",
            details={"reason": "no_attendees"},
        )

    recipients = [{"name": a["name"] or a["email"], "email": a["email"]} for a in attendees]

    result = await send_html_email(
        organization_id=organization_id,
        sender_user_id=current_user.id,
        recipients=recipients,
        subject=payload.subject.strip(),
        html_body=payload.html_body,
        idempotency_key=payload.idempotency_key.strip(),
        settings=settings,
    )

    logger.info(
        "meeting_invitation_sent meeting_id=%s organization_id=%s recipients=%d",
        meeting_id,
        organization_id,
        len(recipients),
    )
    return APIResponse(
        data={
            "meeting_id": meeting_id,
            "sent": result.get("sent"),
            "message_id": result.get("message_id"),
            "gmail_message_id": result.get("gmail_message_id"),
            "recipients_count": result.get("recipients_count"),
            "status": result.get("status"),
            "idempotency_key": result.get("idempotency_key"),
            "duplicate": result.get("duplicate"),
        },
        message="Invitation sent.",
    )
