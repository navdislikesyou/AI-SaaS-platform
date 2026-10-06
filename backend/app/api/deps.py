"""Shared FastAPI dependencies.

Provides singletons for settings, the agent registry, the orchestrator, and the
performance job manager. Auth is intentionally absent; this is the seam where
an authentication dependency will be added later so that individual routes do
not need to change.
"""

from __future__ import annotations

from app.agents.registry import AgentRegistry
from app.core.config import Settings, get_settings
from app.services.job_manager import JobManager
from app.services.orchestrator import Orchestrator

_registry: AgentRegistry | None = None
_orchestrator: Orchestrator | None = None
_job_manager: JobManager | None = None


def get_settings_dep() -> Settings:
    """Return application settings.

    Returns:
        The cached settings instance.
    """
    return get_settings()


def get_registry() -> AgentRegistry:
    """Return the process-wide agent registry.

    Returns:
        The registry built during application startup.
    """
    if _registry is None:
        raise RuntimeError(
            "Agent registry is not initialized. Call init_registry() during startup."
        )
    return _registry


def get_orchestrator() -> Orchestrator:
    """Return the process-wide orchestrator.

    Returns:
        The orchestrator built during application startup.
    """
    if _orchestrator is None:
        raise RuntimeError(
            "Orchestrator is not initialized. Call init_orchestrator() during startup."
        )
    return _orchestrator


def init_registry(registry: AgentRegistry) -> None:
    """Install the process-wide agent registry.

    Args:
        registry: The registry to share across requests.
    """
    global _registry
    _registry = registry


def init_orchestrator(orchestrator: Orchestrator) -> None:
    """Install the process-wide orchestrator.

    Args:
        orchestrator: The orchestrator to share across requests.
    """
    global _orchestrator
    _orchestrator = orchestrator


def get_job_manager() -> JobManager:
    """Return the process-wide performance job manager.

    Created on first use rather than during startup because it holds no async
    resources: job execution uses detached tasks created per submission.

    Returns:
        The shared job manager.
    """
    global _job_manager
    if _job_manager is None:
        _job_manager = JobManager()
    return _job_manager


def init_job_manager(manager: JobManager) -> None:
    """Install the process-wide performance job manager.

    Args:
        manager: The job manager to share across requests.
    """
    global _job_manager
    _job_manager = manager


def reset_state() -> None:
    """Clear the shared singletons. Intended for test isolation."""
    global _registry, _orchestrator, _job_manager
    _registry = None
    _orchestrator = None
    _job_manager = None
