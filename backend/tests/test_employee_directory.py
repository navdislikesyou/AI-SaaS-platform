"""Tests for the employee directory upload service.

Everything runs against a temporary directory, so the repository's own upload
storage is never touched and no test can see another test's files.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import UploadFile

from app.core.exceptions import DirectoryNotFoundError, ValidationFailedError
from app.services.employee_directory import (
    MAX_RECORDS,
    DirectoryStatus,
    EmployeeDirectoryManifest,
    EmployeeDirectoryService,
    StoredDirectory,
    build_row,
    find_directory_row,
    list_directories,
    record_directory,
    row_to_stored,
)


def upload_of(content: bytes, filename: str = "roster.csv") -> UploadFile:
    """Build an UploadFile carrying in-memory content.

    Args:
        content: Raw file bytes.
        filename: Name the client claims.

    Returns:
        An UploadFile ready for the service.
    """
    return UploadFile(filename=filename, file=io.BytesIO(content))


def json_bytes(records: list[dict[str, Any]]) -> bytes:
    """Encode records as a JSON directory.

    Args:
        records: Employee records.

    Returns:
        UTF-8 JSON bytes.
    """
    return json.dumps(records).encode("utf-8")


@pytest.fixture
def service(tmp_path: Path) -> EmployeeDirectoryService:
    """Return a service writing to a temporary directory.

    Args:
        tmp_path: pytest's per-test temporary directory.

    Returns:
        A configured upload service.
    """
    return EmployeeDirectoryService(
        upload_dir=tmp_path / "uploads",
        max_bytes=4096,
        max_employees=50,
    )


@pytest.fixture
def upload_dir(service: EmployeeDirectoryService) -> Path:
    """Return the directory the service writes to.

    Args:
        service: The service under test.

    Returns:
        The absolute upload directory.
    """
    return service.upload_dir


@pytest.fixture
def manifest(tmp_path: Path) -> EmployeeDirectoryManifest:
    """Return a manifest backed by a temporary file.

    Args:
        tmp_path: pytest's per-test temporary directory.

    Returns:
        The temporary manifest store.
    """
    return EmployeeDirectoryManifest(tmp_path / "uploads" / "directories.json")


# --------------------------------------------------------------------------
# Accepting a valid directory
# --------------------------------------------------------------------------


async def test_json_records_are_accepted_and_normalized(
    service: EmployeeDirectoryService,
) -> None:
    """A JSON array of name and email pairs becomes one record each."""
    stored = await service.store(
        upload_of(json_bytes([{"name": "Aarti Rao", "email": "a@example.com"}]), "r.json")
    )

    assert list(stored.records) == [{"name": "Aarti Rao", "email": "a@example.com"}]
    assert stored.extension == ".json"
    assert stored.path.is_file()


async def test_csv_records_are_accepted(service: EmployeeDirectoryService) -> None:
    """A CSV with a name and email header is accepted."""
    stored = await service.store(
        upload_of(b"Name,Email\r\nAarti Rao,a@example.com\r\n", "roster.csv")
    )

    assert list(stored.records) == [{"name": "Aarti Rao", "email": "a@example.com"}]


async def test_csv_headers_are_matched_case_insensitively(
    service: EmployeeDirectoryService,
) -> None:
    """An exported sheet using ``Name`` and ``Email`` is not rejected."""
    stored = await service.store(upload_of(b"Name, Email\r\nAarti Rao, a@example.com\r\n"))

    assert list(stored.records) == [{"name": "Aarti Rao", "email": "a@example.com"}]


async def test_csv_with_a_byte_order_mark_is_accepted(
    service: EmployeeDirectoryService,
) -> None:
    """A UTF-8 BOM is stripped rather than treated as part of the first header."""
    content = "\ufeffname,email\r\nAarti Rao,a@example.com\r\n"

    stored = await service.store(upload_of(content.encode("utf-8"), "bom.csv"))

    assert list(stored.records) == [{"name": "Aarti Rao", "email": "a@example.com"}]


async def test_extra_columns_are_discarded(service: EmployeeDirectoryService) -> None:
    """Columns beyond name and email are dropped, not stored."""
    content = b"name,email,phone,salary\r\nAarti Rao,a@example.com,555,100\r\n"

    stored = await service.store(upload_of(content))

    assert list(stored.records) == [{"name": "Aarti Rao", "email": "a@example.com"}]
    assert "phone" not in stored.records[0]
    assert "salary" not in stored.records[0]


async def test_values_are_trimmed(service: EmployeeDirectoryService) -> None:
    """Surrounding whitespace is removed from both fields."""
    content = b"name,email\r\n  Aarti Rao  ,  a@example.com  \r\n"

    stored = await service.store(upload_of(content))

    assert list(stored.records) == [{"name": "Aarti Rao", "email": "a@example.com"}]


# --------------------------------------------------------------------------
# Rejecting a malformed file
# --------------------------------------------------------------------------


async def test_unsupported_extension_is_rejected_before_any_byte_is_read(
    service: EmployeeDirectoryService,
    upload_dir: Path,
) -> None:
    """A spreadsheet is refused on its extension, leaving nothing on disk."""
    with pytest.raises(ValidationFailedError, match="not a supported employee directory"):
        await service.store(upload_of(b"PK\x03\x04binary", "roster.xlsx"))

    assert not upload_dir.exists() or list(upload_dir.iterdir()) == []


async def test_a_filename_with_no_extension_is_rejected(
    service: EmployeeDirectoryService,
) -> None:
    """A file with no extension cannot select a parser."""
    with pytest.raises(ValidationFailedError, match="not a supported employee directory"):
        await service.store(upload_of(b"name,email\r\n", "roster"))


async def test_empty_file_is_rejected(service: EmployeeDirectoryService) -> None:
    """A zero-byte upload is not a directory."""
    with pytest.raises(ValidationFailedError, match="is empty"):
        await service.store(upload_of(b""))


async def test_binary_content_is_rejected(service: EmployeeDirectoryService) -> None:
    """A file carrying a NUL byte is not text, whatever its extension."""
    with pytest.raises(ValidationFailedError, match="not readable as UTF-8 text"):
        await service.store(upload_of(b"name,email\r\n\x00\x00\r\n"))


async def test_size_limit_is_enforced_and_nothing_is_kept(
    service: EmployeeDirectoryService,
    upload_dir: Path,
) -> None:
    """An oversized upload is discarded instead of buffered."""
    payload = b"name,email\r\n" + b"A,a@example.com\r\n" * 500

    with pytest.raises(ValidationFailedError, match="exceeds the maximum upload size") as info:
        await service.store(upload_of(payload))

    assert info.value.details is not None
    assert info.value.details["max_bytes"] == 4096
    assert list(upload_dir.iterdir()) == []


async def test_undecodable_bytes_are_rejected(service: EmployeeDirectoryService) -> None:
    """Content that is not UTF-8 is refused rather than mangled."""
    with pytest.raises(ValidationFailedError, match="not readable as UTF-8 text"):
        await service.store(upload_of(b"name,email\r\n\xff\xfe\xfd,a@b.com\r\n"))


async def test_malformed_json_is_rejected(service: EmployeeDirectoryService) -> None:
    """Invalid JSON fails at upload rather than at drafting time."""
    with pytest.raises(ValidationFailedError, match="is not valid JSON"):
        await service.store(upload_of(b"{not json", "r.json"))


async def test_json_object_instead_of_array_is_rejected(
    service: EmployeeDirectoryService,
) -> None:
    """A JSON document must be an array of employees."""
    with pytest.raises(ValidationFailedError, match="must contain a JSON array"):
        await service.store(upload_of(b'{"name":"A","email":"a@b.com"}', "r.json"))


async def test_json_element_that_is_not_an_object_is_rejected(
    service: EmployeeDirectoryService,
) -> None:
    """A scalar inside the array names the offending row."""
    with pytest.raises(ValidationFailedError, match="Entry 2 .* is not a JSON object"):
        await service.store(upload_of(b'[{"name":"A","email":"a@b.com"},"x"]', "r.json"))


async def test_empty_json_array_is_rejected(service: EmployeeDirectoryService) -> None:
    """A directory with no employees cannot resolve a recipient."""
    with pytest.raises(ValidationFailedError, match="no employee records"):
        await service.store(upload_of(b"[]", "r.json"))


async def test_csv_without_a_header_is_rejected(service: EmployeeDirectoryService) -> None:
    """A file with no header row names no columns."""
    with pytest.raises(ValidationFailedError, match="no CSV header row"):
        await service.store(upload_of(b"   \r\n", "r.csv"))


async def test_csv_missing_a_required_column_is_rejected(
    service: EmployeeDirectoryService,
) -> None:
    """A file without an email column cannot produce recipients."""
    with pytest.raises(ValidationFailedError, match="missing the 'email' column"):
        await service.store(upload_of(b"name\r\nAarti Rao\r\n", "r.csv"))


async def test_csv_with_a_repeated_column_is_rejected(
    service: EmployeeDirectoryService,
) -> None:
    """A duplicated header is ambiguous and refused."""
    content = b"name,email,name\r\nA,a@b.com,B\r\n"

    with pytest.raises(ValidationFailedError, match="repeats the column 'name'"):
        await service.store(upload_of(content))


async def test_csv_row_with_more_cells_than_the_header_is_rejected(
    service: EmployeeDirectoryService,
) -> None:
    """A ragged row would silently shift every later value."""
    with pytest.raises(ValidationFailedError, match="more cells than the header"):
        await service.store(upload_of(b"name,email\r\nA,a@b.com,extra\r\n"))


async def test_rejected_file_is_removed_from_disk(
    service: EmployeeDirectoryService,
    upload_dir: Path,
) -> None:
    """A file that fails record validation leaves nothing behind."""
    payload = json_bytes([{"name": "A", "email": "not-an-email"}])

    with pytest.raises(ValidationFailedError):
        await service.store(upload_of(payload, "r.json"))

    assert list(upload_dir.iterdir()) == []


# --------------------------------------------------------------------------
# Rejecting an invalid record
# --------------------------------------------------------------------------


async def test_missing_required_field_is_rejected(
    service: EmployeeDirectoryService,
) -> None:
    """A record without an email is refused and the row is named."""
    payload = json_bytes([{"name": "Aarti Rao"}])

    with pytest.raises(ValidationFailedError, match="Entry 1 .* has no 'email'") as info:
        await service.store(upload_of(payload, "r.json"))

    assert info.value.details is not None
    assert info.value.details["row"] == 1
    assert info.value.details["field"] == "email"


async def test_blank_required_field_is_rejected(
    service: EmployeeDirectoryService,
) -> None:
    """A whitespace-only name counts as blank."""
    payload = json_bytes([{"name": "   ", "email": "a@example.com"}])

    with pytest.raises(ValidationFailedError, match="has no 'name'"):
        await service.store(upload_of(payload, "r.json"))


@pytest.mark.parametrize(
    "email",
    ["plainaddress", "two@@example.com", "spaced @example.com", "no-domain@", "a@b"],
)
async def test_implausible_email_is_rejected(
    service: EmployeeDirectoryService,
    email: str,
) -> None:
    """An address that could never receive a draft is refused.

    Args:
        service: The service under test.
        email: The address to try.
    """
    payload = json_bytes([{"name": "Aarti Rao", "email": email}])

    with pytest.raises(ValidationFailedError, match="valid 'email' address"):
        await service.store(upload_of(payload, "r.json"))


async def test_oversized_email_is_rejected(service: EmployeeDirectoryService) -> None:
    """An address longer than RFC 5321 allows is refused."""
    payload = json_bytes([{"name": "Aarti", "email": f"{'a' * 250}@example.com"}])

    with pytest.raises(ValidationFailedError, match="valid 'email' address"):
        await service.store(upload_of(payload, "r.json"))


async def test_oversized_name_is_rejected(service: EmployeeDirectoryService) -> None:
    """A name long enough to be a paragraph is refused."""
    payload = json_bytes([{"name": "A" * 200, "email": "a@example.com"}])

    with pytest.raises(ValidationFailedError, match="longer than 120 characters"):
        await service.store(upload_of(payload, "r.json"))


async def test_duplicate_name_is_rejected_regardless_of_case(
    service: EmployeeDirectoryService,
) -> None:
    """The first-name fallback makes a repeated name ambiguous."""
    payload = json_bytes(
        [
            {"name": "Aarti Rao", "email": "a@example.com"},
            {"name": "aarti rao", "email": "b@example.com"},
        ]
    )

    with pytest.raises(ValidationFailedError, match="repeats the 'name' of entry 1") as info:
        await service.store(upload_of(payload, "r.json"))

    assert info.value.details is not None
    assert info.value.details["conflicts_with"] == 1


async def test_duplicate_email_is_rejected(service: EmployeeDirectoryService) -> None:
    """Two people cannot share one address without one draft going astray."""
    payload = json_bytes(
        [
            {"name": "Aarti Rao", "email": "a@example.com"},
            {"name": "B Rao", "email": "a@example.com"},
        ]
    )

    with pytest.raises(ValidationFailedError, match="repeats the 'email' of entry 1"):
        await service.store(upload_of(payload, "r.json"))


async def test_too_many_employees_is_rejected(tmp_path: Path) -> None:
    """A directory larger than the configured cap is refused."""
    service = EmployeeDirectoryService(upload_dir=tmp_path / "u", max_employees=2)

    records = [{"name": f"P{i}", "email": f"p{i}@example.com"} for i in range(3)]

    with pytest.raises(ValidationFailedError, match="more than 2 employees"):
        await service.store(upload_of(json_bytes(records), "r.json"))


async def test_validation_error_never_echoes_the_offending_value(
    service: EmployeeDirectoryService,
) -> None:
    """An error body must not hand back the value that failed validation."""
    secret = "confidential-internal-codename"
    payload = json_bytes(
        [
            {"name": secret, "email": "a@example.com"},
            {"name": secret, "email": "b@example.com"},
        ]
    )

    with pytest.raises(ValidationFailedError) as info:
        await service.store(upload_of(payload, "r.json"))

    assert secret not in info.value.message
    assert info.value.details is not None
    assert secret not in str(info.value.details)


# --------------------------------------------------------------------------
# Stored names and path isolation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename",
    ["../../etc/passwd.csv", "..\\..\\windows\\system32.csv", "/absolute/roster.csv", "a/b/c.csv"],
)
async def test_traversal_in_the_filename_cannot_escape_the_upload_directory(
    service: EmployeeDirectoryService,
    upload_dir: Path,
    filename: str,
) -> None:
    """A client-supplied path never decides where the file lands.

    Args:
        service: The service under test.
        upload_dir: The upload directory that must contain the result.
        filename: The hostile name to try.
    """
    stored = await service.store(upload_of(b"name,email\r\nA,a@b.com\r\n", filename))

    assert stored.path.parent == upload_dir
    assert stored.path.is_file()
    assert ".." not in stored.stored_name


@pytest.mark.parametrize("filename", ["..", ".", "/", "   "])
async def test_a_filename_that_is_only_traversal_is_rejected(
    service: EmployeeDirectoryService,
    filename: str,
) -> None:
    """A name with no usable stem cannot produce a safe stored name.

    Args:
        service: The service under test.
        filename: The hostile name to try.
    """
    with pytest.raises(ValidationFailedError):
        await service.store(upload_of(b"name,email\r\nA,a@b.com\r\n", filename))


async def test_stored_name_is_generated_and_not_client_controlled(
    service: EmployeeDirectoryService,
) -> None:
    """The on-disk name is a UUID plus a sanitized stem."""
    stored = await service.store(upload_of(b"name,email\r\nA,a@b.com\r\n", "../../weird name!.csv"))

    assert stored.directory_id in stored.stored_name
    assert "/" not in stored.stored_name
    assert "\\" not in stored.stored_name
    assert "!" not in stored.stored_name


async def test_display_filename_is_the_bare_name(
    service: EmployeeDirectoryService,
) -> None:
    """The echoed filename keeps only its last path segment."""
    stored = await service.store(upload_of(b"name,email\r\nA,a@b.com\r\n", "../../etc/roster.csv"))

    assert stored.display_filename == "roster.csv"


async def test_missing_filename_is_rejected(service: EmployeeDirectoryService) -> None:
    """A request with no filename cannot be stored under a safe name."""
    with pytest.raises(ValidationFailedError, match="filename is required"):
        await service.store(upload_of(b"name,email\r\nA,a@b.com\r\n", ""))


async def test_two_uploads_get_distinct_stored_names(
    service: EmployeeDirectoryService,
) -> None:
    """The same filename twice does not overwrite the first upload."""
    first = await service.store(upload_of(b"name,email\r\nA,a@b.com\r\n", "roster.csv"))
    second = await service.store(upload_of(b"name,email\r\nC,d@e.com\r\n", "roster.csv"))

    assert first.path != second.path
    assert first.path.is_file()
    assert second.path.is_file()


def test_discard_removes_the_stored_file(
    service: EmployeeDirectoryService,
    tmp_path: Path,
) -> None:
    """Cleanup deletes the file and tolerates a missing one."""
    path = tmp_path / "leftover.csv"
    path.write_text("name,email\r\n", encoding="utf-8")

    service.upload_dir.mkdir(parents=True, exist_ok=True)
    target = service.upload_dir / "leftover.csv"
    target.write_text("name,email\r\n", encoding="utf-8")

    service.discard(
        StoredDirectory(
            directory_id="d",
            display_filename="leftover.csv",
            stored_name="leftover.csv",
            path=target,
            size_bytes=0,
            extension=".csv",
            records=(),
        )
    )

    assert not target.exists()


# --------------------------------------------------------------------------
# Loading a stored directory
# --------------------------------------------------------------------------


async def _upload(
    service: EmployeeDirectoryService,
    manifest: EmployeeDirectoryManifest,
    records: list[dict[str, str]],
) -> str:
    """Upload records and register them in the given manifest.

    Args:
        service: The service under test.
        manifest: The manifest to record into.
        records: Employee records to store.

    Returns:
        The new directory id.
    """
    stored = await service.store(upload_of(json_bytes(records), "roster.json"))

    record_directory(
        build_row(
            directory_id=stored.directory_id,
            display_filename=stored.display_filename,
            stored_name=stored.stored_name,
            extension=stored.extension,
            size_bytes=stored.size_bytes,
            status=DirectoryStatus.READY,
            employee_count=len(stored.records),
        ),
        manifest,
    )

    return stored.directory_id


async def test_load_records_returns_the_stored_employees(
    service: EmployeeDirectoryService,
    manifest: EmployeeDirectoryManifest,
) -> None:
    """A registered directory round-trips its records.

    Args:
        service: The service under test.
        manifest: The manifest to write to.
    """
    directory_id = await _upload(
        service, manifest, [{"name": "Aarti Rao", "email": "a@example.com"}]
    )

    assert service.load_records(directory_id, manifest) == [
        {"name": "Aarti Rao", "email": "a@example.com"}
    ]


async def test_load_records_rejects_an_unknown_id(
    service: EmployeeDirectoryService,
    manifest: EmployeeDirectoryManifest,
) -> None:
    """An id that was never issued is a 404, not a silent default.

    Args:
        service: The service under test.
        manifest: An empty manifest.
    """
    with pytest.raises(DirectoryNotFoundError, match="was not found"):
        service.load_records("nope", manifest)


async def test_load_records_reports_a_deleted_file_as_unavailable(
    service: EmployeeDirectoryService,
    manifest: EmployeeDirectoryManifest,
) -> None:
    """A registered id whose file is gone is a 404 rather than a fall-back.

    Args:
        service: The service under test.
        manifest: The manifest to write to.
    """
    directory_id = await _upload(
        service, manifest, [{"name": "Aarti Rao", "email": "a@example.com"}]
    )

    row = find_directory_row(directory_id, manifest)
    assert row is not None
    (service.upload_dir / str(row["stored_name"])).unlink()

    with pytest.raises(DirectoryNotFoundError, match="no longer available"):
        service.load_records(directory_id, manifest)


async def test_load_records_rejects_a_file_that_became_invalid(
    service: EmployeeDirectoryService,
    manifest: EmployeeDirectoryManifest,
) -> None:
    """A file corrupted after upload fails loudly instead of being ignored.

    Args:
        service: The service under test.
        manifest: The manifest to write to.
    """
    directory_id = await _upload(
        service, manifest, [{"name": "Aarti Rao", "email": "a@example.com"}]
    )

    row = find_directory_row(directory_id, manifest)
    assert row is not None
    (service.upload_dir / str(row["stored_name"])).write_text("garbage", encoding="utf-8")

    with pytest.raises(ValidationFailedError):
        service.load_records(directory_id, manifest)


async def test_two_directories_do_not_share_records(
    service: EmployeeDirectoryService,
    manifest: EmployeeDirectoryManifest,
) -> None:
    """Each id resolves to its own employees only.

    Args:
        service: The service under test.
        manifest: The manifest to write to.
    """
    first = await _upload(service, manifest, [{"name": "Aarti Rao", "email": "a@example.com"}])
    second = await _upload(service, manifest, [{"name": "Omkar Shenwai", "email": "o@example.com"}])

    assert [r["name"] for r in service.load_records(first, manifest)] == ["Aarti Rao"]
    assert [r["name"] for r in service.load_records(second, manifest)] == ["Omkar Shenwai"]


# --------------------------------------------------------------------------
# Manifest
# --------------------------------------------------------------------------


def test_manifest_missing_file_reads_as_empty(manifest: EmployeeDirectoryManifest) -> None:
    """A first run has no manifest file and that is not an error."""
    assert manifest.read() == []


def test_manifest_corrupt_file_reads_as_empty(manifest: EmployeeDirectoryManifest) -> None:
    """A corrupt manifest is logged and treated as empty."""
    manifest.path.parent.mkdir(parents=True, exist_ok=True)
    manifest.path.write_text("{not json", encoding="utf-8")

    assert manifest.read() == []


def test_manifest_non_list_reads_as_empty(manifest: EmployeeDirectoryManifest) -> None:
    """A manifest that is not a list is not trusted."""
    manifest.path.parent.mkdir(parents=True, exist_ok=True)
    manifest.path.write_text('{"directory_id": "x"}', encoding="utf-8")

    assert manifest.read() == []


def test_manifest_returns_newest_first(manifest: EmployeeDirectoryManifest) -> None:
    """The list endpoint and the selector both want newest first."""
    for index in range(3):
        manifest.append(
            build_row(
                directory_id=f"d{index}",
                display_filename=f"{index}.csv",
                stored_name=f"d{index}.csv",
                extension=".csv",
                size_bytes=1,
                status=DirectoryStatus.READY,
                employee_count=1,
            )
        )

    assert [row["directory_id"] for row in list_directories(manifest)] == ["d2", "d1", "d0"]


def test_manifest_caps_retained_rows(manifest: EmployeeDirectoryManifest) -> None:
    """An unbounded manifest would grow forever in a long-running process."""
    for index in range(MAX_RECORDS + 10):
        manifest.append(
            build_row(
                directory_id=f"d{index}",
                display_filename="r.csv",
                stored_name="r.csv",
                extension=".csv",
                size_bytes=1,
                status=DirectoryStatus.READY,
            )
        )

    assert len(manifest.read()) == MAX_RECORDS


def test_record_directory_never_raises(tmp_path: Path) -> None:
    """A manifest write failure must not fail an upload that already succeeded.

    Args:
        tmp_path: pytest's per-test temporary directory.
    """
    unwritable = EmployeeDirectoryManifest(tmp_path / "roster.csv" / "nested.json")

    row = record_directory(
        build_row(
            directory_id="d",
            display_filename="r.csv",
            stored_name="r.csv",
            extension=".csv",
            size_bytes=1,
            status=DirectoryStatus.READY,
        ),
        unwritable,
    )

    assert row["directory_id"] == "d"


def test_find_directory_row_returns_none_for_a_blank_id(
    manifest: EmployeeDirectoryManifest,
) -> None:
    """An empty id can never match a row."""
    assert find_directory_row("", manifest) is None


def test_row_to_stored_coerces_a_damaged_row() -> None:
    """A hand-edited manifest row must not break the directory list."""
    row = row_to_stored({"directory_id": 7, "size_bytes": "not-a-number", "status": "weird"})

    assert row.directory_id == "7"
    assert row.size_bytes == 0
    assert row.status is DirectoryStatus.FAILED
    assert row.uploaded_at.year == 1970


def test_row_to_stored_reads_a_healthy_row() -> None:
    """A well-formed row survives coercion unchanged."""
    row = row_to_stored(
        {
            "directory_id": "abc",
            "filename": "roster.csv",
            "stored_name": "abc_roster.csv",
            "extension": ".csv",
            "size_bytes": 120,
            "status": "ready",
            "employee_count": 4,
            "uploaded_at": "2026-10-16T14:22:01+05:30",
        }
    )

    assert row.status is DirectoryStatus.READY
    assert row.employee_count == 4
    assert row.size_bytes == 120
    assert row.extension == ".csv"
