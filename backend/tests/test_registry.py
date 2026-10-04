"""Tests for the agent registry."""

from __future__ import annotations

import pytest

from app.agents.registry import AgentRegistry
from app.core.exceptions import UnknownAgentError
from tests.fakes import EchoAgent


def test_register_and_get_returns_same_adapter() -> None:
    """A registered adapter is returned by name."""
    registry = AgentRegistry()
    adapter = EchoAgent(name="knowledge")

    registry.register(adapter)

    assert registry.get("knowledge") is adapter


def test_duplicate_registration_is_rejected() -> None:
    """Registering the same agent name twice raises."""
    registry = AgentRegistry()
    registry.register(EchoAgent(name="knowledge"))

    with pytest.raises(ValueError, match="already registered"):
        registry.register(EchoAgent(name="knowledge"))


def test_unknown_agent_raises_with_known_names() -> None:
    """An unknown name raises UnknownAgentError listing registered agents."""
    registry = AgentRegistry()
    registry.register(EchoAgent(name="knowledge"))

    with pytest.raises(UnknownAgentError) as exc_info:
        registry.get("nope")

    assert exc_info.value.status_code == 404
    assert exc_info.value.details["known_agents"] == ["knowledge"]


def test_list_all_is_sorted_by_name() -> None:
    """The catalog is ordered by name so responses are deterministic."""
    registry = AgentRegistry()
    registry.register(EchoAgent(name="performance"))
    registry.register(EchoAgent(name="automation"))
    registry.register(EchoAgent(name="knowledge"))

    names = [adapter.name for adapter in registry.list_all()]

    assert names == ["automation", "knowledge", "performance"]


def test_available_agents_excludes_unconnected() -> None:
    """Only agents reporting availability are returned."""
    from tests.fakes import UnavailableAgent

    registry = AgentRegistry()
    registry.register(EchoAgent(name="knowledge"))
    registry.register(UnavailableAgent(name="automation"))

    available = [adapter.name for adapter in registry.available_agents()]

    assert available == ["knowledge"]


def test_has_and_contains_report_registration() -> None:
    """Membership checks reflect registration state."""
    registry = AgentRegistry()
    registry.register(EchoAgent(name="knowledge"))

    assert registry.has("knowledge")
    assert "knowledge" in registry
    assert "automation" not in registry


def test_len_counts_registered_agents() -> None:
    """The registry reports how many agents it holds."""
    registry = AgentRegistry()
    registry.register(EchoAgent(name="knowledge"))
    registry.register(EchoAgent(name="automation"))

    assert len(registry) == 2
