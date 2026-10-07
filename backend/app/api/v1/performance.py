"""Performance Analyzer job API.

The Performance Analyzer runs CPU-intensive analytics that can take tens of
seconds, so it is not served through ``POST /api/v1/agents/execute``. Instead a
client submits a job, receives 202 Accepted immediately, and polls for the
outcome.

The router stays thin: it validates the request and delegates to
:class:`~app.services.job_manager.JobManager`, which calls
:class:`performance_agent.service.PerformanceService`. No pandas work and no
analyzer logic lives in this module.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse

from app.api.deps import get_job_manager
from app.core.exceptions import (
    JobNotFoundError,
    UnknownOperationError,
    ValidationFailedError,
)
from app.core.logging_config import get_request_id
from app.schemas.common import APIResponse
from app.schemas.performance import (
    SUPPORTED_OPERATIONS,
    PerformanceJobAccepted,
    PerformanceJobRequest,
    PerformanceJobStatusResponse,
)
from app.services.job_manager import JobManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/performance", tags=["performance"])

JOBS_TAG_DESCRIPTION = (
    "Performance Analyzer jobs. Each job runs one operation over a "
    "server-side dataset in the background and is polled for its result."
)


@router.post(
    "/jobs",
    response_model=APIResponse[PerformanceJobAccepted],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create a performance job",
    description=(
        "Accepts a job for background execution and returns immediately with a "
        f"job id. Supported operations: {', '.join(SUPPORTED_OPERATIONS)}."
    ),
    responses={
        404: {"description": "Unsupported operation"},
        422: {"description": "Invalid request payload"},
    },
)
async def create_performance_job(
    request: PerformanceJobRequest,
    job_manager: JobManager = Depends(get_job_manager),
) -> APIResponse[PerformanceJobAccepted]:
    """Accept a performance job for background execution.

    Returns as soon as the job is recorded; the analysis runs on a worker
    thread while the client polls the status endpoint.

    Args:
        request: The operation and server-side dataset path.
        job_manager: The job manager performing the dispatch.

    Returns:
        An envelope containing the new job id and its queued status.

    Raises:
        UnknownOperationError: If the operation is not supported (404).
        ValidationFailedError: If the payload is otherwise unusable (422).
    """
    operation = request.operation.strip()

    if operation not in SUPPORTED_OPERATIONS:
        raise UnknownOperationError(
            f"Unsupported performance operation: '{operation}'.",
            details={
                "operation": operation,
                "supported": list(SUPPORTED_OPERATIONS),
            },
        )

    file_path = request.file_path.strip()

    if not file_path:
        raise ValidationFailedError(
            "file_path must not be blank.",
            details={"field": "file_path"},
        )

    job = job_manager.submit(
        operation=operation,
        file_path=file_path,
        request_id=get_request_id(),
    )

    logger.info(
        "performance_job_accepted job_id=%s operation=%s",
        job.job_id,
        operation,
    )

    return APIResponse(
        data=PerformanceJobAccepted(
            job_id=job.job_id,
            status=job.status,
            operation=job.operation,
            created_at=job.created_at,
        ),
        message="Performance job created.",
        request_id=get_request_id(),
    )


@router.get(
    "/jobs/{job_id}",
    response_model=APIResponse[PerformanceJobStatusResponse],
    summary="Get performance job status",
    description="Returns the current lifecycle state and, once terminal, the result.",
    responses={404: {"description": "Unknown job"}},
)
async def get_performance_job(
    job_id: str,
    job_manager: JobManager = Depends(get_job_manager),
) -> APIResponse[PerformanceJobStatusResponse]:
    """Return the current state of one performance job.

    Args:
        job_id: The identifier returned when the job was created.
        job_manager: The job manager holding the job state.

    Returns:
        An envelope containing the job status, result, or sanitized error.

    Raises:
        JobNotFoundError: If no job has that identifier (404).
    """
    job = job_manager.get(job_id)

    if job is None:
        raise JobNotFoundError(
            f"Performance job '{job_id}' was not found.",
            details={"job_id": job_id},
        )

    return APIResponse(
        data=PerformanceJobStatusResponse(**job.to_status_response()),
        message=f"Performance job '{job.status.value}'.",
        request_id=get_request_id(),
    )


@router.get(
    "/jobs/{job_id}/artifacts/{filename}",
    response_class=FileResponse,
    summary="Download a generated chart for a performance job",
    description=(
        "Streams one PNG a `visualize` job generated. The filename must match "
        "an artifact the job itself reported, and access is restricted to that "
        "job's visualization directory. Returns 404 for an unknown job, an "
        "unknown artifact, or a filename the job did not generate."
    ),
    responses={
        200: {"content": {"image/png": {}}, "description": "The generated chart"},
        404: {"description": "Unknown job, or unknown artifact for that job"},
    },
)
async def get_performance_artifact(
    job_id: str,
    filename: str,
    job_manager: JobManager = Depends(get_job_manager),
) -> FileResponse:
    """Stream one generated visualization PNG for a completed job.

    Resolution is delegated to
    :meth:`~app.services.job_manager.JobManager.resolve_artifact`, which
    allowlists the filename against the job's own artifact metadata and
    confines the resolved path to that job's visualization directory.

    Args:
        job_id: The job that generated the chart.
        filename: The bare artifact filename from the job's ``visualizations``.
        job_manager: The job manager holding the job and its artifacts.

    Returns:
        The PNG bytes with an ``image/png`` media type.

    Raises:
        JobNotFoundError: If no job has that id, or the job did not generate
            that artifact (404).
    """
    path = job_manager.resolve_artifact(job_id, filename)

    if path is None:
        raise JobNotFoundError(
            f"Artifact '{filename}' was not found for job '{job_id}'.",
            details={"job_id": job_id, "filename": filename},
        )

    return FileResponse(
        path,
        media_type="image/png",
        # No Content-Disposition filename, so the absolute path is never exposed.
        filename=None,
    )
