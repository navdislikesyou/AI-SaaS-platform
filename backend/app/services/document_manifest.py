"""Uploaded Document Manifest.

Records one lightweight metadata row per document submitted through
``POST /api/v1/knowledge/documents``. The manifest answers one question: which
documents has this instance seen, and did each one actually index.

It holds identifiers, names, sizes, timestamps, and status. It holds no document
contents, no extracted text, and no embedding vectors; those live in the upload
directory and in the Chroma collection. Stored paths stay internal and are never
returned to a client.

Like :mod:`app.services.activity_store`, this is a local MVP backed by a JSON
file rather than a database, written atomically under a process-local lock. A
deployment needs real persistent storage, and any future database-backed store
can be swapped in here without changing the router.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

#: Cap on retained rows. The manifest is read by a document list on every page
#: load, so an unbounded file would grow without limit in a long-running process.
MAX_RECORDS = 500

_write_lock = threading.Lock()


class DocumentStatus(StrEnum):
    """Indexing outcome for one uploaded document.

    Attributes:
        INDEXED: Text was extracted, chunked, embedded, and added to the
            vector store.
        FAILED: The upload was rejected or ingestion failed. No chunks were
            committed and the stored file was removed.
    """

    INDEXED = "indexed"
    FAILED = "failed"


class DocumentManifest:
    """JSON-file backed store of uploaded document metadata.

    Attributes:
        path: The manifest file. Its parent directory is created on first write.
    """

    def __init__(self, path: Path | None = None) -> None:
        """Initialize the manifest.

        Args:
            path: Manifest file path. Defaults to the configured location under
                the upload directory.
        """
        resolved = path or get_settings().resolved_knowledge_upload_manifest_path

        self.path = Path(resolved)

    def read(self) -> list[dict[str, Any]]:
        """Read all manifest rows.

        A missing file is an empty manifest, not an error. A corrupt file is also
        treated as empty rather than breaking the document list, and is logged.

        Returns:
            Stored rows, oldest first, exactly as persisted.
        """
        try:
            if not self.path.is_file():
                return []

            raw = self.path.read_text(encoding="utf-8")

            if not raw.strip():
                return []

            parsed = json.loads(raw)

            if not isinstance(parsed, list):
                logger.warning("knowledge_manifest_not_a_list name=%s", self.path.name)

                return []

            return [row for row in parsed if isinstance(row, dict)]

        except json.JSONDecodeError:
            logger.warning("knowledge_manifest_corrupt name=%s", self.path.name)

            return []

        except OSError:
            logger.warning("knowledge_manifest_unreadable name=%s", self.path.name)

            return []

    def append(self, row: dict[str, Any]) -> dict[str, Any]:
        """Append one row and persist the manifest.

        The write is atomic: the new content goes to a temporary file in the same
        directory and is then moved over the target, so a concurrent reader never
        observes a half-written file.

        Args:
            row: The row to store.

        Returns:
            The stored row.
        """
        with _write_lock:
            rows = self.read()

            rows.append(row)

            if len(rows) > MAX_RECORDS:
                rows = rows[-MAX_RECORDS:]

            self._write(rows)

        return row

    def _write(self, rows: list[dict[str, Any]]) -> None:
        """Write rows atomically.

        Args:
            rows: The full set of rows to persist.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = self.path.with_suffix(".json.tmp")

        temp_path.write_text(
            json.dumps(rows, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        os.replace(temp_path, self.path)


def build_row(
    document_id: str,
    display_filename: str,
    stored_name: str,
    extension: str,
    size_bytes: int,
    status: DocumentStatus,
    chunk_count: int | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Build one manifest row.

    Args:
        document_id: Server-generated identifier.
        display_filename: The client's filename, for display.
        stored_name: Generated on-disk filename. Internal; never returned.
        extension: Lowercased validated extension.
        size_bytes: Bytes received from the client.
        status: Indexing outcome.
        chunk_count: Chunks committed, when indexing succeeded.
        error: Sanitized failure reason, when it did not.

    Returns:
        A JSON-serializable manifest row.
    """
    row: dict[str, Any] = {
        "document_id": document_id,
        "filename": display_filename,
        "stored_name": stored_name,
        "extension": extension,
        "size_bytes": size_bytes,
        "status": status.value,
        "uploaded_at": datetime.now().astimezone().isoformat(),
    }

    if chunk_count is not None:
        row["chunk_count"] = chunk_count

    if error is not None:
        row["error"] = error

    return row


_manifest: DocumentManifest | None = None


def get_manifest(settings: Settings | None = None) -> DocumentManifest:
    """Return the process-wide document manifest.

    Returns:
        The shared manifest store.
    """
    global _manifest

    if _manifest is None:
        resolved = settings or get_settings()

        _manifest = DocumentManifest(resolved.resolved_knowledge_upload_manifest_path)

    return _manifest


def set_manifest(manifest: DocumentManifest) -> None:
    """Install a manifest, typically a temporary one for tests.

    Args:
        manifest: The manifest to use for subsequent reads and writes.
    """
    global _manifest

    _manifest = manifest


def reset_manifest() -> None:
    """Restore the default manifest."""
    global _manifest

    _manifest = None


def record_document(
    row: dict[str, Any],
    manifest: DocumentManifest | None = None,
) -> dict[str, Any]:
    """Record one uploaded document.

    Recording never raises. The manifest is supporting metadata, so a write
    failure is logged rather than allowed to fail an upload that has already been
    indexed.

    Args:
        row: The row built by :func:`build_row`.
        manifest: Manifest to write to. Defaults to the process-wide store.

    Returns:
        The stored row, or the unsaved row if persistence failed.
    """
    try:
        return (manifest or get_manifest()).append(row)

    except Exception:
        logger.exception("knowledge_manifest_write_failed")

        return row


def list_documents(
    manifest: DocumentManifest | None = None,
    status: DocumentStatus | None = None,
    limit: int = MAX_RECORDS,
) -> list[dict[str, Any]]:
    """Return manifest rows, newest first.

    Args:
        manifest: Manifest to read from. Defaults to the process-wide store.
        status: Optional filter for one indexing outcome.
        limit: Maximum number of rows to return.

    Returns:
        Rows ordered newest to oldest.
    """
    rows = (manifest or get_manifest()).read()

    if status is not None:
        rows = [row for row in rows if row.get("status") == status.value]

    return list(reversed(rows))[:limit]
