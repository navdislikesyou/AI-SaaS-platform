"""Performance Analyzer catalog entry.

The Performance Analyzer is a data analytics agent: dataset processing,
statistical analysis, KPI calculation, comparison, trend and pattern
identification, visualization, and natural-language insights. It is not an
ML agent, and this backend intentionally models no predictive or classification
behaviour.

Its implementation exists and works, but it is deliberately not served through
``POST /api/v1/agents/execute``. Analysis over a real dataset is CPU-bound and
slow enough that holding a request open for it is the wrong shape. It runs as a
background job instead:

    POST /api/v1/performance/jobs
    GET  /api/v1/performance/jobs/{job_id}

So this adapter exists only to keep the agent visible in ``GET /agents``. It
advertises no capabilities, because each one would otherwise appear offered and
then fail: those operations live behind the job API, where they actually run. It
reports unavailable for the same reason.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.base import PlaceholderAgentAdapter

logger = logging.getLogger(__name__)


class PerformanceAgentAdapter(PlaceholderAgentAdapter):
    """Catalog entry for the data analytics agent.

    Not an execution path. Capabilities are empty and availability is false, so
    the catalog cannot imply the agent is reachable through
    ``/agents/execute``. Its real interface is the job API under
    ``/api/v1/performance/jobs``.
    """

    AGENT_NAME = "performance"

    #: Intentionally empty. These operations run through the job API rather than
    #: the generic agent endpoint, so advertising them here would be a promise
    #: the catalog cannot keep.
    ADVERTISED_CAPABILITIES: list[str] = []

    @property
    def name(self) -> str:
        """Return the agent identifier used in API requests.

        Returns:
            The string ``"performance"``.
        """
        return self.AGENT_NAME

    def capabilities(self) -> list[str]:
        """Return the operations this agent advertises through this endpoint.

        Returns:
            An empty list. The agent's operations are job-based and are not
            reachable through ``/agents/execute``.
        """
        return list(self.ADVERTISED_CAPABILITIES)

    def describe(self) -> str:
        """Return a status string pointing clients at the job API.

        Returns:
            A notice explaining where this agent is actually served.
        """
        return (
            f"{self.display_name} agent is served as background jobs at "
            "/api/v1/performance/jobs, not through this endpoint."
        )

    def run(
        self,
        operation: str,
        payload: dict[str, Any],
        user_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Refuse synchronous execution.

        Args:
            operation: The requested operation. Always rejected.
            payload: The request payload.
            user_context: Optional dict with ``user_id``, ``organization_id``,
                and ``role`` from the authenticated principal.

        Raises:
            NotImplementedError: Always. The base class availability guard
                rejects the call before this point during normal dispatch; the
                guard exists for a direct ``run`` call.
        """
        raise NotImplementedError(
            "The Performance Analyzer runs as a background job. "
            "Use POST /api/v1/performance/jobs."
        )
