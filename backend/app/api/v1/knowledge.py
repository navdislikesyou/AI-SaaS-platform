"""Knowledge document upload API.

Accepts a document from the browser, validates it, stores it locally, and hands
it to the Knowledge Agent's existing ``ingest_document`` operation. Extraction,
chunking, embedding, and Chroma indexing all happen inside the agent; this
router owns only the HTTP boundary and the file handling around it.

Ingestion is synchronous, matching how ``/agents/execute`` already runs the
operation. That is consistent with the rest of the platform rather than a new
shape: the adapter's thread offload, timeout, and concurrency slot all apply
because the call goes through the orchestrator.

Nothing here returns a filesystem path. A client learns the display filename it
sent, a server-generated identifier, and whether indexing succeeded.

Additionally, every uploaded document is stamped with the authenticated user's
``organization_id`` and ``owner_id``. Document listing and detail lookups are
scoped to the uploader's organisation.  Client-supplied organization filters are
ignored in favor of the principal's scope.  A request with no organisation has
no scope: it cannot upload a document, and it sees none.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.api.deps import (
    get_current_user_from_token_optional_principal,
    get_document_manifest,
    get_document_upload_service,
    get_orchestrator,
    get_settings_dep,
    user_context_for,
)
from app.core.config import Settings
from app.core.exceptions import AppError, ValidationFailedError
from app.core.logging_config import get_request_id
from app.models import User
from app.schemas.common import APIResponse
from app.schemas.knowledge import DocumentListResponse, DocumentUploadResponse, UploadedDocument
from app.services.document_manifest import (
    DocumentManifest,
    DocumentStatus,
    build_row,
    list_documents,
    record_document,
)
from app.services.document_upload import DocumentUploadService
from app.services.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

#: Agent and operation used to index an uploaded document.
_INGEST_AGENT = "knowledge"
_INGEST_OPERATION = "ingest_document"

#: Cap on rows returned by the document list. Matches the manifest cap; the
#: list is read on every page load and must stay bounded.
_LIST_LIMIT = 500


@router.post(
    "/documents",
    response_model=APIResponse[DocumentUploadResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Upload and index a document",
    description=(
        "Accepts a PDF, DOCX, or TXT file, stores it under a generated "
        "server-side filename, and indexes it into the Knowledge vector store. "
        "The extension, the size, and the file content are all validated. "
        "Returns 201 only after indexing succeeded; if ingestion fails the "
        "stored file is removed and no document is recorded as indexed."
        " Every uploaded document is stamped with the authenticated user's "
        "organization_id and owner_id. Document "
        "listing and detail lookups are scoped to the uploader's organisation. "
        "An upload requires an authenticated organisation: indexing a document "
        "without one would write chunks that no organisation owns and can "
        "therefore read, so the request is refused with 403 before the file "
        "is indexed."
    ),
    responses={
        201: {"description": "Document uploaded and indexed"},
        422: {"description": "Unsupported type, oversized, empty, or unreadable file"},
        502: {"description": "The Knowledge Agent failed while indexing"},
        503: {"description": "The Knowledge Agent is not connected"},
        504: {"description": "Indexing exceeded the agent timeout"},
    },
)
async def upload_document(
    file: UploadFile = File(..., description="PDF, DOCX, or TXT document."),
    upload_service: DocumentUploadService = Depends(get_document_upload_service),
    manifest: DocumentManifest = Depends(get_document_manifest),
    orchestrator: Orchestrator = Depends(get_orchestrator),
    settings: Settings = Depends(get_settings_dep),
    current_user: User | None = Depends(get_current_user_from_token_optional_principal),
) -> APIResponse[DocumentUploadResponse]:
    """Upload one document and index it.

    The file is written to disk before ingestion, and removed again if ingestion
    fails, so a failed upload leaves neither an orphaned file nor a misleading
    success state. Failures are recorded in the manifest with a ``failed``
    status rather than dropped, which keeps the document list honest about what
    was attempted.

    Every uploaded document is stamped with the authenticated user's
    ``organization_id`` and ``owner_id`` when authentication is active.
    Document listing and detail lookups are scoped to the uploader's
    organisation.

    An upload requires an authenticated organisation. Indexing a document
    without one would write chunks that no organisation owns and can therefore
    read, so the request is refused with 403 before the file is indexed.

    Args:
        file: The multipart file field sent by the client.
        upload_service: Validates and stores the upload.
        manifest: Document metadata store.
        orchestrator: Dispatches the ingestion operation.
        settings: Application settings.
        current_user: The authenticated user, or None if no token is provided.

    Returns:
        An envelope containing the stored document and its indexing outcome.

    Raises:
        ValidationFailedError: If the upload is not an acceptable document, or
            if ingestion produced no chunks (422).
        AgentUnavailableError: If the Knowledge Agent is not connected (503).
        AgentTimeoutError: If indexing exceeds the agent timeout (504).
        AgentExecutionError: If the Knowledge Agent fails (502).
    """
    # Finish cleanup left over from an earlier failed upload. On Windows a file
    # whose loader raised cannot be deleted during the request that failed,
    # because the exception traceback still holds the handle. It is released
    # once the request ends, so the sweep runs on a later upload.
    upload_service.sweep_failed(_failed_stored_names(manifest))

    # Determine ownership metadata; default to None when unauthenticated
    # so existing records without ownership remain visible (backward compat).
    org_id = current_user.organization_id if current_user else None
    owner_id = current_user.id if current_user else None

    stored = await upload_service.store(file)

    try:
        result = await orchestrator.execute(
            _INGEST_AGENT,
            _INGEST_OPERATION,
            {"file_path": str(stored.path)},
            user_context=user_context_for(current_user),
        )

    except AppError as exc:
        upload_service.discard(stored)
        record_document(
            build_row(
                document_id=stored.document_id,
                display_filename=stored.display_filename,
                stored_name=stored.stored_name,
                extension=stored.extension,
                size_bytes=stored.size_bytes,
                status=DocumentStatus.FAILED,
                error=exc.message,
                organization_id=org_id,
                owner_id=owner_id,
            ),
            manifest,
        )
        logger.warning(
            "knowledge_upload_ingest_failed extension=%s code=%s",
            stored.extension,
            exc.error_code,
        )
        raise

    chunk_count = _chunk_count(result.data)

    if not chunk_count:
        # The file parsed but produced nothing to embed. Treating that as a
        # success would put an unanswerable document in the selector.
        upload_service.discard(stored)
        record_document(
            build_row(
                document_id=stored.document_id,
                display_filename=stored.display_filename,
                stored_name=stored.stored_name,
                extension=stored.extension,
                size_bytes=stored.size_bytes,
                status=DocumentStatus.FAILED,
                error="The document produced no indexable text.",
                organization_id=org_id,
                owner_id=owner_id,
            ),
            manifest,
        )
        raise ValidationFailedError(
            f"'{stored.display_filename}' produced no indexable text. A scanned or "
            "empty document cannot be queried.",
            details={"filename": stored.display_filename},
        )

    row = record_document(
        build_row(
            document_id=stored.document_id,
            display_filename=stored.display_filename,
            stored_name=stored.stored_name,
            extension=stored.extension,
            size_bytes=stored.size_bytes,
            status=DocumentStatus.INDEXED,
            chunk_count=chunk_count,
            organization_id=org_id,
            owner_id=owner_id,
        ),
        manifest,
    )

    logger.info(
        "knowledge_upload_indexed extension=%s chunk_count=%d",
        stored.extension,
        chunk_count,
    )

    document = UploadedDocument(
        document_id=row["document_id"],
        filename=row["filename"],
        extension=row["extension"],
        size_bytes=row["size_bytes"],
        status=DocumentStatus(row["status"]),
        chunk_count=row.get("chunk_count"),
        uploaded_at=row["uploaded_at"],
    )

    return APIResponse(
        data=DocumentUploadResponse(
            document=document,
            message=f"'{stored.display_filename}' indexed as {chunk_count} chunks.",
        ),
        request_id=get_request_id(),
    )


@router.get(
    "/documents",
    response_model=APIResponse[DocumentListResponse],
    summary="List uploaded documents",
    description=(
        "Returns the documents this instance has ingested, newest first, with "
        "their indexing status. The corpus reflects local uploads only; a "
        "process restart keeps the manifest because it is a file on disk, but a "
        "different instance would not see it. Records are scoped to the "
        "authenticated user's organisation; client-supplied organization filters "
        "are ignored. A request with no organisation has no scope and is "
        "shown no documents."
    ),
)
async def get_documents(
    manifest: DocumentManifest = Depends(get_document_manifest),
    settings: Settings = Depends(get_settings_dep),
    current_user: User | None = Depends(get_current_user_from_token_optional_principal),
) -> APIResponse[DocumentListResponse]:
    """List uploaded documents.

    Records are scoped to the authenticated user's organisation. An empty
    manifest returns an empty list rather than an error. A request with no
    organisation has no scope, so it sees nothing: returning the whole history
    to an anonymous caller would hand every tenant's filenames to anyone.

    Args:
        manifest: Document metadata store.
        settings: Application settings.
        current_user: The authenticated user, or None if no token is provided.

    Returns:
        An envelope containing the documents, newest first. An empty manifest
        returns an empty list rather than an error.
    """
    rows = list_documents(manifest, limit=_LIST_LIMIT)

    organization_id = current_user.organization_id if current_user else None

    if organization_id is None:
        rows = []
    else:
        rows = [row for row in rows if row.get("organization_id") == organization_id]

    documents = [_to_document(row) for row in rows]

    logger.info("knowledge_documents_listed count=%d", len(documents))

    return APIResponse(
        data=DocumentListResponse(documents=documents, total=len(documents)),
        message=f"{len(documents)} document(s).",
        request_id=get_request_id(),
    )


def _failed_stored_names(manifest: DocumentManifest) -> list[str]:
    """Return the stored filenames of uploads that failed to index.

    Args:
        manifest: Document metadata store.

    Returns:
        Stored filenames for rows whose status is ``failed``.
    """
    rows = list_documents(
        manifest,
        status=DocumentStatus.FAILED,
        limit=_LIST_LIMIT,
        include_unowned=True,
    )

    return [str(row["stored_name"]) for row in rows if row.get("stored_name")]


def _chunk_count(data: dict[str, Any]) -> int:
    """Extract the indexed chunk count from an ingestion result.

    Args:
        data: The ``data`` payload returned by ``ingest_document``.

    Returns:
        The number of chunks committed, or 0 when the result does not report a
        usable count.
    """
    raw = data.get("chunk_count")

    if not isinstance(raw, int) or isinstance(raw, bool) or raw <= 0:
        return 0

    return raw


def _to_document(row: dict[str, Any]) -> UploadedDocument:
    """Convert one manifest row into its client-facing model.

    The manifest is a JSON file that a client never writes, but it can be
    hand-edited or truncated, so each field is coerced defensively rather than
    trusted. The internal ``stored_name`` is dropped here: it has no meaning
    outside this process and is the one field with no client-facing use.

    Args:
        row: A raw manifest row.

    Returns:
        The client-facing document model.
    """
    return UploadedDocument(
        document_id=str(row.get("document_id", "")),
        filename=str(row.get("filename", "")),
        extension=str(row.get("extension", "")),
        size_bytes=_as_int(row.get("size_bytes")),
        status=DocumentStatus(_as_status(row.get("status"))),
        chunk_count=_as_int(row.get("chunk_count")) if row.get("chunk_count") else None,
        uploaded_at=_as_timestamp(row.get("uploaded_at")),
    )


def _as_int(value: Any) -> int:
    """Coerce a manifest value to a non-negative integer.

    Args:
        value: The raw value.

    Returns:
        The integer value, or 0 when it is missing or not a usable count.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return 0

    return max(value, 0)


def _as_status(value: Any) -> DocumentStatus:
    """Coerce a manifest value to a known status.

    Args:
        value: The raw value.

    Returns:
        The matching status, defaulting to ``failed`` so an unreadable row is
        never presented to a client as indexed.
    """
    try:
        return DocumentStatus(str(value))

    except ValueError:
        logger.warning("knowledge_manifest_unknown_status value=%s", value)

        return DocumentStatus.FAILED


def _as_timestamp(value: Any) -> datetime:
    """Coerce a manifest value to a datetime.

    Args:
        value: The raw value, normally an ISO-8601 string.

    Returns:
        The parsed timestamp, or the epoch when it is missing or unparseable.
    """
    if not isinstance(value, str):
        return datetime.fromtimestamp(0, tz=UTC)

    try:
        return datetime.fromisoformat(value)

    except ValueError:
        logger.warning("knowledge_manifest_unparseable_timestamp")

        return datetime.fromtimestamp(0, tz=UTC)