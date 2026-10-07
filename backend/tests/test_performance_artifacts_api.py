"""Tests for the job-scoped visualization artifact endpoint.

Covers serving a real generated PNG, unknown jobs, unknown artifacts, and a
set of traversal and arbitrary-path attempts. Every rejection path must be a
404 rather than a 500, and no response may leak a server filesystem path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.registry import AgentRegistry
from app.api import deps
from app.api.deps import get_job_manager, get_orchestrator, get_registry, get_settings_dep
from app.core.config import Settings
from app.main import create_app
from app.services.job_manager import JobManager
from app.services.orchestrator import Orchestrator

# A minimal but structurally valid PNG.
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\x00\x01\x00"
    b"\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

ARTIFACTS_URL = "/api/v1/performance/jobs/{job_id}/artifacts/{filename}"
SECRET_PATH = "C:/Users/someone/secret/Financials.xlsx"


class StubService:
    """Writes two real PNGs into the directory the job manager scopes per job."""

    def load_dataset(self, file_path: str) -> dict[str, Any]:
        """Return dataset metadata."""
        return {"rows": 700, "columns": 28, "column_names": [], "supported_extensions": [".csv"]}

    def compute_kpis(self, df: Any) -> dict[str, Any]:
        """Return KPI blocks."""
        return {"overall": {}}

    def compare_periods(self, df: Any) -> dict[str, Any]:
        """Return period comparison."""
        return {"status": "Success"}

    def generate_insights(self, df: Any) -> dict[str, Any]:
        """Return insights."""
        return {"total_insights": 0}

    def run_full_pipeline(
        self,
        df: Any,
        include_visualizations: bool = False,
        include_insights: bool = True,
    ) -> dict[str, Any]:
        """Run analysis without writing charts."""
        return {"analysis": {}, "successful_modules": [], "failed_modules": [], "insights": {}}

    def generate_visualizations(
        self,
        df: Any,
        output_dir: str | None = None,
    ) -> dict[str, Any]:
        """Write real PNGs and return bare filenames, matching the real service.

        Args:
            df: The prepared dataset.
            output_dir: Directory the job manager scopes to this job.

        Returns:
            Chart metadata without absolute paths.
        """
        names = ["channel_profit", "channel_sales"]

        target = Path(output_dir or ".") / "visualizations"
        target.mkdir(parents=True, exist_ok=True)

        for name in names:
            (target / f"{name}.png").write_bytes(PNG_BYTES)

        # Also drop a file that was NOT reported, to prove metadata allowlisting.
        (target / "unreported.png").write_bytes(PNG_BYTES)

        return {
            "generated": len(names),
            "visualizations": [f"{name}.png" for name in names],
        }


@pytest.fixture
def settings() -> Settings:
    """Return test settings."""
    return Settings(
        environment="test",
        debug=False,
        cors_origins=["http://testserver"],
        log_level="WARNING",
    )


def build_client(settings: Settings) -> AsyncClient:
    """Build a client over a fresh job manager."""
    registry = AgentRegistry()
    manager = JobManager(service_factory=StubService)

    deps.reset_state()
    app = create_app(settings)
    app.dependency_overrides[get_settings_dep] = lambda: settings
    app.dependency_overrides[get_registry] = lambda: registry
    app.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)
    app.dependency_overrides[get_job_manager] = lambda: manager

    return AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://testserver",
    )


async def run_visualize_job(client: AsyncClient) -> tuple[str, list[str]]:
    """Submit a visualize job and wait for it to complete.

    Args:
        client: The HTTP client.

    Returns:
        The job id and the artifact filenames it reported.
    """
    import asyncio

    created = await client.post(
        "/api/v1/performance/jobs",
        json={
            "operation": "visualize",
            "file_path": "performance_agent/data/Financials_standardized.csv",
        },
    )

    assert created.status_code == 202, created.text

    job_id = created.json()["data"]["job_id"]

    for _ in range(400):
        await asyncio.sleep(0.01)
        data = (await client.get(f"/api/v1/performance/jobs/{job_id}")).json()["data"]
        if data["status"] in ("completed", "failed"):
            break

    assert data["status"] == "completed", data.get("error")

    filenames = [v["filename"] for v in data["result"]["visualizations"]]

    return job_id, filenames


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------


async def test_generated_artifact_is_served(settings: Settings) -> None:
    """A PNG the job generated is served with an image/png media type."""
    async with build_client(settings) as client:
        job_id, filenames = await run_visualize_job(client)

        assert "channel_profit.png" in filenames

        response = await client.get(
            ARTIFACTS_URL.format(job_id=job_id, filename="channel_profit.png")
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == PNG_BYTES


async def test_served_response_leaks_no_server_path(settings: Settings) -> None:
    """The response exposes no absolute filesystem path."""
    async with build_client(settings) as client:
        job_id, _ = await run_visualize_job(client)
        response = await client.get(
            ARTIFACTS_URL.format(job_id=job_id, filename="channel_sales.png")
        )

    headers = " ".join(f"{k}: {v}" for k, v in response.headers.items())

    assert response.headers["content-type"] == "image/png"
    assert ":\\" not in headers
    assert "/Users/" not in headers
    assert "performance_agent" not in headers
    assert "results" not in headers


# --------------------------------------------------------------------------
# Rejections
# --------------------------------------------------------------------------


async def test_unknown_job_returns_404(settings: Settings) -> None:
    """A job id that was never issued returns 404."""
    async with build_client(settings) as client:
        response = await client.get(
            ARTIFACTS_URL.format(job_id="doesnotexist", filename="channel_profit.png")
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"


async def test_unknown_artifact_returns_404(settings: Settings) -> None:
    """A filename the job did not generate returns 404."""
    async with build_client(settings) as client:
        job_id, _ = await run_visualize_job(client)
        response = await client.get(ARTIFACTS_URL.format(job_id=job_id, filename="not_a_chart.png"))

    assert response.status_code == 404


async def test_unreported_but_existing_file_is_not_served(settings: Settings) -> None:
    """A PNG on disk that the job never reported is still refused.

    The file exists in the job's directory, so this proves the allowlist is
    doing the work rather than mere filesystem existence.
    """
    async with build_client(settings) as client:
        job_id, _ = await run_visualize_job(client)
        response = await client.get(ARTIFACTS_URL.format(job_id=job_id, filename="unreported.png"))

    assert response.status_code == 404


@pytest.mark.parametrize(
    "filename",
    [
        pytest.param("../secret.txt", id="parent_traversal"),
        pytest.param("../../secret.txt", id="double_traversal"),
        pytest.param("..%2fsecret.txt", id="encoded_traversal"),
        pytest.param("subdir/../../secret.txt", id="nested_traversal"),
        pytest.param("..\\secret.txt", id="windows_traversal"),
    ],
)
async def test_traversal_attempts_are_rejected(
    settings: Settings,
    filename: str,
) -> None:
    """Traversal and arbitrary-path filenames never escape the job directory."""
    async with build_client(settings) as client:
        job_id, _ = await run_visualize_job(client)
        response = await client.get(ARTIFACTS_URL.format(job_id=job_id, filename=filename))

    assert response.status_code == 404
    assert SECRET_PATH not in response.text


async def test_bare_parent_reference_serves_no_file(settings: Settings) -> None:
    """A bare ``..`` never reaches the artifact route.

    URL normalization collapses ``/artifacts/..`` to ``/jobs/{job_id}``, so the
    request lands on the job-status route and returns JSON. No PNG is served
    either way, which is what matters: the resolver independently rejects it.
    """
    async with build_client(settings) as client:
        job_id, _ = await run_visualize_job(client)
        response = await client.get(ARTIFACTS_URL.format(job_id=job_id, filename=".."))

    assert response.headers["content-type"] != "image/png"
    assert response.content != PNG_BYTES


@pytest.mark.parametrize(
    "filename",
    [
        pytest.param("..", id="bare_parent"),
        pytest.param("../x", id="parent"),
        pytest.param("../../x", id="grandparent"),
        pytest.param("subdir/../../x", id="nested"),
        pytest.param("channel_profit.png/..", id="trailing_parent"),
        pytest.param("C:\\Windows\\win.ini", id="absolute_windows"),
    ],
)
def test_resolver_rejects_non_artifact_names(filename: str) -> None:
    """The resolver refuses anything the job did not report as its own.

    Exercised directly because URL normalization means several of these never
    reach the HTTP route in a form that would test the guard.
    """
    import asyncio

    manager = JobManager(service_factory=StubService)

    async def run() -> None:
        created = manager.submit(
            operation="visualize",
            file_path="performance_agent/data/Financials_standardized.csv",
        )

        for _ in range(400):
            await asyncio.sleep(0.01)
            if created.status.value in ("completed", "failed"):
                break

        assert created.status.value == "completed"
        assert manager.resolve_artifact(created.job_id, filename) is None

    asyncio.run(run())


async def test_absolute_filename_is_rejected(settings: Settings) -> None:
    """An absolute path as the filename is refused."""
    async with build_client(settings) as client:
        job_id, _ = await run_visualize_job(client)
        response = await client.get(
            ARTIFACTS_URL.format(
                job_id=job_id,
                filename="C%3A%5CWindows%5Cwin.ini",
            )
        )

    assert response.status_code == 404


async def test_artifact_of_a_non_visualize_job_is_404(settings: Settings) -> None:
    """A job that generated no charts serves nothing."""
    import asyncio

    async with build_client(settings) as client:
        created = await client.post(
            "/api/v1/performance/jobs",
            json={
                "operation": "analyze",
                "file_path": "performance_agent/data/Financials_standardized.csv",
            },
        )
        job_id = created.json()["data"]["job_id"]

        for _ in range(400):
            await asyncio.sleep(0.01)
            data = (await client.get(f"/api/v1/performance/jobs/{job_id}")).json()["data"]
            if data["status"] in ("completed", "failed"):
                break

        response = await client.get(
            ARTIFACTS_URL.format(job_id=job_id, filename="channel_profit.png")
        )

    assert response.status_code == 404
