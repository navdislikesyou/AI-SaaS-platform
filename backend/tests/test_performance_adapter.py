"""Contract tests for the Performance Analyzer adapter.

Performance is deferred: no service exists, nothing is wired to it, and this
suite must not change that. It verifies only the current contract, namely that
the adapter stays honestly unavailable and that the API returns 503 for it.

These tests deliberately avoid loading datasets, generating images, importing
pandas or matplotlib, or running the analyzers. The Performance Analyzer is
data analytics with no predictive or classification behaviour, and nothing here
should imply otherwise.

Note the asymmetry with the other adapter suites: there is no ``service=``
injection, because there is no service to inject. If someone later adds one,
the availability tests here should start failing, which is the intended signal.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.adapters.performance import PerformanceAgentAdapter
from app.agents.base import PlaceholderAgentAdapter
from app.agents.registry import AgentRegistry
from app.api import deps
from app.api.deps import get_orchestrator, get_registry, get_settings_dep
from app.core.config import Settings
from app.core.exceptions import AgentUnavailableError
from app.main import create_app
from app.services.orchestrator import Orchestrator

EXECUTE_URL = "/api/v1/agents/execute"

#: Operations the deferred analyzer intends to support. None are implemented.
INTENDED_CAPABILITIES = {
    "load_dataset",
    "compute_kpis",
    "compare_periods",
    "analyze",
    "visualize",
}


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


@pytest.fixture
def adapter() -> PerformanceAgentAdapter:
    """Return the deferred performance adapter.

    Returns:
        An adapter with the enable flag off, as shipped.
    """
    return PerformanceAgentAdapter()


def build_client(settings: Settings, adapters: list[Any]) -> AsyncClient:
    """Build an HTTP client over a registry holding the real adapters.

    Args:
        settings: Settings for the application.
        adapters: The adapters to register.

    Returns:
        An AsyncClient bound to the application.
    """
    registry = AgentRegistry()
    for adapter in adapters:
        registry.register(adapter)

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
# Remains deferred
# --------------------------------------------------------------------------


def test_adapter_reports_itself_unavailable(adapter: PerformanceAgentAdapter) -> None:
    """The deferred adapter is unavailable."""
    assert adapter.is_available() is False


def test_adapter_describes_itself_as_not_connected(
    adapter: PerformanceAgentAdapter,
) -> None:
    """The adapter says so in words, not just in a boolean."""
    description = adapter.describe()

    assert "not connected" in description.lower()


@pytest.mark.xfail(
    reason=(
        "Known gap: PerformanceAgentAdapter still derives availability from the "
        "enable flag via PlaceholderAgentAdapter, unlike Knowledge and Automation "
        "which derive it from construction. With PERFORMANCE_AGENT_ENABLED=true "
        "the catalog wrongly reports 'ready' and execute returns 502 from the "
        "NotImplementedError instead of the documented 503. Tracked as a Phase 5 "
        "finding; remove this marker once the adapter stops trusting the flag."
    ),
    strict=True,
)
def test_enabling_the_flag_does_not_make_it_available() -> None:
    """Flipping the enable flag cannot connect an agent with no implementation.

    Knowledge and Automation derive availability from construction. Performance
    is still a placeholder, so the flag should be inert here. This test exists
    to fail loudly if that ever changes without the rest of the suite being
    updated.
    """
    adapter = PerformanceAgentAdapter(enabled=True)

    assert adapter.is_available() is False


def test_adapter_is_still_a_placeholder(adapter: PerformanceAgentAdapter) -> None:
    """Performance still extends the placeholder base, unlike the other two."""
    assert isinstance(adapter, PlaceholderAgentAdapter)


async def test_execution_raises_unavailable(adapter: PerformanceAgentAdapter) -> None:
    """Every operation is refused with a 503-class error."""
    for operation in adapter.capabilities():
        with pytest.raises(AgentUnavailableError) as exc_info:
            await adapter.execute(operation, {})

        assert exc_info.value.status_code == 503


def test_run_is_not_implemented(adapter: PerformanceAgentAdapter) -> None:
    """Calling ``run`` directly raises rather than half-working."""
    with pytest.raises(NotImplementedError):
        adapter.run("analyze", {})


# --------------------------------------------------------------------------
# Capability honesty
# --------------------------------------------------------------------------


def test_advertised_capabilities_are_the_intended_set(
    adapter: PerformanceAgentAdapter,
) -> None:
    """Capabilities still match the documented intent.

    This is the one place where the Performance adapter legitimately advertises
    unimplemented operations, because it is a placeholder that has never been
    connected. Contrast this with Knowledge and Automation, whose capability
    lists were trimmed to what actually works.
    """
    assert set(adapter.capabilities()) == INTENDED_CAPABILITIES


def test_capabilities_are_advertised_while_unavailable() -> None:
    """Capabilities are listed, but nothing is presented as connected.

    A placeholder may describe its intent through capabilities; what it must not
    do is claim readiness. With the flag off the adapter is plainly unavailable.
    """
    adapter = PerformanceAgentAdapter()

    assert adapter.capabilities()
    assert adapter.is_available() is False


def test_capabilities_return_a_copy(adapter: PerformanceAgentAdapter) -> None:
    """Mutating the returned list cannot corrupt adapter state."""
    adapter.capabilities().append("injected")

    assert "injected" not in adapter.capabilities()


# --------------------------------------------------------------------------
# API-level behaviour
# --------------------------------------------------------------------------


async def test_catalog_marks_the_agent_not_connected(settings: Settings) -> None:
    """The catalog reports the agent as registered but unavailable."""
    async with build_client(settings, [PerformanceAgentAdapter()]) as client:
        response = await client.get("/api/v1/agents")

    assert response.status_code == 200
    body = response.json()
    agent = body["data"]["agents"][0]

    assert agent["name"] == "performance"
    assert agent["available"] is False
    assert agent["status"] == "not_connected"
    assert body["data"]["available_count"] == 0


@pytest.mark.parametrize(
    "operation",
    [
        "load_dataset",
        "compute_kpis",
        "compare_periods",
        "analyze",
        "visualize",
    ],
)
async def test_api_returns_503_for_every_advertised_operation(
    settings: Settings,
    operation: str,
) -> None:
    """No advertised operation succeeds, because none is implemented."""
    async with build_client(settings, [PerformanceAgentAdapter()]) as client:
        response = await client.post(
            EXECUTE_URL,
            json={"agent": "performance", "operation": operation, "payload": {}},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AGENT_UNAVAILABLE"


async def test_api_returns_503_for_an_unadvertised_operation(
    settings: Settings,
) -> None:
    """Availability is checked before the operation, so this is also 503."""
    async with build_client(settings, [PerformanceAgentAdapter()]) as client:
        response = await client.post(
            EXECUTE_URL,
            json={"agent": "performance", "operation": "not_a_real_op", "payload": {}},
        )

    assert response.status_code == 503


async def test_api_returns_404_for_an_unknown_agent(settings: Settings) -> None:
    """An unregistered agent name is still a 404, not a 503."""
    async with build_client(settings, [PerformanceAgentAdapter()]) as client:
        response = await client.post(
            EXECUTE_URL,
            json={"agent": "nonexistent", "operation": "analyze", "payload": {}},
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "AGENT_NOT_FOUND"


async def test_execution_loads_no_dataset(settings: Settings) -> None:
    """A refused execute performs no analysis work at all.

    Asserts the payload is never inspected beyond the availability guard, which
    is the observable form of "no dataset was loaded, no PNG was written, no
    model was loaded".
    """
    payload: dict[str, Any] = {}

    async with build_client(settings, [PerformanceAgentAdapter()]) as client:
        response = await client.post(
            EXECUTE_URL,
            json={"agent": "performance", "operation": "analyze", "payload": payload},
        )

    assert response.status_code == 503
    assert payload == {}


async def test_readiness_still_passes_with_a_deferred_agent(settings: Settings) -> None:
    """An unconnected agent does not fail the readiness check.

    The container is healthy even with agents missing, so a deferred agent must
    not turn readiness red and take a restart loop with it.
    """
    async with build_client(settings, [PerformanceAgentAdapter()]) as client:
        response = await client.get("/api/v1/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert any(check["name"] == "agents" for check in body["checks"])
