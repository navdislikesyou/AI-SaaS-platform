"""Agent abstraction shared by every agent adapter.

An :class:`AgentAdapter` is the integration boundary between the backend and a
future agent implementation. The backend only ever sees this interface, so a
real agent can be connected later without changing routes or the orchestrator.

Adapters are intentionally thin. They translate a wire request into whatever
the real agent expects, run it off the event loop, and return a plain dict.
"""

from __future__ import annotations

import abc
import logging
from typing import Any

import anyio

from app.core.exceptions import (
    AgentExecutionError,
    AgentTimeoutError,
    AgentUnavailableError,
    UnknownOperationError,
)

logger = logging.getLogger(__name__)


class AgentAdapter(abc.ABC):
    """Base class for all agent adapters.

    Attributes:
        timeout_seconds: Maximum time an operation may run before it is
            treated as a timeout.
    """

    timeout_seconds: float = 120.0

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Return the stable agent identifier used in API requests."""

    @property
    def display_name(self) -> str:
        """Return a human-readable agent name.

        Returns:
            A title-cased version of :attr:`name`.
        """
        return self.name.replace("_", " ").title()

    @abc.abstractmethod
    def capabilities(self) -> list[str]:
        """Return the high-level operations this agent advertises.

        Returns:
            Operation names the agent is expected to support. These describe
            intent only; no behaviour is implemented behind them yet.
        """

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Report whether a real implementation is connected.

        Returns:
            True when the adapter can execute operations.
        """

    async def execute(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute one operation against the underlying agent.

        The default implementation enforces availability, checks that the
        operation is advertised, and runs :meth:`run` off the event loop.
        Subclasses normally override :meth:`run` rather than this method.

        Args:
            operation: The operation name requested by the client.
            payload: Arbitrary JSON object supplied by the client.

        Returns:
            A JSON-serializable result object.

        Raises:
            AgentUnavailableError: If no real agent is connected.
            UnknownOperationError: If the operation is not advertised.
            AgentTimeoutError: If execution exceeds ``timeout_seconds``.
            AgentExecutionError: If the agent raised an unexpected error.
        """
        if not self.is_available():
            raise AgentUnavailableError(
                f"Agent '{self.name}' is registered but its implementation is "
                f"not connected yet.",
                details={
                    "agent": self.name,
                    "status": "not_implemented",
                    "capabilities": self.capabilities(),
                },
            )

        if operation not in self.capabilities():
            raise UnknownOperationError(
                f"Agent '{self.name}' does not support operation '{operation}'.",
                details={
                    "agent": self.name,
                    "operation": operation,
                    "supported": self.capabilities(),
                },
            )

        logger.info("agent_execute_start agent=%s operation=%s", self.name, operation)
        try:
            result = await self._invoke(operation, payload)
        except TimeoutError:
            logger.warning("agent_execute_timeout agent=%s operation=%s", self.name, operation)
            raise AgentTimeoutError(
                f"Agent '{self.name}' exceeded {self.timeout_seconds:g}s.",
                details={"agent": self.name, "operation": operation},
            ) from None
        except (AgentUnavailableError, AgentExecutionError, UnknownOperationError):
            raise
        except Exception as exc:
            logger.exception("agent_execute_failed agent=%s operation=%s", self.name, operation)
            raise AgentExecutionError(
                f"Agent '{self.name}' failed while handling '{operation}'.",
                details={"agent": self.name, "operation": operation},
            ) from exc

        logger.info("agent_execute_ok agent=%s operation=%s", self.name, operation)
        return result

    async def _invoke(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Run :meth:`run` in a worker thread with a timeout.

        Args:
            operation: The operation name.
            payload: The request payload.

        Returns:
            The agent result as a plain dict.

        Raises:
            AgentExecutionError: If the agent returns a non-object result.
        """
        with anyio.fail_after(self.timeout_seconds):
            raw = await anyio.to_thread.run_sync(
                self.run, operation, payload, abandon_on_cancel=True
            )
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise AgentExecutionError(
                f"Agent '{self.name}' returned {type(raw).__name__}; a JSON object "
                "was expected.",
                details={"agent": self.name, "operation": operation},
            )
        return raw

    def run(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Invoke the real agent synchronously.

        This is the integration seam. Once a real agent implementation exists,
        replace this body with a call into it. It runs in a worker thread, so
        blocking calls are acceptable here.

        Args:
            operation: The operation name.
            payload: The request payload.

        Returns:
            The agent result as a plain dict.
        """
        raise NotImplementedError(f"{type(self).__name__} has no agent implementation connected.")


class PlaceholderAgentAdapter(AgentAdapter):
    """Adapter for an agent whose implementation is not available yet.

    Subclasses declare their name and advertised capabilities. Availability is
    derived from an explicit ``enabled`` flag so that registering an adapter
    never implies a working agent behind it.
    """

    def __init__(self, enabled: bool = False) -> None:
        """Initialize the placeholder adapter.

        Args:
            enabled: Whether a real implementation is connected. Defaults to
                False because no agent code exists in the repository yet.
        """
        self._enabled = enabled

    def is_available(self) -> bool:
        """Report whether the real agent is connected.

        Returns:
            The ``enabled`` flag this adapter was constructed with.
        """
        return self._enabled

    def describe(self) -> str:
        """Return a short human-readable status string.

        Returns:
            Either a not-connected notice or a connected notice.
        """
        if self._enabled:
            return f"{self.display_name} agent is connected."
        return (
            f"{self.display_name} agent is registered but not connected yet. "
            "Its implementation is developed separately and will be connected "
            "through this adapter."
        )
