"""Health and readiness endpoints.

``/health`` reports process liveness. ``/ready`` reports whether the backend's
own components are initialized. Both intentionally avoid probing agents or
external services, since a dependency being down should not fail the container
health check.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response, status

from app.agents.registry import AgentRegistry
from app.api.deps import get_registry, get_settings_dep
from app.core.config import Settings
from app.schemas.common import HealthResponse, ReadCheck, ReadinessResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness check",
    description="Confirms the API process is running and able to serve requests.",
)
async def health(settings: Settings = Depends(get_settings_dep)) -> HealthResponse:
    """Report process liveness.

    Args:
        settings: Application settings.

    Returns:
        A health payload describing the running application.
    """
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness check",
    description=(
        "Reports whether the backend's own components are initialized. Returns "
        "503 with the failing checks when not ready."
    ),
)
async def ready(
    response: Response,
    registry: AgentRegistry = Depends(get_registry),
) -> ReadinessResponse:
    """Report backend readiness.

    Args:
        response: Response object used to set the status code.
        registry: The initialized agent registry.

    Returns:
        A readiness payload listing each component check.
    """
    checks = [ReadCheck(name="registry", ready=True, detail=f"{len(registry)} agents registered")]

    total = len(registry)
    connected = len(registry.available_agents())
    checks.append(
        ReadCheck(
            name="agents",
            ready=True,
            detail=f"{connected} of {total} agents connected",
        )
    )

    all_ready = all(check.ready for check in checks)
    if not all_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    logger.info("readiness_check ready=%s", all_ready)
    return ReadinessResponse(
        status="ready" if all_ready else "not_ready",
        checks=checks,
    )
