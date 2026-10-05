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
from app.core.exceptions import AgentUnavailableError, UnknownOperationError

PLACEHOLDER_ADAPTERS = [
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


@pytest.mark.parametrize("adapter_cls", PLACEHOLDER_ADAPTERS)
def test_adapter_advertises_capabilities(adapter_cls: type[AgentAdapter]) -> None:
    """Adapters advertise capabilities even when unimplemented.

    Args:
        adapter_cls: The adapter class under test.
    """
    adapter = adapter_cls()

    capabilities = adapter.capabilities()

    assert capabilities
    assert all(isinstance(name, str) and name for name in capabilities)


@pytest.mark.parametrize("adapter_cls", PLACEHOLDER_ADAPTERS)
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


@pytest.mark.parametrize("adapter_cls", PLACEHOLDER_ADAPTERS)
async def test_unconnected_adapter_execution_raises_503(
    adapter_cls: type[AgentAdapter],
) -> None:
    """Executing against an unconnected adapter raises a 503-class error.

    Args:
        adapter_cls: The adapter class under test.
    """
    adapter = adapter_cls()

    assert adapter.is_available() is False

    with pytest.raises(AgentUnavailableError) as exc_info:
        await adapter.execute(adapter.capabilities()[0], {})

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
