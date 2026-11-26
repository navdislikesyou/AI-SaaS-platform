"""Employee Insights analytics endpoints.

Provides organization-scoped read-only analytics for employee feedback.
These routes operate directly on the feedback table and enforce tenant
isolation through the authenticated user's organization.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_current_user_from_token
from app.core.exceptions import ForbiddenError
from app.models import User
from app.schemas.common import APIResponse
from app.services.employee_insights_service import get_employee_insights_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/employee-insights", tags=["employee-insights"])


def _organization_id(current_user: User) -> str:
    """Require the authenticated user to belong to an organization."""
    if not current_user.organization_id:
        raise ForbiddenError(
            "Employee insights require an authenticated organisation.",
            details={"agent": "employee_insights", "reason": "missing_organization"},
        )
    return current_user.organization_id


@router.get(
    "/feedback",
    response_model=APIResponse[dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="List saved employee feedback",
    description="Returns a page of persisted feedback for the caller's organization.",
)
async def feedback_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user_from_token),
) -> APIResponse[dict[str, Any]]:
    """Return one organization-scoped page of saved feedback."""
    result = await get_employee_insights_service().get_feedback_page(
        _organization_id(current_user),
        page=page,
        page_size=page_size,
    )
    return APIResponse(data=result, message="Employee feedback retrieved.")


@router.get(
    "/summary/monthly",
    response_model=APIResponse[dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="Monthly sentiment summary",
    description="Returns monthly feedback sentiment breakdown for the caller's organization.",
)
async def monthly_summary(
    current_user: User = Depends(get_current_user_from_token),
) -> APIResponse[dict[str, Any]]:
    """Return monthly sentiment breakdown for the current organization."""
    service = get_employee_insights_service()
    result = await service.get_monthly_summary(_organization_id(current_user))
    return APIResponse(
        data=result,
        message="Monthly sentiment summary retrieved.",
    )


@router.get(
    "/summary/employee",
    response_model=APIResponse[dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="Employee sentiment summary",
    description="Returns per-employee sentiment counts for the caller's organization.",
)
async def employee_summary(
    employee_id: str | None = Query(
        None, description="Filter by employee ID. Omit for all employees."
    ),
    current_user: User = Depends(get_current_user_from_token),
) -> APIResponse[dict[str, Any]]:
    """Return per-employee sentiment counts for the current organization."""
    service = get_employee_insights_service()
    result = await service.get_employee_summary(
        _organization_id(current_user),
        employee_id=employee_id or "all",
    )
    return APIResponse(
        data=result,
        message="Employee sentiment summary retrieved.",
    )
