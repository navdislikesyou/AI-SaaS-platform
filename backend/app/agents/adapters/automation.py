"""Automation Agent adapter.

The Automation Agent interprets natural-language productivity requests and
drafts the actions required to fulfil them. It is connected here through
:class:`automation_agent.service.AutomationService`.

The connected agent drafts. It does not send email, create calendar events, or
perform any other external side effect; doing so needs a confirmation step
that does not exist yet. The capability list reflects that: one drafting
operation, not three.

All real-agent coupling stays in this module. Nothing here reaches into the
service's internals.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.base import AgentAdapter
from app.core.exceptions import AgentUnavailableError, ValidationFailedError

logger = logging.getLogger(__name__)

#: Operations the connected service actually implements. The previously
#: advertised ``propose_action`` and ``execute_action`` have no implementation
#: behind them; they were declared ahead of the code and would have 404'd at
#: runtime. Declaring an operation that does not work is worse than not
#: declaring it, so the list was trimmed to what exists.
ADVERTISED_CAPABILITIES = [
    "draft_action",
]

#: Required payload keys per operation, keyed by operation name.
REQUIRED_KEYS = {
    "draft_action": ("instruction",),
}


class AutomationAgentAdapter(AgentAdapter):
    """Integration boundary for the automation request agent.

    Availability reflects whether the service was constructed successfully,
    not whether a configuration flag was set. Construction is attempted once in
    :meth:`__init__`; a failure is logged and the adapter reports itself
    unavailable rather than crashing at boot.
    """

    AGENT_NAME = "automation"

    def __init__(
        self,
        enabled: bool = False,
        settings: Any | None = None,
        service: Any | None = None,
    ) -> None:
        """Attempt to build the service when the agent is enabled.

        Args:
            enabled: Whether the operator opted in to this agent. When false no
                service is constructed, so a disabled agent costs nothing.
            settings: Application settings. Defaults to the cached process
                settings when a service is built.
            service: A pre-built service. Supplied by tests and by callers that
                manage construction themselves; when given, no attempt is made
                to import or connect the real agent.
        """
        self._enabled = False
        self._service: Any | None = None
        self._settings = settings

        if service is not None:
            self._service = service
            self._enabled = True
            self._apply_settings(settings)
            return

        if not enabled:
            logger.info("automation_adapter_disabled")
            return

        self._connect()

    def _apply_settings(self, settings: Any | None) -> None:
        """Copy timeout and concurrency limits from settings.

        Args:
            settings: Application settings, or None to keep the class defaults.
        """
        if settings is None:
            return
        self.timeout_seconds = settings.automation_agent_timeout_seconds
        self.max_concurrency = settings.agent_max_concurrency

    def _connect(self) -> None:
        """Construct the service, degrading to unavailable on failure.

        No Ollama liveness probe is performed, here or in
        :meth:`is_available`. The agent catalog calls ``is_available`` for
        every agent on every request, so a network round-trip there would add
        latency to every call and could fail for reasons unrelated to this
        agent.
        """
        from app.core.config import get_settings

        settings = self._settings or get_settings()

        try:
            # Imported inside the guard on purpose: an API-only deployment may
            # not have the agent's optional dependencies installed, and an
            # ImportError must degrade to unavailable rather than crash boot.
            from automation_agent.service import AutomationService

            self._service = AutomationService(settings)
        except Exception:
            logger.exception("automation_adapter_connect_failed")
            self._enabled = False
            return

        self._apply_settings(settings)
        self._enabled = True

        logger.info("automation_adapter_connected capabilities=%s", self.capabilities())

    @property
    def name(self) -> str:
        """Return the agent identifier used in API requests.

        Returns:
            The string ``"automation"``.
        """
        return self.AGENT_NAME

    def capabilities(self) -> list[str]:
        """Return the operations this agent supports.

        Returns:
            A copy of the advertised capability list.
        """
        return list(ADVERTISED_CAPABILITIES)

    def is_available(self) -> bool:
        """Report whether the service is present.

        Returns:
            True when a service instance is held, False otherwise.
        """
        return self._enabled

    def describe(self) -> str:
        """Return a short human-readable status string.

        Returns:
            A connected or not-connected notice.
        """
        if self._enabled:
            return f"{self.display_name} agent is connected."
        return (
            f"{self.display_name} agent is registered but not connected. Its "
            "implementation could not be initialized; check that the agent "
            "dependencies are installed and that configuration is correct."
        )

    def run(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate the payload, then call the service.

        Args:
            operation: One of :data:`ADVERTISED_CAPABILITIES`.
            payload: Operation-specific input.

        Returns:
            The service result as a plain dict.

        Raises:
            ValidationFailedError: If a required key is missing or blank.
            AgentUnavailableError: If no service is connected.
        """
        service = self._require_service()
        cleaned = validate_payload(operation, payload)

        return service.execute(cleaned["instruction"])

    def _require_service(self) -> Any:
        """Return the connected service.

        Returns:
            The AutomationService instance.

        Raises:
            AgentUnavailableError: If construction failed earlier. The base
                class rejects the call before this point during normal
                dispatch; the check keeps a direct ``run`` call honest.
        """
        if self._service is None:
            raise AgentUnavailableError(
                f"Agent '{self.name}' has no connected implementation.",
                details={"agent": self.name, "status": "not_initialized"},
            )
        return self._service


def validate_payload(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Check that a payload carries the keys an operation requires.

    ``payload`` is an arbitrary JSON object at the API boundary, so
    operation-specific input rules have to be enforced at the adapter. Doing it
    here rather than in the schema keeps one schema for every agent while still
    returning 422 for bad input instead of letting the agent fail and surface
    as 502.

    Args:
        operation: The requested operation.
        payload: The raw request payload.

    Returns:
        The validated payload, unchanged.

    Raises:
        ValidationFailedError: If a required key is missing or blank.
    """
    required = REQUIRED_KEYS.get(operation, ())

    missing = [key for key in required if not str(payload.get(key, "")).strip()]

    if missing:
        raise ValidationFailedError(
            f"Operation '{operation}' requires: {', '.join(missing)}.",
            details={
                "agent": AutomationAgentAdapter.AGENT_NAME,
                "operation": operation,
                "missing": missing,
            },
        )

    return payload
