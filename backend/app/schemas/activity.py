"""Activity History schemas.

A record describes that an agent operation ran and how it ended. It carries no
agent output: no answers, no drafted email bodies, no chart data, no
filesystem paths.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ActivityRecord(BaseModel):
    """One completed agent operation.

    Attributes:
        id: Unique record identifier.
        agent: Agent identifier, e.g. ``knowledge``.
        operation: Operation name, e.g. ``query``.
        description: Short human-readable summary of what happened.
        status: ``completed`` or ``failed``.
        timestamp: Timezone-aware ISO-8601 timestamp of when it finished.
        duration_ms: Optional elapsed time in milliseconds.
    """

    id: str
    agent: str
    operation: str
    description: str
    status: str
    timestamp: datetime
    duration_ms: int | None = None


class ActivityListResponse(BaseModel):
    """Payload for the activity history endpoint.

    Attributes:
        activities: Records ordered newest first.
    """

    activities: list[ActivityRecord] = Field(default_factory=list)
