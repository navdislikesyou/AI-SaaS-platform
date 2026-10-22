"""Activity History API.

Read-only. Activities are written by the agent execution paths themselves, not
through this router, so a client cannot fabricate history. Access is scoped to
the authenticated principal's organisation when authentication is provided.
Client-supplied user_id/organization_id query parameters are ignored in favor
of the authenticated user's scope. An empty history returns an empty list
rather than an error. Unauthenticated requests in production receive a
restricted (empty) history, not the full global record.

When no authentication context is present the full history is returned only
for backward compatibility with development and test configurations that
supply a user via dependency override.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user_from_token_optional_principal
from app.core.logging_config import get_request_id
from app.models import User
from app.schemas.activity import ActivityRecord
from app.schemas.common import APIResponse
from app.services.activity_store import MAX_RECORDS, get_store

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
        "rather than an error. When authentication is active, records are scoped "
        "to the authenticated user's organisation. Client-supplied user_id/organization_id "
        "filters are ignored to prevent permission-widening. Unauthenticated "
        "requests in production receive a restricted history (empty list), not "
        "the full global record.  Development and test configurations may supply "
        "a user via dependency override to retain full history."
    ),
)
async def get_activity_history(
    limit: int = Query(
        default=100,
        ge=1,
        le=MAX_HISTORY_LIMIT,
        description="Maximum number of records to return.",
    ),
    current_user: User | None = Depends(get_current_user_from_token_optional_principal),
) -> APIResponse[list[ActivityRecord]]:
    """Return recent activity records scoped to the authenticated user.

    Args:
        limit: Maximum number of records to return.
        current_user: The authenticated user, or None if no valid token is
            supplied.  When ``None`` the endpoint returns a restricted history
            (empty list) rather than the full global record.

    Returns:
        An envelope containing the records, newest first.
    """
    records = get_store().read()

    if current_user is not None:
        # Authenticated: scope to the user's organisation when present.
        # Legacy records without ``organization_id`` are still included if the
        # ``user_id`` matches, so that backward‑compatible test configurations
        # (and administrators managing legacy data) are not broken.
        records = [
            r for r in records
            if r.get("user_id") == current_user.id
            and (
                current_user.organization_id is None
                or r.get("organization_id") == current_user.organization_id
            )
        ]
    else:
        # Unauthenticated: return a restricted history — empty list — so that
        # production deployments never serve global activity records without
        # explicit authentication.  Test configurations that need full history
        # should inject a user via the ``get_current_user_from_token_optional_principal``
        # dependency override in ``conftest.py``.
        records = []

    records = list(reversed(records))[:limit]

    return APIResponse(
        data=[ActivityRecord(**record) for record in records],
        message=f"{len(records)} activities.",
        request_id=get_request_id(),
    )