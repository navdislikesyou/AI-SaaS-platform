"""Contract tests for the Knowledge Agent adapter.

These exercise the real :class:`KnowledgeAgentAdapter` through the FastAPI and
orchestrator stack. A fake service stands in for the RAG agent, so no Ollama,
Chroma, HuggingFace download, GPU, or network access is required.

The behaviour under test is the adapter's: payload validation, dict shapes,
availability semantics, and status-code translation. Nothing here asserts how
retrieval or generation works.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.adapters.knowledge import KnowledgeAgentAdapter
from app.agents.registry import AgentRegistry
from app.api import deps
from app.api.deps import (
    get_current_user_from_token_optional_principal,
    get_orchestrator,
    get_registry,
    get_settings_dep,
)
from app.core.config import Settings
from app.core.exceptions import AgentExecutionError, ValidationFailedError
from app.main import create_app
from app.services.orchestrator import Orchestrator
from tests.fakes import FakePrincipal

#: Principal handed to the adapter under test. The adapters authorize the
#: caller before they reach the agent, so a principal is required.
PRINCIPAL = {
    "user_id": "test-user-1",
    "organization_id": "test-org-1",
    "role": "employee",
}

EXECUTE_URL = "/api/v1/agents/execute"


class FakeKnowledgeService:
    """Stands in for ``KnowledgeService`` without loading any model.

    Records what it was called with so tests can assert the adapter translated
    the payload correctly rather than just checking the shape of the reply.
    """

    def __init__(
        self,
        ingest_result: dict[str, Any] | None = None,
        query_result: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        """Initialize the fake.

        Args:
            ingest_result: Value returned by ``ingest``. Defaults to a
                successful two-key ingest result.
            query_result: Value returned by ``query``. Defaults to a
                successful answer with one source.
            error: Raised by both methods when set, simulating an agent
                failure such as an unreachable vector store.
        """
        self._ingest_result = ingest_result or {"indexed": True, "chunk_count": 12}
        self._query_result = query_result or {
            "answer": "The leave policy allows 30 days.",
            "sources": [{"source": "hr.pdf", "page": 3}],
        }
        self._error = error
        self.calls: list[tuple[str, Any]] = []

    def ingest(
        self,
        file_path: str,
        user_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return the configured ingest result.

        Args:
            file_path: Path forwarded by the adapter.
            user_context: Principal context forwarded by the adapter.

        Returns:
            The configured ingest result.

        Raises:
            Exception: The configured error, when one was set.
        """
        self.calls.append(("ingest", file_path))
        if self._error is not None:
            raise self._error
        return self._ingest_result

    def query(
        self,
        question: str,
        user_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return the configured query result.

        Args:
            question: Question forwarded by the adapter.
            user_context: Principal context forwarded by the adapter.

        Returns:
            The configured query result.

        Raises:
            Exception: The configured error, when one was set.
        """
        self.calls.append(("query", question))
        if self._error is not None:
            raise self._error
        return self._query_result


@pytest.fixture
def service() -> FakeKnowledgeService:
    """Return a fake knowledge service.

    Returns:
        A fake with default successful results.
    """
    return FakeKnowledgeService()


@pytest.fixture
def adapter(service: FakeKnowledgeService) -> KnowledgeAgentAdapter:
    """Return a connected knowledge adapter.

    Args:
        service: The injected fake service.

    Returns:
        An adapter reporting itself available.
    """
    return KnowledgeAgentAdapter(service=service)


@pytest.fixture
def settings() -> Settings:
    """Return test settings.

    Returns:
        Settings configured for testing.
    """
    return Settings(
        environment="test",
        debug=False,
        cors_origins=["http://testserver"],
        log_level="WARNING",
    )


def build_registry(adapters: list[Any]) -> AgentRegistry:
    """Register adapters in a fresh registry.

    Args:
        adapters: The adapters to register.

    Returns:
        A registry holding exactly those adapters.
    """
    registry = AgentRegistry()
    for adapter in adapters:
        registry.register(adapter)
    return registry


@pytest.fixture
def client_for(settings: Settings) -> Any:
    """Return a factory building an HTTP client over a chosen registry.

    Tests exercise the real router, orchestrator, and exception handlers rather
    than calling adapter methods directly, so status codes are verified as a
    client would see them.

    Args:
        settings: Test settings.

    Returns:
        A callable taking adapters and returning an async context manager.
    """

    def factory(adapters: list[Any]) -> AsyncIterator[AsyncClient]:
        registry = build_registry(adapters)
        deps.reset_state()
        application = create_app(settings)
        application.dependency_overrides[get_settings_dep] = lambda: settings
        application.dependency_overrides[get_registry] = lambda: registry
        application.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)
        application.dependency_overrides[get_current_user_from_token_optional_principal] = lambda: FakePrincipal()  # noqa: E501
        return AsyncClient(
            transport=ASGITransport(app=application),  # type: ignore[arg-type]
            base_url="http://testserver",
        )

    return factory


# --------------------------------------------------------------------------
# Result shapes
# --------------------------------------------------------------------------


async def test_ingest_document_returns_expected_dict_shape(
    adapter: KnowledgeAgentAdapter,
    service: FakeKnowledgeService,
) -> None:
    """A successful ingest returns exactly ``indexed`` and ``chunk_count``."""
    result = await adapter.execute("ingest_document", {"file_path": "hr.pdf"}, 
        user_context=PRINCIPAL,
)

    assert set(result) == {"indexed", "chunk_count"}
    assert isinstance(result["indexed"], bool)
    assert isinstance(result["chunk_count"], int)


async def test_ingest_document_forwards_the_file_path(
    adapter: KnowledgeAgentAdapter,
    service: FakeKnowledgeService,
) -> None:
    """The adapter passes the client's ``file_path`` through unchanged."""
    await adapter.execute("ingest_document", {"file_path": "docs/policy.pdf"}, 
        user_context=PRINCIPAL,
)

    assert service.calls == [("ingest", "docs/policy.pdf")]


async def test_ingest_document_reports_zero_chunks_as_not_indexed() -> None:
    """An ingest that writes no chunks reports ``indexed`` False, not absent."""
    service = FakeKnowledgeService(ingest_result={"indexed": False, "chunk_count": 0})
    adapter = KnowledgeAgentAdapter(service=service)

    result = await adapter.execute("ingest_document", {"file_path": "empty.txt"}, 
        user_context=PRINCIPAL,
)

    assert result == {"indexed": False, "chunk_count": 0}


async def test_query_returns_expected_dict_shape(
    adapter: KnowledgeAgentAdapter,
    service: FakeKnowledgeService,
) -> None:
    """A successful query returns an ``answer`` string and a ``sources`` list."""
    result = await adapter.execute("query", {"question": "What is the leave policy?"}, 
        user_context=PRINCIPAL,
)

    assert set(result) == {"answer", "sources"}
    assert isinstance(result["answer"], str)
    assert isinstance(result["sources"], list)


async def test_query_forwards_the_question(
    adapter: KnowledgeAgentAdapter,
    service: FakeKnowledgeService,
) -> None:
    """The adapter passes the client's ``question`` through unchanged."""
    await adapter.execute("query", {"question": "How many days of leave?"}, user_context=PRINCIPAL)

    assert service.calls == [("query", "How many days of leave?")]


# --------------------------------------------------------------------------
# Payload validation -> 422
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({}, id="empty_payload"),
        pytest.param({"question": "q"}, id="wrong_operation_keys"),
        pytest.param({"file_path": ""}, id="blank_file_path"),
        pytest.param({"file_path": "   "}, id="whitespace_file_path"),
    ],
)
async def test_ingest_document_without_a_usable_path_is_rejected(
    adapter: KnowledgeAgentAdapter,
    payload: dict[str, Any],
) -> None:
    """A missing or blank ``file_path`` raises a validation error.

    The adapter must reject the request itself. Letting the service fail would
    surface as 502 and tell the client its request was malformed when it was
    the agent that broke.
    """
    with pytest.raises(ValidationFailedError) as exc_info:
        await adapter.execute("ingest_document", payload, user_context=PRINCIPAL)

    assert exc_info.value.status_code == 422
    assert "file_path" in exc_info.value.message


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({}, id="empty_payload"),
        pytest.param({"file_path": "f.pdf"}, id="wrong_operation_keys"),
        pytest.param({"question": ""}, id="blank_question"),
        pytest.param({"question": "   "}, id="whitespace_question"),
    ],
)
async def test_query_without_a_usable_question_is_rejected(
    adapter: KnowledgeAgentAdapter,
    payload: dict[str, Any],
) -> None:
    """A missing or blank ``question`` raises a validation error."""
    with pytest.raises(ValidationFailedError) as exc_info:
        await adapter.execute("query", payload, user_context=PRINCIPAL)

    assert exc_info.value.status_code == 422
    assert "question" in exc_info.value.message


@pytest.mark.xfail(
    reason=(
        "Known gap: an explicit JSON null passes validation because "
        "str(None).strip() == 'None' is truthy, so None reaches the service "
        "and surfaces as 502 instead of 422. Tracked as a Phase 5 finding; "
        "remove this marker once the adapters reject non-string values."
    ),
    strict=True,
)
@pytest.mark.parametrize(
    "operation,payload,expected_key",
    [
        pytest.param("ingest_document", {"file_path": None}, "file_path", id="null_file_path"),
        pytest.param("query", {"question": None}, "question", id="null_question"),
    ],
)
async def test_explicit_null_value_is_rejected(
    adapter: KnowledgeAgentAdapter,
    operation: str,
    payload: dict[str, Any],
    expected_key: str,
) -> None:
    """An explicit ``null`` should be treated the same as a missing key.

    Documented as a failing expectation so the gap stays visible rather than
    being silently encoded as expected behaviour. ``strict=True`` means the
    suite fails if this ever starts passing, which is the signal to drop the
    marker and close the bug.
    """
    with pytest.raises(ValidationFailedError) as exc_info:
        await adapter.execute(operation, payload, user_context=PRINCIPAL)

    assert exc_info.value.status_code == 422
    assert expected_key in exc_info.value.message


async def test_rejected_payload_never_reaches_the_service(
    adapter: KnowledgeAgentAdapter,
    service: FakeKnowledgeService,
) -> None:
    """Validation happens before the service is called at all."""
    with pytest.raises(ValidationFailedError):
        await adapter.execute("query", {"question": "  "}, user_context=PRINCIPAL)

    assert service.calls == []


# --------------------------------------------------------------------------
# Availability
# --------------------------------------------------------------------------


def test_successful_construction_reports_available(
    adapter: KnowledgeAgentAdapter,
) -> None:
    """Availability reflects that a service is present."""
    assert adapter.is_available() is True
    assert "connected" in adapter.describe().lower()


def test_disabled_agent_is_not_available() -> None:
    """An adapter that was never enabled reports unavailable."""
    adapter = KnowledgeAgentAdapter()

    assert adapter.is_available() is False
    assert "not connected" in adapter.describe().lower()


def test_construction_failure_reports_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A service that cannot be constructed leaves the adapter unavailable.

    Simulated by making the service import fail, which is what happens on a
    machine without the optional agent dependencies installed. The failure must
    be contained: the process must still be able to build its registry.
    """
    monkeypatch.setitem(sys.modules, "knowledge_agent.service", None)
    settings = Settings(environment="test", knowledge_agent_enabled=True)

    adapter = KnowledgeAgentAdapter(enabled=True, settings=settings)

    assert adapter.is_available() is False
    assert "not connected" in adapter.describe().lower()


async def test_unavailable_agent_returns_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Execution against an agent that failed to initialize returns 503."""
    monkeypatch.setitem(sys.modules, "knowledge_agent.service", None)
    settings = Settings(environment="test", knowledge_agent_enabled=True)
    adapter = KnowledgeAgentAdapter(enabled=True, settings=settings)

    from app.core.exceptions import AgentUnavailableError

    with pytest.raises(AgentUnavailableError) as exc_info:
        await adapter.execute("query", {"question": "q"}, user_context=PRINCIPAL)

    assert exc_info.value.status_code == 503


# --------------------------------------------------------------------------
# Failure translation -> 502
# --------------------------------------------------------------------------


async def test_service_failure_becomes_agent_execution_error() -> None:
    """An exception from the service becomes a sanitized 502."""
    service = FakeKnowledgeService(error=RuntimeError("chroma unavailable at /secret/path"))
    adapter = KnowledgeAgentAdapter(service=service)

    with pytest.raises(AgentExecutionError) as exc_info:
        await adapter.execute("query", {"question": "q"}, user_context=PRINCIPAL)

    assert exc_info.value.status_code == 502
    assert "/secret/path" not in exc_info.value.message
    assert "chroma unavailable" not in exc_info.value.message


# --------------------------------------------------------------------------
# Capabilities
# --------------------------------------------------------------------------


def test_advertised_capabilities_match_implemented_operations() -> None:
    """Capabilities are exactly the operations the adapter can run.

    Declaring an operation that 404s at runtime is worse than omitting it, so
    the list is pinned here rather than derived from the adapter itself.
    """
    adapter = KnowledgeAgentAdapter(service=FakeKnowledgeService())

    assert adapter.capabilities() == ["ingest_document", "query"]


async def test_every_advertised_capability_is_reachable(
    adapter: KnowledgeAgentAdapter,
) -> None:
    """Each advertised capability dispatches instead of raising 404."""
    payloads = {
        "ingest_document": {"file_path": "hr.pdf"},
        "query": {"question": "q"},
    }

    for operation in adapter.capabilities():
        result = await adapter.execute(operation, payloads[operation], user_context=PRINCIPAL)
        assert isinstance(result, dict)


async def test_operations_without_an_implementation_are_rejected(
    adapter: KnowledgeAgentAdapter,
) -> None:
    """Operations previously advertised but never implemented now 404."""
    from app.core.exceptions import UnknownOperationError

    for operation in ("list_documents", "delete_document"):
        with pytest.raises(UnknownOperationError):
            await adapter.execute(operation, {}, user_context=PRINCIPAL)


# --------------------------------------------------------------------------
# API-level status codes
# --------------------------------------------------------------------------


async def test_api_returns_422_for_a_missing_file_path(client_for: Any) -> None:
    """The API reports a missing ``file_path`` as 422, not 502."""
    async with client_for([KnowledgeAgentAdapter(service=FakeKnowledgeService())]) as client:
        response = await client.post(
            EXECUTE_URL,
            json={"agent": "knowledge", "operation": "ingest_document", "payload": {}},
        )

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"]["missing"] == ["file_path"]


async def test_api_returns_422_for_a_blank_question(client_for: Any) -> None:
    """The API reports a blank ``question`` as 422, not 502."""
    async with client_for([KnowledgeAgentAdapter(service=FakeKnowledgeService())]) as client:
        response = await client.post(
            EXECUTE_URL,
            json={"agent": "knowledge", "operation": "query", "payload": {"question": "  "}},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_api_returns_404_for_an_unsupported_operation(client_for: Any) -> None:
    """An operation outside the advertised list returns 404."""
    async with client_for([KnowledgeAgentAdapter(service=FakeKnowledgeService())]) as client:
        response = await client.post(
            EXECUTE_URL,
            json={"agent": "knowledge", "operation": "delete_document", "payload": {}},
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "OPERATION_NOT_FOUND"


async def test_api_returns_502_when_the_agent_fails(client_for: Any) -> None:
    """A service exception surfaces as 502 with no internal detail leaked."""
    service = FakeKnowledgeService(error=RuntimeError("model exploded at /secret/path"))

    async with client_for([KnowledgeAgentAdapter(service=service)]) as client:
        response = await client.post(
            EXECUTE_URL,
            json={"agent": "knowledge", "operation": "query", "payload": {"question": "q"}},
        )

    assert response.status_code == 502
    body = response.json()
    assert body["error"]["code"] == "AGENT_EXECUTION_FAILED"
    assert "/secret/path" not in response.text
    assert "model exploded" not in response.text


async def test_api_returns_504_when_the_agent_times_out(client_for: Any) -> None:
    """An operation exceeding its budget returns 504."""
    import time

    class SlowKnowledgeService(FakeKnowledgeService):
        def query(
            self,
            question: str,
            user_context: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            time.sleep(0.5)
            return {"answer": "late", "sources": []}

    fast = Settings(environment="test", knowledge_agent_timeout_seconds=0.05)
    adapter = KnowledgeAgentAdapter(service=SlowKnowledgeService(), settings=fast)

    registry = build_registry([adapter])
    deps.reset_state()
    application = create_app(fast)
    application.dependency_overrides[get_settings_dep] = lambda: fast
    application.dependency_overrides[get_registry] = lambda: registry
    application.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)
    application.dependency_overrides[get_current_user_from_token_optional_principal] = lambda: FakePrincipal()  # noqa: E501

    async with AsyncClient(
        transport=ASGITransport(app=application),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            EXECUTE_URL,
            json={"agent": "knowledge", "operation": "query", "payload": {"question": "q"}},
        )

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "AGENT_TIMEOUT"


async def test_api_returns_503_when_the_agent_is_unavailable(client_for: Any) -> None:
    """A disabled adapter returns 503 through the real stack."""
    async with client_for([KnowledgeAgentAdapter()]) as client:
        response = await client.post(
            EXECUTE_URL,
            json={"agent": "knowledge", "operation": "query", "payload": {"question": "q"}},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AGENT_UNAVAILABLE"


async def test_api_returns_the_query_result(client_for: Any) -> None:
    """A successful query returns the service result inside the envelope."""
    async with client_for([KnowledgeAgentAdapter(service=FakeKnowledgeService())]) as client:
        response = await client.post(
            EXECUTE_URL,
            json={
                "agent": "knowledge",
                "operation": "query",
                "payload": {"question": "What is the leave policy?"},
            },
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["agent"] == "knowledge"
    assert data["operation"] == "query"
    assert data["data"]["answer"] == "The leave policy allows 30 days."
    assert data["data"]["sources"] == [{"source": "hr.pdf", "page": 3}]


async def test_catalog_reports_the_real_capability_list(client_for: Any) -> None:
    """The catalog exposes only implemented operations to clients."""
    async with client_for([KnowledgeAgentAdapter(service=FakeKnowledgeService())]) as client:
        response = await client.get("/api/v1/agents")

    agents = response.json()["data"]["agents"]
    assert agents[0]["capabilities"] == ["ingest_document", "query"]
    assert agents[0]["available"] is True
    assert agents[0]["status"] == "ready"
