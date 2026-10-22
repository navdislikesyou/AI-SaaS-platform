"""Performance Analyzer job schemas.

The Performance Analyzer runs CPU-intensive analytics over datasets that can
take tens of seconds, so it is exposed as a job API rather than a synchronous
request. These models describe that job contract on the wire.

These schemas are separate from ``app/schemas/agent.py`` because Performance
deliberately advertises no operations through ``POST /agents/execute``: the
catalog lists it with empty capabilities and points at this job API instead.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import utc_now

#: Operations the job API accepts, matching PerformanceService capabilities.
#: Trimming this list is a deliberate API decision.
SUPPORTED_OPERATIONS: tuple[str, ...] = (
    "load_dataset",
    "compute_kpis",
    "compare_periods",
    "analyze",
    "visualize",
)


class JobStatus(StrEnum):
    """Lifecycle states a performance job moves through.

    A job starts ``QUEUED``, transitions to ``RUNNING`` when a worker picks it
    up, and ends in exactly one terminal state: ``COMPLETED`` or ``FAILED``.
    """

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        """Report whether no further transition is possible.

        Returns:
            True for ``completed`` and ``failed``.
        """
        return self in (JobStatus.COMPLETED, JobStatus.FAILED)


class DatasetStatus(StrEnum):
    """Whether an uploaded dataset can be used by a job.

    Defined here rather than in the upload service for the same reason
    :class:`JobStatus` is: the enum is part of the wire contract, and the job
    runner and the upload service both need to speak it. Two enums with the same
    members would compare unequal, which silently breaks any check.

    Attributes:
        READY: The file parsed and its header was read successfully.
        FAILED: The upload was rejected and the file was removed. Such an entry
            is never returned by the list route.
    """

    READY = "ready"
    FAILED = "failed"


class PerformanceJobRequest(BaseModel):
    """Request to create a performance job.

    Exactly one dataset reference is required: either ``dataset_id``, which names
    an uploaded dataset or the reserved ``sample`` id, or ``file_path``, a
    server-side path for the operator workflow that predates uploads. Supplying
    both is refused rather than resolved, because a silent preference between
    them would mean a job could analyse a file the caller did not select.

    Attributes:
        operation: The analysis to run.
        dataset_id: Identifier returned by the dataset upload route, or the
            reserved ``sample`` value. Preferred, because the server resolves it
            to a path it controls and the client never names a file.
        file_path: Server-side path, read directly by the server. Retained for
            existing server-path callers. Relative paths resolve from the
            backend directory.

    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "operation": "analyze",
                "dataset_id": "sample",
            }
        },
    )

    operation: str = Field(
        min_length=1,
        max_length=64,
        description=f"One of: {', '.join(SUPPORTED_OPERATIONS)}.",
    )

    dataset_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description=(
            "Uploaded dataset id from POST /api/v1/performance/datasets, or the "
            "reserved value 'sample' for the packaged dataset. Ignored only if "
            "file_path is also set, which is rejected."
        ),
    )

    file_path: str | None = Field(
        default=None,
        min_length=1,
        max_length=1024,
        description=(
            "Server-side dataset path. Supported: .csv, .xlsx. Use dataset_id "
            "instead for anything a browser supplies."
        ),
    )

    @model_validator(mode="after")
    def _exactly_one_reference(self) -> PerformanceJobRequest:
        """Require one dataset reference and refuse two.

        Returns:
            The validated request.

        Raises:
            ValueError: If neither or both references were supplied.
        """
        has_dataset = self.dataset_id is not None and self.dataset_id.strip() != ""
        has_path = self.file_path is not None and self.file_path.strip() != ""

        if has_dataset and has_path:
            raise ValueError("Provide either dataset_id or file_path, not both.")

        if not has_dataset and not has_path:
            raise ValueError("Provide dataset_id or file_path.")

        return self


class PerformanceJobAccepted(BaseModel):
    """Payload returned when a job is accepted for background execution.

    Attributes:
        job_id: Identifier to poll with the job status endpoint.
        status: Always ``queued`` on creation.
        operation: The accepted operation.
        created_at: When the job was accepted.
    """

    job_id: str
    status: JobStatus = JobStatus.QUEUED
    operation: str
    created_at: datetime = Field(default_factory=utc_now)


class PerformanceJobResult(BaseModel):
    """Job outcome, present once a job reaches a terminal state.

    Attributes:
        result: Operation-specific payload, JSON-safe.
        error: Sanitized failure description. Present only for failed jobs.
    """

    result: dict[str, Any] | None = None
    error: str | None = None


class PerformanceJobStatusResponse(BaseModel):
    """Full state of one performance job.

    Attributes:
        job_id: The job identifier.
        status: Current lifecycle state.
        operation: The requested operation.
        created_at: When the job was accepted.
        started_at: When a worker began executing it.
        completed_at: When it reached a terminal state.
        result: Operation payload, when completed.
        error: Sanitized failure text, when failed.
    """

    job_id: str
    status: JobStatus
    operation: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class VisualizationArtifact(BaseModel):
    """One generated chart.

    Attributes:
        name: Stable identifier, suitable for a future download path segment.
        filename: Name of the file within the job's visualization directory.
        size_bytes: File size on disk.
    """

    name: str
    filename: str
    size_bytes: int


class VisualizationResult(BaseModel):
    """Visualization outcome for a job.

    Attributes:
        generated: Number of charts written.
        visualizations: Metadata for each chart. No absolute paths.
    """

    generated: int
    visualizations: list[VisualizationArtifact] = Field(default_factory=list)


class UploadedDataset(BaseModel):
    """One dataset a job can be run against.

    Carries no filesystem path and no stored filename: a client receives the id
    it refers to, the name it uploaded, and enough metadata to render a selector.

    Attributes:
        dataset_id: Identifier to send as ``dataset_id`` in a job request. For the
            packaged dataset this is the reserved value ``sample``.
        filename: The name the client uploaded, or the bare basename of the
            packaged dataset.
        format: Extension without the leading dot.
        size_bytes: Size on disk. Zero for a packaged dataset that is absent.
        status: Whether the dataset is usable.
        uploaded_at: When the dataset was uploaded. The epoch for the packaged
            dataset, which was not uploaded at all.
        column_names: Normalized column names read from the header during
            validation. These are the names the analyzers look for, so they may
            differ from what the header literally says. Capped server-side.
        column_count: Number of columns reported.
        is_sample: True for the reserved packaged dataset, so a client can label
            it rather than guess from the id.
        available: False when a referenced dataset cannot currently be read. Only
            meaningful for the packaged entry; an uploaded entry that lost its
            file is reported as unknown instead.
    """

    dataset_id: str
    filename: str
    format: str
    size_bytes: int = 0
    status: DatasetStatus = DatasetStatus.READY
    uploaded_at: datetime = Field(default_factory=utc_now)
    column_names: list[str] = Field(default_factory=list)
    column_count: int = 0
    is_sample: bool = False
    available: bool = True


class DatasetUploadResponse(BaseModel):
    """Payload returned after a dataset upload.

    Attributes:
        dataset: The stored dataset, ready to be selected.
        message: Human-readable confirmation.
    """

    dataset: UploadedDataset
    message: str


class DatasetListResponse(BaseModel):
    """Every dataset this instance can analyse.

    Attributes:
        datasets: The packaged sample first, then uploads, newest first.
        total: Number of entries returned.
        max_upload_bytes: The configured upload size limit, so a client can
            validate a file before sending it.
        supported_extensions: Extensions the upload route accepts.
    """

    datasets: list[UploadedDataset] = Field(default_factory=list)
    total: int = 0
    max_upload_bytes: int = 0
    supported_extensions: list[str] = Field(default_factory=list)
