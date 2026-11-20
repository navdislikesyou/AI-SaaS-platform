"""Tests for pulling Gmail messages into the Employee Insights pipeline.

Sync is not a second extraction path: a message read from Gmail goes through
the same extractor, employee matching, sentiment scoring, persistence, and
deduplication as text pasted into the page. These tests use a fake Gmail
client, so no OAuth, no network, and no model download is involved.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest

import employee_insights.service as employee_insights_service
from app.core.exceptions import GmailNotConnectedError
from employee_insights.service import EmployeeInsightsService

DEFAULT_QUERY = "newer_than:30d -in:spam -in:trash"

FEEDBACK_BODY = "Jon Clerk did an excellent job completing the project."


class PositiveAnalyzer:
    """Return a stable sentiment result without loading the ML model."""

    def analyze(self, text: str) -> dict[str, Any]:
        """Score any sentence the same way.

        Args:
            text: The sentence to classify.

        Returns:
            A deterministic positive result.
        """
        return {"sentiment": "POSITIVE", "confidence": 0.9584}


class FakeCollector:
    """Stand in for ``GmailCollector`` and record what it was asked for."""

    def __init__(self, emails: list[dict[str, Any]]) -> None:
        """Store the messages this collector will hand back.

        Args:
            emails: The messages ``collect_emails`` should return.
        """
        self._emails = emails
        self.calls: list[dict[str, Any]] = []

    def collect_emails(
        self,
        query: str = "in:anywhere",
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        """Record the request and return the canned messages.

        Args:
            query: The Gmail search query the caller asked for.
            max_results: The page size the caller asked for.

        Returns:
            The canned messages.
        """
        self.calls.append({"query": query, "max_results": max_results})
        return list(self._emails)


def _email(message_id: str, subject: str, body: str) -> dict[str, Any]:
    """Build one message in the shape the real collector produces.

    Args:
        message_id: The Gmail message id, used for deduplication.
        subject: The message subject.
        body: The plain-text body.

    Returns:
        A message dictionary.
    """
    return {
        "email_id": message_id,
        "thread_id": f"thread-{message_id}",
        "sender": "Sam Manager <sam@example.test>",
        "recipients": "hr@example.test",
        "subject": subject,
        "date": "Tue, 18 Nov 2026 10:00:00 +0000",
        "body": body,
    }


def _install_gmail(
    monkeypatch: pytest.MonkeyPatch,
    emails: list[dict[str, Any]],
) -> list[tuple[Any, FakeCollector]]:
    """Replace the Gmail client with a fake bound to ``emails``.

    Args:
        monkeypatch: Pytest's monkeypatch fixture.
        emails: Messages the fake collector should return.

    Returns:
        One ``(service, collector)`` pair per construction, so a test can read
        back both the credential the service resolved and the query it used.
    """
    built: list[tuple[Any, FakeCollector]] = []

    async def fake_build(organization_id: str, settings: Any) -> Any:
        return ("stored-credential", organization_id)

    def fake_collector(service: Any) -> FakeCollector:
        collector = FakeCollector(emails)
        built.append((service, collector))
        return collector

    monkeypatch.setattr(employee_insights_service, "build_gmail_service", fake_build)
    monkeypatch.setattr(employee_insights_service, "GmailCollector", fake_collector)
    return built


@pytest.fixture
def bind_test_sessions(session_factory: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the service's session factory at the temporary test database."""

    @asynccontextmanager
    async def open_session():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(employee_insights_service, "get_session", open_session)


@pytest.fixture
def insights_service() -> EmployeeInsightsService:
    """Return a service with a deterministic analyzer already attached.

    Returns:
        An ``EmployeeInsightsService`` that never loads RoBERTa.
    """
    service = EmployeeInsightsService()
    service._analyzer = PositiveAnalyzer()
    return service


@pytest.mark.asyncio
async def test_sync_extracts_and_persists_feedback_from_collected_mail(
    make_organization: Any,
    make_user: Any,
    bind_test_sessions: None,
    insights_service: EmployeeInsightsService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A message read from Gmail lands in history exactly like pasted text."""
    organization = await make_organization()
    await make_user(
        "jon.clerk@example.com",
        organization_id=organization.id,
        full_name="Jon Clerk",
    )
    built = _install_gmail(
        monkeypatch,
        [_email("msg-1", "Q4 review", FEEDBACK_BODY)],
    )

    result = await insights_service.sync_gmail(organization.id, max_results=10)

    assert result["collected"] == 1
    assert result["saved"] == 1
    assert result["duplicates"] == 0
    assert result["skipped"] == 0
    assert result["query"] == DEFAULT_QUERY
    assert built[0][0] == ("stored-credential", organization.id)

    history = await insights_service.get_feedback_page(organization.id, page=1, page_size=20)
    assert history["pagination"]["total_records"] == 1
    record = history["records"][0]
    assert record["feedback"] == FEEDBACK_BODY
    assert record["employee_name"] == "Jon Clerk"
    assert record["source"] == "email"
    assert record["organization_id"] == organization.id


@pytest.mark.asyncio
async def test_sync_uses_the_default_query_unless_one_is_given(
    make_organization: Any,
    bind_test_sessions: None,
    insights_service: EmployeeInsightsService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A blank query falls back to the configured default; a given one is used."""
    organization = await make_organization()
    built = _install_gmail(monkeypatch, [])

    await insights_service.sync_gmail(organization.id, query="   ", max_results=10)
    await insights_service.sync_gmail(
        organization.id,
        query="from:boss@example.test",
        max_results=5,
    )

    assert built[0][1].calls[0] == {"query": DEFAULT_QUERY, "max_results": 10}
    assert built[1][1].calls[0] == {
        "query": "from:boss@example.test",
        "max_results": 5,
    }


@pytest.mark.asyncio
async def test_sync_skips_routine_subjects_and_empty_bodies(
    make_organization: Any,
    make_user: Any,
    bind_test_sessions: None,
    insights_service: EmployeeInsightsService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Calendar noise and messages with no text part are never extracted."""
    organization = await make_organization()
    await make_user(
        "jon.clerk@example.com",
        organization_id=organization.id,
        full_name="Jon Clerk",
    )
    _install_gmail(
        monkeypatch,
        [
            _email("msg-1", "Q4 review", FEEDBACK_BODY),
            # The body would match an employee, so only the subject skips it.
            _email("msg-2", "Reminder: Jon Clerk timesheet", FEEDBACK_BODY),
            _email("msg-3", "Weekly digest", "   "),
        ],
    )

    result = await insights_service.sync_gmail(organization.id, max_results=10)

    assert result["collected"] == 3
    assert result["skipped"] == 2
    assert result["saved"] == 1
    assert result["duplicates"] == 0


@pytest.mark.asyncio
async def test_sync_does_not_duplicate_a_message_it_already_saved(
    make_organization: Any,
    make_user: Any,
    bind_test_sessions: None,
    insights_service: EmployeeInsightsService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-syncing the same mailbox adds no rows and reports the duplicates."""
    organization = await make_organization()
    await make_user(
        "jon.clerk@example.com",
        organization_id=organization.id,
        full_name="Jon Clerk",
    )
    _install_gmail(monkeypatch, [_email("msg-1", "Q4 review", FEEDBACK_BODY)])

    first = await insights_service.sync_gmail(organization.id, max_results=10)
    second = await insights_service.sync_gmail(organization.id, max_results=10)

    assert first["saved"] == 1
    assert first["duplicates"] == 0
    assert second["saved"] == 0
    assert second["duplicates"] == 1

    history = await insights_service.get_feedback_page(organization.id, page=1, page_size=20)
    assert history["pagination"]["total_records"] == 1


@pytest.mark.asyncio
async def test_sync_surfaces_a_missing_connection_instead_of_claiming_success(
    make_organization: Any,
    insights_service: EmployeeInsightsService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unconnected mailbox keeps its own 409 rather than becoming a 502."""
    organization = await make_organization()

    async def not_connected(organization_id: str, settings: Any) -> Any:
        raise GmailNotConnectedError(GmailNotConnectedError.DEFAULT_MESSAGE)

    monkeypatch.setattr(employee_insights_service, "build_gmail_service", not_connected)

    with pytest.raises(GmailNotConnectedError):
        await insights_service.sync_gmail(organization.id, max_results=10)
