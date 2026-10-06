"""Performance Analyzer job schemas.

The Performance Analyzer runs CPU-intensive analytics over datasets that can
take tens of seconds, so it is exposed as a job API rather than a synchronous
request. These models describe that job contract on the wire.

Not yet wired to the agent catalog: Performance no longer advertises
operations through ``POST /agents/execute``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

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


class PerformanceJobRequest(BaseModel):
    """Request to create a performance job.

    Attributes:
        operation: The analysis to run.
        file_path: Server-side path to a CSV or Excel dataset. Read by the
            server; no file content is uploaded.

    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "operation": "analyze",
                "file_path": "performance_agent/data/Financials_standardized.csv",
            }
        },
    )

    operation: str = Field(
        min_length=1,
        max_length=64,
        description=f"One of: {', '.join(SUPPORTED_OPERATIONS)}.",
    )

    file_path: str = Field(
        min_length=1,
        max_length=1024,
        description="Server-side dataset path. Supported: .csv, .xlsx, .xls.",
    )


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
