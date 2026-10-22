"""Performance Analyzer dataset and job API.

The Performance Analyzer runs CPU-intensive analytics that can take tens of
seconds, so it is not served through ``POST /api/v1/agents/execute``. Instead a
client submits a job, receives 202 Accepted immediately, and polls for the
outcome.

A job needs a dataset, and a dataset can arrive two ways. A browser uploads one
through ``POST /performance/datasets`` and then refers to it only by the
server-generated id it was given. An operator who already has a file on the
machine can keep sending ``file_path``. The two are mutually exclusive on a
request, and the id is always resolved to a path the server controls, so no
uploaded dataset is ever named by a client-supplied string.

The router stays thin: it validates the request and delegates to
:class:`~app.services.job_manager.JobManager`, which calls
:class:`performance_agent.service.PerformanceService`, and to
:class:`~app.services.dataset_upload.DatasetUploadService` for uploads. No
pandas work and no analyzer logic lives in this module.

Nothing here returns a filesystem path or a stored filename.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import (
    get_current_user_from_token_optional_principal,
    get_dataset_manifest,
    get_dataset_upload_service,
    get_job_manager,
    get_settings_dep,
    resource_is_visible_to,
)
from app.core.config import Settings
from app.core.exceptions import (
    DatasetNotFoundError,
    JobNotFoundError,
    UnknownOperationError,
    ValidationFailedError,
)
from app.core.logging_config import get_request_id
from app.models import User
from app.schemas.common import APIResponse
from app.schemas.performance import (
    SUPPORTED_OPERATIONS,
    DatasetListResponse,
    DatasetStatus,
    DatasetUploadResponse,
    PerformanceJobAccepted,
    PerformanceJobRequest,
    PerformanceJobStatusResponse,
    UploadedDataset,
)
from app.services.dataset_upload import (
    SAMPLE_DATASET_ID,
    SUPPORTED_EXTENSIONS,
    DatasetManifest,
    DatasetUploadService,
    StoredDatasetRow,
    build_row,
    find_dataset_row,
    list_datasets,
    record_dataset,
    row_to_stored,
)
from app.services.job_manager import JobManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/performance", tags=["performance"])

JOBS_TAG_DESCRIPTION = (
    "Performance Analyzer jobs. Each job runs one operation over a "
    "server-side dataset in the background and is polled for its result."
)

#: Cap on rows returned by the dataset list. Matches the manifest cap; the list is
#: read on every page load and must stay bounded.
_LIST_LIMIT = 500


@router.post(
    "/datasets",
    response_model=APIResponse[DatasetUploadResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Upload a dataset for analysis",
    description=(
        "Accepts a CSV or XLSX dataset, stores it under a generated server-side "
        "filename, and returns the id that identifies it. The extension, the "
        "size, the container format, and the readable header are all validated, "
        "and a rejected upload leaves no file behind. The stored path is never "
        "returned and the original filename is kept only for display. "
        "Legacy `.xls` workbooks are not supported and are refused here."
    ),
    responses={
        201: {"description": "Dataset stored and ready to analyse"},
        422: {"description": "Unsupported type, oversized, empty, or unreadable file"},
    },
)
async def upload_dataset(
    file: UploadFile = File(..., description="CSV or XLSX dataset."),
    service: DatasetUploadService = Depends(get_dataset_upload_service),
    manifest: DatasetManifest = Depends(get_dataset_manifest),
    settings: Settings = Depends(get_settings_dep),
    current_user: User | None = Depends(get_current_user_from_token_optional_principal),
) -> APIResponse[DatasetUploadResponse]:
    """Upload one dataset and validate that it can be read.

    Validation reads only the header and a few rows, so a large workbook is
    accepted without being loaded into memory in full. The response reports the
    normalized column names the analyzers will look for, which is what lets a
    user see whether their headers will be understood.

    Args:
        file: The multipart file field sent by the client.
        service: Validates and stores the upload.
        manifest: Dataset metadata store.
        settings: Application settings.
        current_user: The authenticated user, or None if no token is provided.

    Returns:
        An envelope containing the stored dataset.

    Raises:
        ValidationFailedError: If the file is not an acceptable dataset (422).
    """
    stored = await service.store(file)

    row = record_dataset(
        build_row(
            dataset_id=stored.dataset_id,
            display_filename=stored.display_filename,
            stored_name=stored.stored_name,
            extension=stored.extension,
            size_bytes=stored.size_bytes,
            status=DatasetStatus.READY,
            column_names=list(stored.column_names),
            organization_id=current_user.organization_id if current_user else None,
            owner_id=current_user.id if current_user else None,
        ),
        manifest,
    )

    logger.info(
        "performance_dataset_uploaded id=%s extension=%s",
        stored.dataset_id,
        stored.extension,
    )

    return APIResponse(
        data=DatasetUploadResponse(
            dataset=_to_dataset(row_to_stored(row)),
            message=f"'{stored.display_filename}' is ready to analyse.",
        ),
        request_id=get_request_id(),
    )


@router.get(
    "/datasets",
    response_model=APIResponse[DatasetListResponse],
    summary="List datasets available to this instance",
    description=(
        "Returns the packaged sample dataset first, then the datasets uploaded "
        "through this API, newest first. Any of the ids can be sent as "
        "`dataset_id` in a job request. The list reflects local storage only; a "
        "different instance would not see these uploads."
    ),
)
async def get_datasets(
    service: DatasetUploadService = Depends(get_dataset_upload_service),
    manifest: DatasetManifest = Depends(get_dataset_manifest),
    current_user: User | None = Depends(get_current_user_from_token_optional_principal),
) -> APIResponse[DatasetListResponse]:
    """List the datasets a job may be run against.

    Args:
        service: Supplies the packaged sample entry and the enforced size limit.
        manifest: Dataset metadata store.
        current_user: The authenticated user, or None if no token is provided.

    Returns:
        An envelope containing the datasets, the upload limit, and the accepted
        extensions. An empty manifest returns just the packaged entry rather than
        an error, so a fresh instance still has something selectable.
    """
    sample = service.sample_entry()

    datasets: list[UploadedDataset] = [
        UploadedDataset(
            dataset_id=sample["dataset_id"],
            filename=sample["filename"],
            format=sample["format"],
            size_bytes=sample["size_bytes"],
            status=DatasetStatus.READY,
            column_names=[],
            column_count=0,
            is_sample=True,
            available=sample["available"],
        ),
    ]

    for row in list_datasets(manifest=manifest, limit=_LIST_LIMIT):
        # A dataset belongs to the organisation that uploaded it, so a listing
        # only offers the caller's own datasets. A request with no organisation
        # has no scope, so it is offered no uploaded dataset at all, and a
        # dataset with no recorded owner is offered to nobody.
        organization_id = current_user.organization_id if current_user else None

        if organization_id is None:
            continue

        if row.get("organization_id") != organization_id:
            continue

        record = row_to_stored(row)

        # A row that failed validation is never offered. Nothing else references
        # its id, so listing it would only invite a job that cannot run.
        if record.status is not DatasetStatus.READY:
            continue

        datasets.append(_to_dataset(record))

    logger.info("performance_datasets_listed count=%d", len(datasets))

    return APIResponse(
        data=DatasetListResponse(
            datasets=datasets,
            total=len(datasets),
            # Reported from the service rather than from settings, because the
            # service holds the limit actually enforced during the write.
            max_upload_bytes=service.max_bytes,
            supported_extensions=list(SUPPORTED_EXTENSIONS),
        ),
        message=f"{len(datasets)} dataset(s).",
        request_id=get_request_id(),
    )


@router.post(
    "/jobs",
    response_model=APIResponse[PerformanceJobAccepted],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create a performance job",
    description=(
        "Accepts a job for background execution and returns immediately with a "
        f"job id. Supported operations: {', '.join(SUPPORTED_OPERATIONS)}. Name "
        "the dataset with `dataset_id`, which the server resolves to a file it "
        "controls, or with `file_path` for the server-side workflow."
    ),
    responses={
        404: {"description": "Unsupported operation, or unknown dataset"},
        422: {"description": "Invalid request payload"},
    },
)
async def create_performance_job(
    request: PerformanceJobRequest,
    job_manager: JobManager = Depends(get_job_manager),
    dataset_service: DatasetUploadService = Depends(get_dataset_upload_service),
    dataset_manifest: DatasetManifest = Depends(get_dataset_manifest),
    settings: Settings = Depends(get_settings_dep),
    current_user: User | None = Depends(get_current_user_from_token_optional_principal),
) -> APIResponse[PerformanceJobAccepted]:
    """Accept a performance job for background execution.

    Returns as soon as the job is recorded; the analysis runs on a worker thread
    while the client polls the status endpoint.

    A ``dataset_id`` is resolved here, before the job exists, so an unknown or
    gone dataset fails the request with a 404 instead of creating a job that will
    fail later. There is no fallback: if the dataset cannot be resolved, no job
    runs, because silently analysing a different file than the one that was
    selected would report success for the wrong data.

    Args:
        request: The operation and dataset reference.
        job_manager: The job manager performing the dispatch.
        dataset_service: Resolves a dataset id to a trusted path.
        dataset_manifest: The manifest the id is resolved against. Passed
            explicitly rather than left to the service default, so the job reads
            the same store the upload route wrote to.

    Returns:
        An envelope containing the new job id and its queued status.

    Raises:
        UnknownOperationError: If the operation is not supported (404).
        DatasetNotFoundError: If the referenced dataset cannot be resolved (404).
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

    file_path = _resolve_dataset_path(
        request,
        dataset_service,
        dataset_manifest,
        settings,
        current_user,
    )

    job = job_manager.submit(
        operation=operation,
        file_path=file_path,
        request_id=get_request_id(),
        organization_id=current_user.organization_id if current_user else None,
        owner_id=current_user.id if current_user else None,
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
    current_user: User | None = Depends(get_current_user_from_token_optional_principal),
) -> APIResponse[PerformanceJobStatusResponse]:
    """Return the current state of one performance job.

    Ownership is enforced: a job belonging to another organisation's user is
    not accessible. The job is located by id, and its organization_id is
    compared against the authenticated user's organization_id.

    Args:
        job_id: The identifier returned when the job was created.
        job_manager: The job manager holding the job state.
        current_user: The authenticated user, or None if no token is provided.

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

    # Enforce organization ownership: a job belonging to another organisation's
    # user is not accessible. A caller with no authenticated organisation owns
    # nothing, so an expired or absent token does not make a tenant's job
    # readable.
    if not resource_is_visible_to(job.organization_id, current_user):
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
    current_user: User | None = Depends(get_current_user_from_token_optional_principal),
) -> FileResponse:
    """Stream one generated visualization PNG for a completed job.

    Ownership is enforced: a chart belonging to a job in another organisation
    is not downloadable. The filename must match an entry the job itself
    reported in its ``visualizations`` result, and the resolved path must sit
    inside that job's visualization directory.

    Args:
        job_id: The job that generated the chart.
        filename: The bare artifact filename from the job's ``visualizations``.
        job_manager: The job manager holding the job and its artifacts.
        current_user: The authenticated user, or None if no token is provided.

    Returns:
        The PNG bytes with an ``image/png`` media type.

    Raises:
        JobNotFoundError: If no job has that id, or the job did not generate
            that artifact (404).
    """
    job = job_manager.get(job_id)

    if job is None:
        raise JobNotFoundError(
            f"Performance job '{job_id}' was not found.",
            details={"job_id": job_id},
        )

    # Enforce organization ownership: a chart belonging to a job in another
    # organisation is not downloadable. A caller with no authenticated
    # organisation owns nothing, so it cannot download a tenant's chart.
    if not resource_is_visible_to(job.organization_id, current_user):
        raise JobNotFoundError(
            f"Artifact '{filename}' was not found for job '{job_id}'.",
            details={"job_id": job_id, "filename": filename},
        )

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


def _require_owned_dataset(
    dataset_id: str,
    manifest: DatasetManifest,
    current_user: User | None,
) -> None:
    """Refuse a dataset that belongs to another organisation.

    A dataset carries the organisation that uploaded it. A dataset owned by
    somebody else is reported as missing, so the response does not confirm
    that the id exists. A dataset with no recorded owner is inaccessible to
    every organisation, because ownership cannot be established for it.

    Args:
        dataset_id: The dataset the client asked for.
        manifest: The manifest the id is looked up in.
        current_user: The authenticated user, or None for an anonymous caller.

    Raises:
        DatasetNotFoundError: If the dataset is unknown, unowned, or owned by
            another organisation (404).
    """
    # The packaged sample is the server's own file, offered to every tenant in
    # the listing. It is not one tenant's data, so it is not owned by one.
    if dataset_id == SAMPLE_DATASET_ID:
        return

    organization_id = current_user.organization_id if current_user else None

    if organization_id is None:
        raise DatasetNotFoundError(
            "That dataset could not be resolved.",
            details={"dataset_id": dataset_id},
        )

    row = find_dataset_row(dataset_id, manifest)

    if row is None or row.get("organization_id") != organization_id:
        raise DatasetNotFoundError(
            "That dataset could not be resolved.",
            details={"dataset_id": dataset_id},
        )


def _resolve_dataset_path(
    request: PerformanceJobRequest,
    dataset_service: DatasetUploadService,
    manifest: DatasetManifest,
    settings: Settings,
    current_user: User | None = None,
) -> str:
    """Return the filesystem path a job should read.

    A ``dataset_id`` is turned into a path the server owns. A ``file_path`` is
    resolved against an allowlisted directory so that absolute paths and
    traversal outside the permitted area are rejected.

    A dataset belongs to the organisation that uploaded it, so an id belonging
    to another organisation is refused here rather than resolved. Without this
    check a tenant could submit a job against someone else's dataset and read
    their numbers in the result, because the job would carry the caller's own
    organisation.

    Args:
        request: The validated job request.
        dataset_service: Resolves a dataset id to a trusted path.
        manifest: The manifest the id is resolved against.
        settings: Application settings, used to resolve the allowlisted directory.
        current_user: The authenticated user, or None for an anonymous caller.

    Returns:
        An absolute path string confined to the allowlisted directory.

    Raises:
        DatasetNotFoundError: If a dataset id was supplied and could not be
            resolved, or belongs to another organisation. Never falls back to
            another dataset.
        ValidationFailedError: If the resolved reference is blank, or if
            file_path resolves outside the allowlisted directory, or if an
            absolute path is supplied.
    """
    if request.dataset_id:
        _require_owned_dataset(request.dataset_id, manifest, current_user)
        path = dataset_service.resolve(request.dataset_id, manifest)

    else:
        file_path = str(request.file_path or "").strip()

        if not file_path:
            raise ValidationFailedError(
                "dataset_id must not be blank.",
                details={"field": "dataset_id"},
            )

        # Reject absolute paths outright — no client-supplied path may escape
        # the server-controlled allowlist.
        if Path(file_path).is_absolute():
            raise ValidationFailedError(
                "Absolute paths are not permitted. Use dataset_id instead.",
                details={"field": "file_path"},
            )

        # Resolve relative to the backend directory.
        resolved_path = Path(settings.backend_dir) / file_path

        # Resolve symlinks and relative segments, then verify the canonical
        # path sits inside the allowlisted directory.
        allowed_dir = settings.resolved_performance_sample_dataset_path.parent

        try:
            canonical = resolved_path.resolve()
            # Confine the path to the allowlisted directory using
            # Path.relative_to which correctly handles path separators.
            canonical.relative_to(allowed_dir.resolve())
        except (OSError, ValueError) as exc:
            raise ValidationFailedError(
                "Path escapes the allowlisted directory. Use dataset_id instead.",
                details={"field": "file_path"},
            ) from exc

        path = resolved_path

    resolved = str(path)

    if not resolved:
        raise ValidationFailedError(
            "dataset_id must not be blank.",
            details={"field": "dataset_id"},
        )

    return resolved


def _to_dataset(record: StoredDatasetRow) -> UploadedDataset:
    """Convert one stored record into its client-facing model.

    The internal ``stored_name`` is dropped here: it has no meaning outside this
    process, it is the one field with no client-facing use, and it is the only
    thing in a row that could hint at the server's directory layout.

    Args:
        record: A coerced manifest row.

    Returns:
        The client-facing dataset model.
    """
    return UploadedDataset(
        dataset_id=record.dataset_id,
        filename=record.display_filename,
        format=record.extension.lstrip(".").lower(),
        size_bytes=record.size_bytes,
        status=record.status,
        uploaded_at=record.uploaded_at,
        column_names=list(record.column_names),
        column_count=len(record.column_names),
        is_sample=record.dataset_id == SAMPLE_DATASET_ID,
        available=True,
    )