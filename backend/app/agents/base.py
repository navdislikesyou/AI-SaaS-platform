"""Agent abstraction shared by every agent adapter.

An :class:`AgentAdapter` is the integration boundary between the backend and a
future agent implementation. The backend only ever sees this interface, so a
real agent can be connected later without changing routes or the orchestrator.

Adapters are intentionally thin. They translate a wire request into whatever
the real agent expects, run it off the event loop, and return a plain dict.
"""

from __future__ import annotations

import abc
import asyncio
import logging
import threading
import time
import weakref
from typing import Any

import anyio

from app.core.exceptions import (
    AgentExecutionError,
    AgentTimeoutError,
    AgentUnavailableError,
    AppError,
    UnknownOperationError,
)

logger = logging.getLogger(__name__)

#: Bound on agent operations executing concurrently, used when no settings
#: value is supplied. Real agents are CPU-bound, so this is deliberately far
#: below anyio's default worker-thread limit of 40.
DEFAULT_MAX_AGENT_CONCURRENCY = 4

#: Limiters keyed by event loop. A limiter belongs to the loop that created
#: it, so one process running several loops (as the test suite does) needs one
#: limiter per loop rather than a single shared instance.
_limiters_by_loop: weakref.WeakKeyDictionary[Any, anyio.CapacityLimiter] = (
    weakref.WeakKeyDictionary()
)


def _record_activity(
    agent: str,
    operation: str,
    status: str,
    started: float,
) -> None:
    """Record one agent operation in the Activity History.

    Imported lazily so a failure in history storage can never break agent
    execution, and to keep the storage module out of the adapter import path.

    Args:
        agent: Agent name.
        operation: Operation name.
        status: ``completed`` or ``failed``.
        started: A :func:`time.perf_counter` reading taken before the call.
    """
    try:
        from app.services.activity_store import record_operation

        record_operation(
            agent=agent,
            operation=operation,
            status=status,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    except Exception:
        logger.warning("activity_record_failed agent=%s", agent, exc_info=True)


class AgentAdapter(abc.ABC):
    """Base class for all agent adapters.

    Attributes:
        timeout_seconds: Maximum time an operation may run before it is
            treated as a timeout.
        max_concurrency: Maximum number of agent operations allowed to run at
            once, across every adapter sharing this limit.
    """

    timeout_seconds: float = 120.0
    max_concurrency: int = DEFAULT_MAX_AGENT_CONCURRENCY

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
        except AppError:
            # Any domain error an adapter raised deliberately keeps its own
            # status code. ValidationFailedError in particular must stay a 422
            # rather than being rewrapped as a 502, which is why this catches
            # AppError rather than an explicit list of agent error types.
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

        The worker thread is deliberately *not* abandoned on timeout. Agent
        inference is CPU-bound and synchronous, so a thread cannot be killed
        from outside; abandoning it would leave it burning a core with nobody
        waiting on the result. Instead the thread runs to completion while the
        caller is released immediately by the cancel scope, and the concurrency
        slot is held by the abandoned call until the thread actually finishes.
        That way repeated timeouts cannot pile up unbounded background work.

        Args:
            operation: The operation name.
            payload: The request payload.

        Returns:
            The agent result as a plain dict.

        Raises:
            AgentExecutionError: If the agent returns a non-object result.
        """
        limiter = _limiter_for(self.max_concurrency)
        slot = _Slot(limiter, self.name, operation)
        started = time.perf_counter()

        await slot.acquire()
        try:
            with anyio.fail_after(self.timeout_seconds):
                # The thread pool limiter is deliberately not the slot limiter.
                # The slot already bounds how many agent threads can run, and
                # it stays held until a timed-out thread actually finishes, so
                # at most `max_concurrency` agent threads exist at any moment.
                # Borrowing from the same limiter here would deadlock: the slot
                # would hold every token while the worker waited for one.
                raw = await anyio.to_thread.run_sync(
                    slot.invoke,
                    self.run,
                    operation,
                    payload,
                    abandon_on_cancel=True,
                )
        except BaseException:
            # Exactly one history record per terminal outcome. Recording in the
            # failure branch means a failed or timed-out call is captured too,
            # and re-raising here cannot produce a second record.
            _record_activity(self.name, operation, "failed", started)
            raise
        finally:
            # Only reclaim the slot if the call never reached a worker thread.
            # A thread that outlived its timeout releases the slot itself, and
            # releasing here as well would hand the slot back while the thread
            # is still burning CPU, which is exactly the leak being prevented.
            slot.abandon_if_never_entered()

        _record_activity(self.name, operation, "completed", started)

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


class _Slot:
    """One unit of agent concurrency, released by whoever finishes last.

    A slot exists because a timed-out agent thread cannot be killed. The
    thread is abandoned only in the sense that nobody waits for its result;
    it keeps running, and it keeps holding its slot until it actually returns.
    That converts an unbounded pile of background CPU burn into a bounded one:
    once ``max_concurrency`` threads are stuck, further calls queue instead of
    spawning more work.
    """

    __slots__ = (
        "_agent",
        "_borrower",
        "_entered",
        "_limiter",
        "_lock",
        "_operation",
        "_released",
    )

    def __init__(
        self,
        limiter: anyio.CapacityLimiter,
        agent: str,
        operation: str,
    ) -> None:
        """Initialize the slot.

        Args:
            limiter: The shared concurrency limiter to borrow from.
            agent: Agent name, used for logging.
            operation: Operation name, used for logging.
        """
        self._limiter = limiter
        self._agent = agent
        self._operation = operation
        self._borrower = object()
        self._released = False
        self._entered = False
        self._lock = threading.Lock()

    async def acquire(self) -> None:
        """Wait for a free slot.

        Cancellation is handled by anyio: a cancelled waiter removes itself
        from the queue and never takes a token.

        Raises:
            TimeoutError: Never directly. Cancellation propagates.
        """
        logger.debug(
            "agent_slot_wait agent=%s operation=%s",
            self._agent,
            self._operation,
        )
        await self._limiter.acquire_on_behalf_of(self._borrower)

    def invoke(
        self,
        func: Any,
        operation: str,
        payload: dict[str, Any],
    ) -> Any:
        """Call the agent function, then release the slot from this thread.

        Args:
            func: The bound adapter ``run`` method.
            operation: The operation name.
            payload: The request payload.

        Returns:
            Whatever ``func`` returns.
        """
        with self._lock:
            self._entered = True

        try:
            return func(operation, payload)
        finally:
            self.release()

    def abandon_if_never_entered(self) -> None:
        """Release the slot when no worker thread ever picked the call up.

        A caller cancelled before handoff has nobody to return its token, so it
        must do it itself. Once a worker has entered, the worker owns the
        release and the caller must not touch it, or the bound would be lost
        precisely when it matters: on timeout.
        """
        with self._lock:
            entered = self._entered

        if not entered:
            self.release()

    def release(self) -> None:
        """Return the slot to the limiter, at most once.

        Safe to call from both the worker thread and the cancelled caller.
        """
        with self._lock:
            if self._released:
                return
            self._released = True

        self._limiter.release_on_behalf_of(self._borrower)
        logger.debug(
            "agent_slot_released agent=%s operation=%s",
            self._agent,
            self._operation,
        )


def _limiter_for(max_concurrency: int) -> anyio.CapacityLimiter:
    """Return the concurrency limiter for the running event loop.

    A limiter is bound to the event loop that created it, so one is kept per
    loop. Keying on the loop weakly lets the limiter be collected with it.

    Args:
        max_concurrency: Slot count for the returned limiter.

    Returns:
        The limiter for the current loop, created on first use.
    """
    loop = asyncio.get_running_loop()
    limiter = _limiters_by_loop.get(loop)
    if limiter is None:
        limiter = anyio.CapacityLimiter(max_concurrency)
        _limiters_by_loop[loop] = limiter
        logger.info("agent_limiter_created concurrency=%d", max_concurrency)
    return limiter


class PlaceholderAgentAdapter(AgentAdapter):
    """Adapter that is catalogued but not executable through this endpoint.

    Used when an agent either has no implementation, or has one that is reached
    through a different route. ``PerformanceAgentAdapter`` is the current case:
    the Performance Analyzer is fully implemented, but it runs as a background
    job under ``/api/v1/performance/jobs``, so it must not appear runnable here.

    Subclasses declare their name and advertised capabilities. Availability is
    derived from an explicit ``enabled`` flag, which suits this role because
    there is no construction step that could fail. Adapters backed by a real
    service derive availability from whether construction succeeded instead.
    """

    def __init__(self, enabled: bool = False) -> None:
        """Initialize the placeholder adapter.

        Args:
            enabled: Whether the catalog should present this agent as
                available. Defaults to False.
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
            Either a connected notice or a notice that the agent is catalogued
            but cannot be executed here.
        """
        if self._enabled:
            return f"{self.display_name} agent is connected."
        return (
            f"{self.display_name} agent is registered but not connected yet. "
            "It is not executable through this endpoint; override describe() if "
            "the agent is served by another route."
        )
