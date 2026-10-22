"""Automation Agent adapter.

The Automation Agent interprets natural-language productivity requests and
drafts the actions required to fulfil them. It is connected here through
:class:`automation_agent.service.AutomationService`.

The connected agent drafts. It does not send email, create calendar events, or
perform any other external side effect; doing so needs a confirmation step
that does not exist yet. The capability list reflects that: one drafting
operation, not three.

A draft may name an uploaded employee directory through the optional
``directory_id`` payload key. The adapter resolves that id to a list of records
and passes it to the service for the length of one request. Omitting the key
uses the packaged directory exactly as before. The selection is resolved here
rather than in the agent so that no shared agent state is ever swapped, and so
that an unusable id is an error rather than a silent fall-back to the default.

All real-agent coupling stays in this module. Nothing here reaches into the
service's internals.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.base import AgentAdapter
from app.core.exceptions import (
    AgentUnavailableError,
    DirectoryNotFoundError,
    ForbiddenError,
    ValidationFailedError,
)

logger = logging.getLogger(__name__)

#: Operations the connected service actually implements. The previously
#: advertised ``propose_action`` and ``execute_action`` have no implementation
#: behind them; they were declared ahead of the code and would have 404'd at
#: runtime. Declaring an operation that does not work is worse than not
#: declaring it, so the list was trimmed to what exists.
ADVERTISED_CAPABILITIES = [
    "draft_action",
]

#: Required payload keys per operation, keyed by operation name. ``directory_id``
#: is deliberately absent: it selects an uploaded directory and is optional, so
#: the packaged directory stays the default.
REQUIRED_KEYS = {
    "draft_action": ("instruction",),
}

#: Recipient fields that may reach a client. An uploaded directory can carry any
#: columns the user supplied, so the outgoing records are reduced to exactly
#: what the drafting UI renders. Nothing else is echoed back.
_PUBLIC_RECIPIENT_FIELDS = ("name", "email")


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
        directory_service: Any | None = None,
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
            directory_service: Resolves an uploaded directory id to its records.
                Defaults to the process-wide service, resolved on first use so
                that an instance with no uploads never creates the upload
                directory.
        """
        self._enabled = False
        self._service: Any | None = None
        self._settings = settings
        self._directory_service = directory_service

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

    def run(
        self,
        operation: str,
        payload: dict[str, Any],
        user_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Validate the payload, then call the service.

        An uploaded directory is resolved here and handed to the service for this
        one call. No shared state is mutated, so two concurrent drafts using two
        different directories cannot see each other's recipients.

        Args:
            operation: One of :data:`ADVERTISED_CAPABILITIES`.
            payload: Operation-specific input.
            user_context: Optional dict with ``user_id``, ``organization_id``,
                and ``role`` from the authenticated principal.

        Returns:
            The service result, with recipients reduced to the public fields and
            a ``directory`` block naming the roster that was used.

        Raises:
            ValidationFailedError: If a required key is missing or blank (422).
            ForbiddenError: If the caller has no organisation, so a directory
                cannot be scoped to it (403).
            DirectoryNotFoundError: If ``directory_id`` is unknown, its file
                is gone, or it belongs to another organisation (404).
            AgentUnavailableError: If no service is connected (503).
        """
        service = self._require_service()
        cleaned = validate_payload(operation, payload)

        directory_id = _directory_id(cleaned)

        if not directory_id:
            result = service.execute(cleaned["instruction"], user_context=user_context)

            return _public_result(result, None)

        self._require_owned_directory(directory_id, user_context)

        employees = self._require_directory_service().load_records(directory_id)

        logger.info(
            "automation_draft_directory id=%s employees=%d",
            directory_id,
            len(employees),
        )

        result = service.execute(cleaned["instruction"], employees, user_context=user_context)

        return _public_result(result, directory_id)

    def _require_owned_directory(
        self,
        directory_id: str,
        user_context: dict[str, Any] | None,
    ) -> None:
        """Refuse a directory that belongs to another organisation.

        The directory id arrives from the client, so it can be substituted with
        one belonging to a different tenant. The check happens before the
        roster is read, and a directory owned by another organisation is
        reported as missing so the response does not confirm that it exists.

        Args:
            directory_id: The directory the client asked for.
            user_context: The principal's context, or None for an anonymous
                caller.

        Raises:
            ForbiddenError: If the caller presents no organisation (403).
            DirectoryNotFoundError: If the directory is unknown or belongs to
                another organisation (404).
        """
        from app.services.employee_directory import find_directory_row, get_manifest

        organization_id = None
        if user_context:
            organization_id = user_context.get("organization_id")

        if organization_id is None:
            raise ForbiddenError(
                "Drafting against an uploaded directory requires an "
                "authenticated organisation.",
                details={
                    "agent": AutomationAgentAdapter.AGENT_NAME,
                    "reason": "missing_organization",
                },
            )

        row = find_directory_row(directory_id, get_manifest())

        if row is None or row.get("organization_id") != organization_id:
            raise DirectoryNotFoundError(
                f"Employee directory '{directory_id}' was not found.",
                details={"directory_id": directory_id},
            )

    def _require_directory_service(self) -> Any:
        """Return the service that resolves uploaded directory ids.

        Returns:
            The employee directory service.
        """
        if self._directory_service is None:
            from app.services.employee_directory import get_directory_service

            self._directory_service = get_directory_service()

        return self._directory_service

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


def _directory_id(payload: dict[str, Any]) -> str:
    """Extract the requested employee directory id from a payload.

    An absent, null, or blank value means the caller wants the packaged default,
    which is how this feature stays opt-in.

    Args:
        payload: The validated request payload.

    Returns:
        The directory id, or an empty string when none was requested.
    """
    return str(payload.get("directory_id") or "").strip()


def _public_result(result: Any, directory_id: str | None) -> dict[str, Any]:
    """Reduce a service result to the fields a client may see.

    Two things happen here. Recipients are rebuilt from the public field list,
    because a directory upload may carry any columns its uploader supplied and
    the raw records would otherwise travel back to the browser untouched. And the
    roster that produced the draft is named, so a user who selected a directory
    can confirm it was the one used.

    Args:
        result: The raw service result.
        directory_id: The selected directory id, or None when the packaged
            directory was used.

    Returns:
        A copy of the result with public recipients and a ``directory`` block.
        A result that is not a dict is returned unchanged.
    """
    if not isinstance(result, dict):
        return result

    return {
        **result,
        "recipients": _public_recipients(result.get("recipients")),
        "directory": {
            "directory_id": directory_id,
            "source": "uploaded" if directory_id else "default",
            "employee_count": result.get("employee_count"),
        },
    }


def _public_recipients(recipients: Any) -> list[dict[str, str]]:
    """Keep only the name and email of each resolved recipient.

    Args:
        recipients: The matched employee records from the agent.

    Returns:
        One mapping per recipient, holding only the public fields and only when
        they are strings. Anything else is skipped rather than passed through.
    """
    if not isinstance(recipients, list):
        return []

    public: list[dict[str, str]] = []

    for person in recipients:
        if not isinstance(person, dict):
            continue

        entry = {
            field: person[field]
            for field in _PUBLIC_RECIPIENT_FIELDS
            if isinstance(person.get(field), str)
        }

        if entry:
            public.append(entry)

    return public
