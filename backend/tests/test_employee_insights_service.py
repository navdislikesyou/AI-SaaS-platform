"""Persistence and retrieval tests for Employee Insights feedback."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest
from sqlalchemy import func, select

import employee_insights.service as employee_insights_service
from app.core.exceptions import FeedbackPersistenceError
from app.models import Feedback
from employee_insights.service import EmployeeInsightsService


class PositiveAnalyzer:
    """Return a stable sentiment result without loading the ML model."""

    def analyze(self, text: str) -> dict[str, Any]:
        return {"sentiment": "POSITIVE", "confidence": 0.9584}


@pytest.fixture
def insights_service() -> EmployeeInsightsService:
    service = EmployeeInsightsService()
    service._analyzer = PositiveAnalyzer()
    return service


@pytest.fixture
def bind_test_sessions(session_factory: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def open_session():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(employee_insights_service, "get_session", open_session)


@pytest.mark.asyncio
async def test_extraction_commits_feedback_with_database_timestamp(
    make_organization: Any,
    make_user: Any,
    session_factory: Any,
    bind_test_sessions: None,
    insights_service: EmployeeInsightsService,
) -> None:
    organization = await make_organization()
    employee = await make_user(
        "jon.clerk@example.com",
        organization_id=organization.id,
        full_name="Jon Clerk",
    )

    result = await insights_service.extract_feedback(
        "Jon Clerk did an excellent job completing the client onboarding process.",
        organization_id=organization.id,
    )

    assert result["count"] == 1
    record = result["records"][0]
    assert record["employee_id"] == employee.id
    assert record["employee_name"] == "Jon Clerk"
    assert record["employee_email"] == "jon.clerk@example.com"
    assert record["sentiment"] == "POSITIVE"
    assert record["confidence"] == 0.9584
    assert record["saved"] is True
    assert record["created_at"].endswith("+00:00")

    history = await insights_service.get_feedback_page(
        organization.id,
        page=1,
        page_size=20,
    )
    assert history["pagination"]["total_records"] == 1
    assert history["records"][0]["feedback"] == record["feedback"]
    assert history["records"][0]["created_at"].endswith("+00:00")


@pytest.mark.asyncio
async def test_deduplicates_same_source_message_but_keeps_manual_repeats(
    make_organization: Any,
    make_user: Any,
    bind_test_sessions: None,
    insights_service: EmployeeInsightsService,
) -> None:
    organization = await make_organization()
    await make_user(
        "jon.clerk@example.com",
        organization_id=organization.id,
        full_name="Jon Clerk",
    )
    text = "Jon Clerk delivered the client project successfully."

    first = await insights_service.extract_feedback(
        text,
        organization.id,
        source="email",
        source_message_id="message-1",
    )
    duplicate = await insights_service.extract_feedback(
        text,
        organization.id,
        source="email",
        source_message_id="message-1",
    )
    manual_first = await insights_service.extract_feedback(text, organization.id)
    manual_repeat = await insights_service.extract_feedback(text, organization.id)

    assert first["records"][0]["saved"] is True
    assert duplicate["records"][0]["saved"] is False
    assert duplicate["records"][0]["duplicate"] is True
    assert manual_first["records"][0]["saved"] is True
    assert manual_repeat["records"][0]["saved"] is True

    page = await insights_service.get_feedback_page(organization.id, page=1, page_size=20)
    assert page["pagination"]["total_records"] == 3


@pytest.mark.asyncio
async def test_feedback_history_is_organization_scoped_and_paginated(
    make_organization: Any,
    make_user: Any,
    bind_test_sessions: None,
    insights_service: EmployeeInsightsService,
) -> None:
    first_org = await make_organization("First", "first")
    second_org = await make_organization("Second", "second")
    await make_user("jon@example.com", organization_id=first_org.id, full_name="Jon Clerk")
    await make_user("alex@example.com", organization_id=second_org.id, full_name="Alex Doe")

    for message_id, text in (
        ("one", "Jon Clerk completed the first project."),
        ("two", "Jon Clerk completed the second project."),
    ):
        await insights_service.extract_feedback(
            text,
            first_org.id,
            source="email",
            source_message_id=message_id,
        )
    await insights_service.extract_feedback("Alex Doe completed the project.", second_org.id)

    first_page = await insights_service.get_feedback_page(first_org.id, page=1, page_size=1)
    second_page = await insights_service.get_feedback_page(first_org.id, page=2, page_size=1)

    assert first_page["pagination"] == {
        "page": 1,
        "page_size": 1,
        "total_records": 2,
        "total_pages": 2,
    }
    assert len(first_page["records"]) == len(second_page["records"]) == 1
    assert all(record["organization_id"] == first_org.id for record in first_page["records"])
    assert all(record["organization_id"] == first_org.id for record in second_page["records"])


@pytest.mark.asyncio
async def test_commit_failure_is_reported_instead_of_claiming_success(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: Any,
    make_organization: Any,
    insights_service: EmployeeInsightsService,
) -> None:
    organization = await make_organization()

    @asynccontextmanager
    async def open_session():
        async with session_factory() as session:

            async def fail_commit() -> None:
                raise RuntimeError("database unavailable")

            monkeypatch.setattr(session, "commit", fail_commit)
            yield session

    async def employees(organization_id: str) -> list[dict[str, str]]:
        return [{"employee_id": "employee-1", "name": "Jon Clerk", "email": "jon@example.com"}]

    monkeypatch.setattr(employee_insights_service, "get_session", open_session)
    monkeypatch.setattr(insights_service, "_get_employees_async", employees)

    with pytest.raises(FeedbackPersistenceError):
        await insights_service.extract_feedback(
            "Jon Clerk did an excellent job.",
            organization_id=organization.id,
        )

    async with session_factory() as session:
        count = await session.scalar(select(func.count(Feedback.id)))
    assert count == 0
