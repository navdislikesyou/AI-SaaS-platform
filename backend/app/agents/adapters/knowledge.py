"""Knowledge Agent adapter.

The Knowledge Agent is a retrieval-augmented generation (RAG) system for
document question answering. Its implementation is developed separately and
is not present in this repository, so this adapter advertises the intended
capabilities and reports itself unavailable.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.base import PlaceholderAgentAdapter

logger = logging.getLogger(__name__)


class KnowledgeAgentAdapter(PlaceholderAgentAdapter):
    """Integration boundary for the RAG document question answering agent.

    When the real agent arrives, override :meth:`run` to call it. Everything
    else in the backend stays unchanged.
    """

    AGENT_NAME = "knowledge"

    #: Operations the agent is expected to support once implemented.
    ADVERTISED_CAPABILITIES = [
        "ingest_document",
        "list_documents",
        "delete_document",
        "query",
    ]

    @property
    def name(self) -> str:
        """Return the agent identifier used in API requests.

        Returns:
            The string ``"knowledge"``.
        """
        return self.AGENT_NAME

    def capabilities(self) -> list[str]:
        """Return the operations this agent is expected to support.

        Returns:
            A copy of the advertised capability list.
        """
        return list(self.ADVERTISED_CAPABILITIES)

    def run(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Invoke the real Knowledge Agent.

        Args:
            operation: The requested operation.
            payload: The request payload.

        Raises:
            NotImplementedError: Always, until the agent is connected. The base
                class availability guard normally rejects the call first.
        """
        raise NotImplementedError("Knowledge Agent is not connected yet.")
