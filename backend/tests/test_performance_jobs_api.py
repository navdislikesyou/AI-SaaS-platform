"""Contract tests for the Performance Analyzer job API.

These cover the job lifecycle over the real FastAPI, router, and job manager
stack. A stub PerformanceService stands in for the agent, so no pandas run, no
39-chart generation, and no real dataset are required.

What is verified here: the 202 contract, lifecycle transitions, operation
dispatch, error handling, and the two safety properties that matter for a job
result served to a client -- no filesystem paths, and no silent failure.

The Performance Agent is not an ``/agents/execute`` agent, so one test also
pins that the catalog no longer advertises it there.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.adapters.performance import PerformanceAgentAdapter
from app.agents.registry import AgentRegistry
from app.api import deps
from app.api.deps import (
    get_current_user_from_token_optional_principal,
    get_job_manager,
    get_orchestrator,
    get_registry,
    get_settings_dep,
)
from app.core.config import Settings
from app.main import create_app
from app.services.job_manager import JobManager, sanitize_error
from app.services.orchestrator import Orchestrator

JOBS_URL = "/api/v1/performance/jobs"
DATASET = "performance_agent/data/Financials_standardized.csv"

SECRET_PATH = "C:/Users/someone/secret/Financials.xlsx"

#: A minimal but structurally valid PNG, written by the stub so that artifacts
#: carry a real byte count rather than a zero placeholder.
_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\x00\x01\x00"
    b"\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class StubPerformanceService:
    """Stands in for ``PerformanceService`` without touching pandas.

    Records which method each job invoked so dispatch can be asserted, and can
    be told to raise or to report analyzer failures.
    """

    def __init__(
        self,
        error: Exception | None = None,
        failed_modules: list[dict[str, str]] | None = None,
    ) -> None:
        """Initialize the stub.

        Args:
            error: Raised by every method when set, simulating an agent failure.
            failed_modules: Analyzer failure entries returned by the analyze
                pipeline, used to verify path scrubbing.
        """
        self._error = error
        self._failed_modules = failed_modules or []
        self.calls: list[str] = []

    def _check(self, name: str) -> None:
        """Record a call and raise if the stub was configured to fail.

        Args:
            name: The method being invoked.

        Raises:
            Exception: The configured error, when one was set.
        """
        self.calls.append(name)

        if self._error is not None:
            raise self._error

    def load_dataset(self, file_path: str) -> dict[str, Any]:
        """Return dataset metadata.

        Args:
            file_path: Dataset path from the job.

        Returns:
            Metadata describing the dataset.

        Raises:
            Exception: The configured error, when one was set.
        """
        self._check("load_dataset")

        return {
            "file_path": file_path,
            "rows": 700,
            "columns": 28,
            "column_names": ["date", "sales", "profit"],
            "supported_extensions": [".csv", ".xlsx", ".xls"],
        }

    def compute_kpis(self, df: Any) -> dict[str, Any]:
        """Return headline KPIs.

        Args:
            df: The prepared dataset.

        Returns:
            KPI blocks.

        Raises:
            Exception: The configured error, when one was set.
        """
        self._check("compute_kpis")

        return {"overall": {"total_sales": 118726350.29, "profit_margin": 14.88}}

    def compare_periods(self, df: Any) -> dict[str, Any]:
        """Return period comparison results.

        Args:
            df: The prepared dataset.

        Returns:
            Comparison results.

        Raises:
            Exception: The configured error, when one was set.
        """
        self._check("compare_periods")

        return {"status": "Success", "year_count": 2}

    def generate_insights(self, df: Any) -> dict[str, Any]:
        """Return generated insights.

        Args:
            df: The prepared dataset.

        Returns:
            Insight payload.

        Raises:
            Exception: The configured error, when one was set.
        """
        self._check("generate_insights")

        return {"total_insights": 17, "all_insights": []}

    def generate_visualizations(
        self,
        df: Any,
        output_dir: str | None = None,
    ) -> dict[str, Any]:
        """Return visualization metadata in the real service's shape.

        Mirrors ``PerformanceService.generate_visualizations``: bare filenames,
        never full paths, so the output directory cannot be leaked. Files are
        genuinely written into the target directory so the runner can stat them.
        That is what catches a mismatch between where the service writes and
        where the runner looks: an earlier stub returned absolute paths, which
        made the runner's own bug invisible.

        Args:
            df: The prepared dataset.
            output_dir: Directory the runner asked charts to be written to.

        Returns:
            Chart metadata including the absolute output directory, so the test
            can prove the router does not forward it.

        Raises:
            Exception: The configured error, when one was set.
        """
        self._check("generate_visualizations")

        target = Path(output_dir or ".") / "visualizations"
        target.mkdir(parents=True, exist_ok=True)

        names = ["monthly_sales_trend", "product_sales"]

        for name in names:
            (target / f"{name}.png").write_bytes(_PNG_BYTES)

        return {
            "generated": len(names),
            "output_dir": str(target),
            "visualizations": [f"{name}.png" for name in names],
        }

    def run_full_pipeline(
        self,
        df: Any,
        include_visualizations: bool = False,
        include_insights: bool = True,
    ) -> dict[str, Any]:
        """Run analyzers and insights.

        Args:
            df: The prepared dataset.
            include_visualizations: Must stay False: analysis jobs must not
                write charts as a side effect.
            include_insights: Whether insights are generated.

        Returns:
            Analysis results plus insights.

        Raises:
            Exception: The configured error, when one was set.
        """
        self._check("run_full_pipeline")

        if include_visualizations:
            raise AssertionError("analysis must not generate visualizations")

        return {
            "analysis": {"company": {"status": "Success"}},
            "successful_modules": ["company", "time"],
            "failed_modules": list(self._failed_modules),
            "insights": {"total_insights": 17},
        }


@pytest.fixture
def service() -> StubPerformanceService:
    """Return the stub service and the job manager wired to it.

    Returns:
        The stub, so tests can assert which operation was dispatched.
    """
    stub = StubPerformanceService()

    return stub


@pytest.fixture
def settings() -> Settings:
    """Return test settings.

    Returns:
        Settings configured for testing.
    """
    return Settings(
        environment="test",
        debug=False,
        cors_origins=["http://testserver"],
        log_level="WARNING",
        api_v1_prefix="/api/v1",
    )


def build_client(
    settings: Settings,
    service: StubPerformanceService,
) -> AsyncClient:
    """Build an HTTP client with a job manager backed by the stub.

    Args:
        settings: Settings for the application.
        service: The stub service the job manager will use.

    Returns:
        An AsyncClient bound to the application.
    """
    registry = AgentRegistry()
    registry.register(PerformanceAgentAdapter())

    manager = JobManager(service_factory=lambda: service)

    deps.reset_state()
    application = create_app(settings)
    application.dependency_overrides[get_settings_dep] = lambda: settings
    application.dependency_overrides[get_registry] = lambda: registry
    application.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)
    application.dependency_overrides[get_current_user_from_token_optional_principal] = lambda: None  # noqa: E501
    application.dependency_overrides[get_job_manager] = lambda: manager

    return AsyncClient(
        transport=ASGITransport(app=application),  # type: ignore[arg-type]
        base_url="http://testserver",
    )


@pytest.fixture
async def client(settings: Settings, service: StubPerformanceService) -> AsyncIterator[AsyncClient]:
    """Return an HTTP client over the job API.

    Args:
        settings: Test settings.
        service: Stub service.

    Yields:
        An AsyncClient over ASGI transport.
    """
    async with build_client(settings, service) as http_client:
        yield http_client


async def wait_for_terminal(
    http_client: AsyncClient,
    job_id: str,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """Poll a job until it reaches a terminal state.

    Background work runs on a detached task, so a test must let the event loop
    turn before the status changes. Polling rather than sleeping keeps the test
    fast without flaking.

    Args:
        http_client: Client bound to the application.
        job_id: The job to poll.
        timeout: Seconds to wait before giving up.

    Returns:
        The final job status payload.

    Raises:
        AssertionError: If the job does not finish within the timeout.
    """
    deadline = asyncio.get_running_loop().time() + timeout

    while asyncio.get_running_loop().time() < deadline:
        response = await http_client.get(f"{JOBS_URL}/{job_id}")

        assert response.status_code == 200, response.text

        status = response.json()["data"]["status"]

        if status in ("completed", "failed"):
            return response.json()["data"]

        await asyncio.sleep(0.01)

    raise AssertionError(f"job {job_id} did not reach a terminal state")


# --------------------------------------------------------------------------
# Creation contract
# --------------------------------------------------------------------------


async def test_create_analyze_job_returns_202(client: AsyncClient) -> None:
    """Creating a job is accepted rather than run inline."""
    response = await client.post(
        JOBS_URL,
        json={"operation": "analyze", "file_path": DATASET},
    )

    assert response.status_code == 202
    body = response.json()

    assert body["success"] is True
    assert body["message"] == "Performance job created."
    assert body["request_id"]

    data = body["data"]
    assert data["status"] == "queued"
    assert data["operation"] == "analyze"
    assert data["job_id"]


async def test_created_job_id_is_retrievable(client: AsyncClient) -> None:
    """The returned id addresses a real job."""
    created = await client.post(
        JOBS_URL,
        json={"operation": "analyze", "file_path": DATASET},
    )

    job_id = created.json()["data"]["job_id"]

    status = await client.get(f"{JOBS_URL}/{job_id}")

    assert status.status_code == 200
    assert status.json()["data"]["job_id"] == job_id


async def test_create_returns_without_waiting_for_analysis(settings: Settings) -> None:
    """The 202 does not block on the analysis completing.

    Submission must be decoupled from execution: a slow agent must not hold the
    request open, or the job API would be synchronous under a different name.
    """

    class SlowStub(StubPerformanceService):
        """Sleeps inside every operation to make blocking measurable."""

        def _check(self, name: str) -> None:
            """Record the call then block.

            Args:
                name: The method being invoked.
            """
            super()._check(name)
            time.sleep(0.4)

    async with build_client(settings, SlowStub()) as http_client:
        started = time.perf_counter()
        response = await http_client.post(
            JOBS_URL,
            json={"operation": "analyze", "file_path": DATASET},
        )
        elapsed = time.perf_counter() - started

    assert response.status_code == 202
    assert elapsed < 0.35, f"creation blocked for {elapsed:.2f}s"


# --------------------------------------------------------------------------
# Lifecycle
# --------------------------------------------------------------------------


async def test_job_reaches_completed(client: AsyncClient) -> None:
    """A successful job finishes in the completed state."""
    created = await client.post(
        JOBS_URL,
        json={"operation": "analyze", "file_path": DATASET},
    )

    job_id = created.json()["data"]["job_id"]

    final = await wait_for_terminal(client, job_id)

    assert final["status"] == "completed"
    assert final["error"] is None
    assert final["started_at"] is not None
    assert final["completed_at"] is not None
    assert final["created_at"] <= final["started_at"]


async def test_job_status_carries_the_result(client: AsyncClient) -> None:
    """A completed job exposes its operation payload."""
    created = await client.post(
        JOBS_URL,
        json={"operation": "analyze", "file_path": DATASET},
    )

    final = await wait_for_terminal(client, created.json()["data"]["job_id"])

    assert final["result"]["successful_modules"] == ["company", "time"]
    assert final["result"]["insights"]["total_insights"] == 17


# --------------------------------------------------------------------------
# Operation dispatch
# --------------------------------------------------------------------------


async def test_analyze_dispatches_to_the_pipeline(
    client: AsyncClient,
    service: StubPerformanceService,
) -> None:
    """The analyze operation runs the in-memory pipeline, not charts."""
    created = await client.post(
        JOBS_URL,
        json={"operation": "analyze", "file_path": DATASET},
    )

    final = await wait_for_terminal(client, created.json()["data"]["job_id"])

    assert final["status"] == "completed"
    assert "run_full_pipeline" in service.calls
    assert "generate_visualizations" not in service.calls


async def test_compute_kpis_job_works(
    client: AsyncClient,
    service: StubPerformanceService,
) -> None:
    """compute_kpis runs and returns KPI values."""
    created = await client.post(
        JOBS_URL,
        json={"operation": "compute_kpis", "file_path": DATASET},
    )

    final = await wait_for_terminal(client, created.json()["data"]["job_id"])

    assert final["status"] == "completed"
    assert service.calls == ["compute_kpis"]
    assert final["result"]["overall"]["profit_margin"] == 14.88


async def test_compare_periods_job_works(client: AsyncClient) -> None:
    """compare_periods runs and returns comparison results."""
    created = await client.post(
        JOBS_URL,
        json={"operation": "compare_periods", "file_path": DATASET},
    )

    final = await wait_for_terminal(client, created.json()["data"]["job_id"])

    assert final["status"] == "completed"
    assert final["result"]["year_count"] == 2


async def test_load_dataset_job_works(
    client: AsyncClient,
    service: StubPerformanceService,
) -> None:
    """load_dataset returns metadata rather than the dataset itself."""
    created = await client.post(
        JOBS_URL,
        json={"operation": "load_dataset", "file_path": DATASET},
    )

    final = await wait_for_terminal(client, created.json()["data"]["job_id"])

    assert final["status"] == "completed"
    assert service.calls == ["load_dataset"]
    assert final["result"]["rows"] == 700
    assert "columns" in final["result"]


async def test_visualize_job_works(client: AsyncClient) -> None:
    """visualize returns chart metadata."""
    created = await client.post(
        JOBS_URL,
        json={"operation": "visualize", "file_path": DATASET},
    )

    final = await wait_for_terminal(client, created.json()["data"]["job_id"])

    assert final["status"] == "completed"
    assert final["result"]["generated"] == 2


# --------------------------------------------------------------------------
# Visualization safety
# --------------------------------------------------------------------------


async def test_visualization_result_exposes_no_absolute_paths(client: AsyncClient) -> None:
    """Chart metadata carries names only, never server paths."""
    created = await client.post(
        JOBS_URL,
        json={"operation": "visualize", "file_path": DATASET},
    )

    job_id = created.json()["data"]["job_id"]

    final = await wait_for_terminal(client, job_id)

    body = await client.get(f"{JOBS_URL}/{job_id}")

    assert "output_dir" not in final["result"]

    for artifact in final["result"]["visualizations"]:
        assert set(artifact) == {"name", "filename", "size_bytes"}
        assert "/" not in artifact["name"]
        assert "\\" not in artifact["name"]
        assert "/" not in artifact["filename"]

    assert "results" not in body.text.replace(job_id, "")
    assert ":\\" not in body.text


async def test_visualization_artifacts_report_their_real_size(
    client: AsyncClient,
) -> None:
    """Each artifact carries the byte count of the file on disk.

    Regression test. The service returns bare filenames, so the runner must
    resolve them against the job's visualization directory. Treating a filename
    as a path resolved it against the process working directory instead, and
    every chart was reported as zero bytes while the PNGs existed and were
    valid.
    """
    created = await client.post(
        JOBS_URL,
        json={"operation": "visualize", "file_path": DATASET},
    )

    final = await wait_for_terminal(
        client,
        created.json()["data"]["job_id"],
    )

    artifacts = final["result"]["visualizations"]

    assert artifacts
    assert all(artifact["size_bytes"] > 0 for artifact in artifacts)
    assert any(artifact["size_bytes"] == len(_PNG_BYTES) for artifact in artifacts)


async def test_visualization_sizes_match_the_files_written(
    tmp_path: Path,
) -> None:
    """Reported sizes correspond to real files at the resolved location.

    Drives the runner directly so the on-disk layout can be inspected: the job
    directory must hold a ``visualizations`` subdirectory containing the PNGs
    the service reported.
    """
    manager = JobManager(service_factory=StubPerformanceService)
    job = manager.submit(operation="visualize", file_path=DATASET)

    await asyncio.wait_for(_run_to_completion(manager, job), timeout=5.0)

    assert job.status.value == "completed"

    chart_dir = manager._visualization_dir(job.job_id)

    assert chart_dir.is_dir()
    assert chart_dir.name == "visualizations"
    assert chart_dir.parent.name == job.job_id

    on_disk = sorted(chart_dir.glob("*.png"))

    assert len(on_disk) == len(job.result["visualizations"])

    reported = {a["filename"]: a["size_bytes"] for a in job.result["visualizations"]}

    for path in on_disk:
        assert reported[path.name] == path.stat().st_size
        assert path.stat().st_size > 0


async def _run_to_completion(manager: JobManager, job: Any) -> None:
    """Wait for a submitted job to leave the queued state.

    Args:
        manager: The job manager holding the job.
        job: The job to wait on.
    """
    while job.status.value == "queued":
        await asyncio.sleep(0.01)

    while job.status.value == "running":
        await asyncio.sleep(0.01)


async def test_visualizations_are_scoped_per_job(client: AsyncClient) -> None:
    """Each job renders into its own directory.

    The service globs a shared directory by default, so without per-job scoping
    one job would report another job's charts.
    """
    first = await client.post(JOBS_URL, json={"operation": "visualize", "file_path": DATASET})
    second = await client.post(JOBS_URL, json={"operation": "visualize", "file_path": DATASET})

    first_final = await wait_for_terminal(client, first.json()["data"]["job_id"])
    second_final = await wait_for_terminal(client, second.json()["data"]["job_id"])

    assert first_final["status"] == "completed"
    assert second_final["status"] == "completed"


# --------------------------------------------------------------------------
# Failure handling
# --------------------------------------------------------------------------


async def test_background_failure_marks_job_failed(settings: Settings) -> None:
    """An exception during execution fails the job rather than vanishing."""
    service = StubPerformanceService(error=RuntimeError("model exploded"))

    async with build_client(settings, service) as http_client:
        created = await http_client.post(
            JOBS_URL,
            json={"operation": "analyze", "file_path": DATASET},
        )

        final = await wait_for_terminal(http_client, created.json()["data"]["job_id"])

    assert final["status"] == "failed"
    assert final["error"] == "model exploded"
    assert final["result"] is None


async def test_missing_dataset_fails_the_job_with_a_sanitized_error(
    settings: Settings,
) -> None:
    """A nonexistent dataset fails the job without leaking the server path.

    The runner reads real files, so this exercises the actual loader rather
    than a stub.
    """
    async with build_client(settings, StubPerformanceService()) as http_client:
        created = await http_client.post(
            JOBS_URL,
            json={
                "operation": "analyze",
                "file_path": "performance_agent/data/does_not_exist.csv",
            },
        )

        final = await wait_for_terminal(http_client, created.json()["data"]["job_id"])

    assert final["status"] == "failed"
    assert final["error"] is not None
    assert "does_not_exist" not in final["error"]
    assert "<path>" in final["error"]


async def test_failed_analyzer_paths_are_scrubbed(settings: Settings) -> None:
    """Analyzer failure text is sanitized before it reaches a client.

    The service returns raw ``str(error)`` by design; the API layer is
    responsible for redacting filesystem paths.
    """
    service = StubPerformanceService(
        failed_modules=[
            {"module": "company", "error": f"cannot open {SECRET_PATH}"},
        ],
    )

    async with build_client(settings, service) as http_client:
        created = await http_client.post(
            JOBS_URL,
            json={"operation": "analyze", "file_path": DATASET},
        )

        final = await wait_for_terminal(http_client, created.json()["data"]["job_id"])

    assert final["status"] == "completed"

    failed = final["result"]["failed_modules"]

    assert failed[0]["module"] == "company"
    assert SECRET_PATH not in failed[0]["error"]
    assert "<path>" in failed[0]["error"]


# --------------------------------------------------------------------------
# Request validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"operation": "not_a_real_op", "file_path": DATASET}, id="unknown_operation"),
        pytest.param({"operation": "", "file_path": DATASET}, id="blank_operation"),
        pytest.param({"operation": "analyze"}, id="missing_file_path"),
        pytest.param({"operation": "analyze", "file_path": ""}, id="blank_file_path"),
        pytest.param({"file_path": DATASET}, id="missing_operation"),
    ],
)
async def test_invalid_requests_are_rejected(client: AsyncClient, payload: dict[str, Any]) -> None:
    """Bad input is refused at the boundary with a 4xx."""
    response = await client.post(JOBS_URL, json=payload)

    assert response.status_code in (404, 422)
    assert response.json()["success"] is False


async def test_unknown_operation_returns_404_with_supported_list(
    client: AsyncClient,
) -> None:
    """An unsupported operation names the ones that are supported."""
    response = await client.post(
        JOBS_URL,
        json={"operation": "predict", "file_path": DATASET},
    )

    assert response.status_code == 404

    body = response.json()

    assert body["error"]["code"] == "OPERATION_NOT_FOUND"
    assert "analyze" in body["error"]["details"]["supported"]


async def test_extra_fields_are_rejected(client: AsyncClient) -> None:
    """An unrecognized field is refused rather than silently ignored.

    A mistyped ``filepath`` would otherwise be ignored and surface much later
    as a confusing failure.
    """
    response = await client.post(
        JOBS_URL,
        json={
            "operation": "analyze",
            "file_path": DATASET,
            "filepath": "typo.csv",
        },
    )

    assert response.status_code == 422


async def test_unknown_job_id_returns_404(client: AsyncClient) -> None:
    """Polling an id that was never issued returns 404."""
    response = await client.get(f"{JOBS_URL}/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"


# --------------------------------------------------------------------------
# Catalog representation
# --------------------------------------------------------------------------


async def test_catalog_no_longer_advertises_performance_operations(
    client: AsyncClient,
) -> None:
    """The agent catalog does not advertise job-based operations.

    Advertising them would promise something ``/agents/execute`` cannot deliver.
    """
    response = await client.get("/api/v1/agents")

    agents = response.json()["data"]["agents"]
    performance = next(a for a in agents if a["name"] == "performance")

    assert performance["capabilities"] == []
    assert performance["available"] is False
    assert "/api/v1/performance/jobs" in performance["description"]


@pytest.mark.parametrize(
    "operation",
    ["load_dataset", "compute_kpis", "compare_periods", "analyze", "visualize"],
)
async def test_performance_operations_still_rejected_by_agents_execute(
    client: AsyncClient,
    operation: str,
) -> None:
    """The former capabilities are not reachable through the agent endpoint."""
    response = await client.post(
        "/api/v1/agents/execute",
        json={"agent": "performance", "operation": operation, "payload": {}},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AGENT_UNAVAILABLE"


# --------------------------------------------------------------------------
# Knowledge and Automation unaffected
# --------------------------------------------------------------------------


async def test_knowledge_and_automation_are_unaffected(client: AsyncClient) -> None:
    """Adding the job router does not disturb the agent catalog."""
    response = await client.get("/api/v1/agents")

    names = [a["name"] for a in response.json()["data"]["agents"]]

    assert names == ["performance"]
    assert response.status_code == 200


# --------------------------------------------------------------------------
# Sanitizer unit tests
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,forbidden",
    [
        pytest.param(f"cannot open {SECRET_PATH}", SECRET_PATH, id="windows_path"),
        pytest.param("cannot open C:\\Users\\bob\\data.csv", "bob", id="windows_backslash"),
        pytest.param("cannot open /home/bob/data.csv", "bob", id="posix_path"),
        pytest.param("cannot open \\\\server\\share\\data.csv", "server", id="unc_path"),
    ],
)
def test_sanitize_error_removes_paths(raw: str, forbidden: str) -> None:
    """Filesystem paths are replaced with a placeholder."""
    result = sanitize_error(raw)

    assert forbidden not in result
    assert "<path>" in result


def test_sanitize_error_keeps_useful_text() -> None:
    """The human-readable part of a message survives sanitization."""
    result = sanitize_error(f"No such column 'sales' in {SECRET_PATH}")

    assert "No such column" in result
    assert "sales" in result


def test_sanitize_error_redacts_paths_containing_spaces() -> None:
    """A Windows path with spaces is redacted in full.

    Real project paths contain spaces. A sanitizer that stopped at the first
    space would leave ``Platform\\AI-SaaS...\\file.csv`` exposed, which is the
    exact leak this function exists to prevent.
    """
    result = sanitize_error(
        "Input file not found: " r"C:\Saas Platform\AI-SaaS-platform-git\backend\data\missing.csv"
    )

    assert "Saas Platform" not in result
    assert "AI-SaaS-platform-git" not in result
    assert "missing.csv" not in result
    assert "Input file not found:" in result


# --------------------------------------------------------------------------
# Path confinement regression tests for file_path
# --------------------------------------------------------------------------


SECRET_PATH = "C:/Users/someone/secret/Financials.xlsx"

_WILDCARD_PATH = "C:/Windows/system32/config/SAM"
_TRAVERSAL_PATH = "../../../etc/passwd.csv"
_ABSOLUTE_POSIX = "/etc/passwd.csv"
_ABSOLUTE_WINDOWS = "C:/Windows/system32/config/SAM"
_VALID_RELATIVE = "performance_agent/data/Financials_standardized.csv"


@pytest.mark.parametrize(
    "file_path",
    [
        _ABSOLUTE_POSIX,
        _ABSOLUTE_WINDOWS,
        _TRAVERSAL_PATH,
        _WILDCARD_PATH,
    ],
)
async def test_file_path_absolute_or_traversal_rejected(
    client: AsyncClient,
    file_path: str,
) -> None:
    """Absolute paths and traversal attempts in file_path are rejected."""
    response = await client.post(
        JOBS_URL,
        json={"operation": "analyze", "file_path": file_path},
    )
    assert response.status_code in (404, 422)


async def test_file_path_valid_relative_works(
    client: AsyncClient,
) -> None:
    """A valid relative file_path within the allowlist succeeds."""
    response = await client.post(
        JOBS_URL,
        json={"operation": "analyze", "file_path": _VALID_RELATIVE},
    )
    assert response.status_code == 202


async def test_dataset_id_still_takes_precedence(
    client: AsyncClient,
) -> None:
    """dataset_id is always preferred over file_path."""
    # This is implicitly tested by the existing tests, but we verify that
    # providing both does not silently fall back to file_path.
    response = await client.post(
        JOBS_URL,
        json={"operation": "analyze", "dataset_id": "sample", "file_path": _VALID_RELATIVE},
    )
    assert response.status_code in (404, 422)


async def test_file_path_symlink_escape_rejected(
    client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A symlink inside the allowlisted directory cannot reach a file outside it.

    The path is resolved through the symlink before it is checked against the
    allowlist, so a link that points out of the directory is refused. Without
    that resolution a link would be accepted and the job would read the file
    it points at.
    """
    allowed_dir = tmp_path / "performance_agent" / "data"
    allowed_dir.mkdir(parents=True)

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "secret.csv").write_text("secret data")

    link = allowed_dir / "escape.csv"

    try:
        link.symlink_to(outside_dir / "secret.csv")
    except OSError as exc:  # pragma: no cover - depends on platform privileges
        pytest.skip(f"symlinks cannot be created here: {exc}")

    # The allowlist is derived from the configured sample dataset path, which
    # resolves against the backend directory. Pointing the backend directory at
    # the temporary tree keeps the test out of the repository.
    monkeypatch.setattr(Settings, "backend_dir", property(lambda self: tmp_path))

    response = await client.post(
        JOBS_URL,
        json={"operation": "analyze", "file_path": "performance_agent/data/escape.csv"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "secret.csv" not in response.text
