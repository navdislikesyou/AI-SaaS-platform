"""Tests for the orchestrator dispatch path."""

from __future__ import annotations

import asyncio

import pytest

from app.agents.registry import AgentRegistry
from app.core.exceptions import (
    AgentExecutionError,
    AgentTimeoutError,
    AgentUnavailableError,
    UnknownAgentError,
    UnknownOperationError,
)
from app.services.orchestrator import Orchestrator
from tests.fakes import EchoAgent, ExplodingAgent, SlowAgent, UnavailableAgent


def _orchestrator(*adapters: object) -> Orchestrator:
    """Build an orchestrator over the given adapters.

    Args:
        *adapters: Adapters to register.

    Returns:
        A ready orchestrator.
    """
    registry = AgentRegistry()
    for adapter in adapters:
        registry.register(adapter)  # type: ignore[arg-type]
    return Orchestrator(registry)


async def test_execute_returns_agent_result() -> None:
    """A successful execution returns the agent payload."""
    orchestrator = _orchestrator(EchoAgent(name="knowledge", capabilities=["query"]))

    result = await orchestrator.execute("knowledge", "query", {"question": "hi"})

    assert result.agent == "knowledge"
    assert result.operation == "query"
    assert result.data["echo"] is True
    assert result.data["payload"] == {"question": "hi"}


async def test_execute_records_duration() -> None:
    """The response reports server-side execution time."""
    orchestrator = _orchestrator(EchoAgent(name="knowledge", capabilities=["query"]))

    result = await orchestrator.execute("knowledge", "query", {})

    assert result.duration_ms is not None
    assert result.duration_ms >= 0


async def test_unknown_agent_raises_before_execution() -> None:
    """An unregistered agent name raises UnknownAgentError."""
    orchestrator = _orchestrator(EchoAgent(name="knowledge"))

    with pytest.raises(UnknownAgentError):
        await orchestrator.execute("automation", "draft_action", {})


async def test_unavailable_agent_raises_503() -> None:
    """A registered but unconnected agent raises AgentUnavailableError."""
    orchestrator = _orchestrator(UnavailableAgent(name="automation"))

    with pytest.raises(AgentUnavailableError) as exc_info:
        await orchestrator.execute("automation", "ping", {})

    assert exc_info.value.status_code == 503
    assert exc_info.value.error_code == "AGENT_UNAVAILABLE"


async def test_unsupported_operation_raises_404() -> None:
    """An operation the agent does not advertise is rejected."""
    orchestrator = _orchestrator(EchoAgent(name="knowledge", capabilities=["query"]))

    with pytest.raises(UnknownOperationError) as exc_info:
        await orchestrator.execute("knowledge", "delete_document", {})

    assert exc_info.value.status_code == 404
    assert exc_info.value.details["supported"] == ["query"]


async def test_agent_failure_becomes_execution_error() -> None:
    """An unexpected agent error is wrapped, preserving the cause."""
    orchestrator = _orchestrator(ExplodingAgent(name="performance"))

    with pytest.raises(AgentExecutionError) as exc_info:
        await orchestrator.execute("performance", "ping", {})

    assert exc_info.value.status_code == 502
    assert isinstance(exc_info.value.__cause__, RuntimeError)


async def test_slow_agent_times_out() -> None:
    """An agent exceeding its timeout raises AgentTimeoutError."""
    orchestrator = _orchestrator(SlowAgent(name="slow", delay=0.2))

    with pytest.raises(AgentTimeoutError) as exc_info:
        await orchestrator.execute("slow", "ping", {})

    assert exc_info.value.status_code == 504


async def test_blocking_agent_does_not_stall_the_event_loop() -> None:
    """Blocking agent work is offloaded so concurrent calls still progress.

    This is the property that keeps slow Llama or vector-search calls from
    blocking every other request.
    """
    orchestrator = _orchestrator(SlowAgent(name="slow", delay=0.1, timeout_seconds=5.0))

    results = await asyncio.gather(
        orchestrator.execute("slow", "ping", {}),
        orchestrator.execute("slow", "ping", {}),
    )

    assert all(result.data["slept"] == 0.1 for result in results)


async def test_resolve_returns_registered_adapter() -> None:
    """Resolution exposes the adapter behind a name."""
    adapter = EchoAgent(name="knowledge")
    orchestrator = _orchestrator(adapter)

    assert orchestrator.resolve("knowledge") is adapter


def test_registry_property_is_exposed() -> None:
    """The orchestrator exposes its registry for callers that need it."""
    orchestrator = _orchestrator(EchoAgent(name="knowledge"))

    assert len(orchestrator.registry) == 1
