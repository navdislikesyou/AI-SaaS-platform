"""Automation employee directory API.

Accepts an employee directory from the browser, validates it, and stores it
locally so the Automation Agent can resolve attendee names against it. The
drafting pipeline itself is untouched: a directory only changes which employee
records the existing ``draft_action`` operation matches names against.

Nothing here returns a filesystem path or a stored filename. A client learns
the display filename it sent, a server-generated identifier, and whether the
records validated.

The default directory that ships inside the agent package is not exposed here
and is never replaced. Omitting ``directory_id`` from a draft request continues
to use it exactly as before.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.api.deps import (
    get_employee_directory_manifest,
    get_employee_directory_service,
    get_settings_dep,
)
from app.core.config import Settings
from app.core.exceptions import DirectoryNotFoundError, ValidationFailedError
from app.core.logging_config import get_request_id
from app.schemas.automation import (
    DirectoryDetailResponse,
    DirectoryListResponse,
    DirectoryUploadResponse,
    EmployeeRecord,
    UploadedDirectory,
)
from app.schemas.common import APIResponse
from app.services.employee_directory import (
    PREVIEW_LIMIT,
    DirectoryStatus,
    EmployeeDirectoryManifest,
    EmployeeDirectoryService,
    StoredDirectoryRow,
    build_row,
    find_directory_row,
    list_directories,
    record_directory,
    row_to_stored,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/automation", tags=["automation"])

#: Cap on rows returned by the directory list. Matches the manifest cap; the
#: list is read on every page load and must stay bounded.
_LIST_LIMIT = 500


@router.post(
    "/directories",
    response_model=APIResponse[DirectoryUploadResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Upload an employee directory",
    description=(
        "Accepts a JSON or CSV file of employee records, each holding a `name` "
        "and an `email`, stores it under a generated server-side filename, and "
        "returns a preview of the accepted records. The extension, the size, the "
        "file structure, and every record are validated. Any column other than "
        "`name` and `email` is discarded. Returns 201 only when every record "
        "passed validation; otherwise the stored file is removed and nothing is "
        "recorded as usable."
    ),
    responses={
        201: {"description": "Employee directory uploaded and validated"},
        422: {"description": "Unsupported format, oversized, or invalid records"},
    },
)
async def upload_directory(
    file: UploadFile = File(..., description="JSON or CSV employee directory."),
    service: EmployeeDirectoryService = Depends(get_employee_directory_service),
    manifest: EmployeeDirectoryManifest = Depends(get_employee_directory_manifest),
) -> APIResponse[DirectoryUploadResponse]:
    """Upload one employee directory and validate its records.

    The file is written to disk before its records are parsed, and removed again
    if any record fails validation, so a rejected upload leaves neither an
    orphaned file nor a usable-looking entry in the list.

    Args:
        file: The multipart file field sent by the client.
        service: Validates and stores the upload.
        manifest: Employee directory metadata store.

    Returns:
        An envelope containing the stored directory and a preview of its records.

    Raises:
        ValidationFailedError: If the file or any record is not acceptable
            (422).
    """
    try:
        stored = await service.store(file)
    except ValidationFailedError as exc:
        logger.warning("automation_directory_upload_rejected reason=%s", exc.message)

        raise

    records = list(stored.records)

    row = record_directory(
        build_row(
            directory_id=stored.directory_id,
            display_filename=stored.display_filename,
            stored_name=stored.stored_name,
            extension=stored.extension,
            size_bytes=stored.size_bytes,
            status=DirectoryStatus.READY,
            employee_count=len(records),
        ),
        manifest,
    )

    directory = _to_directory(row)

    return APIResponse(
        data=DirectoryUploadResponse(
            directory=directory,
            preview=[EmployeeRecord(**record) for record in records[:PREVIEW_LIMIT]],
            message=f"'{stored.display_filename}' accepted with {len(records)} employee(s).",
        ),
        request_id=get_request_id(),
    )


@router.get(
    "/directories",
    response_model=APIResponse[DirectoryListResponse],
    summary="List uploaded employee directories",
    description=(
        "Returns the employee directories this instance has accepted, newest "
        "first, with their validation status. The list reflects local uploads "
        "only; a different instance would not see them."
    ),
)
async def get_directories(
    manifest: EmployeeDirectoryManifest = Depends(get_employee_directory_manifest),
    settings: Settings = Depends(get_settings_dep),
) -> APIResponse[DirectoryListResponse]:
    """List uploaded employee directories.

    Args:
        manifest: Employee directory metadata store.
        settings: Application settings.

    Returns:
        An envelope containing the directories, newest first. An empty manifest
        returns an empty list rather than an error.
    """
    rows = list_directories(manifest, limit=_LIST_LIMIT)

    directories = [_to_directory(row) for row in rows]

    logger.info("automation_directories_listed count=%d", len(directories))

    return APIResponse(
        data=DirectoryListResponse(directories=directories, total=len(directories)),
        message=f"{len(directories)} directory(s).",
        request_id=get_request_id(),
    )


@router.get(
    "/directories/{directory_id}",
    response_model=APIResponse[DirectoryDetailResponse],
    summary="Get one uploaded employee directory",
    description=(
        "Returns the employee records of one uploaded directory. An unknown id "
        "and an id whose stored file is gone are reported the same way, so the "
        "response never confirms whether a given identifier ever existed."
    ),
    responses={
        404: {"description": "Unknown directory, or its stored file is gone"},
        422: {"description": "The stored file no longer holds valid records"},
    },
)
async def get_directory(
    directory_id: str,
    service: EmployeeDirectoryService = Depends(get_employee_directory_service),
    manifest: EmployeeDirectoryManifest = Depends(get_employee_directory_manifest),
) -> APIResponse[DirectoryDetailResponse]:
    """Return one uploaded directory and its employee records.

    Args:
        directory_id: The identifier returned by the upload route.
        service: Reads and validates the stored file.
        manifest: Employee directory metadata store.

    Returns:
        An envelope containing the directory and its records.

    Raises:
        DirectoryNotFoundError: If the id is unknown or its file is gone (404).
        ValidationFailedError: If the stored file no longer holds valid records
            (422).
    """
    row = find_directory_row(directory_id, manifest)

    if row is None:
        raise DirectoryNotFoundError(
            f"Employee directory '{directory_id}' was not found.",
            details={"directory_id": directory_id},
        )

    records = service.load_records(directory_id, manifest)

    return APIResponse(
        data=DirectoryDetailResponse(
            directory=_to_directory(row),
            employees=[EmployeeRecord(**record) for record in records],
            employees_truncated=len(records) > _LIST_LIMIT,
        ),
        request_id=get_request_id(),
    )


def _to_directory(row: dict[str, Any] | StoredDirectoryRow) -> UploadedDirectory:
    """Convert one manifest row into its client-facing model.

    The internal ``stored_name`` is dropped here: it has no meaning outside this
    process and is the one field with no client-facing use. Every value is
    coerced defensively because the manifest is a plain JSON file that can be
    hand-edited or truncated.

    Args:
        row: A raw manifest row, or an already-coerced record.

    Returns:
        The client-facing directory model.
    """
    record = row if isinstance(row, StoredDirectoryRow) else row_to_stored(row)

    return UploadedDirectory(
        directory_id=record.directory_id,
        filename=record.display_filename,
        format=record.extension.lstrip("."),
        employee_count=record.employee_count or 0,
        size_bytes=record.size_bytes,
        status=record.status,
        uploaded_at=record.uploaded_at,
    )
