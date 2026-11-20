"""Employee Insights Agent adapter.

Integration boundary for the employee feedback sentiment analysis agent.
The agent reads raw email text, attributes feedback sentences to employees,
classifies sentiment with RoBERTa, and persists results in the organization-
scoped feedback table.

Availability reflects whether the service was constructed successfully.
Construction is attempted once in :meth:`__init__`; a failure is logged and the
adapter reports itself unavailable rather than crashing at boot. The RoBERTa
model itself is loaded lazily by the service on first use, never at startup.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any

import anyio

from app.agents.base import AgentAdapter
from app.core.exceptions import (
    AgentUnavailableError,
    ForbiddenError,
    ValidationFailedError,
)

logger = logging.getLogger(__name__)

#: Operations the connected service actually implements.
ADVERTISED_CAPABILITIES = [
    "extract_feedback",
    "employee_summary",
    "sync_gmail",
]

#: Required payload keys per operation, keyed by operation name.
REQUIRED_KEYS = {
    "extract_feedback": ("email_text",),
    "employee_summary": ("employee_id",),
    #: ``query`` is optional and defaults to the configured Gmail query.
    "sync_gmail": ("max_results",),
}

#: Roles allowed to pull the organisation's shared mailbox. A sync reads mail
#: on behalf of everyone, so it is deliberately not an employee-level
#: operation, matching ``require_manager`` on the connection routes.
SYNC_ROLES = frozenset({"manager", "admin"})


class EmployeeInsightsAgentAdapter(AgentAdapter):
    """Integration boundary for the employee feedback insights agent.

    The RoBERTa sentiment model is initialized lazily by the service on first
    request, so construction never downloads a model and never blocks startup.
    """

    AGENT_NAME = "employee_insights"

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
            service: A pre-built service. Supplied by tests; when given, no
                attempt is made to import or connect the real agent.
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
            logger.info("employee_insights_adapter_disabled")
            return

        self._connect()

    def _apply_settings(self, settings: Any | None) -> None:
        """Copy timeout and concurrency limits from settings."""
        if settings is None:
            return
        self.timeout_seconds = getattr(settings, "employee_insights_agent_timeout_seconds", 180.0)
        self.max_concurrency = getattr(settings, "agent_max_concurrency", 4)

    def _connect(self) -> None:
        """Construct the service, degrading to unavailable on failure."""
        from app.core.config import get_settings

        settings = self._settings or get_settings()

        try:
            # Imported inside the guard on purpose: torch/transformers are
            # optional heavy dependencies. An ImportError must degrade to
            # unavailable rather than crash boot.
            from employee_insights.service import EmployeeInsightsService

            self._service = EmployeeInsightsService()
        except Exception:
            logger.exception("employee_insights_adapter_connect_failed")
            self._enabled = False
            return

        self._apply_settings(settings)
        self._enabled = True

        logger.info(
            "employee_insights_adapter_connected capabilities=%s",
            self.capabilities(),
        )

    @property
    def name(self) -> str:
        """Return the agent identifier used in API requests."""
        return self.AGENT_NAME

    def capabilities(self) -> list[str]:
        """Return the operations this agent supports."""
        return list(ADVERTISED_CAPABILITIES)

    def is_available(self) -> bool:
        """Report whether the service is present."""
        return self._enabled

    def describe(self) -> str:
        """Return a short human-readable status string."""
        if self._enabled:
            return f"{self.display_name} agent is connected."
        return (
            f"{self.display_name} agent is registered but not connected. Its "
            "implementation could not be initialized; check that the agent "
            "dependencies are installed and that configuration is correct."
        )

    def run(
        self,
        operation: str,
        payload: dict[str, Any],
        user_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Validate the payload, then call the service.

        Args:
            operation: One of :data:`ADVERTISED_CAPABILITIES`.
            payload: Operation-specific input.
            user_context: Optional dict with ``user_id``, ``organization_id``,
                and ``role`` from the authenticated principal.

        Returns:
            The service result as a plain dict.

        Raises:
            ValidationFailedError: If a required key is missing or blank (422).
            AgentUnavailableError: If no service is connected (503).
            ForbiddenError: If a sync is attempted without a manager or
                administrator role, or without an organisation (403).
        """
        service = self._require_service()
        cleaned = _validate_payload(operation, payload)

        organization_id = None
        if user_context:
            organization_id = user_context.get("organization_id")
        if not isinstance(organization_id, str) or not organization_id.strip():
            raise ForbiddenError(
                "Employee insights require an authenticated organisation.",
                details={"agent": self.name, "reason": "missing_organization"},
            )

        if operation == "extract_feedback":
            return _call_service(
                service.extract_feedback,
                cleaned["email_text"],
                organization_id=organization_id,
                source=cleaned.get("source", "manual"),
                source_message_id=cleaned.get("source_message_id"),
            )

        if operation == "employee_summary":
            return _call_service(
                service.get_employee_summary,
                organization_id=organization_id,
                employee_id=cleaned.get("employee_id", "all"),
            )

        if operation == "sync_gmail":
            # After payload validation so a bad request is still a 422 rather
            # than being masked behind the role check.
            _require_sync_role(user_context, self.name)
            return _call_service(
                service.sync_gmail,
                organization_id=organization_id,
                query=str(cleaned.get("query") or ""),
                max_results=_coerce_max_results(cleaned, self._settings),
            )

        raise AgentUnavailableError(
            f"Agent '{self.name}' operation '{operation}' is not implemented.",
            details={"agent": self.name, "operation": operation},
        )

    def _require_service(self) -> Any:
        """Return the connected service."""
        if self._service is None:
            raise AgentUnavailableError(
                f"Agent '{self.name}' has no connected implementation.",
                details={"agent": self.name, "status": "not_initialized"},
            )
        return self._service


def _validate_payload(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Check that a payload carries the keys an operation requires."""
    required = REQUIRED_KEYS.get(operation, ())

    missing = [key for key in required if not str(payload.get(key, "")).strip()]

    if missing:
        raise ValidationFailedError(
            f"Operation '{operation}' requires: {', '.join(missing)}.",
            details={
                "agent": EmployeeInsightsAgentAdapter.AGENT_NAME,
                "operation": operation,
                "missing": missing,
            },
        )

    return payload


def _require_sync_role(user_context: dict[str, Any] | None, agent_name: str) -> None:
    """Refuse a mailbox sync to anyone below manager level.

    Args:
        user_context: The authenticated principal, or None.
        agent_name: Agent identifier, reported back in the error details.

    Raises:
        ForbiddenError: If the caller's role is not manager or admin (403).
    """
    role = str((user_context or {}).get("role") or "").strip().lower()

    if role not in SYNC_ROLES:
        raise ForbiddenError(
            "Gmail synchronization requires a manager or administrator role.",
            details={
                "agent": agent_name,
                "operation": "sync_gmail",
                "reason": "insufficient_role",
            },
        )


def _coerce_max_results(payload: dict[str, Any], settings: Any | None) -> int:
    """Read ``max_results`` as a bounded whole number.

    Args:
        payload: The payload, already checked for a non-blank value.
        settings: Application settings supplying the ceiling. When None the
            cached process settings are read.

    Returns:
        The requested message count.

    Raises:
        ValidationFailedError: If the value is not an integer in 1..limit (422).
    """
    try:
        value = int(str(payload.get("max_results", "")).strip())
    except (TypeError, ValueError):
        value = 0

    if settings is None:
        from app.core.config import get_settings

        settings = get_settings()
    limit = int(getattr(settings, "gmail_sync_max_results", 500))

    if value < 1 or value > limit:
        raise ValidationFailedError(
            f"Operation 'sync_gmail' requires max_results to be a whole "
            f"number between 1 and {limit}.",
            details={
                "agent": EmployeeInsightsAgentAdapter.AGENT_NAME,
                "operation": "sync_gmail",
                "field": "max_results",
                "minimum": 1,
                "maximum": limit,
            },
        )

    return value


def _call_service(method: Any, *args: Any, **kwargs: Any) -> Any:
    """Run async service methods on the request loop and sync fakes directly."""
    if inspect.iscoroutinefunction(method):

        async def invoke() -> Any:
            return await method(*args, **kwargs)

        return anyio.from_thread.run(invoke)
    return method(*args, **kwargs)
