"""Automation Agent adapter.

The Automation Agent interprets natural-language productivity requests and
drafts the actions required to fulfil them. It does not yet perform external
side effects such as sending email or creating calendar events; a confirmation
step is expected before any such action executes. Its implementation is
developed separately and is not present in this repository.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.base import PlaceholderAgentAdapter

logger = logging.getLogger(__name__)


class AutomationAgentAdapter(PlaceholderAgentAdapter):
    """Integration boundary for the automation request agent.

    When the real agent arrives, override :meth:`run` to call it. Any
    side-effecting operation should be modelled as a proposal that is
    confirmed by the user before execution.
    """

    AGENT_NAME = "automation"

    #: Operations the agent is expected to support once implemented.
    ADVERTISED_CAPABILITIES = [
        "draft_action",
        "propose_action",
        "execute_action",
    ]

    @property
    def name(self) -> str:
        """Return the agent identifier used in API requests.

        Returns:
            The string ``"automation"``.
        """
        return self.AGENT_NAME

    def capabilities(self) -> list[str]:
        """Return the operations this agent is expected to support.

        Returns:
            A copy of the advertised capability list.
        """
        return list(self.ADVERTISED_CAPABILITIES)

    def run(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Invoke the real Automation Agent.

        Args:
            operation: The requested operation.
            payload: The request payload.

        Raises:
            NotImplementedError: Always, until the agent is connected. The base
                class availability guard normally rejects the call first.
        """
        raise NotImplementedError("Automation Agent is not connected yet.")
