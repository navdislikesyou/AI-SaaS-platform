"""Performance Analyzer adapter.

The Performance Analyzer is a data analytics agent: dataset processing,
statistical analysis, KPI calculation, comparison, trend and pattern
identification, visualization, and natural-language insights. It is not an
ML agent, and this backend intentionally models no predictive or classification
behaviour. Its implementation is developed separately and is not present in
this repository.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.base import PlaceholderAgentAdapter

logger = logging.getLogger(__name__)


class PerformanceAgentAdapter(PlaceholderAgentAdapter):
    """Integration boundary for the data analytics agent.

    When the real agent arrives, override :meth:`run` to call it. Everything
    else in the backend stays unchanged.
    """

    AGENT_NAME = "performance"

    #: Operations the agent is expected to support once implemented.
    ADVERTISED_CAPABILITIES = [
        "load_dataset",
        "compute_kpis",
        "compare_periods",
        "analyze",
        "visualize",
    ]

    @property
    def name(self) -> str:
        """Return the agent identifier used in API requests.

        Returns:
            The string ``"performance"``.
        """
        return self.AGENT_NAME

    def capabilities(self) -> list[str]:
        """Return the operations this agent is expected to support.

        Returns:
            A copy of the advertised capability list.
        """
        return list(self.ADVERTISED_CAPABILITIES)

    def run(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Invoke the real Performance Analyzer.

        Args:
            operation: The requested operation.
            payload: The request payload.

        Raises:
            NotImplementedError: Always, until the agent is connected. The base
                class availability guard normally rejects the call first.
        """
        raise NotImplementedError("Performance Analyzer is not connected yet.")
