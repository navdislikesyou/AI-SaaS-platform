"""HTTP tests for saved Employee Insights feedback."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest

import employee_insights.service as employee_insights_service
from app.api.deps import get_current_user_from_token
from app.api.v1 import employee_insights as employee_insights_api
from employee_insights.service import EmployeeInsightsService
from tests.fakes import FakePrincipal


class PositiveAnalyzer:
    """Return a deterministic result without loading the production model."""

    def analyze(self, text: str) -> dict[str, Any]:
        return {"sentiment": "POSITIVE", "confidence": 0.9584}


@pytest.fixture
def bind_test_sessions(session_factory: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def open_session():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(employee_insights_service, "get_session", open_session)


@pytest.mark.asyncio
async def test_history_route_is_paginated_and_organization_scoped(
    app: Any,
    client: Any,
    make_organization: Any,
    make_user: Any,
    bind_test_sessions: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_org = await make_organization("First", "first")
    second_org = await make_organization("Second", "second")
    await make_user("jon@example.com", organization_id=first_org.id, full_name="Jon Clerk")
    await make_user("alex@example.com", organization_id=second_org.id, full_name="Alex Doe")

    service = EmployeeInsightsService()
    service._analyzer = PositiveAnalyzer()
    monkeypatch.setattr(employee_insights_api, "get_employee_insights_service", lambda: service)
    app.dependency_overrides[get_current_user_from_token] = lambda: FakePrincipal(
        organization_id=first_org.id
    )

    for message_id, text in (
        ("one", "Jon Clerk completed the first project."),
        ("two", "Jon Clerk completed the second project."),
    ):
        await service.extract_feedback(
            text,
            first_org.id,
            source="email",
            source_message_id=message_id,
        )
    await service.extract_feedback("Alex Doe completed the project.", second_org.id)

    first_page = await client.get(
        "/api/v1/employee-insights/feedback",
        params={"page": 1, "page_size": 1},
    )
    second_page = await client.get(
        "/api/v1/employee-insights/feedback",
        params={"page": 2, "page_size": 1},
    )
    summary = await client.get("/api/v1/employee-insights/summary/employee")
    monthly = await client.get("/api/v1/employee-insights/summary/monthly")

    assert first_page.status_code == second_page.status_code == 200
    assert first_page.json()["data"]["pagination"]["total_records"] == 2
    assert first_page.json()["data"]["pagination"]["total_pages"] == 2
    for response in (first_page, second_page):
        record = response.json()["data"]["records"][0]
        assert record["organization_id"] == first_org.id
        assert record["employee_name"] == "Jon Clerk"
        assert record["created_at"].endswith("+00:00")
    assert summary.status_code == 200
    assert summary.json()["data"]["employees"][0]["total"] == 2
    assert monthly.status_code == 200
    assert monthly.json()["data"]["monthly"][0]["total"] == 2


@pytest.mark.asyncio
async def test_history_route_rejects_users_without_an_organization(
    app: Any,
    client: Any,
) -> None:
    app.dependency_overrides[get_current_user_from_token] = lambda: FakePrincipal(
        organization_id=""
    )

    response = await client.get("/api/v1/employee-insights/feedback")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
