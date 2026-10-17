"""Validation and local storage for employee directories uploaded to the Automation Agent.

The Automation Agent resolves attendee names against a directory of employee
records. That directory ships inside the agent package, which is the right
default and the only one available until someone uploads another one. This
module owns the alternative: deciding whether an uploaded file is a usable
directory, turning an untrusted client filename into a stored file that cannot
escape the upload directory, and normalising the records down to the two fields
the agent actually reads.

Records are reduced to ``name`` and ``email`` and nothing else, at parse time.
An uploaded file may carry more columns, and those are dropped rather than
stored, so there is no internal field that could later be echoed back to a
browser through the recipients array.

Storage is local disk on the machine running the API, which is a deliberate
development-MVP choice for the same reasons as the Knowledge upload directory.
A deployment needs persistent, shared storage and a real metadata store; nothing
else about the pipeline has to change, because the agent only ever receives a
list of records.

Validation happens in four layers, because each catches a different problem:

1. The extension, checked against an allowlist before any byte is read. This is
   the cheapest filter and the only one that decides which parser runs.
2. The declared size, enforced while streaming so an oversized upload is
   discarded instead of buffered, and a NUL byte in the leading content, which
   means the upload is not text at all.
3. The structure: JSON must be a list of objects, CSV must have a header naming
   ``name`` and ``email``. A mislabelled file is rejected here rather than
   surfacing later as an opaque drafting failure.
4. Each record: required fields present and non-blank, a plausible email, no
   duplicate name, no duplicate email, and a bounded employee count.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app.core.config import Settings, get_settings
from app.core.exceptions import DirectoryNotFoundError, ValidationFailedError

logger = logging.getLogger(__name__)

#: Formats the directory parser understands. Kept as a module constant so the
#: router, the error messages, and the tests all agree on the list. XLSX is
#: deliberately absent: reading it needs a dependency that is not part of an
#: API-only install, and adding one here would make the Automation adapter
#: unavailable on deployments that never upload a spreadsheet.
SUPPORTED_FORMATS: tuple[str, ...] = (".json", ".csv")

#: The only fields the Automation Agent reads. Every other column in an uploaded
#: file is discarded during parsing.
REQUIRED_FIELDS: tuple[str, ...] = ("name", "email")

#: Records returned in an upload response so the user can preview a directory
#: without a second request. The full list is available from the detail route.
PREVIEW_LIMIT: int = 20

#: Cap on retained manifest rows. The manifest is read by a directory list on
#: every page load, so an unbounded file would grow without limit in a
#: long-running process.
MAX_RECORDS: int = 500

#: Streaming chunk size. Small enough that a large upload is never buffered.
_READ_CHUNK_BYTES = 64 * 1024

#: Bytes read from the front of the stream to check that the upload is text.
_SNIFF_BYTES = 4096

#: Characters allowed to survive into the stored filename. Anything else becomes
#: an underscore, so the result can never contain a separator.
_UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")

#: Upper bound on the readable part of a stored filename, so the generated name
#: stays readable without letting a client dictate an arbitrarily long path.
_MAX_STEM_CHARS = 60

#: Longest accepted employee name. Long enough for any real name, short enough
#: to bound a single match during attendee resolution.
_MAX_NAME_CHARS = 120

#: RFC 5321 caps a forward path at 254 characters.
_MAX_EMAIL_CHARS = 254

#: Deliberately permissive address shape. The goal is to reject typos that would
#: make a draft undeliverable, not to reimplement RFC 5322. The standard
#: library's ``email`` module is not used here because the Automation adapter's
#: tests forbid importing it anywhere in the agent code path, to keep mail
#: handling out of a drafting agent.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

#: Delete attempts before giving up on the final unlink.
_UNLINK_ATTEMPTS = 5

#: Delay between delete attempts, in seconds.
_UNLINK_RETRY_SECONDS = 0.1

_write_lock = threading.Lock()


class DirectoryStatus(StrEnum):
    """Outcome for one uploaded employee directory.

    Attributes:
        READY: The file parsed and every record passed validation.
        FAILED: The file was stored but its records did not validate. It is
            listed as unusable rather than hidden, so the upload history is
            honest about what was attempted.
    """

    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True)
class StoredDirectory:
    """One uploaded employee directory as it now exists on disk.

    Attributes:
        directory_id: Server-generated identifier, also the manifest key and the
            only thing a client ever refers to.
        display_filename: The client's filename, kept for display only.
        stored_name: The generated on-disk filename. Never client-controlled and
            never returned.
        path: Absolute path of the stored file.
        size_bytes: Size actually written to disk.
        extension: Lowercased validated extension.
        records: The normalised ``name`` and ``email`` pairs read from the file.
    """

    directory_id: str
    display_filename: str
    stored_name: str
    path: Path
    size_bytes: int
    extension: str
    records: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class StoredDirectoryRow:
    """One manifest row, read back defensively.

    The manifest is a plain JSON file that a hand edit or a partial write could
    make inconsistent, so every field is coerced on the way out rather than
    trusted.

    Attributes:
        directory_id: Server-generated identifier.
        display_filename: The client's filename, for display.
        stored_name: Generated on-disk filename. Internal; never returned.
        extension: Lowercased validated extension.
        size_bytes: Bytes received from the client.
        status: Validation outcome.
        employee_count: Records accepted, when validation succeeded.
        uploaded_at: ISO 8601 upload timestamp.
        error: Sanitized failure reason, when validation did not succeed.
    """

    directory_id: str
    display_filename: str
    stored_name: str
    extension: str
    size_bytes: int
    status: DirectoryStatus
    uploaded_at: datetime
    employee_count: int | None = None
    error: str | None = None


class EmployeeDirectoryManifest:
    """JSON-file backed store of uploaded employee directory metadata.

    Attributes:
        path: The manifest file. Its parent directory is created on first write.
    """

    def __init__(self, path: Path | None = None) -> None:
        """Initialize the manifest.

        Args:
            path: Manifest file path. Defaults to the configured location under
                the upload directory.
        """
        resolved = path or get_settings().resolved_automation_upload_manifest_path

        self.path = Path(resolved)

    def read(self) -> list[dict[str, Any]]:
        """Read all manifest rows.

        A missing file is an empty manifest, not an error. A corrupt file is also
        treated as empty rather than breaking the directory list, and is logged.

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
                logger.warning("automation_manifest_not_a_list name=%s", self.path.name)

                return []

            return [row for row in parsed if isinstance(row, dict)]

        except json.JSONDecodeError:
            logger.warning("automation_manifest_corrupt name=%s", self.path.name)

            return []

        except OSError:
            logger.warning("automation_manifest_unreadable name=%s", self.path.name)

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


class EmployeeDirectoryService:
    """Validates uploads and writes them to the configured upload directory.

    Attributes:
        upload_dir: Absolute directory holding stored employee directories.
        max_bytes: Largest accepted upload.
        max_employees: Largest accepted employee count in one directory.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        upload_dir: Path | None = None,
        max_bytes: int | None = None,
        max_employees: int | None = None,
    ) -> None:
        """Initialize the service.

        Args:
            settings: Settings to read configuration from. Defaults to the
                process-wide settings.
            upload_dir: Override for the storage directory. Used by tests to
                keep uploads out of the repository.
            max_bytes: Override for the size limit. Used by tests to exercise
                the limit without allocating a large payload.
            max_employees: Override for the record limit.
        """
        resolved = settings or get_settings()

        self.upload_dir = upload_dir or resolved.resolved_automation_upload_dir
        self.max_bytes = (
            max_bytes if max_bytes is not None else resolved.automation_max_upload_bytes
        )
        self.max_employees = (
            max_employees
            if max_employees is not None
            else resolved.automation_max_directory_employees
        )

    async def store(self, upload: UploadFile) -> StoredDirectory:
        """Validate an upload and write it to the upload directory.

        The extension is checked before any byte is read, the size limit is
        enforced during the write, and the records are validated after it. A
        partially written or invalid file is always removed before returning or
        raising, so a rejected upload leaves nothing behind.

        Args:
            upload: The multipart file field sent by the client.

        Returns:
            The stored directory and its normalised records.

        Raises:
            ValidationFailedError: If the filename, size, structure, or any
                record is not acceptable. The stored file, if any, has already
                been removed.
        """
        display_filename = self._display_filename(upload.filename)
        extension = self._validate_format(display_filename)

        self.upload_dir.mkdir(parents=True, exist_ok=True)

        directory_id = uuid.uuid4().hex
        stored_name = f"{directory_id}_{_safe_stem(display_filename)}{extension}"
        target = self.upload_dir / stored_name

        size_bytes = await self._write(upload, target, display_filename)

        try:
            records = self._read_records_from(target, display_filename, extension)
        except ValidationFailedError:
            _remove(target)
            raise

        logger.info(
            "automation_directory_stored format=%s size_bytes=%d employees=%d",
            extension,
            size_bytes,
            len(records),
        )

        return StoredDirectory(
            directory_id=directory_id,
            display_filename=display_filename,
            stored_name=stored_name,
            path=target,
            size_bytes=size_bytes,
            extension=extension,
            records=tuple(records),
        )

    def load_records(
        self,
        directory_id: str,
        manifest: EmployeeDirectoryManifest | None = None,
    ) -> list[dict[str, str]]:
        """Read the records of a previously uploaded directory.

        The file is re-read and re-validated on every call rather than cached, so
        a file that was edited or truncated on disk after upload is caught here
        instead of silently driving a draft. Callers must never fall back to the
        packaged directory when this raises: a fallback would send a draft to the
        wrong people while reporting success.

        Args:
            directory_id: The identifier returned by the upload route.
            manifest: Manifest to resolve the id against. Defaults to the
                process-wide store.

        Returns:
            The normalised records, each holding exactly ``name`` and ``email``.

        Raises:
            DirectoryNotFoundError: If the id is unknown or its stored file is
                gone (404).
            ValidationFailedError: If the stored file no longer holds valid
                records (422).
        """
        row = find_directory_row(directory_id, manifest)

        if row is None:
            raise DirectoryNotFoundError(
                f"Employee directory '{directory_id}' was not found.",
                details={"directory_id": directory_id},
            )

        stored_name = str(row.get("stored_name") or "")
        target = self.upload_dir / Path(stored_name).name

        if not stored_name or not target.is_file():
            logger.warning("automation_directory_file_missing id=%s", directory_id)

            raise DirectoryNotFoundError(
                f"Employee directory '{directory_id}' is no longer available.",
                details={"directory_id": directory_id},
            )

        display_filename = str(row.get("filename") or "the uploaded directory")
        extension = str(row.get("extension") or ".json").lower()

        return self._read_records_from(target, display_filename, extension)

    def discard(self, stored: StoredDirectory) -> None:
        """Delete a stored directory.

        Args:
            stored: The directory to remove.
        """
        if not _remove(stored.path):
            logger.warning("automation_directory_orphan_left name=%s", stored.stored_name)

    def _read_records_from(
        self,
        target: Path,
        display_filename: str,
        extension: str,
    ) -> list[dict[str, str]]:
        """Parse and validate the records in a stored file.

        Args:
            target: The stored file.
            display_filename: Name used in error messages.
            extension: The validated lowercase extension, which selects the
                parser.

        Returns:
            Normalised records, each holding exactly ``name`` and ``email``.

        Raises:
            ValidationFailedError: If the file is unreadable, structurally
                invalid, or holds an invalid record.
        """
        try:
            raw = target.read_bytes()
        except OSError as exc:
            logger.warning("automation_directory_unreadable name=%s", target.name)

            raise ValidationFailedError(
                f"'{display_filename}' could not be read back from storage.",
                details={"filename": display_filename},
            ) from exc

        text = _decode(raw, display_filename)

        if extension == ".csv":
            rows = _rows_from_csv(text, display_filename)
        else:
            rows = _rows_from_json(text, display_filename)

        records = _normalize_records(rows, display_filename, self.max_employees)

        if not records:
            raise ValidationFailedError(
                f"'{display_filename}' contains no employee records.",
                details={"filename": display_filename},
            )

        return records

    async def _write(
        self,
        upload: UploadFile,
        target: Path,
        display_filename: str,
    ) -> int:
        """Stream an upload to disk while enforcing the size limit.

        Args:
            upload: The multipart file field sent by the client.
            target: Destination path inside the upload directory.
            display_filename: Sanitized display name, used in error messages.

        Returns:
            The number of bytes written.

        Raises:
            ValidationFailedError: If the upload is empty, exceeds the size
                limit, or is not text.
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
            logger.exception("automation_directory_write_failed")
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

        if b"\x00" in head:
            _remove(target)
            raise ValidationFailedError(
                f"'{display_filename}' is not readable as UTF-8 text.",
                details={"filename": display_filename, "expected_format": "text"},
            )

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
                "An employee directory filename is required.",
                details={"supported_formats": list(SUPPORTED_FORMATS)},
            )

        return candidate[:255]

    def _validate_format(self, display_filename: str) -> str:
        """Return the validated lowercase extension for a filename.

        Args:
            display_filename: The sanitized display filename.

        Returns:
            The lowercase extension, one of :data:`SUPPORTED_FORMATS`.

        Raises:
            ValidationFailedError: If the extension is not supported.
        """
        suffix = Path(display_filename).suffix.lower()

        if suffix not in SUPPORTED_FORMATS:
            raise ValidationFailedError(
                f"'{display_filename}' is not a supported employee directory format. "
                f"Supported formats: {', '.join(SUPPORTED_FORMATS)}.",
                details={
                    "filename": display_filename,
                    "supported_formats": list(SUPPORTED_FORMATS),
                },
            )

        return suffix


def _safe_stem(display_filename: str) -> str:
    """Return a readable, path-free stem for a stored filename.

    Args:
        display_filename: The sanitized display filename.

    Returns:
        A stem containing only ``A-Z``, ``a-z``, digits, dot, underscore, and
        hyphen, truncated to a fixed length. Falls back to ``directory`` when
        nothing usable survives sanitization.
    """
    stem = Path(display_filename).stem
    cleaned = _UNSAFE_NAME_CHARS.sub("_", stem).strip("._-")

    return cleaned[:_MAX_STEM_CHARS] or "directory"


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
                logger.warning("automation_directory_cleanup_deferred name=%s", path.name)

                return False
            time.sleep(_UNLINK_RETRY_SECONDS)

        except OSError:
            logger.exception("automation_directory_cleanup_failed name=%s", path.name)

            return False

    return False


def _decode(raw: bytes, display_filename: str) -> str:
    """Decode stored bytes as UTF-8 text, tolerating a byte-order mark.

    A BOM is stripped rather than rejected because every spreadsheet exporter
    writes one, and rejecting it would fail correct files.

    Args:
        raw: The stored file contents.
        display_filename: Name used in error messages.

    Returns:
        The decoded text.

    Raises:
        ValidationFailedError: If the content is not decodable UTF-8.
    """
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationFailedError(
            f"'{display_filename}' is not readable as UTF-8 text.",
            details={"filename": display_filename},
        ) from exc


def _rows_from_json(text: str, display_filename: str) -> list[dict[str, Any]]:
    """Extract employee rows from a JSON document.

    Args:
        text: The decoded file contents.
        display_filename: Name used in error messages.

    Returns:
        One mapping per element of the top-level array.

    Raises:
        ValidationFailedError: If the content is not JSON, is not a list, or
            holds an element that is not an object.
    """
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationFailedError(
            f"'{display_filename}' is not valid JSON.",
            details={"filename": display_filename, "expected_format": "json"},
        ) from exc

    if not isinstance(parsed, list):
        raise ValidationFailedError(
            f"'{display_filename}' must contain a JSON array of employees.",
            details={"filename": display_filename, "expected_format": "json"},
        )

    for index, entry in enumerate(parsed, start=1):
        if not isinstance(entry, dict):
            raise ValidationFailedError(
                f"Entry {index} in '{display_filename}' is not a JSON object.",
                details={"filename": display_filename, "row": index},
            )

    return parsed


def _rows_from_csv(text: str, display_filename: str) -> list[dict[str, Any]]:
    """Extract employee rows from a CSV document.

    Header names are matched case-insensitively so an exported sheet is not
    rejected over ``Name`` versus ``name``.

    Args:
        text: The decoded file contents.
        display_filename: Name used in error messages.

    Returns:
        One mapping per data row, keyed by normalized header name.

    Raises:
        ValidationFailedError: If there is no usable header, a required column is
            absent, a column is repeated, or a row has more cells than the
            header.
    """
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""))

        raw_header = list(reader.fieldnames or [])
        header = [_normalize_header(name) for name in raw_header]

        if not any(header):
            raise ValidationFailedError(
                f"'{display_filename}' has no CSV header row.",
                details={"filename": display_filename, "expected_format": "csv"},
            )

        duplicates = sorted({name for name in header if name and header.count(name) > 1})

        if duplicates:
            raise ValidationFailedError(
                f"'{display_filename}' repeats the column {duplicates[0]!r}.",
                details={"filename": display_filename, "field": duplicates[0]},
            )

        missing = [name for name in REQUIRED_FIELDS if name not in header]

        if missing:
            raise ValidationFailedError(
                f"'{display_filename}' is missing the '{missing[0]}' column.",
                details={
                    "filename": display_filename,
                    "field": missing[0],
                    "required_fields": list(REQUIRED_FIELDS),
                    "columns": [name for name in header if name],
                },
            )

        # DictReader keys each row by the raw header cell, so the normalized
        # names used for matching have to be paired back with the raw ones.
        columns = {
            normalized: raw
            for raw, normalized in zip(raw_header, header, strict=True)
            if normalized
        }

        rows: list[dict[str, Any]] = []

        for index, row in enumerate(reader, start=1):
            if row.get(None) is not None:
                raise ValidationFailedError(
                    f"Row {index} in '{display_filename}' has more cells than the "
                    "header declares.",
                    details={"filename": display_filename, "row": index},
                )

            rows.append({name: row.get(raw) for name, raw in columns.items()})

    except csv.Error as exc:
        raise ValidationFailedError(
            f"'{display_filename}' could not be parsed as CSV.",
            details={"filename": display_filename, "expected_format": "csv"},
        ) from exc

    return rows


def _normalize_header(name: str | None) -> str:
    """Normalize a CSV header cell for matching.

    Args:
        name: The raw header cell.

    Returns:
        The trimmed, lowercased header name.
    """
    return (name or "").strip().lower()


def _normalize_records(
    rows: list[dict[str, Any]],
    display_filename: str,
    max_employees: int,
) -> list[dict[str, str]]:
    """Validate rows and reduce them to the two fields the agent reads.

    Any column beyond ``name`` and ``email`` is dropped here rather than stored,
    so an uploaded file cannot introduce an internal field that some later layer
    might echo back to a client.

    Args:
        rows: One mapping per employee, keyed by normalized field name.
        display_filename: Name used in error messages.
        max_employees: Largest accepted employee count.

    Returns:
        Records holding exactly ``name`` and ``email``.

    Raises:
        ValidationFailedError: If a required field is missing or blank, an email
            is implausible, a name or email is repeated, or the count exceeds
            ``max_employees``.
    """
    records: list[dict[str, str]] = []
    seen_names: dict[str, int] = {}
    seen_emails: dict[str, int] = {}

    for index, row in enumerate(rows, start=1):
        record: dict[str, str] = {}

        for field_name in REQUIRED_FIELDS:
            value = row.get(field_name)

            text_value = "" if value is None else str(value).strip()

            if not text_value:
                raise ValidationFailedError(
                    f"Entry {index} in '{display_filename}' has no '{field_name}'.",
                    details={
                        "filename": display_filename,
                        "row": index,
                        "field": field_name,
                    },
                )

            record[field_name] = text_value

        name = record["name"]
        email = record["email"]

        if len(name) > _MAX_NAME_CHARS:
            raise ValidationFailedError(
                f"Entry {index} in '{display_filename}' has a 'name' longer than "
                f"{_MAX_NAME_CHARS} characters.",
                details={
                    "filename": display_filename,
                    "row": index,
                    "field": "name",
                    "max_chars": _MAX_NAME_CHARS,
                },
            )

        if len(email) > _MAX_EMAIL_CHARS or not _EMAIL_PATTERN.match(email):
            raise ValidationFailedError(
                f"Entry {index} in '{display_filename}' does not have a valid " "'email' address.",
                details={
                    "filename": display_filename,
                    "row": index,
                    "field": "email",
                },
            )

        name_key = name.casefold()

        if name_key in seen_names:
            raise ValidationFailedError(
                f"Entry {index} in '{display_filename}' repeats the 'name' of "
                f"entry {seen_names[name_key]}.",
                details={
                    "filename": display_filename,
                    "row": index,
                    "field": "name",
                    "conflicts_with": seen_names[name_key],
                },
            )

        email_key = email.casefold()

        if email_key in seen_emails:
            raise ValidationFailedError(
                f"Entry {index} in '{display_filename}' repeats the 'email' of "
                f"entry {seen_emails[email_key]}.",
                details={
                    "filename": display_filename,
                    "row": index,
                    "field": "email",
                    "conflicts_with": seen_emails[email_key],
                },
            )

        seen_names[name_key] = index
        seen_emails[email_key] = index
        records.append(record)

        if len(records) > max_employees:
            raise ValidationFailedError(
                f"'{display_filename}' contains more than {max_employees} employees.",
                details={
                    "filename": display_filename,
                    "max_employees": max_employees,
                },
            )

    return records


_manifest: EmployeeDirectoryManifest | None = None
_default_service: EmployeeDirectoryService | None = None


def get_manifest(settings: Settings | None = None) -> EmployeeDirectoryManifest:
    """Return the process-wide employee directory manifest.

    Both the API router and the Automation adapter resolve directory ids through
    this function, so they share one instance rather than two singletons that
    happen to point at the same file.

    Args:
        settings: Settings supplying the manifest path. Defaults to the
            process-wide settings.

    Returns:
        The shared manifest store.
    """
    global _manifest

    if _manifest is None:
        resolved = settings or get_settings()

        _manifest = EmployeeDirectoryManifest(resolved.resolved_automation_upload_manifest_path)

    return _manifest


def set_manifest(manifest: EmployeeDirectoryManifest | None) -> None:
    """Install a manifest, typically a temporary one for tests.

    Args:
        manifest: The manifest to use for subsequent reads and writes, or None
            to restore the default.
    """
    global _manifest

    _manifest = manifest


def get_directory_service(settings: Settings | None = None) -> EmployeeDirectoryService:
    """Return the process-wide employee directory service.

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
        _default_service = EmployeeDirectoryService(settings)

    return _default_service


def set_directory_service(service: EmployeeDirectoryService | None) -> None:
    """Install an upload service, typically a temporary one for tests.

    Args:
        service: The service to use for subsequent uploads, or None to restore
            the default.
    """
    global _default_service

    _default_service = service


def build_row(
    directory_id: str,
    display_filename: str,
    stored_name: str,
    extension: str,
    size_bytes: int,
    status: DirectoryStatus,
    employee_count: int | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Build one manifest row.

    Args:
        directory_id: Server-generated identifier.
        display_filename: The client's filename, for display.
        stored_name: Generated on-disk filename. Internal; never returned.
        extension: Lowercased validated extension.
        size_bytes: Bytes received from the client.
        status: Validation outcome.
        employee_count: Records accepted, when validation succeeded.
        error: Sanitized failure reason, when it did not.

    Returns:
        A JSON-serializable manifest row.
    """
    row: dict[str, Any] = {
        "directory_id": directory_id,
        "filename": display_filename,
        "stored_name": stored_name,
        "extension": extension,
        "size_bytes": size_bytes,
        "status": status.value,
        "uploaded_at": datetime.now().astimezone().isoformat(),
    }

    if employee_count is not None:
        row["employee_count"] = employee_count

    if error is not None:
        row["error"] = error

    return row


def record_directory(
    row: dict[str, Any],
    manifest: EmployeeDirectoryManifest | None = None,
) -> dict[str, Any]:
    """Record one uploaded employee directory.

    Recording never raises. The manifest is supporting metadata, so a write
    failure is logged rather than allowed to fail an upload that has already
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
        logger.exception("automation_manifest_write_failed")

        return row


def list_directories(
    manifest: EmployeeDirectoryManifest | None = None,
    status: DirectoryStatus | None = None,
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


def find_directory_row(
    directory_id: str,
    manifest: EmployeeDirectoryManifest | None = None,
) -> dict[str, Any] | None:
    """Return the manifest row for one directory id.

    Args:
        directory_id: The identifier a client supplied.
        manifest: Manifest to read from. Defaults to the process-wide store.

    Returns:
        The matching row, or None when no row carries that id.
    """
    if not directory_id:
        return None

    for row in (manifest or get_manifest()).read():
        if str(row.get("directory_id") or "") == directory_id:
            return row

    return None


def row_to_stored(row: dict[str, Any]) -> StoredDirectoryRow:
    """Coerce one manifest row into a typed record.

    Every field is coerced rather than trusted: the manifest is a plain JSON
    file that a hand edit or a partial write could make inconsistent, and a
    malformed row must not break the directory list.

    Args:
        row: A raw manifest row.

    Returns:
        A populated record. An unreadable status degrades to ``FAILED`` so a
        damaged row is never presented as usable.
    """
    return StoredDirectoryRow(
        directory_id=str(row.get("directory_id") or ""),
        display_filename=str(row.get("filename") or ""),
        stored_name=str(row.get("stored_name") or ""),
        extension=str(row.get("extension") or ""),
        size_bytes=_as_int(row.get("size_bytes")),
        status=_as_status(row.get("status")),
        uploaded_at=_as_timestamp(row.get("uploaded_at")),
        employee_count=_as_optional_int(row.get("employee_count")),
        error=str(row["error"]) if row.get("error") else None,
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


def _as_optional_int(value: Any) -> int | None:
    """Coerce a manifest value to an integer or None.

    Args:
        value: The raw value.

    Returns:
        The parsed integer, or None when the value is absent or unparseable.
    """
    if value is None:
        return None

    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return None


def _as_status(value: Any) -> DirectoryStatus:
    """Coerce a manifest value to a directory status.

    Args:
        value: The raw value.

    Returns:
        The matching status, defaulting to ``FAILED`` so an unreadable row is
        never shown as usable.
    """
    try:
        return DirectoryStatus(str(value))
    except ValueError:
        return DirectoryStatus.FAILED


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
        logger.warning("automation_manifest_bad_timestamp value=%s", value)

        return datetime.fromtimestamp(0, tz=UTC)
