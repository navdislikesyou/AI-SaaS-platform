"""Agent registry.

Owns the set of registered :class:`~app.agents.base.AgentAdapter` instances
and resolves them by name. Registration happens once during application
startup; the registry is otherwise read-only at request time.
"""

from __future__ import annotations

import logging

from app.agents.base import AgentAdapter
from app.core.exceptions import UnknownAgentError

logger = logging.getLogger(__name__)


class AgentRegistry:
    """A name-keyed collection of agent adapters."""

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._agents: dict[str, AgentAdapter] = {}

    def register(self, adapter: AgentAdapter) -> None:
        """Add an adapter to the registry.

        Args:
            adapter: The adapter to register.

        Raises:
            ValueError: If an agent with the same name is already registered.
        """
        name = adapter.name
        if name in self._agents:
            raise ValueError(f"Agent '{name}' is already registered.")
        self._agents[name] = adapter
        logger.info(
            "agent_registered agent=%s available=%s capabilities=%s",
            name,
            adapter.is_available(),
            adapter.capabilities(),
        )

    def get(self, name: str) -> AgentAdapter:
        """Return the adapter registered under a name.

        Args:
            name: The agent identifier.

        Returns:
            The registered adapter.

        Raises:
            UnknownAgentError: If no agent is registered under that name.
        """
        try:
            return self._agents[name]
        except KeyError:
            raise UnknownAgentError(
                f"Unknown agent '{name}'.",
                details={"agent": name, "known_agents": sorted(self._agents)},
            ) from None

    def has(self, name: str) -> bool:
        """Report whether an agent name is registered.

        Args:
            name: The agent identifier.

        Returns:
            True when the agent is registered.
        """
        return name in self._agents

    def list_all(self) -> list[AgentAdapter]:
        """Return every registered adapter.

        Returns:
            All adapters sorted by name.
        """
        return [self._agents[name] for name in sorted(self._agents)]

    def available_agents(self) -> list[AgentAdapter]:
        """Return the adapters whose implementations are connected.

        Returns:
            Adapters reporting themselves available.
        """
        return [adapter for adapter in self.list_all() if adapter.is_available()]

    def __len__(self) -> int:
        """Return the number of registered agents.

        Returns:
            The adapter count.
        """
        return len(self._agents)

    def __contains__(self, name: object) -> bool:
        """Support ``name in registry`` checks.

        Args:
            name: The identifier to test.

        Returns:
            True when the name is registered.
        """
        return isinstance(name, str) and name in self._agents
