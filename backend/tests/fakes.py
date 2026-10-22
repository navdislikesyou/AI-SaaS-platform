"""Fake agents used to test the backend architecture.

These stand in for real agent implementations so the registry, orchestrator,
and HTTP layer can be exercised without any agent code. They contain no AI
logic and are test-only.
"""

from __future__ import annotations

import time
from typing import Any

from app.agents.base import AgentAdapter


class FakePrincipal:
    """A stand-in for an authenticated user.

    Routers resolve the principal to scope resources to an organisation. A
    record without an owner is invisible to every organisation, so a test that
    uploads a resource and then lists it needs a principal that owns it.
    """

    def __init__(
        self,
        user_id: str = "test-user-1",
        organization_id: str = "test-org-1",
        role: str = "employee",
    ) -> None:
        """Initialize the principal.

        Args:
            user_id: The user identifier.
            organization_id: The organisation that owns the user's resources.
            role: The role name the routers may read.
        """
        self.id = user_id
        self.organization_id = organization_id
        self.role = role
        self.is_active = True


class EchoAgent(AgentAdapter):
    """An available agent that echoes back the operation and payload.

    Used to verify the full dispatch path succeeds when an implementation is
    connected.
    """

    def __init__(
        self,
        name: str = "echo",
        capabilities: list[str] | None = None,
    ) -> None:
        """Initialize the echo agent.

        Args:
            name: The agent identifier.
            capabilities: Operations to advertise. Defaults to a single
                ``ping`` operation.
        """
        self._name = name
        self._capabilities = capabilities or ["ping"]
        self.calls: list[tuple[str, dict[str, Any]]] = []

    @property
    def name(self) -> str:
        """Return the agent identifier.

        Returns:
            The configured name.
        """
        return self._name

    def capabilities(self) -> list[str]:
        """Return the advertised operations.

        Returns:
            A copy of the capability list.
        """
        return list(self._capabilities)

    def is_available(self) -> bool:
        """Report the agent as connected.

        Returns:
            Always True.
        """
        return True

    def run(
        self,
        operation: str,
        payload: dict[str, Any],
        user_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Echo the operation and payload.

        Args:
            operation: The requested operation.
            payload: The request payload.
            user_context: Optional dict with ``user_id``, ``organization_id``,
                and ``role`` from the authenticated principal.

        Returns:
            An object echoing the call, plus a call counter.
        """
        self.calls.append((operation, payload))
        return {
            "echo": True,
            "operation": operation,
            "payload": payload,
            "call_count": len(self.calls),
        }


class UnavailableAgent(AgentAdapter):
    """An agent whose implementation is not connected.

    Mirrors the production placeholder state so 503 handling can be tested.
    """

    def __init__(self, name: str = "unavailable") -> None:
        """Initialize the unavailable agent.

        Args:
            name: The agent identifier.
        """
        self._name = name

    @property
    def name(self) -> str:
        """Return the agent identifier.

        Returns:
            The configured name.
        """
        return self._name

    def capabilities(self) -> list[str]:
        """Return the advertised operations.

        Returns:
            A single ``ping`` operation.
        """
        return ["ping"]

    def is_available(self) -> bool:
        """Report the agent as not connected.

        Returns:
            Always False.
        """
        return False


class ExplodingAgent(AgentAdapter):
    """An available agent that always raises.

    Used to verify that agent failures become a sanitized 502 response.
    """

    def __init__(self, name: str = "exploding") -> None:
        """Initialize the failing agent.

        Args:
            name: The agent identifier.
        """
        self._name = name

    @property
    def name(self) -> str:
        """Return the agent identifier.

        Returns:
            The configured name.
        """
        return self._name

    def capabilities(self) -> list[str]:
        """Return the advertised operations.

        Returns:
            A single ``ping`` operation.
        """
        return ["ping"]

    def is_available(self) -> bool:
        """Report the agent as connected.

        Returns:
            Always True.
        """
        return True

    def run(
        self,
        operation: str,
        payload: dict[str, Any],
        user_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Raise a runtime error.

        Args:
            operation: The requested operation.
            payload: The request payload.
            user_context: Optional dict with ``user_id``, ``organization_id``,
                and ``role`` from the authenticated principal.

        Raises:
            RuntimeError: Always.
        """
        raise RuntimeError("agent blew up with a sensitive internal detail")


class SlowAgent(AgentAdapter):
    """An available agent that blocks for a fixed delay.

    Used to verify that blocking work does not stall the event loop.
    """

    def __init__(
        self,
        name: str = "slow",
        delay: float = 0.05,
        timeout_seconds: float = 0.01,
    ) -> None:
        """Initialize the slow agent.

        Args:
            name: The agent identifier.
            delay: Seconds to sleep inside the agent call.
            timeout_seconds: Adapter timeout. The default is deliberately
                shorter than ``delay`` so the timeout path is exercised.
        """
        self._name = name
        self._delay = delay
        self.timeout_seconds = timeout_seconds

    @property
    def name(self) -> str:
        """Return the agent identifier.

        Returns:
            The configured name.
        """
        return self._name

    def capabilities(self) -> list[str]:
        """Return the advertised operations.

        Returns:
            A single ``ping`` operation.
        """
        return ["ping"]

    def is_available(self) -> bool:
        """Report the agent as connected.

        Returns:
            Always True.
        """
        return True

    def run(
        self,
        operation: str,
        payload: dict[str, Any],
        user_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Sleep past the adapter timeout.

        Args:
            operation: The requested operation.
            payload: The request payload.
            user_context: Optional dict with ``user_id``, ``organization_id``,
                and ``role`` from the authenticated principal.

        Returns:
            A payload reporting the elapsed sleep. Normally unreachable because
            the adapter timeout fires first.
        """
        time.sleep(self._delay)
        return {"slept": self._delay}
