"""Organization-scoped Gmail sending for the Automation Agent.

This module is the only place that calls Google's ``users().messages().send``
endpoint. It reuses :mod:`app.services.gmail_connection` for credential
decryption, refresh, and ``invalid_grant`` handling, and reuses
:mod:`app.core.token_encryption` through that module. It never reads a
``credentials.json`` file, never uses ``InstalledAppFlow``, and never
logs an access token, refresh token, or email body.

The public entry point is :func:`send_html_email`. It is async and is
meant to be invoked from a worker thread via ``anyio.from_thread.run``,
the same bridge the Employee Insights adapter already uses for its Gmail
calls.
"""

from __future__ import annotations

import base64
import email.utils
import html as _html
import json
import logging
import re
from datetime import UTC, datetime
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import anyio
from googleapiclient.errors import HttpError
from sqlalchemy import select

from app.core.config import Settings
from app.core.database import get_session
from app.core.exceptions import (
    EmailSendConflictError,
    EmailSendUncertainError,
    GmailScopeMissingError,
    GoogleOAuthNotConfiguredError,
    ValidationFailedError,
)
from app.models import EmailSend, User
from app.services.gmail_connection import (
    build_gmail_service,
    get_connection_status,
)

logger = logging.getLogger(__name__)

_GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.send"
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _scope_present(scopes: list[str]) -> bool:
    """Return whether ``gmail.send`` is among the granted scopes."""
    return _GMAIL_SCOPE in scopes


def build_raw_message(
    *,
    sender: str,
    recipients: list[str],
    subject: str,
    html_body: str,
) -> str:
    """Build the base64url-encoded raw MIME message Gmail expects.

    The message is ``multipart/alternative`` with a tag-stripped plain-text
    fallback and the HTML part. UTF-8 is used throughout and the subject is
    header-encoded so non-ASCII subjects survive.

    Args:
        sender: The mailbox the message is sent from.
        recipients: Recipient email addresses.
        subject: Subject line.
        html_body: HTML body.

    Returns:
        The base64url-encoded raw message string.
    """
    message = MIMEMultipart("alternative")
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = Header(subject, "utf-8")  # type: ignore[assignment]
    message["Date"] = email.utils.formatdate(localtime=False)
    message["Message-ID"] = email.utils.make_msgid(domain=sender.split("@", 1)[-1] or None)

    if _looks_like_html(html_body):
        html_part = html_body
        plain_part = _strip_html(html_body)
    else:
        html_part = _text_to_html(html_body)
        plain_part = html_body

    message.attach(MIMEText(plain_part, "plain", "utf-8"))
    message.attach(MIMEText(html_part, "html", "utf-8"))

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    return raw


def _looks_like_html(text: str) -> bool:
    """Return whether the text already contains HTML markup.

    Args:
        text: Candidate body.

    Returns:
        True when an HTML tag is present.
    """
    return bool(re.search(r"<[a-zA-Z][^>]*>", text))


def _text_to_html(text: str) -> str:
    """Convert plain text into readable HTML paragraphs.

    Newlines are preserved: a blank line starts a new paragraph and a single
    newline becomes a ``<br>``. Special characters are escaped so untrusted
    text cannot inject markup.

    Args:
        text: Plain-text body.

    Returns:
        An HTML rendering of the text.
    """
    escaped = _html.escape(text)
    paragraphs = re.split(r"\n\s*\n", escaped)
    rendered: list[str] = []
    for paragraph in paragraphs:
        lines = list(paragraph.split("\n"))
        inner = "<br>\n".join(lines).strip()
        if inner:
            rendered.append(f"<p>{inner}</p>")
    if not rendered:
        return f"<p>{escaped}</p>"
    return "\n".join(rendered)


def _strip_html(html: str) -> str:
    """Return a plain-text rendering of an HTML body.

    Block-level boundaries become newlines so the plain-text alternative
    keeps the paragraph structure of the HTML part.

    Args:
        html: The HTML body.

    Returns:
        The text content with tags removed.
    """
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|li|h[1-6]|tr)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = text.strip()
    return text or "(HTML message)"


def _validate_recipients(recipients: Any, max_count: int) -> list[dict[str, str]]:
    """Validate and normalize the recipient list.

    Args:
        recipients: The raw recipient list from the payload.
        max_count: Maximum number of recipients allowed.

    Returns:
        A list of ``{"name", "email"}`` mappings with normalized addresses.

    Raises:
        ValidationFailedError: If the recipients are malformed or too many.
    """
    if not isinstance(recipients, list) or not recipients:
        raise ValidationFailedError(
            "Operation 'send_email' requires a non-empty recipients list.",
            details={
                "agent": "automation",
                "operation": "send_email",
                "reason": "invalid_recipients",
            },
        )

    if len(recipients) > max_count:
        raise ValidationFailedError(
            f"Operation 'send_email' allows at most {max_count} recipients.",
            details={
                "agent": "automation",
                "operation": "send_email",
                "reason": "too_many_recipients",
            },
        )

    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in recipients:
        if not isinstance(item, dict):
            raise ValidationFailedError(
                "Operation 'send_email' recipients must be objects with name and email.",
                details={
                    "agent": "automation",
                    "operation": "send_email",
                    "reason": "invalid_recipients",
                },
            )
        name = str(item.get("name") or "").strip()
        email_addr = str(item.get("email") or "").strip().lower()
        if not email_addr or not _EMAIL_RE.match(email_addr):
            raise ValidationFailedError(
                f"Operation 'send_email' recipient email is invalid: {email_addr!r}.",
                details={
                    "agent": "automation",
                    "operation": "send_email",
                    "reason": "invalid_recipients",
                },
            )
        if email_addr in seen:
            continue
        seen.add(email_addr)
        normalized.append({"name": name or email_addr, "email": email_addr})

    if not normalized:
        raise ValidationFailedError(
            "Operation 'send_email' requires at least one valid recipient.",
            details={
                "agent": "automation",
                "operation": "send_email",
                "reason": "invalid_recipients",
            },
        )
    return normalized


async def _verify_recipients_production(
    recipients: list[dict[str, str]], organization_id: str
) -> None:
    """Ensure every recipient resolves to a verified AXON user in the org.

    In production, recipient identities must come from verified, organization-
    specific AXON User records. Demo employee-directory addresses are never
    accepted here.

    Args:
        recipients: Normalized recipients.
        organization_id: The authenticated organization.

    Raises:
        ValidationFailedError: If any recipient is not a verified org user.
    """
    async with get_session() as session:
        result = await session.execute(
            select(User.email).where(User.organization_id == organization_id)
        )
        allowed = {str(row[0]).strip().lower() for row in result.all() if row[0]}

    for recipient in recipients:
        if recipient["email"] not in allowed:
            raise ValidationFailedError(
                "Operation 'send_email' recipient is not a verified organization user.",
                details={
                    "agent": "automation",
                    "operation": "send_email",
                    "reason": "recipient_not_verified",
                    "email": recipient["email"],
                },
            )


async def _claim_idempotency(
    *,
    organization_id: str,
    sender_user_id: str | None,
    sender_mailbox: str,
    recipients: list[dict[str, str]],
    subject: str,
    idempotency_key: str,
) -> EmailSend:
    """Claim or replay an idempotency key.

    Args:
        organization_id: The authenticated organization.
        sender_user_id: The authenticated sender.
        sender_mailbox: The connected mailbox.
        recipients: Normalized recipients.
        subject: Subject line.
        idempotency_key: Client-supplied key.

    Returns:
        The claimed (or replayed) :class:`EmailSend` row.

    Raises:
        EmailSendConflictError: If the key is in progress, uncertain, or reused
            for different recipients/subject.
    """
    recipient_json = json.dumps([r["email"] for r in recipients], ensure_ascii=False)

    async with get_session() as session:
        existing = await session.execute(
            select(EmailSend).where(
                EmailSend.organization_id == organization_id,
                EmailSend.idempotency_key == idempotency_key,
            )
        )
        row = existing.scalar_one_or_none()

        if row is not None:
            if row.status == "sent":
                # Idempotent replay: same recipients/subject → return recorded.
                if row.recipients != recipient_json or row.subject != subject:
                    raise EmailSendConflictError(
                        "Idempotency key reused for a different email.",
                        details={"reason": "mismatch", "message_id": row.id},
                    )
                return row
            if row.status == "uncertain":
                raise EmailSendConflictError(
                    "A previous send attempt has an uncertain outcome and cannot "
                    "be retried automatically.",
                    details={"reason": "uncertain", "message_id": row.id},
                )
            if row.status == "sending":
                raise EmailSendConflictError(
                    "A send with this idempotency key is already in progress.",
                    details={"reason": "in_progress", "message_id": row.id},
                )
            # status == "failed": allow re-claim.
            row.status = "sending"
            row.sender_user_id = sender_user_id
            row.sender_mailbox = sender_mailbox
            row.recipients = recipient_json
            row.subject = subject
            row.error_code = None
            row.gmail_message_id = None
            row.updated_at = datetime.now(UTC)
            await session.commit()
            await session.refresh(row)
            return row

        row = EmailSend(
            organization_id=organization_id,
            sender_user_id=sender_user_id,
            sender_mailbox=sender_mailbox,
            recipients=recipient_json,
            subject=subject,
            status="sending",
            idempotency_key=idempotency_key,
        )
        session.add(row)
        try:
            await session.commit()
        except Exception as exc:
            await session.rollback()
            # Concurrent insert lost the race: re-read and classify.
            existing2 = await session.execute(
                select(EmailSend).where(
                    EmailSend.organization_id == organization_id,
                    EmailSend.idempotency_key == idempotency_key,
                )
            )
            row2 = existing2.scalar_one_or_none()
            if row2 is not None:
                if row2.status == "sent":
                    if row2.recipients != recipient_json or row2.subject != subject:
                        raise EmailSendConflictError(
                            "Idempotency key reused for a different email.",
                            details={"reason": "mismatch", "message_id": row2.id},
                        ) from exc
                    return row2
                if row2.status == "uncertain":
                    raise EmailSendConflictError(
                        "A previous send attempt has an uncertain outcome and cannot "
                        "be retried automatically.",
                        details={"reason": "uncertain", "message_id": row2.id},
                    ) from exc
                if row2.status == "sending":
                    raise EmailSendConflictError(
                        "A send with this idempotency key is already in progress.",
                        details={"reason": "in_progress", "message_id": row2.id},
                    ) from exc
                # failed: re-claim
                row2.status = "sending"
                row2.sender_user_id = sender_user_id
                row2.sender_mailbox = sender_mailbox
                row2.recipients = recipient_json
                row2.subject = subject
                row2.error_code = None
                row2.gmail_message_id = None
                row2.updated_at = datetime.now(UTC)
                await session.commit()
                await session.refresh(row2)
                return row2
            raise
        await session.refresh(row)
        return row


async def _update_status(
    row_id: str, *, status: str, gmail_message_id: str | None = None, error_code: str | None = None
) -> None:
    """Update an audit row's terminal state.

    Args:
        row_id: The audit row id.
        status: Terminal status (``sent``, ``failed``, ``uncertain``).
        gmail_message_id: Upstream message id when sent.
        error_code: Sanitized error code when failed/uncertain.
    """
    async with get_session() as session:
        result = await session.execute(select(EmailSend).where(EmailSend.id == row_id))
        row = result.scalar_one_or_none()
        if row is None:
            return
        row.status = status
        row.gmail_message_id = gmail_message_id
        row.error_code = error_code
        row.updated_at = datetime.now(UTC)
        await session.commit()


async def send_html_email(
    *,
    organization_id: str,
    sender_user_id: str | None,
    recipients: list[dict[str, str]],
    subject: str,
    html_body: str,
    idempotency_key: str,
    settings: Settings,
) -> dict[str, Any]:
    """Send an HTML email through the organization's connected Gmail mailbox.

    Args:
        organization_id: Authenticated organization.
        sender_user_id: Authenticated sender.
        recipients: Normalized recipients.
        subject: Subject line.
        html_body: HTML body.
        idempotency_key: Client-supplied idempotency key.
        settings: Application settings.

    Returns:
        A sanitized result with ``sent``, ``message_id``, ``recipients_count``,
        ``subject``, ``status`` and ``idempotency_key``.

    Raises:
        GoogleOAuthNotConfiguredError: If OAuth is disabled.
        GmailScopeMissingError: If the connection lacks ``gmail.send``.
        GmailNotConnectedError: If no connection exists.
        EmailSendConflictError: On in-progress/uncertain/mismatch.
        ValidationFailedError: On invalid recipients (production verification).
        AgentExecutionError: On a conclusive Gmail API failure.
        EmailSendUncertainError: On an uncertain transport outcome.
    """
    from app.core.exceptions import AgentExecutionError, GmailNotConnectedError

    if not settings.google_oauth_configured:
        raise GoogleOAuthNotConfiguredError(GoogleOAuthNotConfiguredError.DEFAULT_MESSAGE)

    recipients = _validate_recipients(recipients, settings.gmail_send_max_recipients)
    if len(html_body.encode("utf-8")) > settings.gmail_send_max_html_bytes:
        raise ValidationFailedError(
            "Operation 'send_email' HTML body exceeds the size limit.",
            details={"agent": "automation", "operation": "send_email", "reason": "html_too_large"},
        )
    if not subject.strip():
        raise ValidationFailedError(
            "Operation 'send_email' requires a non-empty subject.",
            details={"agent": "automation", "operation": "send_email", "reason": "invalid_subject"},
        )
    subject = subject.strip()

    # Production: recipients must resolve to verified org users.
    if settings.is_production:
        await _verify_recipients_production(recipients, organization_id)

    status_info = await get_connection_status(organization_id)
    if not status_info.connected:
        raise GmailNotConnectedError(GmailNotConnectedError.DEFAULT_MESSAGE)
    if not _scope_present(status_info.scopes):
        raise GmailScopeMissingError(GmailScopeMissingError.DEFAULT_MESSAGE)

    sender_mailbox = status_info.gmail_address
    if not sender_mailbox:
        raise GmailNotConnectedError(GmailNotConnectedError.DEFAULT_MESSAGE)

    # Claim before any Google call.
    row = await _claim_idempotency(
        organization_id=organization_id,
        sender_user_id=sender_user_id,
        sender_mailbox=sender_mailbox,
        recipients=recipients,
        subject=subject,
        idempotency_key=idempotency_key,
    )

    # Idempotent replay: already sent, no Google call.
    if row.status == "sent" and row.gmail_message_id is not None:
        # Re-read recipients to confirm match already done in claim.
        return {
            "sent": True,
            "message_id": row.id,
            "gmail_message_id": row.gmail_message_id,
            "recipients_count": len(recipients),
            "subject": subject,
            "status": "sent",
            "idempotency_key": idempotency_key,
            "duplicate": True,
        }

    # Build service (decrypt + refresh + invalid_grant handling).
    try:
        gmail_service = await build_gmail_service(organization_id, settings)
    except Exception:
        # Any failure here is conclusive: no send was attempted.
        await _update_status(row.id, status="failed", error_code="gmail_service_unavailable")
        raise

    raw = build_raw_message(
        sender=sender_mailbox,
        recipients=[r["email"] for r in recipients],
        subject=subject,
        html_body=html_body,
    )

    try:
        result = await anyio.to_thread.run_sync(_send_sync, gmail_service, raw)
    except HttpError as exc:
        code = getattr(exc, "status_code", None) or getattr(
            getattr(exc, "resp", None), "status", None
        )
        logger.warning(
            "gmail_send_http_error organization_id=%s status=%s",
            organization_id,
            code,
        )
        await _update_status(row.id, status="failed", error_code=f"gmail_api_{code}")
        raise AgentExecutionError(
            "Gmail could not send the email. Please try again.",
            details={"reason": "gmail_api_error", "status": code},
        ) from exc
    except (TimeoutError, ConnectionError, OSError) as exc:
        # Outcome unknown: the request may have reached Google.
        logger.warning(
            "gmail_send_uncertain_outcome organization_id=%s",
            organization_id,
            exc_info=True,
        )
        await _update_status(row.id, status="uncertain", error_code="send_outcome_uncertain")
        raise EmailSendUncertainError(
            "The send outcome could not be confirmed. Check your mailbox before retrying.",
            details={"reason": "uncertain", "message_id": row.id},
        ) from exc
    except Exception as exc:  # noqa: BLE001 - fail safe
        logger.exception("gmail_send_unexpected_error organization_id=%s", organization_id)
        await _update_status(row.id, status="uncertain", error_code="send_outcome_uncertain")
        raise EmailSendUncertainError(
            "The send outcome could not be confirmed. Check your mailbox before retrying.",
            details={"reason": "uncertain", "message_id": row.id},
        ) from exc

    gmail_message_id = None
    if isinstance(result, dict):
        gmail_message_id = result.get("id")

    await _update_status(row.id, status="sent", gmail_message_id=gmail_message_id)

    logger.info(
        "gmail_send_completed organization_id=%s message_id=%s recipients=%d",
        organization_id,
        row.id,
        len(recipients),
    )

    return {
        "sent": True,
        "message_id": row.id,
        "gmail_message_id": gmail_message_id,
        "recipients_count": len(recipients),
        "subject": subject,
        "status": "sent",
        "idempotency_key": idempotency_key,
    }


def _send_sync(gmail_service: Any, raw: str) -> Any:
    """Perform the blocking Gmail send call.

    Args:
        gmail_service: An authorized Gmail API client.
        raw: The base64url-encoded raw message.

    Returns:
        The Gmail API response.
    """
    return gmail_service.users().messages().send(userId="me", body={"raw": raw}).execute()
