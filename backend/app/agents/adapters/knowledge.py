"""Knowledge Agent adapter.

The Knowledge Agent is a retrieval-augmented generation (RAG) system for
document question answering. It is connected here through
:class:`knowledge_agent.service.KnowledgeService`, which owns the embedding
model, the vector store, and the LLM client.

All real-agent coupling stays in this module. Nothing here reaches into the
service's internals; the service is only called through its public dict-in,
dict-out methods.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.agents.base import AgentAdapter
from app.core.exceptions import (
    AgentUnavailableError,
    ForbiddenError,
    ValidationFailedError,
)

logger = logging.getLogger(__name__)

#: Operations the connected service actually implements. Anything not listed
#: here is rejected with a 404 rather than advertised and then failing.
ADVERTISED_CAPABILITIES = [
    "ingest_document",
    "query",
]

#: Required payload keys per operation, keyed by operation name.
REQUIRED_KEYS = {
    "ingest_document": ("file_path",),
    "query": ("question",),
}


class KnowledgeAgentAdapter(AgentAdapter):
    """Integration boundary for the RAG document question answering agent.

    Availability reflects whether the service was constructed successfully,
    not whether a configuration flag was set. Construction is attempted once in
    :meth:`__init__`; a failure is logged and the adapter reports itself
    unavailable, so a missing model or an unreachable Ollama server produces a
    clean 503 instead of crashing at boot.
    """

    AGENT_NAME = "knowledge"

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
            logger.info("knowledge_adapter_disabled")
            return

        self._connect()

    def _apply_settings(self, settings: Any | None) -> None:
        """Copy timeout and concurrency limits from settings.

        Args:
            settings: Application settings, or None to keep the class defaults.
        """
        if settings is None:
            return
        self.timeout_seconds = settings.knowledge_agent_timeout_seconds
        self.max_concurrency = settings.agent_max_concurrency

    def _connect(self) -> None:
        """Construct the service, degrading to unavailable on failure.

        This runs at startup and loads a model plus opens a Chroma directory,
        so any failure here must be survivable: the API has to keep serving
        catalog and health endpoints even when an agent is broken.

        No Ollama liveness probe is performed, here or in
        :meth:`is_available`. The agent catalog calls ``is_available`` for
        every agent on every request, so a network round-trip there would add
        latency to every call and could fail for reasons unrelated to this
        agent. A dead Ollama server surfaces as a 502 on execute instead.
        """
        from app.core.config import get_settings

        settings = self._settings or get_settings()

        try:
            # Imported inside the guard on purpose. The agent packages need
            # heavy optional dependencies (torch, langchain, chromadb) that are
            # absent in an API-only deployment, so the import itself can fail.
            # An ImportError must degrade to unavailable rather than take the
            # process down at startup.
            from knowledge_agent.service import KnowledgeService

            self._service = KnowledgeService(settings)
        except Exception:
            logger.exception("knowledge_adapter_connect_failed")
            self._enabled = False
            return

        self._apply_settings(settings)
        self._enabled = True

        logger.info("knowledge_adapter_connected capabilities=%s", self.capabilities())

    @property
    def name(self) -> str:
        """Return the agent identifier used in API requests.

        Returns:
            The string ``"knowledge"``.
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
        """Validate the payload, authorize the caller, then call the service.

        Every operation here reads or writes documents that belong to one
        organisation, so the caller must present an organisation. Without one
        the retrieval path cannot be scoped and the answer would be drawn
        from every tenant's documents at once, so the operation is refused
        rather than answered from unscoped data.

        Args:
            operation: One of :data:`ADVERTISED_CAPABILITIES`.
            payload: Operation-specific input.
            user_context: Optional dict with ``user_id``, ``organization_id``,
                and ``role`` from the authenticated principal.

        Returns:
            The service result as a plain dict.

        Raises:
            ValidationFailedError: If a required key is missing or blank.
                Raising the domain error here is what makes a bad request a 422
                instead of a 502.
            ForbiddenError: If the caller has no organisation, so the
                documents it would read cannot be scoped (403).
            AgentUnavailableError: If no service is connected.
        """
        service = self._require_service()
        cleaned = validate_payload(operation, payload)

        _require_organization(operation, user_context)

        if operation == "ingest_document":
            return service.ingest(cleaned["file_path"], user_context=user_context)

        result = service.query(cleaned["question"], user_context=user_context)

        return _with_public_sources(result)

    def _require_service(self) -> Any:
        """Return the connected service.

        Returns:
            The KnowledgeService instance.

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


def _with_public_sources(result: Any) -> dict[str, Any]:
    """Replace absolute source paths with bare filenames in a query result.

    ``query`` returns one ``source`` per citation, and the loader records
    whatever path it was handed. For an uploaded document that is the absolute
    path of the generated stored file, which must not reach a browser: it leaks
    the server's directory layout and shows the user a UUID instead of the
    document they uploaded.

    Only the display string changes. Retrieval, chunk identity, and citation
    order are untouched, so existing behaviour is preserved. A source that is
    already relative, such as one ingested by server path through
    ``/agents/execute``, is left exactly as it was.

    Args:
        result: The raw service result.

    Returns:
        A copy of the result whose citation sources are display-safe. A result
        without sources is returned unchanged.
    """
    if not isinstance(result, dict):
        return result

    sources = result.get("sources")

    if not isinstance(sources, list):
        return result

    sanitized = [dict(entry) if isinstance(entry, dict) else entry for entry in sources]

    for entry in sanitized:
        if not isinstance(entry, dict):
            continue

        source = entry.get("source")

        if isinstance(source, str) and Path(source).is_absolute():
            entry["source"] = Path(source).name

    return {**result, "sources": sanitized}


def _require_organization(
    operation: str,
    user_context: dict[str, Any] | None,
) -> None:
    """Refuse an operation that cannot be scoped to one organisation.

    The knowledge base is shared: every tenant's documents sit in one vector
    store. A query without an organisation would retrieve from all of them, and
    an ingest without one would write a document no organisation owns and can
    therefore read. Both are refused instead of being answered from unscoped
    data.

    Args:
        operation: The requested operation.
        user_context: The principal's context, or None for an anonymous caller.

    Raises:
        ForbiddenError: If the caller presents no organisation (403).
    """
    organization_id = None
    if user_context:
        organization_id = user_context.get("organization_id")

    if organization_id is not None:
        return

    raise ForbiddenError(
        "Knowledge operations require an authenticated organisation.",
        details={
            "agent": KnowledgeAgentAdapter.AGENT_NAME,
            "operation": operation,
            "reason": "missing_organization",
        },
    )


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
                "agent": KnowledgeAgentAdapter.AGENT_NAME,
                "operation": operation,
                "missing": missing,
            },
        )

    return payload
