"""In-process background job manager for long-running agent work.

Runs Performance Analyzer jobs off the request path so a client receives a 202
immediately instead of waiting tens of seconds for pandas to finish.

The store is a plain dictionary behind :class:`JobManager`. Nothing outside this
module touches it, so replacing it with Redis or a database means reimplementing
this one class. The background mechanism is :func:`asyncio.create_task` wrapping
:func:`anyio.to_thread.run_sync`, because:

* a task group would await at scope exit and block the response;
* running the work inline would block the event loop;
* a detached task returns immediately and still observes its own state writes.

CPU-bound work runs in a worker thread, bounded by a shared capacity limiter
reusing the pattern from :mod:`app.agents.base`, so a burst of submissions cannot
spawn unbounded parallel pandas work.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import anyio
import pandas as pd

from app.core.config import get_settings
from app.core.logging_config import new_request_id
from app.schemas.common import utc_now
from app.schemas.performance import (
    SUPPORTED_OPERATIONS,
    JobStatus,
    VisualizationArtifact,
)

logger = logging.getLogger(__name__)

#: Filesystem path patterns scrubbed from error text before it reaches a client.
#: Covers Windows drive paths, UNC paths, and POSIX paths. The whole path is
#: replaced rather than just the directories, so a client learns that a file was
#: missing without learning where the server stores its data. The full text
#: stays in server logs.
_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Drive paths: C:\Users\bob\data.csv or C:/Users/bob/data.csv. Windows
    # paths routinely contain spaces (C:\Program Files\...), so these run to
    # the end of the line. Stopping at the first space would leave the rest of
    # the path exposed, which is the one outcome this function prevents.
    re.compile(r"[A-Za-z]:[\\/][^\n]*"),
    # UNC paths: \\server\share\data.csv
    re.compile(r"\\\\[^\n]*"),
    # POSIX paths, anchored on a separator preceded by whitespace or a quote.
    # These stop at whitespace, which is safe here because a space in a POSIX
    # path must be escaped and would normally appear quoted.
    re.compile(r"(?<=[\s'\"])/[^\s'\"]*"),
)

_PATH_PLACEHOLDER = "<path>"


def sanitize_error(text: str) -> str:
    """Remove filesystem paths from an error message.

    Analyzer and loader exceptions carry raw ``str(error)`` text, which routinely
    contains absolute server paths and filenames. This makes the message safe to
    return to a client. The unmodified text is logged by the caller.

    Args:
        text: The raw error message.

    Returns:
        The message with filesystem paths redacted.
    """
    sanitized = text

    for pattern in _PATH_PATTERNS:
        sanitized = pattern.sub(_PATH_PLACEHOLDER, sanitized)

    return sanitized


@dataclass
class Job:
    """One performance job and its current state.

    Attributes:
        job_id: Unique identifier returned to the client.
        operation: The requested operation name.
        file_path: Server-side dataset path.
        status: Current lifecycle state.
        created_at: When the job was accepted.
        started_at: When a worker began executing it.
        completed_at: When it reached a terminal state.
        result: Operation payload, once completed.
        error: Sanitized failure text, once failed.
        request_id: Correlation id of the creating request.
        organization_id: The organisation owning this job.
        owner_id: The user who created this job.
    """

    job_id: str
    operation: str
    file_path: str
    status: JobStatus = JobStatus.QUEUED
    created_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    request_id: str | None = None
    organization_id: str | None = None
    owner_id: str | None = None

    def to_status_response(self) -> dict[str, Any]:
        """Render the job as a client-facing payload.

        Returns:
            A JSON-serializable status dictionary.
        """
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "operation": self.operation,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
        }


class JobManager:
    """Create, run, and track performance jobs in this process.

    Not thread-safe by design: all mutation happens on the event loop, and the
    worker only touches its own job record inside the event loop thread via
    :func:`asyncio.create_task`.
    """

    def __init__(self, service_factory: Any | None = None) -> None:
        """Initialize the manager.

        Args:
            service_factory: Callable returning a PerformanceService. Defaults
                to constructing one from the cached settings. Tests inject a
                stub this way.
        """
        self._jobs: dict[str, Job] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._service_factory = service_factory
        self._limiter: anyio.CapacityLimiter | None = None

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

    def get(self, job_id: str) -> Job | None:
        """Return a job by identifier.

        Args:
            job_id: The job identifier.

        Returns:
            The job, or None when no job has that id.
        """
        return self._jobs.get(job_id)

    def list_jobs(self, organization_id: str | None = None) -> list[Job]:
        """Return every tracked job, newest first.

        Args:
            organization_id: If provided, only return jobs belonging to this
                organisation.

        Returns:
            All known jobs ordered by creation time descending, filtered by
            organisation when specified.
        """
        jobs = sorted(
            self._jobs.values(),
            key=lambda job: job.created_at,
            reverse=True,
        )

        if organization_id is not None:
            jobs = [job for job in jobs if job.organization_id == organization_id]

        return jobs

    def clear(self) -> None:
        """Drop all tracked jobs. Intended for test isolation."""
        self._jobs.clear()
        self._tasks.clear()

    # ------------------------------------------------------------------
    # Artifacts
    # ------------------------------------------------------------------

    def resolve_artifact(self, job_id: str, filename: str) -> Path | None:
        """Resolve one generated chart to a readable path.

        Security rests on an allowlist, not on sanitizing the client's input.
        The filename must match an entry the job itself reported in its
        ``visualizations`` result, so a client cannot name an arbitrary file.
        The name is additionally required to be a bare filename, and the
        resolved path must still sit inside this job's visualization directory
        once symlinks and relative segments are collapsed. All three checks must
        pass.

        Args:
            job_id: The job whose artifacts are being requested.
            filename: The bare artifact filename, e.g. ``channel_profit.png``.

        Returns:
            An absolute path to the artifact, or None when the job is unknown,
            has not produced charts, or the filename is not one of its own.
        """
        job = self._jobs.get(job_id)

        if job is None or not job.result:
            return None

        visualizations = job.result.get("visualizations")

        if not isinstance(visualizations, list):
            return None

        # Allowlist: only names this job actually generated are servable.
        if not any(
            isinstance(entry, dict) and entry.get("filename") == filename
            for entry in visualizations
        ):
            return None

        # Must be a bare filename: no directory component at all.
        if not filename or Path(filename).name != filename:
            return None

        if filename in (".", "..") or Path(filename).is_absolute():
            return None

        directory = self._visualization_dir(job_id).resolve()

        try:
            candidate = (directory / filename).resolve()
        except OSError:
            return None

        # Final containment check, after collapsing any relative segments.
        if candidate.parent != directory:
            return None

        if not candidate.is_file():
            return None

        return candidate

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------

    def submit(
        self,
        operation: str,
        file_path: str,
        request_id: str | None = None,
        organization_id: str | None = None,
        owner_id: str | None = None,
    ) -> Job:
        """Create a job and start it in the background.

        Returns as soon as the job is recorded, so the caller can answer 202
        without waiting for the analysis.

        Args:
            operation: The operation to run.
            file_path: Server-side dataset path.
            request_id: Correlation id of the creating request.
            organization_id: The organisation owning this job.
            owner_id: The user who created this job.

        Returns:
            The created job, in ``queued`` state.

        Raises:
            ValueError: If the operation is not supported. The router validates
                this first; the check guards direct callers.
        """
        if operation not in SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation: {operation}")

        job = Job(
            job_id=uuid.uuid4().hex,
            operation=operation,
            file_path=file_path,
            request_id=request_id or new_request_id(),
            organization_id=organization_id,
            owner_id=owner_id,
        )

        self._jobs[job.job_id] = job

        task = asyncio.create_task(self._run(job))
        self._tasks[job.job_id] = task

        logger.info(
            "performance_job_created job_id=%s operation=%s",
            job.job_id,
            operation,
        )

        return job

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def _run(self, job: Job) -> None:
        """Execute one job, recording its terminal state.

        Never raises: a failure is recorded on the job so the client's status
        poll reports it rather than the exception disappearing into a detached
        task.

        Args:
            job: The job to execute.
        """
        job.status = JobStatus.RUNNING
        job.started_at = utc_now()

        try:
            service = self._build_service()

            payload = await anyio.to_thread.run_sync(
                self._execute_blocking,
                service,
                job,
                limiter=self._get_limiter(),
                abandon_on_cancel=True,
            )

            job.result = payload
            job.status = JobStatus.COMPLETED

        except Exception as exc:
            logger.exception(
                "performance_job_failed job_id=%s operation=%s",
                job.job_id,
                job.operation,
            )

            job.error = sanitize_error(str(exc) or exc.__class__.__name__)
            job.status = JobStatus.FAILED

        finally:
            job.completed_at = utc_now()

            # One history record per job, emitted only on the terminal
            # transition. This block runs exactly once per job, so repeated
            # GET polls cannot produce duplicates.
            self._record_activity(job)

            logger.info(
                "performance_job_finished job_id=%s status=%s",
                job.job_id,
                job.status.value,
            )

    def _execute_blocking(self, service: Any, job: Job) -> dict[str, Any]:
        """Run the operation. Blocking; called in a worker thread.

        All pandas work happens here so nothing CPU-bound touches the event
        loop.

        Args:
            service: The PerformanceService instance.
            job: The job being executed.

        Returns:
            A JSON-safe operation payload.

        Raises:
            FileNotFoundError: If the dataset does not exist.
            ValueError: If the dataset extension is unsupported.
            Exception: Whatever the underlying analysis raises.
        """
        path = self._resolve_path(job.file_path)

        if job.operation == "load_dataset":
            payload = service.load_dataset(str(path))
            payload.pop("output_dir", None)
            # The service reports the path it read. Reduce it to a bare filename:
            # an uploaded dataset lives under the upload directory, so returning
            # the path as given would disclose the server's directory layout to
            # any client that can run the operation.
            payload["file_path"] = path.name
            return payload

        df = self._load_frame(path)

        if job.operation == "compute_kpis":
            return service.compute_kpis(df)

        if job.operation == "compare_periods":
            return service.compare_periods(df)

        if job.operation == "analyze":
            return self._run_analysis(service, df, job)

        return self._run_visualizations(service, df, job)

    def _run_analysis(
        self,
        service: Any,
        df: pd.DataFrame,
        job: Job,
    ) -> dict[str, Any]:
        """Run analyzers and insights without writing charts.

        Uses the service's own pipeline method so there is no second
        implementation of what ``analyze`` means.

        Args:
            service: The PerformanceService instance.
            df: The prepared dataset.
            job: The job being executed, used for correlation.

        Returns:
            Analysis results plus insights.
        """
        payload = service.run_full_pipeline(
            df,
            include_visualizations=False,
            include_insights=True,
        )

        payload["failed_modules"] = self._scrub_failed(payload.get("failed_modules"))

        logger.info(
            "performance_job_analysis job_id=%s modules=%d failed=%d",
            job.job_id,
            len(payload.get("successful_modules", [])),
            len(payload.get("failed_modules", [])),
        )

        return payload

    def _run_visualizations(
        self,
        service: Any,
        df: pd.DataFrame,
        job: Job,
    ) -> dict[str, Any]:
        """Render charts into a job-scoped directory.

        Charts go to their own directory per job. The service's default
        directory is shared, so reusing it would report every PNG ever written
        rather than this job's output.

        Args:
            service: The PerformanceService instance.
            df: The prepared dataset.
            job: The job being executed, whose id scopes the output.

        Returns:
            Chart metadata with no absolute paths, and each artifact's real size
            on disk.
        """
        # The service returns bare filenames, not full paths, so that it never
        # leaks the output directory. Resolve each one against the directory it
        # actually wrote to; treating a filename as a path would resolve it
        # against the process working directory and report every chart as empty.
        target = self._visualization_dir(job.job_id)

        raw = service.generate_visualizations(
            df,
            output_dir=str(self._visualization_parent(job.job_id)),
        )

        artifacts: list[dict[str, Any]] = []

        for filename in raw.get("visualizations", []):
            path = target / Path(filename).name

            size = 0

            if path.is_file():
                size = path.stat().st_size
            else:
                logger.warning(
                    "performance_job_visualization_missing job_id=%s",
                    job.job_id,
                )

            artifacts.append(
                VisualizationArtifact(
                    name=path.stem,
                    filename=path.name,
                    size_bytes=size,
                ).model_dump()
            )

        logger.info(
            "performance_job_visualizations job_id=%s count=%d",
            job.job_id,
            len(artifacts),
        )

        return {
            "generated": len(artifacts),
            "visualizations": artifacts,
        }

    @staticmethod
    def _record_activity(job: Job) -> None:
        """Record one Performance job outcome in the Activity History.

        Only metadata is stored. The result payload, chart metadata, and the
        dataset path are all deliberately excluded.

        Args:
            job: The job that just reached a terminal state.
        """
        status = job.status.value

        if status not in ("completed", "failed"):
            return

        description: str | None = None

        # An integer chart count is metadata, not content.
        if job.operation == "visualize" and status == "completed":
            generated = (job.result or {}).get("generated")

            if isinstance(generated, int):
                description = f"Generated {generated} visualizations"

        duration_ms: int | None = None

        if job.started_at and job.completed_at:
            duration_ms = int((job.completed_at - job.started_at).total_seconds() * 1000)

        try:
            from app.services.activity_store import record_operation

            record_operation(
                agent="performance",
                operation=job.operation,
                status=status,
                duration_ms=duration_ms,
                description=description,
            )

        except Exception:
            logger.warning("activity_record_failed agent=performance", exc_info=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _scrub_failed(failed: Any) -> list[dict[str, Any]]:
        """Redact filesystem paths from analyzer failure entries.

        The service returns raw ``str(error)`` text by design. That text can
        contain absolute server paths, so it is sanitized here at the API
        boundary. The unmodified text is already logged by the registry.

        Args:
            failed: The raw ``failed_modules`` list.

        Returns:
            The list with path text redacted.
        """
        if not isinstance(failed, list):
            return []

        scrubbed: list[dict[str, Any]] = []

        for entry in failed:
            if not isinstance(entry, dict):
                continue

            scrubbed.append(
                {
                    "module": str(entry.get("module", "unknown")),
                    "error": sanitize_error(str(entry.get("error", ""))),
                }
            )

        return scrubbed

    @classmethod
    def _visualization_dir(cls, job_id: str) -> Path:
        """Return the directory holding one job's charts.

        Two paths are involved and they are not the same. The runner passes a
        parent directory to the service, and the service appends its own
        ``visualizations`` segment. Deriving both here keeps the runner and the
        service agreeing on where the PNGs land, which is what lets the runner
        stat them afterwards.

        Args:
            job_id: The job identifier scoping the output.

        Returns:
            An absolute path to the directory the service will write into.
        """
        return cls._visualization_parent(job_id) / "visualizations"

    @staticmethod
    def _visualization_parent(job_id: str) -> Path:
        """Return the directory handed to the service as its output root.

        Args:
            job_id: The job identifier scoping the output.

        Returns:
            An absolute path the service will treat as its parent.
        """
        from performance_agent.reporting import resolve_results_dir

        return resolve_results_dir("results/visualizations") / "jobs" / job_id

    @staticmethod
    def _load_frame(path: Path) -> pd.DataFrame:
        """Load and normalize a dataset for analysis.

        Args:
            path: Resolved dataset path.

        Returns:
            The prepared DataFrame.

        Raises:
            FileNotFoundError: If the dataset does not exist.
            ValueError: If the extension is unsupported.
        """
        from performance_agent.dataset import load_clean_dataset

        return load_clean_dataset(path)

    def _resolve_path(self, file_path: str) -> Path:
        """Resolve a dataset path against the backend root.

        Relative paths resolve from the backend directory rather than the
        process working directory, matching how agent paths are configured.
        Absolute paths are used as given.

        Args:
            file_path: The path from the request.

        Returns:
            An absolute path.
        """
        path = Path(file_path)

        if path.is_absolute():
            return path

        return get_settings().backend_dir / path

    def _build_service(self) -> Any:
        """Construct a PerformanceService.

        Returns:
            A service instance, or the injected factory's result.
        """
        if self._service_factory is not None:
            return self._service_factory()

        from performance_agent.service import PerformanceService

        return PerformanceService(settings=get_settings())

    def _get_limiter(self) -> anyio.CapacityLimiter:
        """Return the shared worker limiter, creating it on first use.

        Returns:
            The limiter bounding concurrent job execution.
        """
        if self._limiter is None:
            self._limiter = anyio.CapacityLimiter(get_settings().agent_max_concurrency)
        return self._limiter
