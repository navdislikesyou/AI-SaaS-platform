"""Extraction-quality tests for Gmail feedback.

Irrelevant mail must never reach the feedback table, one email must produce
at most one consolidated record per employee, sentiment must be scored over
the consolidated text, and tenant isolation plus the sync role gate must
hold. The sentiment model and the Gmail client are fakes throughout, so no
model download, OAuth, or network access happens.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest

import employee_insights.service as employee_insights_service
from app.agents.adapters.employee_insights import EmployeeInsightsAgentAdapter
from app.core.exceptions import ForbiddenError
from employee_insights.service import EmployeeInsightsService


class PositiveAnalyzer:
    """Return a stable sentiment result without loading the ML model."""

    def analyze(self, text: str) -> dict[str, Any]:
        """Score any text the same way.

        Args:
            text: The consolidated feedback text.

        Returns:
            A deterministic positive result.
        """
        return {"sentiment": "POSITIVE", "confidence": 0.9584}


class KeywordAnalyzer:
    """Classify from keywords so the consolidated content is what gets scored.

    Records every text it sees, letting a test assert that analysis ran over
    the consolidated record rather than over isolated fragments.
    """

    NEGATIVE_TOKENS = ("needs improvement", "delays", "poor communication")
    POSITIVE_TOKENS = ("excellent", "on time")

    def __init__(self) -> None:
        self.seen: list[str] = []

    def analyze(self, text: str) -> dict[str, Any]:
        """Label ``text`` from its keywords and remember it.

        Args:
            text: The consolidated feedback text.

        Returns:
            A sentiment dict shaped like the real analyzer's output.
        """
        self.seen.append(text)
        lowered = text.lower()
        if any(token in lowered for token in self.NEGATIVE_TOKENS):
            label = "NEGATIVE"
        elif any(token in lowered for token in self.POSITIVE_TOKENS):
            label = "POSITIVE"
        else:
            label = "NEUTRAL"
        return {"text": text, "sentiment": label, "confidence": 0.91}


class RecordingService:
    """Stand in for the service so the adapter's role gate can be observed."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def sync_gmail(
        self,
        organization_id: str = "",
        query: str = "",
        max_results: int = 0,
    ) -> dict[str, Any]:
        """Record the call and return a sync-shaped result.

        Args:
            organization_id: Organization the sync ran for.
            query: The Gmail query used.
            max_results: The page size used.

        Returns:
            A result shaped like the real sync summary.
        """
        self.calls.append(
            (
                "sync_gmail",
                {
                    "organization_id": organization_id,
                    "query": query,
                    "max_results": max_results,
                },
            )
        )
        return {
            "organization_id": organization_id,
            "query": query,
            "collected": 0,
            "skipped": 0,
            "saved": 0,
            "duplicates": 0,
        }


def _email(
    message_id: str,
    subject: str,
    body: str,
    sender: str = "Sam Manager <sam@example.test>",
) -> dict[str, Any]:
    """Build one message in the shape the real collector produces.

    Args:
        message_id: The Gmail message id, used for deduplication.
        subject: The message subject.
        body: The plain-text body.
        sender: The raw sender header.

    Returns:
        A message dictionary.
    """
    return {
        "email_id": message_id,
        "thread_id": f"thread-{message_id}",
        "sender": sender,
        "recipients": "hr@example.test",
        "subject": subject,
        "date": "Tue, 18 Nov 2026 10:00:00 +0000",
        "body": body,
    }


def _install_gmail(
    monkeypatch: pytest.MonkeyPatch,
    emails: list[dict[str, Any]],
) -> list[tuple[Any, Any]]:
    """Replace the Gmail client with a fake bound to ``emails``.

    Args:
        monkeypatch: Pytest's monkeypatch fixture.
        emails: Messages the fake collector should return.

    Returns:
        One ``(credential, collector)`` pair per construction.
    """
    built: list[tuple[Any, Any]] = []

    async def fake_build(organization_id: str, settings: Any) -> Any:
        return ("stored-credential", organization_id)

    def fake_collector(service: Any) -> Any:
        class _FakeCollector:
            def collect_emails(
                self,
                query: str = "in:anywhere",
                max_results: int = 100,
            ) -> list[dict[str, Any]]:
                return list(emails)

        collector = _FakeCollector()
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
async def test_five_emails_produce_five_consolidated_records(
    make_organization: Any,
    make_user: Any,
    bind_test_sessions: None,
    insights_service: EmployeeInsightsService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement 1: one single-employee email yields exactly one record."""
    organization = await make_organization()
    for email, name in (
        ("ava.brooks@example.com", "Ava Brooks"),
        ("ben.carter@example.com", "Ben Carter"),
        ("clara.nguyen@example.com", "Clara Nguyen"),
        ("diego.ruiz@example.com", "Diego Ruiz"),
        ("emma.fields@example.com", "Emma Fields"),
    ):
        await make_user(email, organization_id=organization.id, full_name=name)

    bodies = {
        "Ava Brooks": (
            "Ava Brooks completed the client migration early.",
            "Her documentation was thorough and clear.",
        ),
        "Ben Carter": (
            "Ben Carter resolved every support escalation.",
            "He kept the customer informed throughout.",
        ),
        "Clara Nguyen": (
            "Clara Nguyen prepared the audit evidence pack.",
            "She handed it in two days early.",
        ),
        "Diego Ruiz": (
            "Diego Ruiz rebuilt the inventory sync.",
            "His tests cover the edge cases.",
        ),
        "Emma Fields": (
            "Emma Fields led the onboarding workshop.",
            "She collected feedback from every new hire.",
        ),
    }
    emails = [
        _email(f"msg-{index}", "Q4 review", f"{first} {second}")
        for index, (first, second) in enumerate(bodies.values(), start=1)
    ]
    _install_gmail(monkeypatch, emails)

    result = await insights_service.sync_gmail(organization.id, max_results=10)

    assert result["collected"] == 5
    assert result["skipped"] == 0
    assert result["saved"] == 5
    assert result["duplicates"] == 0

    history = await insights_service.get_feedback_page(organization.id, page=1, page_size=20)
    assert history["pagination"]["total_records"] == 5
    by_employee = {record["employee_name"]: record for record in history["records"]}
    assert set(by_employee) == set(bodies)
    for name, (first, second) in bodies.items():
        feedback = by_employee[name]["feedback"]
        assert feedback.startswith(first)
        assert second in feedback


@pytest.mark.asyncio
async def test_one_email_about_two_employees_produces_two_records(
    make_organization: Any,
    make_user: Any,
    bind_test_sessions: None,
    insights_service: EmployeeInsightsService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement 2: each employee gets their own record with their content."""
    organization = await make_organization()
    await make_user("jon.clerk@example.com", organization_id=organization.id, full_name="Jon Clerk")
    await make_user("sarah.doe@example.com", organization_id=organization.id, full_name="Sarah Doe")
    first_sentence = "Jon Clerk rebuilt the payment service under a tight deadline."
    context_sentence = "Both engineers worked through the weekend."
    sarah_sentence = "Sarah Doe redesigned the checkout flow in parallel."
    closing_sentence = "Jon's changes fixed the overnight outage."
    _install_gmail(
        monkeypatch,
        [
            _email(
                "msg-1",
                "Payment service review",
                f"{first_sentence} {context_sentence} {sarah_sentence} {closing_sentence}",
            )
        ],
    )

    result = await insights_service.sync_gmail(organization.id, max_results=10)

    assert result["saved"] == 2
    history = await insights_service.get_feedback_page(organization.id, page=1, page_size=20)
    assert history["pagination"]["total_records"] == 2
    by_employee = {record["employee_name"]: record for record in history["records"]}
    assert set(by_employee) == {"Jon Clerk", "Sarah Doe"}

    jon_feedback = by_employee["Jon Clerk"]["feedback"]
    assert jon_feedback.startswith(first_sentence)
    # The unnamed sentence between Jon's two sentences is kept as context.
    assert context_sentence in jon_feedback
    assert closing_sentence in jon_feedback
    assert "Sarah Doe" not in jon_feedback

    assert by_employee["Sarah Doe"]["feedback"] == sarah_sentence


@pytest.mark.asyncio
async def test_google_community_and_newsletter_emails_are_ignored(
    make_organization: Any,
    make_user: Any,
    bind_test_sessions: None,
    insights_service: EmployeeInsightsService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement 3: bulk mail is skipped even when it names an employee."""
    organization = await make_organization()
    await make_user("jon.clerk@example.com", organization_id=organization.id, full_name="Jon Clerk")
    _install_gmail(
        monkeypatch,
        [
            _email(
                "msg-1",
                "Google Community weekly highlights",
                "Jon Clerk led the migration to the new community platform. "
                "Great work all around.",
                sender="Google Community <community-noreply@google.com>",
            ),
            _email(
                "msg-2",
                "Your monthly HR newsletter",
                "Jon Clerk was employee of the month this quarter. "
                "Read the full story and unsubscribe here.",
                sender="HR Digest <news@example.test>",
            ),
        ],
    )

    result = await insights_service.sync_gmail(organization.id, max_results=10)

    assert result["collected"] == 2
    assert result["skipped"] == 2
    assert result["saved"] == 0
    assert result["duplicates"] == 0

    history = await insights_service.get_feedback_page(organization.id, page=1, page_size=20)
    assert history["pagination"]["total_records"] == 0


@pytest.mark.asyncio
async def test_irrelevant_emails_are_never_persisted(
    make_organization: Any,
    make_user: Any,
    bind_test_sessions: None,
    insights_service: EmployeeInsightsService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement 4: automated and unrelated mail leaves the table empty."""
    organization = await make_organization()
    await make_user("jon.clerk@example.com", organization_id=organization.id, full_name="Jon Clerk")
    _install_gmail(
        monkeypatch,
        [
            _email(
                "msg-1",
                "Security alert: password expires soon",
                "Security alert: the password for Jon Clerk expires in three days. "
                "Reset it to keep your mailbox.",
            ),
            _email(
                "msg-2",
                "Automated notification: nightly build",
                "Automated notification: the nightly build failed for Jon Clerk's "
                "module. No action is needed from you.",
                sender="CI Bot <ci@example.test>",
            ),
            _email(
                "msg-3",
                "Your weekly timesheet report",
                "Timesheet summary for Jon Clerk: 38 hours logged this week.",
                sender="No-Reply <noreply@example.test>",
            ),
            # Personal mail with no employee reference: extracted, but there
            # is nobody to attribute, so nothing is written.
            _email(
                "msg-4",
                "Lunch tomorrow?",
                "Want to grab lunch tomorrow around noon? Let me know what time works.",
            ),
        ],
    )

    result = await insights_service.sync_gmail(organization.id, max_results=10)

    assert result["collected"] == 4
    assert result["skipped"] == 3
    assert result["saved"] == 0
    assert result["duplicates"] == 0

    history = await insights_service.get_feedback_page(organization.id, page=1, page_size=20)
    assert history["pagination"]["total_records"] == 0


@pytest.mark.asyncio
async def test_sentiment_is_classified_from_the_consolidated_content(
    make_organization: Any,
    make_user: Any,
    bind_test_sessions: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement 5: labels come from the whole record, not fragments."""
    organization = await make_organization()
    for email, name in (
        ("ava.brooks@example.com", "Ava Brooks"),
        ("ben.carter@example.com", "Ben Carter"),
        ("clara.nguyen@example.com", "Clara Nguyen"),
        ("diego.ruiz@example.com", "Diego Ruiz"),
    ):
        await make_user(email, organization_id=organization.id, full_name=name)

    service = EmployeeInsightsService()
    analyzer = KeywordAnalyzer()
    service._analyzer = analyzer
    _install_gmail(
        monkeypatch,
        [
            _email(
                "msg-1",
                "Audit result",
                "Ava Brooks finished the audit ahead of schedule. "
                "She completed everything on time with excellent notes.",
            ),
            _email(
                "msg-2",
                "Vendor review",
                "Ben Carter took over the vendor review. "
                "He caused repeated delays and poor communication.",
            ),
            _email(
                "msg-3",
                "Compliance report",
                "Clara Nguyen filed the monthly compliance report. "
                "She completed the assigned tasks according to schedule.",
            ),
            _email(
                "msg-4",
                "Onboarding checklist",
                "Diego Ruiz owns the onboarding checklist. "
                "Diego Ruiz's checklist needs improvement in communication "
                "and task management.",
            ),
        ],
    )

    result = await service.sync_gmail(organization.id, max_results=10)

    assert result["saved"] == 4
    history = await service.get_feedback_page(organization.id, page=1, page_size=20)
    sentiments = {record["employee_name"]: record["sentiment"] for record in history["records"]}
    assert sentiments == {
        "Ava Brooks": "POSITIVE",
        "Ben Carter": "NEGATIVE",
        "Clara Nguyen": "NEUTRAL",
        "Diego Ruiz": "NEGATIVE",
    }

    # One analysis per employee record, not one per sentence.
    assert len(analyzer.seen) == 4
    positive_text = next(text for text in analyzer.seen if "excellent" in text.lower())
    assert "ahead of schedule" in positive_text


@pytest.mark.asyncio
async def test_repeated_sync_does_not_create_duplicate_records(
    make_organization: Any,
    make_user: Any,
    bind_test_sessions: None,
    insights_service: EmployeeInsightsService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement 6: a second sync of the same mailbox adds no rows."""
    organization = await make_organization()
    await make_user(
        "ava.brooks@example.com", organization_id=organization.id, full_name="Ava Brooks"
    )
    await make_user(
        "ben.carter@example.com", organization_id=organization.id, full_name="Ben Carter"
    )
    _install_gmail(
        monkeypatch,
        [
            _email(
                "msg-1",
                "Q4 review",
                "Ava Brooks completed the migration early. "
                "Her documentation was thorough and clear.",
            ),
            _email(
                "msg-2",
                "Support review",
                "Ben Carter resolved every escalation. " "He kept each customer informed.",
            ),
        ],
    )

    first = await insights_service.sync_gmail(organization.id, max_results=10)
    second = await insights_service.sync_gmail(organization.id, max_results=10)

    assert first["saved"] == 2
    assert first["duplicates"] == 0
    assert second["saved"] == 0
    assert second["duplicates"] == 2

    history = await insights_service.get_feedback_page(organization.id, page=1, page_size=20)
    assert history["pagination"]["total_records"] == 2


@pytest.mark.asyncio
async def test_manual_feedback_submission_is_unchanged(
    make_organization: Any,
    make_user: Any,
    bind_test_sessions: None,
    insights_service: EmployeeInsightsService,
) -> None:
    """Requirement 7: pasted text bypasses email relevance and repeat-saves.

    The text deliberately contains the word "newsletter": relevance
    validation belongs to the Gmail sync, so manual input must save it.
    """
    organization = await make_organization()
    await make_user("sarah.doe@example.com", organization_id=organization.id, full_name="Sarah Doe")
    text = (
        "Sarah Doe ran the training session. "
        "The newsletter review workshop was her best one yet."
    )

    first = await insights_service.extract_feedback(text, organization.id)
    repeat = await insights_service.extract_feedback(text, organization.id)

    assert first["records"][0]["saved"] is True
    assert first["records"][0]["source"] == "manual"
    assert first["records"][0]["feedback"] == text
    assert repeat["records"][0]["saved"] is True
    assert repeat["records"][0]["duplicate"] is False

    history = await insights_service.get_feedback_page(organization.id, page=1, page_size=20)
    assert history["pagination"]["total_records"] == 2
    assert all(record["source"] == "manual" for record in history["records"])


@pytest.mark.asyncio
async def test_organization_isolation_and_sync_rbac_remain_enforced(
    make_organization: Any,
    make_user: Any,
    bind_test_sessions: None,
    insights_service: EmployeeInsightsService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement 8: no cross-organization attribution; sync stays gated."""
    first_org = await make_organization("First", "first")
    second_org = await make_organization("Second", "second")
    await make_user("jon@example.com", organization_id=first_org.id, full_name="Jon Clerk")
    await make_user("alex@example.com", organization_id=second_org.id, full_name="Alex Doe")
    body = "Jon Clerk completed the client project. " "His delivery was ahead of schedule."
    _install_gmail(monkeypatch, [_email("msg-1", "Q4 review", body)])

    first_sync = await insights_service.sync_gmail(first_org.id, max_results=10)
    second_sync = await insights_service.sync_gmail(second_org.id, max_results=10)
    cross_org = await insights_service.extract_feedback(body, second_org.id)

    # The roster of the second organization does not contain Jon Clerk, so
    # the same text matches nobody there.
    assert first_sync["saved"] == 1
    assert second_sync["saved"] == 0
    assert cross_org["count"] == 0

    first_history = await insights_service.get_feedback_page(first_org.id, page=1, page_size=20)
    second_history = await insights_service.get_feedback_page(second_org.id, page=1, page_size=20)
    assert first_history["pagination"]["total_records"] == 1
    assert second_history["pagination"]["total_records"] == 0

    # The adapter refuses a sync below manager level before the service runs.
    service = RecordingService()
    adapter = EmployeeInsightsAgentAdapter(service=service)
    with pytest.raises(ForbiddenError) as exc_info:
        await adapter.execute(
            "sync_gmail",
            {"max_results": 10},
            user_context={
                "user_id": "user-1",
                "organization_id": first_org.id,
                "role": "employee",
            },
        )
    assert exc_info.value.status_code == 403
    assert service.calls == []

    await adapter.execute(
        "sync_gmail",
        {"max_results": 10},
        user_context={
            "user_id": "user-2",
            "organization_id": first_org.id,
            "role": "manager",
        },
    )
    assert [name for name, _ in service.calls] == ["sync_gmail"]
