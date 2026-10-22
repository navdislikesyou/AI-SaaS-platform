"""Knowledge document upload schemas.

These describe what a client may see about an uploaded document. Stored paths,
stored filenames, document contents, and embedding vectors are deliberately
absent: the manifest keeps them internal, and a client receives the display
filename, the identifier, and the indexing outcome.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.services.document_manifest import DocumentStatus


class UploadedDocument(BaseModel):
    """One document this instance has ingested.

    Attributes:
        document_id: Server-generated identifier.
        filename: The original filename as supplied by the client, for display.
        extension: Lowercased validated extension.
        size_bytes: Bytes received from the client.
        status: Whether the document was indexed or ingestion failed.
        chunk_count: Chunks committed to the vector store, when indexed.
        uploaded_at: Timezone-aware ISO-8601 timestamp of the upload.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "document_id": "9f2c1d0b4a7e4c1f9b3d5e7a8c0d2f41",
                "filename": "Employee Handbook.pdf",
                "extension": ".pdf",
                "size_bytes": 1843200,
                "status": "indexed",
                "chunk_count": 142,
                "uploaded_at": "2026-10-13T14:22:01+05:30",
            }
        }
    )

    document_id: str
    filename: str
    extension: str
    size_bytes: int
    status: DocumentStatus
    chunk_count: int | None = None
    uploaded_at: datetime


class DocumentUploadResponse(BaseModel):
    """Result of one document upload.

    Attributes:
        document: The stored document and its indexing outcome.
        message: Human-readable summary for the client.
    """

    document: UploadedDocument
    message: str = "Document uploaded and indexed."


class DocumentListResponse(BaseModel):
    """Payload for the uploaded document list.

    Attributes:
        documents: Documents ordered newest first.
        total: Number of documents returned.
    """

    documents: list[UploadedDocument] = Field(default_factory=list)
    total: int = 0
