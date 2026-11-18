"""Contract tests for the Employee Insights Agent adapter.

These exercise the real :class:`EmployeeInsightsAgentAdapter` through the
orchestrator stack. A fake service stands in for the employee insights agent,
so no RoBERTa model download, GPU, or network access is required.

The behaviour under test is the adapter's: payload validation, dict shapes,
availability semantics, and status-code translation. Nothing here asserts how
feedback extraction or sentiment analysis works.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.adapters.employee_insights import EmployeeInsightsAgentAdapter
from app.agents.registry import AgentRegistry
from app.api import deps
from app.api.deps import (
    get_current_user_from_token_optional_principal,
    get_orchestrator,
    get_registry,
)
from app.core.exceptions import (
    AgentExecutionError,
    AgentUnavailableError,
    ForbiddenError,
    UnknownOperationError,
    ValidationFailedError,
)
from app.main import create_app
from app.services.orchestrator import Orchestrator
from tests.fakes import FakePrincipal

PRINCIPAL = {
    "user_id": "test-user-1",
    "organization_id": "test-org-1",
    "role": "employee",
}

EXECUTE_URL = "/api/v1/agents/execute"

ADAPTER_SOURCE = Path("app/agents/adapters/employee_insights.py")
SERVICE_SOURCE = Path("employee_insights/service.py")


class FakeEmployeeInsightsService:
    """Stands in for ``EmployeeInsightsService`` without any ML model.

    Records what it was called with so tests can assert the adapter translated
    the payload correctly.
    """

    def __init__(
        self,
        result: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._result = result or {
            "records": [
                {
                    "employee_id": "EMP-001",
                    "employee_name": "Test Employee",
                    "employee_email": "test@example.com",
                    "feedback": "did an excellent job",
                    "sentiment": "POSITIVE",
                    "confidence": 0.95,
                    "source": "manual",
                    "saved": True,
                }
            ],
            "count": 1,
            "source": "manual",
        }
        self._error = error
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def extract_feedback(
        self,
        email_text: str,
        organization_id: str = "",
        source: str = "manual",
        source_message_id: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            ("extract_feedback", {"email_text": email_text, "organization_id": organization_id})
        )
        if self._error:
            raise self._error
        return dict(self._result)


def _make_app(adapter: EmployeeInsightsAgentAdapter) -> Any:
    """Build a FastAPI app with the given adapter registered."""
    registry = AgentRegistry()
    registry.register(adapter)
    orchestrator = Orchestrator(registry)

    app = create_app()

    deps.init_registry(registry)
    deps.init_orchestrator(orchestrator)

    app.dependency_overrides[get_registry] = lambda: registry
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator

    async def _override_user() -> FakePrincipal | None:
        return FakePrincipal(**PRINCIPAL)

    app.dependency_overrides[get_current_user_from_token_optional_principal] = _override_user

    return app


@pytest.mark.asyncio
async def test_extract_feedback_returns_dict() -> None:
    """extract_feedback returns a JSON-serializable dict."""
    adapter = EmployeeInsightsAgentAdapter(service=FakeEmployeeInsightsService())
    assert adapter.is_available() is True

    result = await adapter.execute(
        "extract_feedback",
        {"email_text": "Navneet did an excellent job."},
        user_context=PRINCIPAL,
    )
    assert isinstance(result, dict)
    assert "records" in result


@pytest.mark.asyncio
async def test_async_service_runs_on_request_loop() -> None:
    """Run async DB services on the request loop, not a worker's new loop."""
    request_loop = asyncio.get_running_loop()

    class AsyncEmployeeInsightsService:
        async def extract_feedback(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            assert asyncio.get_running_loop() is request_loop
            return {"records": [], "count": 0}

    adapter = EmployeeInsightsAgentAdapter(service=AsyncEmployeeInsightsService())
    result = await adapter.execute(
        "extract_feedback",
        {"email_text": "Jon Clerk did an excellent job."},
        user_context=PRINCIPAL,
    )

    assert result == {"records": [], "count": 0}


@pytest.mark.asyncio
async def test_employee_insights_requires_organization_context() -> None:
    adapter = EmployeeInsightsAgentAdapter(service=FakeEmployeeInsightsService())

    with pytest.raises(ForbiddenError):
        await adapter.execute(
            "extract_feedback",
            {"email_text": "Jon Clerk did an excellent job."},
            user_context={"user_id": "user-1"},
        )


@pytest.mark.asyncio
async def test_missing_email_text_raises_validation_error() -> None:
    """A payload without email_text raises ValidationFailedError (422)."""
    adapter = EmployeeInsightsAgentAdapter(service=FakeEmployeeInsightsService())

    with pytest.raises(ValidationFailedError) as exc_info:
        await adapter.execute("extract_feedback", {}, user_context=PRINCIPAL)
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_blank_email_text_raises_validation_error() -> None:
    """A whitespace-only email_text is rejected like a missing one."""
    adapter = EmployeeInsightsAgentAdapter(service=FakeEmployeeInsightsService())

    with pytest.raises(ValidationFailedError):
        await adapter.execute("extract_feedback", {"email_text": "   "}, user_context=PRINCIPAL)


@pytest.mark.asyncio
async def test_unknown_operation_raises_unknown_operation() -> None:
    """An unadvertised operation raises UnknownOperationError (404)."""
    adapter = EmployeeInsightsAgentAdapter(service=FakeEmployeeInsightsService())

    with pytest.raises(UnknownOperationError):
        await adapter.execute("nonexistent_operation", {}, user_context=PRINCIPAL)


@pytest.mark.asyncio
async def test_unconnected_adapter_raises_unavailable() -> None:
    """An adapter without a service raises AgentUnavailableError (503)."""
    adapter = EmployeeInsightsAgentAdapter()
    assert adapter.is_available() is False

    with pytest.raises(AgentUnavailableError) as exc_info:
        await adapter.execute("extract_feedback", {}, user_context=PRINCIPAL)
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_service_failure_translated_to_execution_error() -> None:
    """An exception from the service becomes a sanitized 502."""

    class ExplodingService:
        def extract_feedback(self, *args: object, **kwargs: object) -> dict[str, Any]:
            raise RuntimeError("internal detail at /secret/path")

    adapter = EmployeeInsightsAgentAdapter(service=ExplodingService())

    with pytest.raises(AgentExecutionError) as exc_info:
        await adapter.execute(
            "extract_feedback",
            {"email_text": "Navneet did an excellent job."},
            user_context=PRINCIPAL,
        )

    assert exc_info.value.status_code == 502
    assert "/secret/path" not in exc_info.value.message
    assert "internal detail" not in exc_info.value.message


@pytest.mark.asyncio
async def test_endpoint_execute_via_http() -> None:
    """POST /api/v1/agents/execute with agent=employee_insights works end-to-end."""
    adapter = EmployeeInsightsAgentAdapter(service=FakeEmployeeInsightsService())
    app = _make_app(adapter)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            EXECUTE_URL,
            json={
                "agent": "employee_insights",
                "operation": "extract_feedback",
                "payload": {"email_text": "Navneet did an excellent job."},
            },
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["data"]["agent"] == "employee_insights"
    assert body["data"]["operation"] == "extract_feedback"
    assert isinstance(body["data"]["data"], dict)
