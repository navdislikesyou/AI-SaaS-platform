"""Service layer for the Employee Insights agent."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC
from typing import Any

import anyio
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.exceptions import FeedbackPersistenceError
from app.models import Feedback, User
from app.services.gmail_connection import build_gmail_service
from employee_insights.email_collector.gmail_collector import GmailCollector

logger = logging.getLogger(__name__)

PRONOUNS = {
    "he",
    "she",
    "his",
    "her",
    "they",
    "their",
    "him",
    "them",
    "himself",
    "herself",
    "themselves",
}

NON_FEEDBACK_PATTERNS = [
    r"\bmeeting\s+scheduled\b",
    r"\bmeeting\s+invitation\b",
    r"\breminder\b",
    r"\bcalendar\s+invitation\b",
    r"\bmeeting\s+begins?\b",
    r"\bmeeting\s+starts?\b",
]

#: Signals that a message is bulk, machine-generated, or unrelated mail. Each
#: category (Google Community notices, newsletters and promotions, social
#: alerts, automated system notifications) carries subject or body patterns
#: as well as any sender pattern, so relevance is judged on subject, sender,
#: and body together rather than on the sender alone. The Gmail sync applies
#: these before extraction, so no irrelevant message can reach the feedback
#: table.
IRRELEVANT_EMAIL_PATTERNS = [
    # Google Community notices and Google account mail.
    r"google community",
    r"\b(?:community-noreply|no-?reply|do-?not-?reply)@google\.com",
    # Newsletters, digests, and promotional mail.
    r"\bnewsletter\b",
    r"\b(?:daily|weekly|monthly|email) digest\b",
    r"\bunsubscribe\b",
    r"stop receiving (?:these|future|our) emails",
    r"update your (?:email |mailing )?preferences",
    r"you (?:are|were) receiving this (?:email|message)",
    r"\b\d{1,2}\s*%\s*off\b",
    r"\b(?:flash sale|black friday|promo(?:tional)? code|special offer|exclusive offer)\b",
    r"\blimited[- ]time (?:offer|deal|sale)\b",
    # Social network notifications.
    r"\b[a-z0-9.-]*@(?:mail\.)?(?:facebookmail|fbmail|linkedin|twitter|instagram)\.com\b",
    r"\b(?:wants? to (?:connect|follow)|invited you to connect)\b",
    r"\b(?:mentioned|tagged) you in (?:a|the) (?:post|comment|photo|update)\b",
    # Automated and system notifications.
    r"\bno-?reply@|\bdo-?not-?reply@|\bdonotreply@|\bnotifications?@[a-z0-9.-]+\.[a-z]{2,}\b",
    r"do not (?:reply|respond)",
    r"\bthis is an automated\b",
    r"\bautomated (?:e-?mail|message|notification)\b",
    r"\b(?:security|account) (?:alert|notification)\b",
    r"\bpassword (?:reset|change|expires|expiration)\b",
    r"\bverification (?:code|email)\b",
    r"\b(?:order|payment|shipping) confirmation\b",
    r"\byour (?:latest )?receipt\b",
    r"\bsystem (?:notification|alert)\b",
]


def _split_sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()]


def _is_irrelevant_email(subject: str, sender: str, body: str) -> bool:
    """Report whether a message is bulk, automated, or unrelated mail.

    Subject, sender, and body are searched together, so no category of
    noise is decided by the sender alone: a newsletter sent from a
    person-looking address is still caught by its subject or footer.

    Args:
        subject: The message subject.
        sender: The raw sender header.
        body: The plain-text body.

    Returns:
        True when the sync pipeline should skip the message.
    """
    haystack = "\n".join((subject, sender, body)).lower()
    return any(re.search(pattern, haystack) for pattern in IRRELEVANT_EMAIL_PATTERNS)


def _consolidate_per_employee(
    attribution: list[tuple[str, list[dict[str, str]]]],
) -> list[tuple[dict[str, str], str]]:
    """Join each employee's sentences into one consolidated text.

    Sentences keep their original order. A sentence that names nobody and
    carries no pronoun is included as context only when it sits strictly
    between two sentences already attributed to the same employee, so a
    record reads as one feedback message instead of isolated fragments and
    never absorbs another employee's sentences.

    Args:
        attribution: ``(sentence, owners)`` pairs in message order.

    Returns:
        One ``(employee, consolidated_text)`` pair per employee with at
        least one attributed sentence, in first-mention order.
    """
    owner_by_id: dict[str, dict[str, str]] = {}
    spans: dict[str, tuple[int, int]] = {}
    for index, (_, owners) in enumerate(attribution):
        for employee in owners:
            employee_id = employee["employee_id"]
            owner_by_id[employee_id] = employee
            first, last = spans.get(employee_id, (index, index))
            spans[employee_id] = (min(first, index), max(last, index))

    picked: dict[str, list[tuple[int, str]]] = {}
    for index, (sentence, owners) in enumerate(attribution):
        for employee in owners:
            picked.setdefault(employee["employee_id"], []).append((index, sentence))

    for index, (sentence, owners) in enumerate(attribution):
        if owners:
            continue
        for employee_id, (first, last) in spans.items():
            if first < index < last:
                picked.setdefault(employee_id, []).append((index, sentence))

    return [
        (owner_by_id[employee_id], " ".join(text for _, text in sorted(pairs)))
        for employee_id, pairs in picked.items()
    ]


def _feedback_hash(feedback_text: str, employee_id: str) -> str:
    """Deterministic SHA-256 hash for organization-scoped deduplication."""
    h = hashlib.sha256()
    h.update(feedback_text.encode("utf-8"))
    h.update(b"|")
    h.update(employee_id.encode("utf-8"))
    return h.hexdigest()


class EmployeeInsightsService:
    """Orchestrates feedback extraction, sentiment analysis, and persistence.

    The RoBERTa model is loaded lazily on first use and cached. Employee
    records are resolved only from the caller's organization.
    """

    def __init__(self) -> None:
        self._analyzer: Any = None
        self._initialized: bool = False

    def _ensure_analyzer(self) -> None:
        """Initialize the RoBERTa sentiment analyzer on first use."""
        if self._analyzer is None:
            from employee_insights.analysis.sentiment_analyzer import (
                SentimentAnalyzer,
            )

            self._analyzer = SentimentAnalyzer()
            self._initialized = True
            logger.info("employee_insights_analyzer_initialized")

    async def _get_employees_async(self, organization_id: str) -> list[dict[str, str]]:
        """Resolve active employees from the caller's organization."""
        async with get_session() as session:
            result = await session.execute(
                select(User.id, User.full_name, User.email).where(
                    User.organization_id == organization_id,
                    User.is_active.is_(True),
                )
            )
            rows = result.all()
        return [
            {
                "employee_id": str(row.id),
                "name": row.full_name,
                "email": row.email or "",
            }
            for row in rows
        ]

    @staticmethod
    def _strong_aliases(employee: dict[str, str]) -> set[str]:
        """Return aliases that identify an employee unambiguously.

        Args:
            employee: One roster entry.

        Returns:
            The full name, email address, employee id, and email local part.
        """
        name = re.sub(r"\s+", " ", employee.get("name", "").lower()).strip()
        email = employee.get("email", "").lower().strip()
        employee_id = employee.get("employee_id", "").lower().strip()
        aliases = {alias for alias in (name, email, employee_id) if alias}
        local = email.split("@", 1)[0] if email else ""
        if local:
            aliases.add(local)
            spaced = local.replace(".", " ").strip()
            if spaced:
                aliases.add(spaced)
        return aliases

    @staticmethod
    def _name_tokens(employee: dict[str, str]) -> list[str]:
        """Return the single-word name aliases for an employee.

        Args:
            employee: One roster entry.

        Returns:
            Lower-cased first, middle, and last name tokens of at least three
            characters, the short forms that must be treated as weak evidence.
        """
        tokens: list[str] = []
        for part in employee.get("name", "").split():
            token = part.strip(".,;:!?-'\"\u2019").lower()
            if len(token) >= 3:
                tokens.append(token)
        return tokens

    @staticmethod
    def _is_proper_noun(token: str, sentence: str) -> bool:
        """Report whether a token stands in the sentence as a name.

        Args:
            token: The lower-cased name token.
            sentence: The original, cased sentence.

        Returns:
            True when a capitalised or upper-case occurrence exists, so an
            ordinary word used as a common noun never matches a person.
        """
        capitalised = token[:1].upper() + token[1:]
        pattern = (
            r"(?<!\w)(?:" + re.escape(capitalised) + r"|" + re.escape(token.upper()) + r")(?!\w)"
        )
        return re.search(pattern, sentence) is not None

    def _identify_employees(
        self, sentence: str, employees: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        """Match employees mentioned in a sentence by name, email, or id.

        The full name, email address, and employee id match on their own. A
        first or last name used alone is only honoured when the token belongs
        to exactly one employee in the roster and stands in the sentence as a
        proper noun, so shared first names and ordinary words (for example
        "the clerk filed it") never attribute feedback to the wrong person.

        Args:
            sentence: The sentence to search.
            employees: The caller's organization roster.

        Returns:
            The matched roster entries, in roster order.
        """
        normalized = re.sub(r"\s+", " ", sentence.lower()).strip()

        token_owner: dict[str, set[str]] = {}
        for employee in employees:
            for token in self._name_tokens(employee):
                token_owner.setdefault(token, set()).add(employee["employee_id"])

        matches: list[dict[str, str]] = []
        for employee in employees:
            if any(
                re.search(r"(?<![\w@.+-])" + re.escape(alias) + r"(?![\w@.+-])", normalized)
                for alias in self._strong_aliases(employee)
            ):
                matches.append(employee)
                continue

            employee_id = employee["employee_id"]
            for token in self._name_tokens(employee):
                if token_owner.get(token) != {employee_id}:
                    continue  # shared with a colleague: ambiguous on its own.
                if not self._is_proper_noun(token, sentence):
                    continue  # an ordinary word, not the person's name.
                matches.append(employee)
                break
        return matches

    def _is_routine_message(self, sentence: str) -> bool:
        return any(re.search(pattern, sentence.lower()) for pattern in NON_FEEDBACK_PATTERNS)

    def _has_pronoun_reference(self, sentence: str) -> bool:
        words = set(re.findall(r"\b\w+\b", sentence.lower()))
        return bool(words.intersection(PRONOUNS))

    async def _save_feedback_async(
        self,
        session: AsyncSession,
        organization_id: str,
        employee: dict[str, str],
        feedback_text: str,
        sentiment: dict[str, Any],
        source: str,
        source_message_id: str | None,
    ) -> tuple[bool, Feedback]:
        """Commit one feedback row, distinguishing duplicates from storage errors.

        When the record came from a source message, any earlier row for the
        same message and employee counts as a duplicate regardless of its
        text, so one email can never grow a second record per employee even
        if the consolidation output changes between releases.
        """
        fb_hash = _feedback_hash(feedback_text, employee["employee_id"])
        if source_message_id is not None:
            existing = await session.scalar(
                select(Feedback).where(
                    Feedback.organization_id == organization_id,
                    Feedback.source == source,
                    Feedback.source_message_id == source_message_id,
                    Feedback.employee_id == employee["employee_id"],
                )
            )
            if existing is not None:
                return False, existing
        values = {
            "organization_id": organization_id,
            "employee_id": employee["employee_id"],
            "employee_name": employee["name"],
            "employee_email": employee.get("email") or None,
            "feedback_text": feedback_text,
            "sentiment": sentiment["sentiment"],
            "confidence": sentiment.get("confidence"),
            "source": source,
            "source_message_id": source_message_id,
            "feedback_hash": fb_hash,
        }
        if session.bind is None:
            raise FeedbackPersistenceError(
                "Feedback could not be saved. Please try again.",
                details={"reason": "database_write_failed"},
            )
        dialect_name = session.bind.dialect.name
        if dialect_name == "postgresql":
            insert = postgres_insert
        elif dialect_name == "sqlite":
            insert = sqlite_insert
        else:
            raise FeedbackPersistenceError(
                "Feedback storage is not supported by this database.",
                details={"reason": "unsupported_database"},
            )

        statement = (
            insert(Feedback)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=[
                    Feedback.organization_id,
                    Feedback.source,
                    Feedback.source_message_id,
                    Feedback.employee_id,
                    Feedback.feedback_hash,
                ]
            )
            .returning(Feedback)
        )
        result = await session.execute(statement)
        record = result.scalar_one_or_none()
        if record is not None:
            return True, record

        if source_message_id is not None:
            result = await session.execute(
                select(Feedback).where(
                    Feedback.organization_id == organization_id,
                    Feedback.source == source,
                    Feedback.source_message_id == source_message_id,
                    Feedback.employee_id == employee["employee_id"],
                    Feedback.feedback_hash == fb_hash,
                )
            )
            duplicate = result.scalar_one_or_none()
            if duplicate is not None:
                return False, duplicate

        logger.error(
            "employee_feedback_insert_conflict organization_id=%s",
            organization_id,
        )
        raise FeedbackPersistenceError(
            "Feedback could not be saved. Please try again.",
            details={"reason": "database_write_failed"},
        )

    async def extract_feedback(
        self,
        email_text: str,
        organization_id: str,
        source: str = "manual",
        source_message_id: str | None = None,
    ) -> dict[str, Any]:
        """Extract feedback from text, attribute it, and persist it.

        The text is read once: every sentence attributed to an employee is
        consolidated into a single record for that person, so one message
        produces at most one row per employee and sentiment is scored over
        the consolidated text rather than over isolated fragments.

        Args:
            email_text: The message body or pasted text to read.
            organization_id: Organization whose roster and history to use.
            source: Where the text came from (``manual`` or ``email``).
            source_message_id: Source message id used for deduplication.

        Returns:
            The persisted records and counts for the call.

        Raises:
            RuntimeError: If the sentiment analyzer failed to initialize.
            FeedbackPersistenceError: If the records could not be stored.
        """

        await anyio.to_thread.run_sync(self._ensure_analyzer)
        employees = await self._get_employees_async(organization_id)
        sentences = _split_sentences(email_text)
        analyzer = self._analyzer
        if analyzer is None:
            raise RuntimeError("The Employee Insights analyzer was not initialized.")

        # Attribute every sentence in message order. A sentence nobody is
        # named in is kept as a context candidate so a consolidated record
        # preserves the surrounding meaning instead of reading as fragments.
        attribution: list[tuple[str, list[dict[str, str]]]] = []
        previous_employees: list[dict[str, str]] = []
        for sentence in sentences:
            if self._is_routine_message(sentence):
                continue
            matched = self._identify_employees(sentence, employees)
            if matched:
                previous_employees = matched
            elif previous_employees and self._has_pronoun_reference(sentence):
                matched = previous_employees
            attribution.append((sentence, matched))

        pending: list[tuple[dict[str, str], str, dict[str, Any]]] = []
        for employee, feedback_text in _consolidate_per_employee(attribution):
            sentiment = await anyio.to_thread.run_sync(analyzer.analyze, feedback_text)
            pending.append((employee, feedback_text, sentiment))

        persisted: list[tuple[dict[str, str], str, dict[str, Any], bool, Feedback]] = []
        if pending:
            try:
                async with get_session() as session:
                    for employee, text, sentiment in pending:
                        saved, feedback_record = await self._save_feedback_async(
                            session,
                            organization_id,
                            employee,
                            text,
                            sentiment,
                            source,
                            source_message_id,
                        )
                        persisted.append((employee, text, sentiment, saved, feedback_record))
                    await session.commit()
                    for _, _, _, saved, feedback_record in persisted:
                        if saved:
                            await session.refresh(feedback_record)
            except FeedbackPersistenceError:
                await session.rollback()
                raise
            except Exception as exc:
                await session.rollback()
                logger.exception(
                    "employee_feedback_commit_failed organization_id=%s",
                    organization_id,
                )
                raise FeedbackPersistenceError(
                    "Feedback could not be saved. Please try again.",
                    details={"reason": "database_write_failed"},
                ) from exc

        extracted: list[dict[str, Any]] = []
        for employee, text, sentiment, saved, feedback_record in persisted:
            extracted.append(
                {
                    "id": feedback_record.id,
                    "employee_id": employee["employee_id"],
                    "employee_name": employee["name"],
                    "employee_email": employee.get("email"),
                    "feedback": text,
                    "sentiment": sentiment["sentiment"],
                    "confidence": sentiment.get("confidence"),
                    "source": source,
                    "saved": saved,
                    "duplicate": not saved,
                    "created_at": _utc_isoformat(feedback_record.created_at),
                }
            )

        return {
            "records": extracted,
            "count": len(extracted),
            "source": source,
            "organization_id": organization_id,
        }

    async def sync_gmail(
        self,
        organization_id: str,
        query: str = "",
        max_results: int = 100,
    ) -> dict[str, Any]:
        """Pull recent Gmail messages and run them through the feedback pipeline.

        Every message goes through the same extraction, employee matching,
        sentiment scoring, persistence, and deduplication as manual input, so a
        synced record is indistinguishable from a pasted one in history.
        Before extraction, application-level relevance validation drops bulk,
        automated, and unrelated mail (newsletters, Google Community notices,
        social and system notifications) that the Gmail query alone lets
        through.

        Args:
            organization_id: Organization whose mailbox and employees to use.
            query: Gmail search query. A blank value falls back to the
                configured default (``newer_than:30d -in:spam -in:trash``).
            max_results: Largest number of messages to fetch from Gmail.

        Returns:
            Counts for the run: ``collected`` messages fetched, ``skipped``
            messages that were empty, routine, or irrelevant, ``saved`` new
            feedback rows, and ``duplicates`` rows already present, plus the
            query actually used.

        Raises:
            GmailNotConnectedError: If the organization has no mailbox
                connected, or the stored grant was revoked at Google.
            GoogleTokenUnavailableError: If the stored credential cannot be
                decrypted with the current passphrase.
            AgentExecutionError: If Google refuses the request.
        """
        settings = get_settings()
        effective_query = query.strip() or settings.gmail_sync_default_query

        gmail_service = await build_gmail_service(organization_id, settings)
        collector = GmailCollector(service=gmail_service)
        emails = await anyio.to_thread.run_sync(
            collector.collect_emails,
            effective_query,
            max_results,
        )

        skipped = 0
        saved = 0
        duplicates = 0

        for email in emails:
            subject = str(email.get("subject") or "")
            body = str(email.get("body") or "")
            sender = str(email.get("sender") or "")
            message_id = email.get("email_id") or None

            # Empty bodies, routine mail (calendar invites, reminders), and
            # irrelevant mail (newsletters, Google Community notices,
            # automated alerts) carry no feedback, so they are not worth a
            # full pass.
            if (
                not body.strip()
                or self._is_routine_message(subject)
                or _is_irrelevant_email(subject, sender, body)
            ):
                skipped += 1
                continue

            result = await self.extract_feedback(
                body,
                organization_id,
                source="email",
                source_message_id=str(message_id) if message_id else None,
            )
            for record in result.get("records", []):
                if record.get("saved"):
                    saved += 1
                else:
                    duplicates += 1

        return {
            "organization_id": organization_id,
            "query": effective_query,
            "collected": len(emails),
            "skipped": skipped,
            "saved": saved,
            "duplicates": duplicates,
        }

    async def get_feedback_page(
        self, organization_id: str, page: int, page_size: int
    ) -> dict[str, Any]:
        """Return one organization-scoped page of persisted feedback."""
        async with get_session() as session:
            total = await session.scalar(
                select(func.count(Feedback.id)).where(Feedback.organization_id == organization_id)
            )
            result = await session.execute(
                select(Feedback)
                .where(Feedback.organization_id == organization_id)
                .order_by(Feedback.created_at.desc(), Feedback.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            rows = result.scalars().all()

        total_records = int(total or 0)
        return {
            "records": [record.to_dict() for record in rows],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_records": total_records,
                "total_pages": (total_records + page_size - 1) // page_size,
            },
            "organization_id": organization_id,
        }

    async def get_employee_summary(
        self, organization_id: str, employee_id: str = "all"
    ) -> dict[str, Any]:
        """Return per-employee sentiment counts for an organization.

        When ``employee_id`` is provided and not ``"all"``, only that
        employee's summary is returned.
        """

        async with get_session() as session:
            stmt = (
                select(
                    Feedback.employee_id,
                    Feedback.employee_name,
                    Feedback.sentiment,
                    func.count(Feedback.id).label("count"),
                )
                .where(Feedback.organization_id == organization_id)
                .group_by(
                    Feedback.employee_id,
                    Feedback.employee_name,
                    Feedback.sentiment,
                )
            )
            if employee_id and employee_id != "all":
                stmt = stmt.where(Feedback.employee_id == employee_id)
            result = await session.execute(stmt)
            rows = result.all()

        by_employee: dict[str, dict[str, Any]] = {}
        for row in rows:
            eid = row.employee_id
            if eid not in by_employee:
                by_employee[eid] = {
                    "employee_id": eid,
                    "employee_name": row.employee_name,
                    "positive": 0,
                    "negative": 0,
                    "neutral": 0,
                    "total": 0,
                }
            sentiment = row.sentiment.lower()
            if sentiment in ("positive", "negative", "neutral"):
                cnt = int(row._mapping["count"])
                by_employee[eid][sentiment] += cnt
                by_employee[eid]["total"] += cnt

        return {
            "employees": list(by_employee.values()),
            "organization_id": organization_id,
        }

    async def get_monthly_summary(self, organization_id: str) -> dict[str, Any]:
        """Return monthly sentiment breakdown for an organization."""

        async with get_session() as session:
            month_expression = (
                func.strftime("%Y-%m", Feedback.created_at)
                if session.bind is not None and session.bind.dialect.name == "sqlite"
                else func.to_char(Feedback.created_at, "YYYY-MM")
            )
            result = await session.execute(
                select(
                    month_expression.label("month"),
                    Feedback.sentiment,
                    func.count(Feedback.id).label("count"),
                )
                .where(Feedback.organization_id == organization_id)
                .group_by("month", Feedback.sentiment)
                .order_by("month")
            )
            rows = result.all()

        monthly: dict[str, dict[str, int]] = {}
        for row in rows:
            month = row.month
            cnt = int(row._mapping["count"])
            if month not in monthly:
                monthly[month] = {"positive": 0, "negative": 0, "neutral": 0, "total": 0}
            sentiment = row.sentiment.lower()
            if sentiment in ("positive", "negative", "neutral"):
                monthly[month][sentiment] += cnt
                monthly[month]["total"] += cnt

        return {
            "monthly": [{"month": m, **counts} for m, counts in sorted(monthly.items())],
            "organization_id": organization_id,
        }


def _utc_isoformat(value: Any) -> str:
    """Serialize a database timestamp as a timezone-aware UTC value."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()
