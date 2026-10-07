"""Contract tests every agent adapter must satisfy.

A new adapter, or a real agent connected behind an existing adapter, is
integrated by passing this suite. That turns integration into a pass/fail
check rather than an open-ended debugging session.
"""

from __future__ import annotations

import pytest

from app.agents.adapters.automation import AutomationAgentAdapter
from app.agents.adapters.knowledge import KnowledgeAgentAdapter
from app.agents.adapters.performance import PerformanceAgentAdapter
from app.agents.base import AgentAdapter, PlaceholderAgentAdapter
from app.core.exceptions import (
    AgentExecutionError,
    AgentUnavailableError,
    UnknownOperationError,
    ValidationFailedError,
)

#: Adapters that are execution paths through /agents/execute. Each advertises
#: operations and refuses them only when no implementation is connected.
PLACEHOLDER_ADAPTERS = [
    KnowledgeAgentAdapter,
    AutomationAgentAdapter,
]

#: Adapters that are catalog entries only. The Performance Analyzer is
#: implemented, but its work is CPU-bound and runs as a background job through
#: /api/v1/performance/jobs rather than through /agents/execute, so it
#: advertises nothing here and says where it is actually served.
CATALOG_ONLY_ADAPTERS = [
    PerformanceAgentAdapter,
]

#: Every adapter that must satisfy the shared contract.
ALL_ADAPTERS = [
    KnowledgeAgentAdapter,
    AutomationAgentAdapter,
    PerformanceAgentAdapter,
]


class _StubService:
    """Stand-in for a connected agent service.

    Adapters that build a real service derive availability from whether
    construction succeeded, so a connected instance cannot be produced by
    passing ``enabled=True`` alone. Injecting this stub expresses "connected"
    without loading a model.
    """

    def __getattr__(self, name: str) -> object:
        """Return a callable returning a dict for any service method."""
        return lambda *args, **kwargs: {"stub": name}


def connected_adapter(adapter_cls: type[AgentAdapter]) -> AgentAdapter:
    """Build an adapter that reports itself connected.

    Adapters backed by a real service take an injected service; the remaining
    placeholder-style adapters take the enabled flag.

    Args:
        adapter_cls: The adapter class under test.

    Returns:
        An adapter reporting ``is_available() is True``.
    """
    if issubclass(adapter_cls, PlaceholderAgentAdapter):
        return adapter_cls(enabled=True)
    return adapter_cls(service=_StubService())


@pytest.mark.parametrize("adapter_cls", PLACEHOLDER_ADAPTERS)
def test_adapter_reports_a_non_empty_name(adapter_cls: type[AgentAdapter]) -> None:
    """Adapters expose a stable, non-empty identifier.

    Args:
        adapter_cls: The adapter class under test.
    """
    adapter = adapter_cls()

    assert isinstance(adapter.name, str)
    assert adapter.name.strip()
    assert adapter.name.islower()


@pytest.mark.parametrize("adapter_cls", ALL_ADAPTERS)
def test_capabilities_are_well_formed(adapter_cls: type[AgentAdapter]) -> None:
    """Every advertised capability is a non-empty string.

    A catalog entry may advertise nothing; what it must never do is advertise
    something malformed.

    Args:
        adapter_cls: The adapter class under test.
    """
    capabilities = adapter_cls().capabilities()

    assert all(isinstance(name, str) and name for name in capabilities)


@pytest.mark.parametrize("adapter_cls", PLACEHOLDER_ADAPTERS)
def test_execution_adapter_advertises_capabilities(adapter_cls: type[AgentAdapter]) -> None:
    """An adapter that can execute must advertise at least one operation.

    Excludes catalog-only adapters, which are reachable through a different
    endpoint entirely.

    Args:
        adapter_cls: The adapter class under test.
    """
    assert adapter_cls().capabilities()


@pytest.mark.parametrize("adapter_cls", ALL_ADAPTERS)
def test_capabilities_return_a_copy(adapter_cls: type[AgentAdapter]) -> None:
    """Mutating the returned list cannot corrupt adapter state.

    Args:
        adapter_cls: The adapter class under test.
    """
    adapter = adapter_cls()

    adapter.capabilities().append("injected")

    assert "injected" not in adapter.capabilities()


@pytest.mark.parametrize("adapter_cls", PLACEHOLDER_ADAPTERS)
def test_adapter_has_display_name(adapter_cls: type[AgentAdapter]) -> None:
    """Adapters provide a human-readable label.

    Args:
        adapter_cls: The adapter class under test.
    """
    adapter = adapter_cls()

    assert adapter.display_name
    assert adapter.display_name != adapter.name


@pytest.mark.parametrize("adapter_cls", ALL_ADAPTERS)
async def test_unconnected_adapter_execution_raises_503(
    adapter_cls: type[AgentAdapter],
) -> None:
    """Executing against an unconnected adapter raises a 503-class error.

    Catalog-only adapters advertise nothing, so they are probed with a
    representative operation name rather than from their capability list.

    Args:
        adapter_cls: The adapter class under test.
    """
    adapter = adapter_cls()

    assert adapter.is_available() is False

    capabilities = adapter.capabilities()

    operation = capabilities[0] if capabilities else "analyze"

    with pytest.raises(AgentUnavailableError) as exc_info:
        await adapter.execute(operation, {})

    assert exc_info.value.status_code == 503


@pytest.mark.parametrize("adapter_cls", PLACEHOLDER_ADAPTERS)
def test_adapter_describes_not_connected_state(
    adapter_cls: type[AgentAdapter],
) -> None:
    """Placeholders describe themselves honestly as not connected.

    Args:
        adapter_cls: The adapter class under test.
    """
    description = adapter_cls().describe()

    assert "not connected" in description.lower()


@pytest.mark.parametrize("adapter_cls", CATALOG_ONLY_ADAPTERS)
def test_catalog_only_adapter_points_at_its_real_endpoint(
    adapter_cls: type[AgentAdapter],
) -> None:
    """A catalog-only adapter says where it is actually served.

    Silence would leave a client with an agent that appears registered, offers
    nothing, and explains nothing.

    Args:
        adapter_cls: The adapter class under test.
    """
    description = adapter_cls().describe()

    assert "not connected" not in description.lower()
    assert "jobs" in description


@pytest.mark.parametrize("adapter_cls", PLACEHOLDER_ADAPTERS)
async def test_adapter_rejects_unknown_operation_when_available(
    adapter_cls: type[AgentAdapter],
) -> None:
    """Once connected, unadvertised operations are still rejected.

    Args:
        adapter_cls: The adapter class under test.
    """
    adapter = connected_adapter(adapter_cls)

    assert adapter.is_available() is True

    with pytest.raises(UnknownOperationError):
        await adapter.execute("definitely_not_supported", {})


# --------------------------------------------------------------------------
# Contract for adapters backed by a real agent service
#
# The tests above describe what any adapter may do. The ones below describe
# what an adapter must do once a real agent is connected, which is the state
# Knowledge and Automation are in. Placeholders are excluded: they have no
# service to call, so "returns a dict" is not yet a property they can satisfy.
# --------------------------------------------------------------------------

#: Adapters whose availability is derived from successful construction.
SERVICE_BACKED_ADAPTERS = [
    KnowledgeAgentAdapter,
    AutomationAgentAdapter,
]

#: A payload that satisfies every operation on the adapters above.
VALID_PAYLOAD = {
    "file_path": "hr.pdf",
    "question": "What is the leave policy?",
    "instruction": "Schedule a sprint planning on 5 March with Navneet",
}


@pytest.mark.parametrize("adapter_cls", SERVICE_BACKED_ADAPTERS)
async def test_connected_adapter_returns_a_dictionary(
    adapter_cls: type[AgentAdapter],
) -> None:
    """Every advertised operation resolves to a dict, never None or an object.

    The API contract serializes ``data`` as JSON, so a non-dict result would
    either fail to serialize or leak a model object into the response.

    Args:
        adapter_cls: The adapter class under test.
    """
    adapter = connected_adapter(adapter_cls)

    for operation in adapter.capabilities():
        result = await adapter.execute(operation, dict(VALID_PAYLOAD))

        assert isinstance(result, dict), f"{operation} returned {type(result).__name__}"


@pytest.mark.parametrize("adapter_cls", SERVICE_BACKED_ADAPTERS)
async def test_capabilities_match_operations_that_dispatch(
    adapter_cls: type[AgentAdapter],
) -> None:
    """Advertised capabilities correspond to operations that actually run.

    Declaring an operation that 404s at runtime is worse than omitting it, so
    each advertised name must reach ``run`` rather than being refused by the
    capability check.

    Args:
        adapter_cls: The adapter class under test.
    """
    adapter = connected_adapter(adapter_cls)

    for operation in adapter.capabilities():
        result = await adapter.execute(operation, dict(VALID_PAYLOAD))

        assert isinstance(result, dict), f"{operation} is advertised but does not run"


@pytest.mark.parametrize("adapter_cls", SERVICE_BACKED_ADAPTERS)
async def test_availability_reflects_constructed_state(
    adapter_cls: type[AgentAdapter],
) -> None:
    """Availability is decided by whether a service was built, not by a flag.

    An adapter constructed with a service is available; the same class with no
    service is not. This is the property that makes ``GET /agents`` honest when
    an agent is enabled but broken.

    Args:
        adapter_cls: The adapter class under test.
    """
    assert connected_adapter(adapter_cls).is_available() is True
    assert adapter_cls().is_available() is False


@pytest.mark.parametrize("adapter_cls", SERVICE_BACKED_ADAPTERS)
async def test_invalid_payload_raises_a_validation_error(
    adapter_cls: type[AgentAdapter],
) -> None:
    """An empty payload is a 422, not a 502.

    ``payload`` is an arbitrary JSON object at the API boundary, so an
    operation-specific rule is the adapter's responsibility. A missing key that
    reaches the agent would surface as 502 and wrongly tell the client its
    request was fine.

    Args:
        adapter_cls: The adapter class under test.
    """
    adapter = connected_adapter(adapter_cls)

    for operation in adapter.capabilities():
        with pytest.raises(ValidationFailedError) as exc_info:
            await adapter.execute(operation, {})

        assert exc_info.value.status_code == 422


@pytest.mark.parametrize("adapter_cls", SERVICE_BACKED_ADAPTERS)
async def test_blank_payload_value_raises_a_validation_error(
    adapter_cls: type[AgentAdapter],
) -> None:
    """A whitespace-only required value is rejected like a missing one.

    A blank string would otherwise reach the agent and fail there.

    Args:
        adapter_cls: The adapter class under test.
    """
    adapter = connected_adapter(adapter_cls)
    blank = {key: "   " for key in VALID_PAYLOAD}

    for operation in adapter.capabilities():
        with pytest.raises(ValidationFailedError):
            await adapter.execute(operation, blank)


@pytest.mark.parametrize("adapter_cls", SERVICE_BACKED_ADAPTERS)
async def test_agent_failure_is_translated_to_execution_error(
    adapter_cls: type[AgentAdapter],
) -> None:
    """An exception from the agent becomes a sanitized 502.

    The original message must not survive: agent exceptions routinely carry
    file paths and internal state that must not reach a client.

    Args:
        adapter_cls: The adapter class under test.
    """

    class ExplodingService:
        def __getattr__(self, name: str) -> object:
            """Return a method that always raises."""

            def explode(*args: object, **kwargs: object) -> dict[str, object]:
                raise RuntimeError("internal detail at /secret/path")

            return explode

    adapter = adapter_cls(service=ExplodingService())

    for operation in adapter.capabilities():
        with pytest.raises(AgentExecutionError) as exc_info:
            await adapter.execute(operation, dict(VALID_PAYLOAD))

        assert exc_info.value.status_code == 502
        assert "/secret/path" not in exc_info.value.message
        assert "internal detail" not in exc_info.value.message


@pytest.mark.parametrize("adapter_cls", SERVICE_BACKED_ADAPTERS)
def test_describe_matches_actual_availability(
    adapter_cls: type[AgentAdapter],
) -> None:
    """The prose description agrees with the boolean.

    A catalog entry saying "connected" while ``is_available()`` is False would
    be worse than either alone.

    Args:
        adapter_cls: The adapter class under test.
    """
    connected = connected_adapter(adapter_cls).describe().lower()
    disconnected = adapter_cls().describe().lower()

    assert "not connected" not in connected
    assert "not connected" in disconnected
