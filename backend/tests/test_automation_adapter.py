"""Contract tests for the Automation Agent adapter.

These exercise the real :class:`AutomationAgentAdapter` through the FastAPI and
orchestrator stack. A fake service stands in for the automation agent, so no
Ollama server, model download, GPU, or network access is required.

The behaviour under test is the adapter's: payload validation, dict shapes,
availability semantics, and status-code translation. Nothing here asserts how
instruction parsing or drafting works.

One test asserts a property that matters beyond shape: the Automation Agent
drafts, and the adapter must not introduce the ability to send mail or touch a
calendar. Drafting without a confirmation step is not a partial feature, it is
the safety boundary.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.adapters.automation import AutomationAgentAdapter
from app.agents.registry import AgentRegistry
from app.api import deps
from app.api.deps import get_orchestrator, get_registry, get_settings_dep
from app.core.config import Settings
from app.core.exceptions import (
    AgentExecutionError,
    AgentUnavailableError,
    UnknownOperationError,
    ValidationFailedError,
)
from app.main import create_app
from app.services.orchestrator import Orchestrator

EXECUTE_URL = "/api/v1/agents/execute"

ADAPTER_SOURCE = Path("app/agents/adapters/automation.py")
SERVICE_SOURCE = Path("automation_agent/service.py")
AGENT_SOURCE = Path("automation_agent/automation_agent.py")

#: Symbols that would indicate a side effect the agent is not allowed to have.
FORBIDDEN_IMPORTS = {
    "smtplib",
    "email",
    "poplib",
    "imaplib",
    "requests",
    "httpx",
    "urllib.request",
    "urllib3",
    "googleapiclient",
    "google.oauth2",
    "msal",
    "socket",
}


class FakeAutomationService:
    """Stands in for ``AutomationService`` without any LLM client.

    Records what it was called with so tests can assert the adapter translated
    the payload correctly rather than just checking the shape of the reply.
    """

    def __init__(
        self,
        result: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        """Initialize the fake.

        Args:
            result: Value returned by ``execute``. Defaults to a drafted
                meeting invitation.
            error: Raised by ``execute`` when set, simulating an agent failure
                such as an unreachable Ollama server.
        """
        self._result = result or {
            "meeting": {
                "title": "Sprint Planning",
                "date": "5 March",
                "time": "10 AM",
                "venue": "Conference Room A",
                "attendees": ["Navneet Verma"],
            },
            "recipients": [{"name": "Navneet Verma", "email": "navneet@example.com"}],
            "email": "Dear Team,\n\nSprint planning is scheduled for 5 March.",
        }
        self._error = error
        self.calls: list[str] = []
        self.rosters: list[list[dict[str, str]] | None] = []

    def execute(
        self,
        instruction: str,
        employees: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Return the configured result.

        Args:
            instruction: Instruction forwarded by the adapter.
            employees: Employee records the adapter resolved, or None when the
                packaged directory is in use.

        Returns:
            The configured result.

        Raises:
            Exception: The configured error, when one was set.
        """
        self.calls.append(instruction)
        self.rosters.append(employees)
        if self._error is not None:
            raise self._error
        return self._result


@pytest.fixture
def service() -> FakeAutomationService:
    """Return a fake automation service.

    Returns:
        A fake with a default successful draft result.
    """
    return FakeAutomationService()


@pytest.fixture
def adapter(service: FakeAutomationService) -> AutomationAgentAdapter:
    """Return a connected automation adapter.

    Args:
        service: The injected fake service.

    Returns:
        An adapter reporting itself available.
    """
    return AutomationAgentAdapter(service=service)


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


def build_client(settings: Settings, adapters: list[Any]) -> AsyncClient:
    """Build an HTTP client over a registry of real adapters.

    Tests go through the real router, orchestrator, and exception handlers so
    status codes are verified as a client would see them.

    Args:
        settings: Settings for the application.
        adapters: The adapters to register.

    Returns:
        An AsyncClient bound to the application.
    """
    registry = build_registry(adapters)
    deps.reset_state()
    application = create_app(settings)
    application.dependency_overrides[get_settings_dep] = lambda: settings
    application.dependency_overrides[get_registry] = lambda: registry
    application.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)

    return AsyncClient(
        transport=ASGITransport(app=application),  # type: ignore[arg-type]
        base_url="http://testserver",
    )


# --------------------------------------------------------------------------
# Result shapes
# --------------------------------------------------------------------------


async def test_draft_action_returns_expected_dict_shape(
    adapter: AutomationAgentAdapter,
) -> None:
    """A successful draft returns meeting, recipients, email, and directory keys."""
    result = await adapter.execute(
        "draft_action",
        {"instruction": "Schedule sprint planning on 5 March at 10 AM with Navneet"},
    )

    assert set(result) == {"meeting", "recipients", "email", "directory"}
    assert isinstance(result["meeting"], dict)
    assert isinstance(result["recipients"], list)
    assert isinstance(result["email"], str)
    assert result["directory"]["source"] == "default"
    assert result["directory"]["directory_id"] is None


async def test_draft_action_forwards_the_instruction(
    adapter: AutomationAgentAdapter,
    service: FakeAutomationService,
) -> None:
    """The adapter passes the client's ``instruction`` through unchanged."""
    instruction = "Schedule a client meeting on 12 April at 3 PM in Room B"

    await adapter.execute("draft_action", {"instruction": instruction})

    assert service.calls == [instruction]
    assert service.rosters == [None]


async def test_draft_action_returns_a_draft_rather_than_a_sent_receipt(
    adapter: AutomationAgentAdapter,
) -> None:
    """The result describes a draft and carries no delivery confirmation.

    A key like ``sent``, ``delivered``, or ``message_id`` would mean the agent
    had contacted a mail server. Drafting is the whole contract here.
    """
    result = await adapter.execute("draft_action", {"instruction": "Draft a standup invite"})

    forbidden = {"sent", "delivered", "message_id", "smtp_response", "calendar_event_id"}
    assert forbidden.isdisjoint(result.keys())
    assert result["email"]


# --------------------------------------------------------------------------
# Payload validation -> 422
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({}, id="empty_payload"),
        pytest.param({"question": "q"}, id="wrong_operation_keys"),
        pytest.param({"instruction": ""}, id="blank_instruction"),
        pytest.param({"instruction": "   "}, id="whitespace_instruction"),
        pytest.param({"instruction": "\t\n"}, id="control_character_instruction"),
    ],
)
async def test_draft_action_without_a_usable_instruction_is_rejected(
    adapter: AutomationAgentAdapter,
    payload: dict[str, Any],
) -> None:
    """A missing or blank ``instruction`` raises a validation error."""
    with pytest.raises(ValidationFailedError) as exc_info:
        await adapter.execute("draft_action", payload)

    assert exc_info.value.status_code == 422
    assert "instruction" in exc_info.value.message


async def test_rejected_payload_never_reaches_the_service(
    adapter: AutomationAgentAdapter,
    service: FakeAutomationService,
) -> None:
    """Validation happens before the service is called at all."""
    with pytest.raises(ValidationFailedError):
        await adapter.execute("draft_action", {"instruction": ""})

    assert service.calls == []


# --------------------------------------------------------------------------
# Availability
# --------------------------------------------------------------------------


def test_successful_construction_reports_available(
    adapter: AutomationAgentAdapter,
) -> None:
    """Availability reflects that a service is present."""
    assert adapter.is_available() is True
    assert "connected" in adapter.describe().lower()


def test_disabled_agent_is_not_available() -> None:
    """An adapter that was never enabled reports unavailable."""
    adapter = AutomationAgentAdapter()

    assert adapter.is_available() is False
    assert "not connected" in adapter.describe().lower()


def test_construction_failure_reports_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A service that cannot be constructed leaves the adapter unavailable.

    Simulated by making the service import fail, which is what happens on a
    machine without the optional agent dependencies installed. The failure must
    be contained rather than propagating out of the registry build.
    """
    monkeypatch.setitem(sys.modules, "automation_agent.service", None)
    settings = Settings(environment="test", automation_agent_enabled=True)

    adapter = AutomationAgentAdapter(enabled=True, settings=settings)

    assert adapter.is_available() is False
    assert "not connected" in adapter.describe().lower()


async def test_unavailable_agent_returns_503() -> None:
    """Execution against an unconnected adapter returns 503."""
    adapter = AutomationAgentAdapter()

    with pytest.raises(AgentUnavailableError) as exc_info:
        await adapter.execute("draft_action", {"instruction": "do something"})

    assert exc_info.value.status_code == 503


# --------------------------------------------------------------------------
# Failure translation -> 502
# --------------------------------------------------------------------------


async def test_service_failure_becomes_agent_execution_error() -> None:
    """An exception from the service becomes a sanitized 502."""
    service = FakeAutomationService(error=RuntimeError("ollama refused at /secret/path"))
    adapter = AutomationAgentAdapter(service=service)

    with pytest.raises(AgentExecutionError) as exc_info:
        await adapter.execute("draft_action", {"instruction": "draft an invite"})

    assert exc_info.value.status_code == 502
    assert "/secret/path" not in exc_info.value.message
    assert "ollama refused" not in exc_info.value.message


# --------------------------------------------------------------------------
# Capabilities
# --------------------------------------------------------------------------


def test_advertised_capabilities_match_implemented_operations() -> None:
    """Capabilities are exactly the operations the adapter can run.

    ``propose_action`` and ``execute_action`` were advertised before any
    implementation existed. They are pinned out here so re-adding them requires
    a deliberate decision rather than passing silently.
    """
    adapter = AutomationAgentAdapter(service=FakeAutomationService())

    assert adapter.capabilities() == ["draft_action"]


async def test_every_advertised_capability_is_reachable(
    adapter: AutomationAgentAdapter,
) -> None:
    """Each advertised capability dispatches instead of raising 404."""
    for operation in adapter.capabilities():
        result = await adapter.execute(operation, {"instruction": "draft an invite"})
        assert isinstance(result, dict)


@pytest.mark.parametrize("operation", ["propose_action", "execute_action"])
async def test_operations_without_an_implementation_are_rejected(
    adapter: AutomationAgentAdapter,
    operation: str,
) -> None:
    """Previously advertised operations with no implementation now 404."""
    with pytest.raises(UnknownOperationError):
        await adapter.execute(operation, {"instruction": "do something"})


# --------------------------------------------------------------------------
# No external side effects
# --------------------------------------------------------------------------


def _imported_modules(path: Path) -> set[str]:
    """Return every module name imported by a source file.

    Args:
        path: The Python file to inspect.

    Returns:
        Fully qualified module names, including dotted submodules.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)

    return modules


@pytest.mark.parametrize(
    "path",
    [
        pytest.param(ADAPTER_SOURCE, id="adapter"),
        pytest.param(SERVICE_SOURCE, id="service"),
        pytest.param(AGENT_SOURCE, id="agent"),
    ],
)
def test_no_mail_or_calendar_integration_is_imported(path: Path) -> None:
    """No layer imports a mail or calendar client.

    Covers SMTP, IMAP, Gmail API, MSAL, and raw outbound HTTP. A generic HTTP
    library is listed too, because the agents reach Ollama over HTTP through
    LangChain rather than by importing a client directly.
    """
    imported = _imported_modules(path)

    offenders = {
        module
        for module in imported
        if any(module == bad or module.startswith(f"{bad}.") for bad in FORBIDDEN_IMPORTS)
    }

    assert not offenders, f"{path} imports side-effect modules: {sorted(offenders)}"


def _defined_methods(path: Path) -> set[str]:
    """Return public method names defined on the classes in a source file.

    Reads the AST rather than importing the module, so the check does not pull
    in the agent's optional dependencies.

    Args:
        path: The Python file to inspect.

    Returns:
        Names of every ``def`` that is not double-underscore prefixed.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("__")
    }


def test_agent_drafts_and_does_not_send() -> None:
    """No layer defines a send, schedule, or submit method.

    Checked by AST so the assertion holds without the agent's optional
    dependencies installed.
    """
    methods = _defined_methods(AGENT_SOURCE) | _defined_methods(SERVICE_SOURCE)

    forbidden = {
        "send",
        "send_email",
        "send_invitation",
        "send_message",
        "create_event",
        "create_calendar_event",
        "schedule",
        "schedule_event",
        "submit",
    }

    assert not methods & forbidden


def test_adapter_exposes_no_transport_method() -> None:
    """The adapter itself carries no mail or calendar transport.

    The adapter is the layer a client reaches first, so a send method here
    would make the capability reachable even with the agent left alone.
    """
    methods = _defined_methods(ADAPTER_SOURCE)

    assert not methods & {
        "send",
        "send_email",
        "create_event",
        "schedule",
        "submit",
        "_post",
        "_request",
    }


# --------------------------------------------------------------------------
# API-level status codes
# --------------------------------------------------------------------------


async def test_api_returns_the_draft_result(settings: Settings) -> None:
    """A successful draft returns the service result inside the envelope."""
    adapter = AutomationAgentAdapter(service=FakeAutomationService())

    async with build_client(settings, [adapter]) as client:
        response = await client.post(
            EXECUTE_URL,
            json={
                "agent": "automation",
                "operation": "draft_action",
                "payload": {"instruction": "Schedule sprint planning with Navneet"},
            },
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["agent"] == "automation"
    assert data["operation"] == "draft_action"
    assert set(data["data"]) == {"meeting", "recipients", "email", "directory"}
    assert data["data"]["directory"] == {
        "directory_id": None,
        "source": "default",
        "employee_count": None,
    }


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({}, id="empty_payload"),
        pytest.param({"instruction": ""}, id="blank_instruction"),
    ],
)
async def test_api_returns_422_for_an_unusable_instruction(
    settings: Settings,
    payload: dict[str, Any],
) -> None:
    """The API reports a missing or blank instruction as 422, not 502."""
    adapter = AutomationAgentAdapter(service=FakeAutomationService())

    async with build_client(settings, [adapter]) as client:
        response = await client.post(
            EXECUTE_URL,
            json={"agent": "automation", "operation": "draft_action", "payload": payload},
        )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"]["missing"] == ["instruction"]


async def test_api_returns_404_for_an_unsupported_operation(settings: Settings) -> None:
    """An operation outside the advertised list returns 404."""
    adapter = AutomationAgentAdapter(service=FakeAutomationService())

    async with build_client(settings, [adapter]) as client:
        response = await client.post(
            EXECUTE_URL,
            json={
                "agent": "automation",
                "operation": "execute_action",
                "payload": {"instruction": "send this now"},
            },
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "OPERATION_NOT_FOUND"


async def test_api_returns_502_when_the_agent_fails(settings: Settings) -> None:
    """A service exception surfaces as 502 with no internal detail leaked."""
    service = FakeAutomationService(error=RuntimeError("llm crashed at /secret/path"))
    adapter = AutomationAgentAdapter(service=service)

    async with build_client(settings, [adapter]) as client:
        response = await client.post(
            EXECUTE_URL,
            json={
                "agent": "automation",
                "operation": "draft_action",
                "payload": {"instruction": "draft an invite"},
            },
        )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AGENT_EXECUTION_FAILED"
    assert "/secret/path" not in response.text
    assert "llm crashed" not in response.text


async def test_api_returns_503_when_the_agent_is_unavailable(settings: Settings) -> None:
    """A disabled adapter returns 503 through the real stack."""
    async with build_client(settings, [AutomationAgentAdapter()]) as client:
        response = await client.post(
            EXECUTE_URL,
            json={
                "agent": "automation",
                "operation": "draft_action",
                "payload": {"instruction": "draft an invite"},
            },
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AGENT_UNAVAILABLE"


async def test_api_returns_504_when_the_agent_times_out() -> None:
    """An operation exceeding its budget returns 504."""
    import time

    class SlowAutomationService(FakeAutomationService):
        def execute(self, instruction: str) -> dict[str, Any]:
            time.sleep(0.5)
            return {"meeting": {}, "recipients": [], "email": "late"}

    fast = Settings(environment="test", automation_agent_timeout_seconds=0.05)
    adapter = AutomationAgentAdapter(service=SlowAutomationService(), settings=fast)

    async with build_client(fast, [adapter]) as client:
        response = await client.post(
            EXECUTE_URL,
            json={
                "agent": "automation",
                "operation": "draft_action",
                "payload": {"instruction": "draft an invite"},
            },
        )

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "AGENT_TIMEOUT"


async def test_catalog_reports_the_real_capability_list(settings: Settings) -> None:
    """The catalog exposes only the implemented operation."""
    adapter = AutomationAgentAdapter(service=FakeAutomationService())

    async with build_client(settings, [adapter]) as client:
        response = await client.get("/api/v1/agents")

    agent = response.json()["data"]["agents"][0]
    assert agent["capabilities"] == ["draft_action"]
    assert agent["available"] is True
    assert agent["status"] == "ready"
