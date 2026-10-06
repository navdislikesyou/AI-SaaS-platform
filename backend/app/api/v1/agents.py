"""Agent catalog and generic execution endpoints.

These routes are generic on purpose. They know agent names and operations, but
nothing about how any agent works, so adding a fourth agent requires a new
adapter and registry entry rather than new endpoints.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status

from app.agents.base import AgentAdapter
from app.agents.registry import AgentRegistry
from app.api.deps import get_orchestrator, get_registry, get_settings_dep
from app.core.config import Settings
from app.core.logging_config import get_request_id
from app.schemas.agent import (
    AgentExecuteRequest,
    AgentExecuteResponse,
    AgentInfo,
    AgentListResponse,
)
from app.schemas.common import APIResponse
from app.services.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])

AGENT_DESCRIPTIONS: dict[str, str] = {
    "knowledge": (
        "Retrieval-augmented question answering over uploaded documents "
        "(PDF, DOCX, TXT). Connected; requires the agent dependencies and a "
        "local Ollama server."
    ),
    "automation": (
        "Interprets natural-language productivity requests and drafts the "
        "actions required. Connected; drafts only, external side effects are "
        "not performed."
    ),
    "performance": (
        "Data analytics over datasets: KPIs, comparisons, trends, patterns, "
        "visualizations, and narrative insights. Served as background jobs at "
        "POST /api/v1/performance/jobs, not through this endpoint."
    ),
}


def _describe(adapter: AgentAdapter) -> AgentInfo:
    """Build catalog metadata for one adapter.

    Args:
        adapter: The adapter to describe.

    Returns:
        Populated agent metadata.
    """
    return AgentInfo(
        name=adapter.name,
        display_name=adapter.display_name,
        available=adapter.is_available(),
        capabilities=adapter.capabilities(),
        status="ready" if adapter.is_available() else "not_connected",
        description=AGENT_DESCRIPTIONS.get(adapter.name, "Registered agent."),
    )


@router.get(
    "",
    response_model=APIResponse[AgentListResponse],
    summary="List registered agents",
    description=(
        "Returns every registered agent with its availability and advertised "
        "capabilities. Agents appear here even when their implementation is "
        "not connected yet."
    ),
)
async def list_agents(
    registry: AgentRegistry = Depends(get_registry),
) -> APIResponse[AgentListResponse]:
    """List all registered agents.

    Args:
        registry: The agent registry.

    Returns:
        An envelope containing the agent catalog.
    """
    agents = [_describe(adapter) for adapter in registry.list_all()]
    return APIResponse(
        data=AgentListResponse(
            agents=agents,
            total=len(agents),
            available_count=sum(1 for agent in agents if agent.available),
        ),
        message=f"{len(agents)} agents registered.",
        request_id=get_request_id(),
    )


@router.get(
    "/{agent_name}",
    response_model=APIResponse[AgentInfo],
    summary="Describe one agent",
    responses={404: {"description": "Unknown agent"}},
)
async def get_agent(
    agent_name: str,
    registry: AgentRegistry = Depends(get_registry),
) -> APIResponse[AgentInfo]:
    """Return metadata for a single agent.

    Args:
        agent_name: The agent identifier.
        registry: The agent registry.

    Returns:
        An envelope containing the agent metadata.

    Raises:
        UnknownAgentError: If the agent is not registered. Rendered as 404 by
            the centralized exception handler.
    """
    adapter = registry.get(agent_name)
    return APIResponse(
        data=_describe(adapter),
        message=f"Agent '{agent_name}'.",
        request_id=get_request_id(),
    )


@router.post(
    "/execute",
    response_model=APIResponse[AgentExecuteResponse],
    summary="Execute an agent operation",
    status_code=status.HTTP_200_OK,
    responses={
        404: {"description": "Unknown agent or unsupported operation"},
        503: {"description": "Agent implementation not connected"},
        502: {"description": "Agent execution failed"},
        504: {"description": "Agent execution timed out"},
    },
)
async def execute_agent_operation(
    request: AgentExecuteRequest,
    orchestrator: Orchestrator = Depends(get_orchestrator),
    settings: Settings = Depends(get_settings_dep),
) -> APIResponse[AgentExecuteResponse]:
    """Execute one operation against one agent.

    Args:
        request: The agent, operation, and payload to run.
        orchestrator: The orchestrator performing the dispatch.
        settings: Application settings.

    Returns:
        An envelope containing the agent result.

    Raises:
        UnknownAgentError: If the agent is not registered (404).
        AgentUnavailableError: If the agent has no implementation (503).
        UnknownOperationError: If the operation is not advertised (404).
        AgentTimeoutError: If the agent exceeds its timeout (504).
        AgentExecutionError: If the agent fails (502).
    """
    if settings.is_production:
        logger.warning(
            "agent_execute agent=%s operation=%s request_id=%s",
            request.agent,
            request.operation,
            get_request_id(),
        )

    result = await orchestrator.execute(request.agent, request.operation, request.payload)
    return APIResponse(
        data=result,
        message=f"Operation '{request.operation}' completed on '{request.agent}'.",
        request_id=get_request_id(),
    )
