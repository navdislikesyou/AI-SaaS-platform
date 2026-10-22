"""Validation and local storage for datasets uploaded to the Performance Analyzer.

The Performance Analyzer reads a dataset from the filesystem and hands it to
pandas, so a browser upload has to end as a trusted server-side path. This module
owns that translation: deciding whether the uploaded bytes are a dataset the
analyzers could actually read, and turning an untrusted client filename into a
stored file that cannot escape the upload directory.

Storage is local disk on the machine running the API. That is a deliberate
development-MVP choice, matching the Knowledge and Automation upload directories.
Known limitations of that choice, restated because they are not obvious from the
code:

* Uploaded datasets are **not shared between instances**. A second process, or a
  container without this volume, does not see them.
* Uploaded datasets **do not survive** replacing the container or the checkout,
  because nothing backs the directory.
* The manifest is a **single JSON file**, so concurrent writes from several
  processes are not safe.
* There is **no delete route**, so the directory grows until an operator removes
  files by hand.

A deployment needs persistent, shared storage and a real metadata store. Nothing
else about the pipeline has to change when that happens, because the agent and the
job runner only ever see a path.

Validation happens in four layers, because each catches a different problem:

1. The extension, checked against an allowlist before any byte is read. This is
   the cheapest filter and the only one that decides which parser runs.
2. The size, enforced while streaming so an oversized upload is discarded rather
   than buffered, plus a NUL byte in the leading content for CSV, which means the
   upload is not text at all.
3. The container format. An XLSX must be a ZIP archive, so a CSV renamed
   ``.xlsx`` is rejected here rather than deep inside the parser.
4. The content itself, read through a **bounded** preview: only the header and a
   few rows are parsed, which proves the file is readable and yields its real
   column names without ever materializing the whole dataset. This is what
   separates "uploaded a file" from "uploaded something pandas cannot open".
   The preview also settles the three questions a dataset raises in practice: a
   CSV that is not UTF-8, a header row that names no column, and a file that
   holds a header but no data rows are each refused with a message that says
   which of them it is.

``.xls`` is deliberately unsupported. ``pandas.read_excel`` routes it to the
``xlrd`` engine, which is not a dependency of this project, so a ``.xls`` would be
accepted here only to fail later as an opaque job error. It is rejected up front
instead, and the error names the formats that do work.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app.core.config import Settings, get_settings
from app.core.exceptions import DatasetNotFoundError, ValidationFailedError
from app.schemas.performance import DatasetStatus

logger = logging.getLogger(__name__)

#: Formats a browser upload may use. Narrower than
#: ``performance_agent.dataset.SUPPORTED_EXTENSIONS`` on purpose: that tuple
#: includes ``.xls``, which cannot actually be read without ``xlrd``. An
#: operator pointing a job straight at a ``.xls`` on disk still fails in the
#: loader exactly as before, but an upload is refused early with a message that
#: says what to do instead.
SUPPORTED_EXTENSIONS: tuple[str, ...] = (".csv", ".xlsx")

#: Reserved identifier for the dataset shipped inside the agent package. A
#: client may send this value but never a path, which is what lets the default
#: dataset stay reachable from a browser without exposing the filesystem.
SAMPLE_DATASET_ID = "sample"

#: Rows read while validating an upload. Enough to prove the parser works and to
#: learn the header; small enough that validation cost does not scale with the
#: file, which is the point of doing it at all.
PREVIEW_ROWS: int = 5

#: Column names reported back to the client. A wide sheet would otherwise make
#: the upload response unbounded.
_MAX_REPORTED_COLUMNS: int = 200

#: Cap on retained manifest rows. The manifest is read by a dataset list on
#: every page load, so an unbounded file would grow without limit in a
#: long-running process.
MAX_RECORDS: int = 500

#: Streaming chunk size. Small enough that a large upload is never buffered.
_READ_CHUNK_BYTES = 64 * 1024

#: Bytes read from the front of the stream to check the container format.
_SNIFF_BYTES = 4096

#: Every XLSX file is a ZIP archive, so it always starts with one of these.
_ZIP_MAGICS: tuple[bytes, ...] = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")

#: Characters allowed to survive into the stored filename. Anything else becomes
#: an underscore, so the result can never contain a separator.
_UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")

#: The placeholder name pandas gives a header cell that is blank. A header row
#: of blank cells therefore comes back as "Unnamed: 0", "Unnamed: 1", and so on,
#: which names no column an analyzer could resolve.
_UNNAMED_COLUMN = re.compile(r"^unnamed: \d+$", re.IGNORECASE)

#: Upper bound on the readable part of a stored filename, so the generated name
#: stays readable without letting a client dictate an arbitrarily long path.
_MAX_STEM_CHARS = 60

#: Delete attempts before giving up on the final unlink.
_UNLINK_ATTEMPTS = 5

#: Delay between delete attempts, in seconds.
_UNLINK_RETRY_SECONDS = 0.1

_write_lock = threading.Lock()


@dataclass(frozen=True)
class StoredDataset:
    """One uploaded dataset as it now exists on disk.

    Attributes:
        dataset_id: Server-generated identifier, also the manifest key and the
            only thing a client ever refers to.
        display_filename: The client's filename, kept for display only.
        stored_name: The generated on-disk filename. Never client-controlled and
            never returned.
        path: Absolute path of the stored file. Stays inside this process.
        size_bytes: Size actually written to disk.
        extension: Lowercased validated extension.
        column_names: Normalized column names read from the header.
    """

    dataset_id: str
    display_filename: str
    stored_name: str
    path: Path
    size_bytes: int
    extension: str
    column_names: tuple[str, ...]


@dataclass(frozen=True)
class StoredDatasetRow:
    """One manifest row, read back defensively.

    The manifest is a plain JSON file that a hand edit or a partial write could
    make inconsistent, so every field is coerced on the way out rather than
    trusted.

    Attributes:
        dataset_id: Server-generated identifier.
        display_filename: The client's filename, for display.
        stored_name: Generated on-disk filename. Internal; never returned.
        extension: Lowercased validated extension.
        size_bytes: Bytes received from the client.
        status: Validation outcome.
        uploaded_at: ISO 8601 upload timestamp.
        column_names: Normalized column names read from the header.
    """

    dataset_id: str
    display_filename: str
    stored_name: str
    extension: str
    size_bytes: int
    status: DatasetStatus
    uploaded_at: datetime
    column_names: tuple[str, ...] = ()


class DatasetManifest:
    """JSON-file backed store of uploaded dataset metadata.

    Attributes:
        path: The manifest file. Its parent directory is created on first write.
    """

    def __init__(self, path: Path | None = None) -> None:
        """Initialize the manifest.

        Args:
            path: Manifest file path. Defaults to the configured location under
                the upload directory.
        """
        resolved = path or get_settings().resolved_performance_upload_manifest_path

        self.path = Path(resolved)

    def read(self) -> list[dict[str, Any]]:
        """Read all manifest rows.

        A missing file is an empty manifest, not an error. A corrupt file is also
        treated as empty rather than breaking the dataset list, and is logged.

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
                logger.warning("performance_manifest_not_a_list name=%s", self.path.name)

                return []

            return [row for row in parsed if isinstance(row, dict)]

        except json.JSONDecodeError:
            logger.warning("performance_manifest_corrupt name=%s", self.path.name)

            return []

        except OSError:
            logger.warning("performance_manifest_unreadable name=%s", self.path.name)

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


class DatasetUploadService:
    """Validates uploads and resolves dataset ids to trusted paths.

    Attributes:
        upload_dir: Absolute directory holding stored datasets.
        max_bytes: Largest accepted upload.
        settings: Settings supplying the packaged sample dataset path.
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
            upload_dir: Override for the storage directory. Used by tests to keep
                uploads out of the repository.
            max_bytes: Override for the size limit. Used by tests to exercise the
                limit without allocating a large payload.
        """
        resolved = settings or get_settings()

        self._settings = resolved

        self.upload_dir = upload_dir or resolved.resolved_performance_upload_dir
        self.max_bytes = (
            max_bytes if max_bytes is not None else resolved.performance_max_upload_bytes
        )

    # ------------------------------------------------------------------
    # Uploads
    # ------------------------------------------------------------------

    async def store(self, upload: UploadFile) -> StoredDataset:
        """Validate an upload and write it to the upload directory.

        The extension is checked before any byte is read, the size limit is
        enforced during the write, and the content is checked after it. A
        partially written or unreadable file is always removed before returning
        or raising, so a rejected upload leaves nothing on disk.

        Args:
            upload: The multipart file field sent by the client.

        Returns:
            The stored dataset, ready to hand to a job.

        Raises:
            ValidationFailedError: If the filename, size, or content is not
                acceptable. The stored file, if any, has already been removed.
        """
        display_filename = self._display_filename(upload.filename)
        extension = self._validate_extension(display_filename)

        self.upload_dir.mkdir(parents=True, exist_ok=True)

        dataset_id = uuid.uuid4().hex
        stored_name = f"{dataset_id}_{_safe_stem(display_filename)}{extension}"
        target = self.upload_dir / stored_name

        size_bytes = await self._write(upload, target, display_filename, extension)

        try:
            column_names = _preview_columns(target, extension, display_filename)
        except ValidationFailedError:
            _remove(target)
            raise

        logger.info(
            "performance_dataset_stored extension=%s size_bytes=%d columns=%d",
            extension,
            size_bytes,
            len(column_names),
        )

        return StoredDataset(
            dataset_id=dataset_id,
            display_filename=display_filename,
            stored_name=stored_name,
            path=target,
            size_bytes=size_bytes,
            extension=extension,
            column_names=tuple(column_names),
        )

    def discard(self, stored: StoredDataset) -> None:
        """Delete a stored dataset.

        Used to clean up when a later step fails after the file was saved, so a
        failed upload leaves nothing behind and cannot be mistaken for a usable
        dataset.

        Args:
            stored: The dataset to remove.
        """
        if not _remove(stored.path):
            logger.warning(
                "performance_dataset_orphan_left name=%s",
                stored.stored_name,
            )

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
                container signature.

        Returns:
            The number of bytes written.

        Raises:
            ValidationFailedError: If the upload is empty, exceeds the size
                limit, or does not match its extension.
        """
        size_bytes = 0
        head = b""

        try:
            # "x" refuses to overwrite. The generated name carries a UUID, so a
            # collision is not expected, but silently replacing an existing
            # upload would be the wrong failure mode if it ever happened. It is
            # also what makes overwriting a packaged sample dataset impossible:
            # samples live in the agent package, never in this directory.
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
            logger.exception("performance_dataset_write_failed")
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
                "A dataset filename is required.",
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
                f"'{display_filename}' is not a supported dataset type. "
                f"Supported types: {', '.join(SUPPORTED_EXTENSIONS)}.",
                details={
                    "filename": display_filename,
                    "supported_extensions": list(SUPPORTED_EXTENSIONS),
                },
            )

        return suffix

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve(self, dataset_id: str, manifest: DatasetManifest | None = None) -> Path:
        """Resolve a dataset id to a trusted path the job runner may read.

        This is the only bridge from a client-supplied reference to a filesystem
        path, and it resolves in one direction only: an id is looked up in the
        manifest, and the stored name from that row is reduced to a bare filename
        before being joined to the upload directory. The id is never treated as
        a path fragment, so ``../../etc/passwd`` and an absolute path are simply
        unknown ids.

        The reserved id ``sample`` resolves to the packaged dataset configured on
        the server. No client-supplied string is ever resolved against the
        filesystem.

        Args:
            dataset_id: The reference a client supplied.
            manifest: Manifest to resolve against. Defaults to the process-wide
                store.

        Returns:
            An absolute path inside the upload directory, or the packaged sample
            dataset path.

        Raises:
            DatasetNotFoundError: If the id is unknown, is not ``sample``, or its
                stored file is gone. Callers must not fall back to another
                dataset.
        """
        candidate = (dataset_id or "").strip()

        if not candidate or "/" in candidate or "\\" in candidate:
            raise DatasetNotFoundError(
                "That dataset could not be resolved. Upload the dataset again.",
                details={"dataset_id": dataset_id},
            )

        if candidate == SAMPLE_DATASET_ID:
            return self._sample_path()

        row = find_dataset_row(candidate, manifest)

        if row is None:
            raise DatasetNotFoundError(
                f"Dataset '{candidate}' was not found.",
                details={"dataset_id": candidate},
            )

        # The stored name comes from a file on disk, not from the client, and is
        # reduced to a bare filename anyway. Belt and braces: a hand-edited
        # manifest cannot escape the upload directory through this line.
        stored_name = Path(str(row.get("stored_name") or "")).name

        if not stored_name or stored_name in {".", ".."}:
            raise DatasetNotFoundError(
                f"Dataset '{candidate}' was not found.",
                details={"dataset_id": candidate},
            )

        target = self.upload_dir / stored_name

        if not target.is_file():
            logger.warning("performance_dataset_file_missing id=%s", candidate)

            raise DatasetNotFoundError(
                f"Dataset '{candidate}' is no longer available.",
                details={"dataset_id": candidate},
            )

        return target

    def sample_entry(self) -> dict[str, Any]:
        """Describe the packaged sample dataset for a client.

        Returns:
            Metadata for the reserved ``sample`` id. The filename is the bare
            basename, never the configured path, so the response discloses no
            server directory layout. When the packaged file is absent the entry
            reports it rather than pretending the dataset is available.
        """
        path = self._sample_path()

        return {
            "dataset_id": SAMPLE_DATASET_ID,
            "filename": path.name,
            "format": path.suffix.lower().lstrip("."),
            "size_bytes": path.stat().st_size if path.is_file() else 0,
            "available": path.is_file(),
        }

    def _sample_path(self) -> Path:
        """Return the configured packaged sample dataset path.

        Returns:
            The absolute path from settings. Existence is not checked here;
            callers that need it check for themselves.
        """
        return self._settings.resolved_performance_sample_dataset_path


# --------------------------------------------------------------------------
# Content verification
# --------------------------------------------------------------------------


def _safe_stem(display_filename: str) -> str:
    """Return a readable, path-free stem for a stored filename.

    Args:
        display_filename: The sanitized display filename.

    Returns:
        A stem containing only ``A-Z``, ``a-z``, digits, dot, underscore, and
        hyphen, truncated to a fixed length. Falls back to ``dataset`` when
        nothing usable survives sanitization.
    """
    stem = Path(display_filename).stem
    cleaned = _UNSAFE_NAME_CHARS.sub("_", stem).strip("._-")

    return cleaned[:_MAX_STEM_CHARS] or "dataset"


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
    if extension == ".xlsx" and not head.startswith(_ZIP_MAGICS):
        _remove(target)
        raise ValidationFailedError(
            f"'{display_filename}' is not a readable XLSX workbook. "
            "Save the file as .xlsx rather than renaming a CSV.",
            details={"filename": display_filename, "expected_signature": "XLSX"},
        )

    if extension == ".csv" and b"\x00" in head:
        _remove(target)
        raise ValidationFailedError(
            f"'{display_filename}' is not readable as a text file.",
            details={"filename": display_filename, "expected_signature": "CSV"},
        )


def _preview_columns(
    target: Path,
    extension: str,
    display_filename: str,
) -> list[str]:
    """Read a bounded preview of a dataset and return its column names.

    This is the whole reason the upload path parses anything at all: it proves
    the file is readable by the parser its extension implies, and it yields the
    real header. Only :data:`PREVIEW_ROWS` rows are read, so validation cost does
    not scale with file size and a large workbook is never fully materialized
    just to be accepted.

    Column names are normalized exactly as the analyzers see them, so what the
    client is told matches what a later job will actually look for.

    Args:
        target: The stored file.
        extension: The validated lowercase extension, which selects the reader.
        display_filename: The sanitized display filename, for error messages.

    Returns:
        Normalized column names, capped at :data:`_MAX_REPORTED_COLUMNS`.

    Raises:
        ValidationFailedError: If the file cannot be read as a dataset, has no
            usable header row, or holds no data rows.
    """
    # Imported here rather than at module scope for the same reason
    # JobManager._load_frame defers it: this module must stay importable on an
    # API-only install that has not installed the agent dependencies.
    import pandas as pd

    from performance_agent.dataset import normalize_column_names

    try:
        if extension == ".csv":
            frame = pd.read_csv(target, nrows=PREVIEW_ROWS)
        else:
            # sheet_name is deliberately left unset, which reads the first
            # worksheet. That is the same behaviour the job runner gets, so an
            # upload cannot appear to work and then analyze a different sheet.
            frame = pd.read_excel(target, nrows=PREVIEW_ROWS)

    except UnicodeDecodeError as exc:
        # The reader decodes a CSV as UTF-8, so this is an encoding problem and
        # not a structural one. Saying so is more useful than "unreadable",
        # because the fix is to re-save the file rather than to repair it.
        logger.warning(
            "performance_dataset_not_utf8 name=%s error=%s",
            target.name,
            exc.__class__.__name__,
        )

        raise ValidationFailedError(
            f"'{display_filename}' is not readable as UTF-8 text. Re-save the file "
            "as UTF-8 CSV.",
            details={"filename": display_filename, "expected_encoding": "utf-8"},
        ) from exc

    except ValidationFailedError:
        raise

    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        # ParserError and EmptyDataError are both ValueError subclasses, and
        # BadZipFile is what a truncated workbook raises. None of these messages
        # are returned: they routinely embed the absolute path.
        logger.warning(
            "performance_dataset_unreadable name=%s error=%s",
            target.name,
            exc.__class__.__name__,
        )

        raise ValidationFailedError(
            f"'{display_filename}' could not be read as a {extension.lstrip('.').upper()} "
            "dataset. Check that the file is not corrupted and that the first row "
            "holds column names.",
            details={"filename": display_filename},
        ) from exc

    except Exception as exc:
        # openpyxl and the XML stack behind it raise their own exception types,
        # which are not importable without the engine installed.
        logger.warning(
            "performance_dataset_parse_failed name=%s error=%s",
            target.name,
            exc.__class__.__name__,
        )

        raise ValidationFailedError(
            f"'{display_filename}' could not be read as a "
            f"{extension.lstrip('.').upper()} dataset.",
            details={"filename": display_filename},
        ) from exc

    if len(frame.columns) == 0 or not _has_usable_header(frame.columns):
        # pandas always names the columns it reads, so an empty column list is
        # rare, and a header row of blank cells comes back as the placeholder
        # names "Unnamed: 0", "Unnamed: 1", and so on. Either way the file
        # carries no column names, and every analyzer would look for columns
        # that do not exist.
        raise ValidationFailedError(
            f"'{display_filename}' has no column names. The first row of a dataset "
            "must hold its headers.",
            details={"filename": display_filename},
        )

    if len(frame.index) == 0:
        # A header and nothing else cannot produce an analysis. Refusing it here
        # gives a useful reason instead of a job that completes with no output.
        raise ValidationFailedError(
            f"'{display_filename}' has a header row but no data rows.",
            details={"filename": display_filename},
        )

    normalized = normalize_column_names(frame)

    return [str(column) for column in normalized.columns][:_MAX_REPORTED_COLUMNS]


def _has_usable_header(columns: Any) -> bool:
    """Report whether a parsed header names at least one column.

    A header row of blank cells is read by pandas as the placeholder names
    ``Unnamed: 0``, ``Unnamed: 1``, and so on, and a row of spaces becomes
    empty strings. Neither is a column name an analyzer could resolve.

    Args:
        columns: The columns of the parsed preview frame.

    Returns:
        True when at least one column carries a name of its own.
    """
    for column in columns:
        name = str(column).strip()

        if not name or _UNNAMED_COLUMN.match(name):
            continue

        return True

    return False


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
                logger.warning(
                    "performance_dataset_cleanup_deferred name=%s",
                    path.name,
                )

            time.sleep(_UNLINK_RETRY_SECONDS)

        except OSError:
            logger.exception("performance_dataset_cleanup_failed name=%s", path.name)

            return False

    return False


# --------------------------------------------------------------------------
# Manifest access
# --------------------------------------------------------------------------


def build_row(
    dataset_id: str,
    display_filename: str,
    stored_name: str,
    extension: str,
    size_bytes: int,
    status: DatasetStatus,
    column_names: list[str] | None = None,
    organization_id: str | None = None,
    owner_id: str | None = None,
) -> dict[str, Any]:
    """Build one manifest row.

    Args:
        dataset_id: Server-generated identifier.
        display_filename: The client's filename, for display.
        stored_name: Generated on-disk filename. Internal; never returned.
        extension: Lowercased validated extension.
        size_bytes: Bytes received from the client.
        status: Validation outcome.
        column_names: Normalized column names read from the header.
        organization_id: The organisation that owns the dataset.
        owner_id: The user who uploaded the dataset.

    Returns:
        A JSON-serializable manifest row.
    """
    row: dict[str, Any] = {
        "dataset_id": dataset_id,
        "filename": display_filename,
        "stored_name": stored_name,
        "extension": extension,
        "size_bytes": size_bytes,
        "status": status.value,
        "column_names": list(column_names or []),
        "uploaded_at": datetime.now().astimezone().isoformat(),
    }

    if organization_id is not None:
        row["organization_id"] = organization_id
    if owner_id is not None:
        row["owner_id"] = owner_id

    return row


def record_dataset(
    row: dict[str, Any],
    manifest: DatasetManifest | None = None,
) -> dict[str, Any]:
    """Record one uploaded dataset.

    Recording never raises. The manifest is supporting metadata, so a write
    failure is logged rather than allowed to fail an upload that already
    succeeded.

    Args:
        row: The row built by :func:`build_row`.
        manifest: Manifest to write to. Defaults to the process-wide store.

    Returns:
        The stored row, or the unsaved row if persistence failed.
    """
    try:
        return (manifest or get_manifest()).append(row)

    except Exception:
        logger.exception("performance_manifest_write_failed")

        return row


def list_datasets(
    manifest: DatasetManifest | None = None,
    status: DatasetStatus | None = None,
    limit: int = MAX_RECORDS,
) -> list[dict[str, Any]]:
    """Return manifest rows, newest first.

    Args:
        manifest: Manifest to read from. Defaults to the process-wide store.
        status: Optional filter for one validation outcome.
        limit: Maximum number of rows to return.

    Returns:
        Rows ordered newest to oldest.
    """
    rows = (manifest or get_manifest()).read()

    if status is not None:
        rows = [row for row in rows if row.get("status") == status.value]

    return list(reversed(rows))[:limit]


def find_dataset_row(
    dataset_id: str,
    manifest: DatasetManifest | None = None,
) -> dict[str, Any] | None:
    """Return the manifest row for one dataset id.

    Args:
        dataset_id: The identifier a client supplied.
        manifest: Manifest to read from. Defaults to the process-wide store.

    Returns:
        The matching row, or None when no row carries that id.
    """
    if not dataset_id:
        return None

    for row in (manifest or get_manifest()).read():
        if str(row.get("dataset_id") or "") == dataset_id:
            return row

    return None


def row_to_stored(row: dict[str, Any]) -> StoredDatasetRow:
    """Coerce one manifest row into a typed record.

    Every field is coerced rather than trusted: the manifest is a plain JSON file
    that a hand edit or a partial write could make inconsistent, and a malformed
    row must not break the dataset list.

    Args:
        row: A raw manifest row.

    Returns:
        A populated record. An unreadable status degrades to ``FAILED`` so a
        damaged row is never presented as usable.
    """
    raw_columns = row.get("column_names")

    columns: tuple[str, ...] = ()

    if isinstance(raw_columns, list):
        columns = tuple(str(column) for column in raw_columns)

    return StoredDatasetRow(
        dataset_id=str(row.get("dataset_id") or ""),
        display_filename=str(row.get("filename") or ""),
        stored_name=str(row.get("stored_name") or ""),
        extension=str(row.get("extension") or ""),
        size_bytes=_as_int(row.get("size_bytes")),
        status=_as_status(row.get("status")),
        uploaded_at=_as_timestamp(row.get("uploaded_at")),
        column_names=columns,
    )


def _as_int(value: Any) -> int:
    """Coerce a manifest value to a non-negative integer.

    Args:
        value: The raw value.

    Returns:
        The parsed integer, or zero when it is absent or unparseable.
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0

    return max(parsed, 0)


def _as_status(value: Any) -> DatasetStatus:
    """Coerce a manifest value to a dataset status.

    Args:
        value: The raw value.

    Returns:
        The matching status, defaulting to ``FAILED`` so an unreadable row is
        never shown as usable.
    """
    try:
        return DatasetStatus(str(value))
    except ValueError:
        return DatasetStatus.FAILED


def _as_timestamp(value: Any) -> datetime:
    """Coerce a manifest value to a timestamp.

    Args:
        value: The raw value, expected to be ISO 8601.

    Returns:
        The parsed timestamp, falling back to the Unix epoch so a row with an
        unreadable timestamp still sorts and renders.
    """
    if isinstance(value, datetime):
        return value

    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        logger.warning("performance_manifest_bad_timestamp value=%s", value)

        return datetime.fromtimestamp(0, tz=UTC)


# --------------------------------------------------------------------------
# Process-wide instances
# --------------------------------------------------------------------------

_default_service: DatasetUploadService | None = None
_manifest: DatasetManifest | None = None


def get_dataset_service(settings: Settings | None = None) -> DatasetUploadService:
    """Return the process-wide dataset upload service.

    Created on first use rather than during startup so that a deployment with no
    uploads never creates the upload directory.

    Args:
        settings: Settings supplying the upload directory. Defaults to the
            process-wide settings.

    Returns:
        The shared upload service.
    """
    global _default_service

    if _default_service is None:
        _default_service = DatasetUploadService(settings)

    return _default_service


def set_dataset_service(service: DatasetUploadService | None) -> None:
    """Install an upload service, typically a temporary one for tests.

    Args:
        service: The service to use for subsequent uploads, or None to restore
            the default.
    """
    global _default_service

    _default_service = service


def get_manifest(settings: Settings | None = None) -> DatasetManifest:
    """Return the process-wide dataset manifest.

    Args:
        settings: Settings to read configuration from. Defaults to the
            process-wide settings.

    Returns:
        The shared manifest store.
    """
    global _manifest

    if _manifest is None:
        resolved = settings or get_settings()

        _manifest = DatasetManifest(resolved.resolved_performance_upload_manifest_path)

    return _manifest


def set_manifest(manifest: DatasetManifest | None) -> None:
    """Install a manifest, typically a temporary one for tests.

    Args:
        manifest: The manifest to use for subsequent reads and writes, or None
            to restore the default.
    """
    global _manifest

    _manifest = manifest


set_dataset_manifest_store = set_manifest
"""Alias for ``set_manifest``, used by ``app.api.deps.reset_state``."""
