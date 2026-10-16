"""Validation and local storage for documents uploaded to the Knowledge Agent.

The upload endpoint receives bytes over HTTP and hands the Knowledge Agent a
server-side path, because that is the only thing ``ingest_document`` accepts.
This module owns the awkward part of that translation: deciding whether the
bytes are acceptable, and turning an untrusted client filename into a stored
file that cannot escape the upload directory.

Storage is local disk on the machine running the API. That is a deliberate
development-MVP choice. A deployment needs persistent, shared storage and an
object store or equivalent; nothing else about the pipeline has to change when
that happens, because the agent only ever sees a path.

Validation happens in three layers, because each catches a different lie:

1. The extension, checked against an allowlist. This is the cheapest filter and
   the only one that decides which loader runs.
2. The declared size, enforced while streaming so an oversized upload is
   discarded instead of buffered.
3. The content itself, sniffed from the leading bytes and, for DOCX, from the
   ZIP directory. A ``.pdf`` that is really a script, or a truncated DOCX, is
   rejected here rather than inside the agent.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.core.config import Settings, get_settings
from app.core.exceptions import ValidationFailedError

logger = logging.getLogger(__name__)

#: Extensions the Knowledge loaders understand. Kept in step with
#: ``knowledge_agent/loaders/loader.py``: an extension outside this tuple would
#: reach the agent only to fail there as a 502.
SUPPORTED_EXTENSIONS: tuple[str, ...] = (".pdf", ".docx", ".txt")

#: Read at most this many bytes from the front of the stream to identify the
#: format. Signature and structure checks both operate on a prefix.
_SNIFF_BYTES = 4096

#: Streaming chunk size. Small enough that a large upload is never buffered.
_READ_CHUNK_BYTES = 64 * 1024

_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK"

#: Characters allowed to survive into the stored filename. Anything else
#: becomes an underscore, so the result can never contain a separator.
_UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")

#: Upper bound on the readable part of a stored filename, so the generated name
#: stays readable without letting a client dictate an arbitrarily long path.
_MAX_STEM_CHARS = 60


@dataclass(frozen=True)
class StoredDocument:
    """One uploaded file as it now exists on disk.

    Attributes:
        document_id: Server-generated identifier, also the manifest key.
        display_filename: The client's filename, kept for display only.
        stored_name: The generated on-disk filename. Never client-controlled.
        path: Absolute path of the stored file.
        size_bytes: Size actually written to disk.
        extension: Lowercased validated extension.
    """

    document_id: str
    display_filename: str
    stored_name: str
    path: Path
    size_bytes: int
    extension: str


class DocumentUploadService:
    """Validates uploads and writes them to the configured upload directory.

    Attributes:
        upload_dir: Absolute directory holding stored documents.
        max_bytes: Largest accepted upload.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        upload_dir: Path | None = None,
        max_bytes: int | None = None,
    ) -> None:
        """Initialize the service.

        Args:
            settings: Settings to read configuration from. Defaults to the
                process-wide settings.
            upload_dir: Override for the storage directory. Used by tests to
                keep uploads out of the repository.
            max_bytes: Override for the size limit. Used by tests to exercise
                the limit without allocating a large payload.
        """
        resolved = settings or get_settings()

        self.upload_dir = upload_dir or resolved.resolved_knowledge_upload_dir
        self.max_bytes = max_bytes if max_bytes is not None else resolved.knowledge_max_upload_bytes

    async def store(self, upload: UploadFile) -> StoredDocument:
        """Validate an upload and write it to the upload directory.

        The extension is checked before any byte is read, and the size limit is
        enforced during the write, so a rejected upload is abandoned early. A
        partially written file is always removed before returning or raising.

        Args:
            upload: The multipart file field sent by the client.

        Returns:
            The stored document, ready to hand to the ingestion pipeline.

        Raises:
            ValidationFailedError: If the filename, size, or content is not
                acceptable. The stored file, if any, has already been removed.
        """
        display_filename = self._display_filename(upload.filename)
        extension = self._validate_extension(display_filename)

        self.upload_dir.mkdir(parents=True, exist_ok=True)

        document_id = uuid.uuid4().hex
        stored_name = f"{document_id}_{_safe_stem(display_filename)}{extension}"
        target = self.upload_dir / stored_name

        size_bytes = await self._write(upload, target, display_filename, extension)

        try:
            _verify_content(target, extension, display_filename)
        except ValidationFailedError:
            _remove(target)
            raise

        logger.info(
            "knowledge_upload_stored extension=%s size_bytes=%d",
            extension,
            size_bytes,
        )

        return StoredDocument(
            document_id=document_id,
            display_filename=display_filename,
            stored_name=stored_name,
            path=target,
            size_bytes=size_bytes,
            extension=extension,
        )

    def discard(self, stored: StoredDocument) -> None:
        """Delete a stored document.

        Used to clean up when ingestion fails after the file was already saved,
        so a failed upload leaves nothing on disk and cannot be mistaken for an
        indexed document.

        Args:
            stored: The document to remove.
        """
        if not _remove(stored.path):
            logger.warning(
                "knowledge_upload_orphan_left name=%s",
                stored.stored_name,
            )

    def sweep_failed(self, stored_names: list[str]) -> int:
        """Delete stored files that a failed upload could not remove.

        A failed ingestion tries to delete its file immediately. On Windows that
        delete can fail, because the exception raised by the document loader
        carries a traceback whose frames still reference the open file, and the
        operating system refuses to remove a file with a live handle. The
        handle is released once the failed request is finished.

        So the leftover is recorded in the manifest with ``status: failed`` and
        swept here on a later upload, by which point the handle is gone. The
        document was never indexed, so nothing is lost by deleting it.

        Args:
            stored_names: Stored filenames of failed uploads to try to remove.

        Returns:
            The number of files removed.
        """
        removed = 0

        for stored_name in stored_names:
            path = self.upload_dir / Path(stored_name).name

            if not path.is_file():
                continue

            try:
                path.unlink()

            except PermissionError:
                logger.warning("knowledge_upload_cleanup_deferred name=%s", stored_name)

            except OSError:
                logger.exception("knowledge_upload_cleanup_failed name=%s", stored_name)

            else:
                removed += 1

        if removed:
            logger.info("knowledge_upload_failed_files_swept count=%d", removed)

        return removed

    async def _write(
        self,
        upload: UploadFile,
        target: Path,
        display_filename: str,
        extension: str,
    ) -> int:
        """Stream an upload to disk while enforcing the size limit.

        Args:
            upload: The multipart file field sent by the client.
            target: Destination path inside the upload directory.
            display_filename: Sanitized display name, used in error messages.
            extension: Validated lowercase extension, checked against the
                content signature.

        Returns:
            The number of bytes written.

        Raises:
            ValidationFailedError: If the upload is empty, exceeds the size
                limit, or has a non-matching signature.
        """
        size_bytes = 0
        head = b""

        try:
            # "x" refuses to overwrite. The generated name is a UUID, so a
            # collision is not expected, but silently replacing an existing
            # upload would be the wrong failure mode if it ever happened.
            with target.open("xb") as handle:
                while True:
                    chunk = await upload.read(_READ_CHUNK_BYTES)

                    if not chunk:
                        break

                    if not head:
                        head = chunk[:_SNIFF_BYTES]

                    size_bytes += len(chunk)

                    if size_bytes > self.max_bytes:
                        raise ValidationFailedError(
                            f"'{display_filename}' exceeds the maximum upload size of "
                            f"{self.max_bytes} bytes.",
                            details={
                                "max_bytes": self.max_bytes,
                                "filename": display_filename,
                            },
                        )

                    handle.write(chunk)

        except ValidationFailedError:
            _remove(target)
            raise

        except OSError as exc:
            _remove(target)
            logger.exception("knowledge_upload_write_failed")
            raise ValidationFailedError(
                f"'{display_filename}' could not be written to the upload directory.",
                details={"filename": display_filename},
            ) from exc

        if size_bytes == 0:
            _remove(target)
            raise ValidationFailedError(
                f"'{display_filename}' is empty.",
                details={"filename": display_filename},
            )

        _verify_signature(head, extension, display_filename, target)

        return size_bytes

    def _display_filename(self, filename: str | None) -> str:
        """Reduce a client filename to a safe display name.

        The name is for display only, but it is still echoed back and used in log
        lines, so any directory component is dropped here. A traversal attempt in
        the filename must not survive into a message or a stored stem.

        Args:
            filename: The filename as supplied by the client.

        Returns:
            A bare filename with no path separators.

        Raises:
            ValidationFailedError: If no usable filename was supplied.
        """
        candidate = (filename or "").replace("\\", "/")
        candidate = candidate.rsplit("/", 1)[-1].strip()

        if not candidate or candidate in {".", ".."}:
            raise ValidationFailedError(
                "A document filename is required.",
                details={"supported_extensions": list(SUPPORTED_EXTENSIONS)},
            )

        return candidate[:255]

    def _validate_extension(self, display_filename: str) -> str:
        """Return the validated lowercase extension for a filename.

        Args:
            display_filename: The sanitized display filename.

        Returns:
            The lowercase extension, one of :data:`SUPPORTED_EXTENSIONS`.

        Raises:
            ValidationFailedError: If the extension is not supported.
        """
        suffix = Path(display_filename).suffix.lower()

        if suffix not in SUPPORTED_EXTENSIONS:
            raise ValidationFailedError(
                f"'{display_filename}' is not a supported document type. "
                f"Supported types: {', '.join(SUPPORTED_EXTENSIONS)}.",
                details={
                    "filename": display_filename,
                    "supported_extensions": list(SUPPORTED_EXTENSIONS),
                },
            )

        return suffix


def _safe_stem(display_filename: str) -> str:
    """Return a readable, path-free stem for a stored filename.

    Args:
        display_filename: The sanitized display filename.

    Returns:
        A stem containing only ``A-Z``, ``a-z``, digits, dot, underscore, and
        hyphen, truncated to a fixed length. Falls back to ``document`` when
        nothing usable survives sanitization.
    """
    stem = Path(display_filename).stem
    cleaned = _UNSAFE_NAME_CHARS.sub("_", stem).strip("._-")

    return cleaned[:_MAX_STEM_CHARS] or "document"


def _verify_signature(
    head: bytes,
    extension: str,
    display_filename: str,
    target: Path,
) -> None:
    """Check the leading bytes against the declared extension.

    Args:
        head: The first bytes of the upload.
        extension: The validated lowercase extension.
        display_filename: The sanitized display filename, for error messages.
        target: The stored file, removed when the check fails.

    Raises:
        ValidationFailedError: If the content does not match the extension.
    """
    if extension == ".pdf" and not head.startswith(_PDF_MAGIC):
        _remove(target)
        raise ValidationFailedError(
            f"'{display_filename}' is not a readable PDF.",
            details={"filename": display_filename, "expected_signature": "PDF"},
        )

    if extension == ".docx" and not head.startswith(_ZIP_MAGIC):
        _remove(target)
        raise ValidationFailedError(
            f"'{display_filename}' is not a readable DOCX.",
            details={"filename": display_filename, "expected_signature": "DOCX"},
        )

    if extension == ".txt" and b"\x00" in head:
        _remove(target)
        raise ValidationFailedError(
            f"'{display_filename}' is not a readable text file.",
            details={"filename": display_filename, "expected_signature": "TXT"},
        )


def _verify_content(target: Path, extension: str, display_filename: str) -> None:
    """Check the stored file opens with the parser its extension implies.

    The signature check catches a mislabelled file. This catches a correctly
    labelled but malformed one, which would otherwise fail deep inside the
    agent as an opaque 502.

    Args:
        target: The stored file.
        extension: The validated lowercase extension.
        display_filename: The sanitized display filename, for error messages.

    Raises:
        ValidationFailedError: If the file cannot be parsed.
    """
    if extension == ".docx" and not _is_docx(target):
        raise ValidationFailedError(
            f"'{display_filename}' is not a readable DOCX archive.",
            details={"filename": display_filename, "expected_signature": "DOCX"},
        )

    if extension == ".txt" and not _is_text(target):
        raise ValidationFailedError(
            f"'{display_filename}' is not a readable UTF-8 text file.",
            details={"filename": display_filename, "expected_signature": "TXT"},
        )


def _is_docx(path: Path) -> bool:
    """Report whether a file is a DOCX archive with a Word document part.

    Args:
        path: The stored file.

    Returns:
        True when the file is a ZIP archive containing ``word/document.xml``.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            return "word/document.xml" in archive.namelist()
    except (zipfile.BadZipFile, OSError):
        logger.warning("knowledge_upload_bad_docx name=%s", path.name)

        return False


def _is_text(path: Path) -> bool:
    """Report whether a file decodes as UTF-8 and holds no NUL bytes.

    Args:
        path: The stored file.

    Returns:
        True when the content is decodable text.
    """
    try:
        raw = path.read_bytes()
    except OSError:
        logger.warning("knowledge_upload_unreadable name=%s", path.name)

        return False

    if b"\x00" in raw:
        return False

    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return False

    return bool(raw.strip())


#: Delete attempts before giving up on the final unlink.
_UNLINK_ATTEMPTS = 5

#: Delay between delete attempts, in seconds.
_UNLINK_RETRY_SECONDS = 0.1


def _remove(path: Path) -> bool:
    """Delete a file, retrying briefly and ignoring a missing one.

    Cleanup must never mask the failure that triggered it, so an unlink error is
    logged rather than raised.

    Args:
        path: The file to delete.

    Returns:
        True when the file is gone, False when it could not be deleted.
    """
    for attempt in range(_UNLINK_ATTEMPTS):
        try:
            path.unlink(missing_ok=True)

            return True

        except PermissionError:
            if attempt == _UNLINK_ATTEMPTS - 1:
                logger.warning("knowledge_upload_cleanup_deferred name=%s", path.name)

                return False
            time.sleep(_UNLINK_RETRY_SECONDS)

        except OSError:
            logger.exception("knowledge_upload_cleanup_failed name=%s", path.name)

            return False

    return False


_default_service: DocumentUploadService | None = None


def get_upload_service() -> DocumentUploadService:
    """Return the process-wide upload service.

    Created on first use rather than during startup so that a read-only
    deployment still boots, and so the directory is created only when something
    is actually uploaded.

    Returns:
        The shared upload service.
    """
    global _default_service

    if _default_service is None:
        _default_service = DocumentUploadService()

    return _default_service


def set_upload_service(service: DocumentUploadService) -> None:
    """Install an upload service, typically a temporary one for tests.

    Args:
        service: The service to use for subsequent uploads.
    """
    global _default_service

    _default_service = service


def reset_upload_service() -> None:
    """Restore the default upload service."""
    global _default_service

    _default_service = None
