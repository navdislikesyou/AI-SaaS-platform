"""Orchestration service.

Coordinates a single request: resolve the agent, confirm it can run, delegate
to its adapter, and return a standardized result. It contains no agent
business logic and never imports an agent implementation directly.

Agent selection is explicit for v1, meaning the client names the agent. An LLM
based routing strategy may be added later without changing this class's public
method.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.agents.base import AgentAdapter
from app.agents.registry import AgentRegistry
from app.schemas.agent import AgentExecuteResponse

logger = logging.getLogger(__name__)


class Orchestrator:
    """Routes agent requests to the correct adapter."""

    def __init__(self, registry: AgentRegistry) -> None:
        """Initialize the orchestrator.

        Args:
            registry: The registry used to resolve agents by name.
        """
        self._registry = registry

    @property
    def registry(self) -> AgentRegistry:
        """Return the registry this orchestrator delegates to.

        Returns:
            The agent registry.
        """
        return self._registry

    def resolve(self, agent_name: str) -> AgentAdapter:
        """Resolve an agent name to its adapter.

        Args:
            agent_name: The agent identifier requested by the client.

        Returns:
            The registered adapter.

        Raises:
            UnknownAgentError: If the name is not registered.
        """
        adapter = self._registry.get(agent_name)
        logger.info("agent_resolved agent=%s available=%s", agent_name, adapter.is_available())
        return adapter

    async def execute(
        self,
        agent_name: str,
        operation: str,
        payload: dict[str, Any],
        user_context: dict[str, Any] | None = None,
    ) -> AgentExecuteResponse:
        """Execute one operation on one agent.

        Args:
            agent_name: The agent identifier requested by the client.
            operation: The operation to run.
            payload: Operation-specific input.
            user_context: Optional dict with ``user_id``, ``organization_id``,
                and ``role`` from the authenticated principal.

        Returns:
            A standardized execution response.

        Raises:
            UnknownAgentError: If the agent is not registered.
            AgentUnavailableError: If the agent has no connected implementation.
            UnknownOperationError: If the agent does not advertise the operation.
            AgentTimeoutError: If execution exceeds the adapter timeout.
            AgentExecutionError: If the agent fails unexpectedly.
        """
        adapter = self.resolve(agent_name)
        started = time.perf_counter()
        data = await adapter.execute(operation, payload, user_context=user_context)
        duration_ms = (time.perf_counter() - started) * 1000

        return AgentExecuteResponse(
            agent=adapter.name,
            operation=operation,
            data=data,
            duration_ms=round(duration_ms, 2),
        )
