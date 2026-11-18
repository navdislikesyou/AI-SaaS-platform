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

from app.core.database import get_session
from app.core.exceptions import FeedbackPersistenceError
from app.models import Feedback, User

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


def _split_sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()]


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

    def _identify_employees(
        self, sentence: str, employees: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        """Match employees mentioned in a sentence by name, email, or id."""
        normalized = re.sub(r"\s+", " ", sentence.lower()).strip()
        matches: list[dict[str, str]] = []
        for employee in employees:
            aliases = {
                employee.get("name", "").lower().strip(),
                employee.get("email", "").lower().strip(),
                employee.get("employee_id", "").lower().strip(),
            }
            name_parts = employee.get("name", "").split()
            aliases.update(part.lower().strip() for part in name_parts)
            email_user = employee.get("email", "").split("@")[0].replace(".", " ")
            if email_user:
                aliases.add(email_user.lower().strip())
            aliases = {a for a in aliases if a and len(a) > 1}

            for alias in aliases:
                pattern = r"(?<![\w@.+-])" + re.escape(alias) + r"(?![\w@.+-])"
                if re.search(pattern, normalized):
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
        """Commit one feedback row, distinguishing duplicates from storage errors."""
        fb_hash = _feedback_hash(feedback_text, employee["employee_id"])
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
        """Extract feedback sentences from email text, attribute to employees,
        classify sentiment, and persist. Returns extracted records and counts.
        """

        await anyio.to_thread.run_sync(self._ensure_analyzer)
        employees = await self._get_employees_async(organization_id)
        sentences = _split_sentences(email_text)
        analyzer = self._analyzer
        if analyzer is None:
            raise RuntimeError("The Employee Insights analyzer was not initialized.")

        pending: list[tuple[dict[str, str], str, dict[str, Any]]] = []
        previous_employees: list[dict[str, str]] = []

        for sentence in sentences:
            if self._is_routine_message(sentence):
                continue

            matched = self._identify_employees(sentence, employees)
            if matched:
                previous_employees = matched
            elif previous_employees and self._has_pronoun_reference(sentence):
                matched = previous_employees
            else:
                continue

            sentiment = await anyio.to_thread.run_sync(analyzer.analyze, sentence)

            for employee in matched:
                pending.append((employee, sentence, sentiment))

        persisted: list[tuple[dict[str, str], str, dict[str, Any], bool, Feedback]] = []
        if pending:
            try:
                async with get_session() as session:
                    for employee, sentence, sentiment in pending:
                        saved, feedback_record = await self._save_feedback_async(
                            session,
                            organization_id,
                            employee,
                            sentence,
                            sentiment,
                            source,
                            source_message_id,
                        )
                        persisted.append((employee, sentence, sentiment, saved, feedback_record))
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
        for employee, sentence, sentiment, saved, feedback_record in persisted:
            extracted.append(
                {
                    "id": feedback_record.id,
                    "employee_id": employee["employee_id"],
                    "employee_name": employee["name"],
                    "employee_email": employee.get("email"),
                    "feedback": sentence,
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
