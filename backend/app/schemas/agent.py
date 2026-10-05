"""Agent-related request and response schemas.

These models describe the wire contract only. They intentionally do not model
the internals of any agent, so integrating a real agent does not require
changing them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import utc_now


class AgentInfo(BaseModel):
    """Metadata describing one registered agent.

    Attributes:
        name: Stable agent identifier used when executing operations.
        display_name: Human-readable label.
        available: Whether a real implementation is connected.
        capabilities: Operations the agent advertises.
        status: ``ready`` or ``not_connected``.
        description: Short summary of the agent's purpose.
    """

    name: str
    display_name: str
    available: bool
    capabilities: list[str]
    status: str
    description: str


class AgentListResponse(BaseModel):
    """Catalog of registered agents.

    Attributes:
        agents: Metadata for every registered agent.
        total: Number of agents listed.
        available_count: How many have a connected implementation.
    """

    agents: list[AgentInfo]
    total: int
    available_count: int


class AgentExecuteRequest(BaseModel):
    """Request to run one operation on one agent.

    Attributes:
        agent: Target agent name.
        operation: Operation to run on that agent.
        payload: Operation-specific input as a JSON object.
        metadata: Optional client-supplied correlation data.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "agent": "knowledge",
                "operation": "query",
                "payload": {"question": "What is this document about?"},
            }
        }
    )

    agent: str = Field(min_length=1, max_length=64)
    operation: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] | None = None


class AgentExecuteResponse(BaseModel):
    """Result of an agent operation.

    Attributes:
        agent: Agent that handled the request.
        operation: Operation that was requested.
        data: The agent result as a JSON object.
        request_id: Correlation id for this call.
        duration_ms: Server-side execution time in milliseconds.
        timestamp: Server time in UTC.
    """

    agent: str
    operation: str
    data: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None
    duration_ms: float | None = None
    timestamp: datetime = Field(default_factory=utc_now)
