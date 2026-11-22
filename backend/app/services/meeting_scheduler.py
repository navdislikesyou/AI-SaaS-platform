"""Persistent reminder scheduler for meeting reminders.

A single background task runs inside the FastAPI lifespan. It polls the
``meeting_reminders`` table for due reminders, claims them atomically with
``FOR UPDATE SKIP LOCKED`` (so concurrent scheduler executions never process
the same reminder), and sends each one through the existing Gmail send
infrastructure (``app/services/gmail_send.py``).

Reminders are durable database records, not in-memory job entries. On backend
restart the scheduler's first tick recovers any overdue ``pending`` reminders
whose ``scheduled_for`` has already passed.

Single-worker deployment limitation: like the Performance Analyzer job store,
this scheduler is in-process. With multiple workers, only the worker that owns
a given reminder's row lock will process it; reminders claimed by a different
worker are skipped via ``SKIP LOCKED``. There is no cross-worker coordination,
so a multi-worker deployment should run the scheduler on exactly one worker.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.core.exceptions import GmailNotConnectedError
from app.services.gmail_send import (
    EmailSendUncertainError,
    GmailScopeMissingError,
    GoogleOAuthNotConfiguredError,
    send_html_email,
)
from app.services.meeting_service import MeetingService

logger = logging.getLogger(__name__)

#: Default poll interval in seconds.
DEFAULT_POLL_INTERVAL_SECONDS = 60

#: Maximum reminders to claim and process per tick.
_BATCH_LIMIT = 25

#: Template directory shipped with the Automation Agent.
_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "automation_agent" / "templates"

#: Subject pattern per reminder type.
_REMINDER_SUBJECTS = {
    "24h": "Reminder: {title} - Tomorrow",
    "30m": "Upcoming Meeting: {title}",
}

#: Sender name printed at the foot of reminder emails.
_REMINDER_SENDER = "Project Management Office"


def _utc_now() -> datetime:
    """Return the current time as an aware UTC datetime."""
    return datetime.now(UTC)


def _render_reminder_template(
    reminder_type: str,
    meeting: dict[str, Any],
    attendees: list[dict[str, Any]],
) -> tuple[str, str]:
    """Render a reminder email subject and HTML body from a shipped template.

    The templates live in ``automation_agent/templates/`` and use Jinja2-style
    ``{{ var }}`` placeholders plus a single ``{% if reason %}`` block. This
    renderer handles those constructs without importing the agent package,
    keeping the scheduler free of agent coupling.

    Args:
        reminder_type: ``"24h"`` or ``"30m"``.
        meeting: Meeting dict with ``title``, ``date``, ``time``, ``venue``.
        attendees: Resolved attendee records; the first name greets the body.

    Returns:
        A ``(subject, html_body)`` tuple.
    """
    template_file = _TEMPLATE_DIR / f"reminder_{reminder_type}.html"
    if not template_file.is_file():
        raise FileNotFoundError(f"Reminder template not found: {template_file}")

    template = template_file.read_text(encoding="utf-8")

    recipient_name = attendees[0].get("name") if attendees else None
    recipient_name = recipient_name or "Team"

    date_display = meeting.get("date") or "Not Specified"
    time_display = meeting.get("time") or "Not Specified"
    venue_display = meeting.get("venue") or "Not Specified"
    reason = meeting.get("description") or ""

    # Handle the {% if reason %}...{% endif %} block.
    if not reason:
        template = re.sub(
            r"\s*\{\% if reason \%\}.*?\{\% endif \%\}",
            "",
            template,
            flags=re.DOTALL,
        )

    context = {
        "recipient_name": recipient_name,
        "sender_name": _REMINDER_SENDER,
        "title": meeting.get("title") or "Meeting",
        "date": date_display,
        "time": time_display,
        "venue": venue_display,
    }
    for key, value in context.items():
        template = template.replace(f"{{{{ {key} }}}}", str(value))

    subject = _REMINDER_SUBJECTS[reminder_type].format(title=context["title"])
    return subject, template


class MeetingScheduler:
    """Persistent, database-backed reminder scheduler."""

    def __init__(
        self,
        settings: Settings,
        poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> None:
        self._settings = settings
        self._poll_interval = poll_interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._service = MeetingService(settings)

    async def start(self) -> None:
        """Start the scheduler background task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info(
            "meeting_scheduler_started poll_interval_seconds=%d",
            self._poll_interval,
        )

    async def stop(self) -> None:
        """Stop the scheduler background task."""
        if not self._running:
            return
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("meeting_scheduler_stopped")

    async def _run(self) -> None:
        """Main scheduler loop: claim and send due reminders each tick."""
        while self._running:
            try:
                await self._process_due_reminders()
            except asyncio.CancelledError:
                raise
            except Exception:
                # A tick failure must not kill the scheduler loop.
                logger.exception("meeting_scheduler_tick_failed")
            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                raise

    async def _process_due_reminders(self) -> None:
        """Claim due reminders and send each one."""
        claimed = await self._service.claim_due_reminders(limit=_BATCH_LIMIT)
        if not claimed:
            return

        logger.info(
            "meeting_scheduler_claimed count=%d",
            len(claimed),
        )

        for reminder in claimed:
            try:
                await self._send_one_reminder(reminder)
            except EmailSendUncertainError:
                # Outcome unknown: preserve uncertain state, never auto-retry.
                await self._service.finalize_reminder(reminder_id=reminder.id, status="uncertain")
                logger.warning(
                    "reminder_uncertain reminder_id=%s meeting_id=%s",
                    reminder.id,
                    reminder.meeting_id,
                )
            except (
                GoogleOAuthNotConfiguredError,
                GmailNotConnectedError,
                GmailScopeMissingError,
            ):
                # Mailbox not available: conclusive failure, mark failed.
                await self._service.finalize_reminder(reminder_id=reminder.id, status="failed")
                logger.warning(
                    "reminder_unavailable reminder_id=%s meeting_id=%s",
                    reminder.id,
                    reminder.meeting_id,
                )
            except Exception:
                # Conclusive Gmail failure or unexpected error.
                await self._service.finalize_reminder(reminder_id=reminder.id, status="failed")
                logger.exception(
                    "reminder_send_failed reminder_id=%s meeting_id=%s",
                    reminder.id,
                    reminder.meeting_id,
                )

    async def _send_one_reminder(self, reminder: Any) -> None:
        """Send one reminder and finalize its delivery status.

        Args:
            reminder: A claimed :class:`MeetingReminder` (status ``sending``).

        Raises:
            EmailSendUncertainError: If the send outcome is unknown.
            GoogleOAuthNotConfiguredError / GmailNotConnectedError /
            GmailScopeMissingError: If the mailbox cannot be used.
            Exception: On any conclusive Gmail failure.
        """
        meeting = await self._service.get_meeting(reminder.meeting_id)
        if meeting is None:
            # Meeting was deleted; nothing to do.
            await self._service.finalize_reminder(reminder_id=reminder.id, status="cancelled")
            return

        if meeting.status == "cancelled":
            await self._service.finalize_reminder(reminder_id=reminder.id, status="cancelled")
            return

        # Verify this reminder belongs to the current schedule generation.
        if reminder.schedule_generation != meeting.schedule_generation:
            await self._service.finalize_reminder(reminder_id=reminder.id, status="cancelled")
            return

        attendees = await self._service.list_attendees(reminder.meeting_id)
        if not attendees:
            await self._service.finalize_reminder(reminder_id=reminder.id, status="cancelled")
            return

        # Build display date/time in the meeting's configured time zone.
        import zoneinfo

        tz = zoneinfo.ZoneInfo(meeting.timezone)
        starts_at = meeting.starts_at
        if starts_at.tzinfo is None:
            starts_at = starts_at.replace(tzinfo=UTC)
        local_start = starts_at.astimezone(tz)

        meeting_display = {
            "title": meeting.title,
            "date": local_start.strftime("%d %B %Y"),
            "time": local_start.strftime("%I:%M %p"),
            "venue": meeting.venue or "Not Specified",
            "description": meeting.description or "",
        }

        subject, html_body = _render_reminder_template(
            reminder.reminder_type,
            meeting_display,
            [
                {
                    "name": a.get("name"),
                    "email": a.get("email"),
                }
                for a in attendees
            ],
        )

        result = await send_html_email(
            organization_id=meeting.organization_id,
            sender_user_id=meeting.organizer_user_id,
            recipients=[
                {
                    "name": a.get("name") or a.get("email") or "Attendee",
                    "email": a.get("email") or "",
                }
                for a in attendees
            ],
            subject=subject,
            html_body=html_body,
            idempotency_key=reminder.idempotency_key,
            settings=self._settings,
        )

        email_send_id = result.get("message_id")
        await self._service.finalize_reminder(
            reminder_id=reminder.id,
            status="sent",
            email_send_id=email_send_id,
        )
        logger.info(
            "reminder_sent reminder_id=%s meeting_id=%s type=%s email_send_id=%s",
            reminder.id,
            reminder.meeting_id,
            reminder.reminder_type,
            email_send_id,
        )
