"""Activity History API.

Read-only. Activities are written by the agent execution paths themselves, not
through this router, so a client cannot fabricate history.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from app.core.logging_config import get_request_id
from app.schemas.activity import ActivityRecord
from app.schemas.common import APIResponse
from app.services.activity_store import MAX_RECORDS, list_activities

logger = logging.getLogger(__name__)

router = APIRouter(tags=["activity-history"])

#: Upper bound accepted for the limit query parameter.
MAX_HISTORY_LIMIT = MAX_RECORDS


@router.get(
    "/activity-history",
    response_model=APIResponse[list[ActivityRecord]],
    summary="List recent agent activity",
    description=(
        "Returns lightweight activity records for Knowledge, Automation, and "
        "Performance, newest first. An empty history returns an empty list "
        "rather than an error."
    ),
)
async def get_activity_history(
    limit: int = Query(
        default=100,
        ge=1,
        le=MAX_HISTORY_LIMIT,
        description="Maximum number of records to return.",
    ),
) -> APIResponse[list[ActivityRecord]]:
    """Return recent activity records.

    Args:
        limit: Maximum number of records to return.

    Returns:
        An envelope containing the records, newest first.
    """
    records = [ActivityRecord(**record) for record in list_activities(limit)]

    logger.info("activity_history_read count=%d", len(records))

    return APIResponse(
        data=records,
        message=f"{len(records)} activities.",
        request_id=get_request_id(),
    )
