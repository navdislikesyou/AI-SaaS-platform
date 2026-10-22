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

Every uploaded directory is stamped with the authenticated user's
``organization_id`` and ``owner_id``. Directory listing and detail lookups are
scoped to the uploader's organisation.  Client-supplied organization filters
are ignored in favor of the principal's scope.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.api.deps import (
    get_current_user_from_token_optional_principal,
    get_employee_directory_manifest,
    get_employee_directory_service,
    get_settings_dep,
    resource_is_visible_to,
)
from app.core.config import Settings
from app.core.exceptions import DirectoryNotFoundError, ValidationFailedError
from app.core.logging_config import get_request_id
from app.models import User
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
        " Every uploaded directory is stamped with the authenticated user's "
        "organization_id and owner_id. Directory listing and detail lookups are "
        "scoped to the uploader's organisation."
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
    settings: Settings = Depends(get_settings_dep),
    current_user: User | None = Depends(get_current_user_from_token_optional_principal),
) -> APIResponse[DirectoryUploadResponse]:
    """Upload one employee directory and validate its records.

    The file is written to disk before its records are parsed, and removed again
    if any record fails validation, so a rejected upload leaves neither an
    orphaned file nor a usable-looking entry in the list.

    Every uploaded directory is stamped with the authenticated user's
    ``organization_id`` and ``owner_id`` when authentication is active.
    Directory listing and detail lookups are scoped to the uploader's
    organisation.

    Args:
        file: The multipart file field sent by the client.
        service: Validates and stores the upload.
        manifest: Employee directory metadata store.
        settings: Application settings.
        current_user: The authenticated user, or None if no token is provided.

    Returns:
        An envelope containing the stored directory and a preview of its records.

    Raises:
        ValidationFailedError: If the file or any record is not acceptable
            (422).
    """
    # Determine ownership metadata; default to None when unauthenticated
    # so existing records without ownership remain visible (backward compat).
    org_id = current_user.organization_id if current_user else None
    owner_id = current_user.id if current_user else None

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
            organization_id=org_id,
            owner_id=owner_id,
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
        "only; a different instance would not see them. Records are scoped to "
        "the authenticated user's organisation; client-supplied organization "
        "filters are ignored. A request with no organisation has no scope and "
        "is shown no directories."
    ),
)
async def get_directories(
    manifest: EmployeeDirectoryManifest = Depends(get_employee_directory_manifest),
    settings: Settings = Depends(get_settings_dep),
    current_user: User | None = Depends(get_current_user_from_token_optional_principal),
) -> APIResponse[DirectoryListResponse]:
    """List uploaded employee directories.

    Records are scoped to the authenticated user's organisation. An empty
    manifest returns an empty list rather than an error. A request with no
    organisation has no scope, so it sees nothing: returning the whole history
    to an anonymous caller would hand every tenant's roster names to anyone.

    Args:
        manifest: Employee directory metadata store.
        settings: Application settings.
        current_user: The authenticated user, or None if no token is provided.

    Returns:
        An envelope containing the directories, newest first. An empty manifest
        returns an empty list rather than an error.
    """
    rows = list_directories(manifest, limit=_LIST_LIMIT)

    organization_id = current_user.organization_id if current_user else None

    if organization_id is None:
        rows = []
    else:
        rows = [row for row in rows if row.get("organization_id") == organization_id]

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
        "response never confirms whether a given identifier ever existed. "
        "Ownership is enforced: a directory uploaded by another organisation's "
        "user is not accessible."
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
    current_user: User | None = Depends(get_current_user_from_token_optional_principal),
) -> APIResponse[DirectoryDetailResponse]:
    """Return one uploaded directory and its employee records.

    Ownership is enforced: a directory uploaded by another user or organization
    is not accessible. The directory_id is resolved against the manifest, and
    the row's organization_id is compared against the authenticated user's
    organization_id.

    Args:
        directory_id: The identifier returned by the upload route.
        service: Reads and validates the stored file.
        manifest: Employee directory metadata store.
        current_user: The authenticated user, or None if no token is provided.

    Returns:
        An envelope containing the directory and its records.

    Raises:
        DirectoryNotFoundError: If the id is unknown or its file is gone (404).
        ValidationFailedError: If the directory belongs to another organisation
            (403).
    """
    row = find_directory_row(directory_id, manifest)

    if row is None:
        raise DirectoryNotFoundError(
            f"Employee directory '{directory_id}' was not found.",
            details={"directory_id": directory_id},
        )

    # Enforce organization ownership: a directory uploaded by another
    # organisation's user is not accessible. A caller with no authenticated
    # organisation owns nothing, so it cannot read a directory that belongs to
    # a tenant either.
    if not resource_is_visible_to(row.get("organization_id"), current_user):
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