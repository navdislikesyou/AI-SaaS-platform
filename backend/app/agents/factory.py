"""Construction of the default agent registry.

Keeps adapter wiring in one place so startup code and tests build the same
registry shape. Settings are passed through so each adapter can derive its
availability and execution limits from configuration rather than hardcoding
them.
"""

from __future__ import annotations

from app.agents.adapters.automation import AutomationAgentAdapter
from app.agents.adapters.knowledge import KnowledgeAgentAdapter
from app.agents.adapters.performance import PerformanceAgentAdapter
from app.agents.base import AgentAdapter
from app.agents.registry import AgentRegistry
from app.core.config import Settings


def build_registry(settings: Settings) -> AgentRegistry:
    """Create a registry populated with every known agent adapter.

    All agents register even when their implementations are missing, so the
    catalog endpoint reflects the full platform surface and returns a clean
    503 on execution rather than a 404.

    Adapters for the Knowledge and Automation agents attempt to connect during
    construction. A connection failure is logged and degrades that adapter to
    unavailable; it never propagates, so a broken agent cannot stop the API
    from starting.

    Args:
        settings: Application settings.

    Returns:
        A registry containing all configured adapters.
    """
    registry = AgentRegistry()
    for adapter in default_adapters(settings):
        registry.register(adapter)
    return registry


def default_adapters(settings: Settings) -> list[AgentAdapter]:
    """Instantiate the adapter for each agent on the platform.

    Args:
        settings: Application settings.

    Returns:
        Adapters for the Knowledge, Automation, and Performance agents.
    """
    return [
        KnowledgeAgentAdapter(
            enabled=settings.knowledge_agent_enabled,
            settings=settings,
        ),
        AutomationAgentAdapter(
            enabled=settings.automation_agent_enabled,
            settings=settings,
        ),
        PerformanceAgentAdapter(enabled=settings.performance_agent_enabled),
    ]
