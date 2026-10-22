"""Automation employee directory schemas.

These describe what a client may see about an uploaded employee directory.
Stored paths, stored filenames, and manifest internals are deliberately absent:
the manifest keeps them internal, and a client receives the display filename, the
identifier, and the validation outcome.

Employee records are limited to ``name`` and ``email`` in every model here. An
uploaded file may carry more columns, but those are dropped when the file is
parsed, so no field exists anywhere in the API that could expose something the
uploader did not intend to publish.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.services.employee_directory import DirectoryStatus


class EmployeeRecord(BaseModel):
    """One employee, as the Automation Agent resolves them.

    Attributes:
        name: Employee name, matched against the words of an instruction.
        email: Employee email address, used as the draft recipient.
    """

    name: str
    email: str


class UploadedDirectory(BaseModel):
    """One employee directory this instance has accepted.

    Attributes:
        directory_id: Server-generated identifier. This is the only reference a
            client supplies when selecting a directory for a draft.
        filename: The original filename as supplied by the client, for display.
        format: Lowercased validated extension, without the leading dot.
        employee_count: Records accepted from the file.
        size_bytes: Bytes received from the client.
        status: Whether the records validated or the upload failed.
        uploaded_at: Timezone-aware ISO-8601 timestamp of the upload.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "directory_id": "9f2c1d0b4a7e4c1f9b3d5e7a8c0d2f41",
                "filename": "engineering_roster.csv",
                "format": "csv",
                "employee_count": 42,
                "size_bytes": 1843,
                "status": "ready",
                "uploaded_at": "2026-10-16T14:22:01+05:30",
            }
        }
    )

    directory_id: str
    filename: str
    format: str
    employee_count: int
    size_bytes: int
    status: DirectoryStatus
    uploaded_at: datetime


class DirectoryUploadResponse(BaseModel):
    """Result of one employee directory upload.

    Attributes:
        directory: The stored directory and its validation outcome.
        preview: The first records from the file, so the user can confirm the
            upload resolved to the employees they expected before using it.
        message: Human-readable summary for the client.
    """

    directory: UploadedDirectory
    preview: list[EmployeeRecord] = Field(default_factory=list)
    message: str = "Employee directory uploaded."


class DirectoryListResponse(BaseModel):
    """Payload for the uploaded directory list.

    Attributes:
        directories: Directories ordered newest first.
        total: Number of directories returned.
    """

    directories: list[UploadedDirectory] = Field(default_factory=list)
    total: int = 0


class DirectoryDetailResponse(BaseModel):
    """Payload for one uploaded directory and its records.

    Attributes:
        directory: The stored directory and its validation outcome.
        employees: The validated records, newest-read order preserved.
        employees_truncated: True when the stored file holds more records than
            were returned, so a client never mistakes a capped list for the whole
            directory.
    """

    directory: UploadedDirectory
    employees: list[EmployeeRecord] = Field(default_factory=list)
    employees_truncated: bool = False
