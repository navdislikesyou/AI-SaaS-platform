"""Tests for the Activity History store and API.

Every test points the store at a temporary file, so the real
``activity_history.json`` is never read or written.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.registry import AgentRegistry
from app.api import deps
from app.api.deps import (
    get_current_user_from_token_optional_principal,
    get_orchestrator,
    get_registry,
    get_settings_dep,
)
from app.core.config import Settings
from app.main import create_app
from app.services import activity_store
from app.services.activity_store import ActivityStore
from app.services.job_manager import JobManager
from app.services.orchestrator import Orchestrator

HISTORY_URL = "/api/v1/activity-history"

SECRET_ANSWER = "The platform uses BAAI/bge-base-en-v1.5 embeddings."
SECRET_EMAIL_BODY = "Dear Team, you are invited to a confidential strategy review."
SECRET_PATH = "C:/Users/someone/secret/Financials.xlsx"


@pytest.fixture
def history_file(tmp_path: Path) -> Iterator[Path]:
    """Install a temporary store for the duration of a test.

    Args:
        tmp_path: pytest's per-test temporary directory.

    Yields:
        The temporary history file path.
    """
    path = tmp_path / "activity_history.json"

    activity_store.set_store(ActivityStore(path))

    try:
        yield path

    finally:
        activity_store.reset_store()


@pytest.fixture
def settings() -> Settings:
    """Return test settings."""
    return Settings(environment="test", log_level="WARNING", _env_file=None)


class _TestUser:
    def __init__(self, **kwargs: object) -> None:
        self.id = "test-user-1"
        self.organization_id = "test-org-1"


def build_client(settings: Settings, job_manager: JobManager | None = None) -> AsyncClient:
    """Build an HTTP client with the history store already swapped in.

    Args:
        settings: Application settings.
        job_manager: Optional job manager to install.

    Returns:
        An AsyncClient bound to the application.
    """
    registry = AgentRegistry()

    deps.reset_state()
    app = create_app(settings)
    app.dependency_overrides[get_settings_dep] = lambda: settings
    app.dependency_overrides[get_registry] = lambda: registry
    app.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)
    # Provide a test user so that activity-history and other endpoints that
    # depend on ``get_current_user_from_token_optional_principal`` receive a
    # scoped user rather than ``None``.
    app.dependency_overrides[get_current_user_from_token_optional_principal] = lambda: _TestUser(  # noqa: E501
        id="test-user-1", organization_id="test-org-1"
    )

    if job_manager is not None:
        from app.api.deps import get_job_manager

        app.dependency_overrides[get_job_manager] = lambda: job_manager

    return AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://testserver",
    )


# --------------------------------------------------------------------------
# Store basics
# --------------------------------------------------------------------------


def test_missing_file_reads_as_empty_history(history_file: Path) -> None:
    """A history file that does not exist yet is an empty history, not an error."""
    assert not history_file.exists()
    assert ActivityStore(history_file).read() == []


def test_append_persists_a_record(history_file: Path) -> None:
    """A record is written and can be read back."""
    store = ActivityStore(history_file)

    store.append(
        {
            "id": "abc",
            "agent": "knowledge",
            "operation": "query",
            "description": "Answered a knowledge question",
            "status": "completed",
            "timestamp": "2026-10-07T14:31:00+05:30",
        }
    )

    stored = json.loads(history_file.read_text(encoding="utf-8"))

    assert len(stored) == 1
    assert stored[0]["agent"] == "knowledge"
    assert stored[0]["status"] == "completed"


def test_corrupt_file_reads_as_empty(history_file: Path) -> None:
    """A malformed file degrades to empty rather than raising."""
    history_file.parent.mkdir(parents=True, exist_ok=True)
    history_file.write_text("{not json", encoding="utf-8")

    assert ActivityStore(history_file).read() == []


def test_record_activity_generates_id_and_timestamp(history_file: Path) -> None:
    """A recorded activity carries an id and a timezone-aware timestamp."""
    record = activity_store.record_operation("knowledge", "query", "completed")

    assert record["id"]
    assert record["agent"] == "knowledge"
    assert record["operation"] == "query"
    assert record["status"] == "completed"
    # Offset-aware, so the browser can localize it.
    assert "+" in record["timestamp"] or record["timestamp"].endswith("Z")


def test_list_returns_newest_first(history_file: Path) -> None:
    """Activities come back newest first regardless of write order."""
    store = ActivityStore(history_file)

    for index in range(3):
        store.append(
            {
                "id": str(index),
                "agent": "knowledge",
                "operation": "query",
                "description": "Answered a knowledge question",
                "status": "completed",
                "timestamp": f"2026-10-07T14:0{index}:00+05:30",
            }
        )

    listed = activity_store.list_activities()

    assert [r["id"] for r in listed] == ["2", "1", "0"]


def test_list_respects_limit(history_file: Path) -> None:
    """A limit caps how many records come back."""
    store = ActivityStore(history_file)

    for index in range(5):
        store.append(
            {
                "id": str(index),
                "agent": "automation",
                "operation": "draft_action",
                "description": "Drafted automation action",
                "status": "completed",
                "timestamp": "2026-10-07T14:00:00+05:30",
            }
        )

    assert len(activity_store.list_activities(limit=2)) == 2


# --------------------------------------------------------------------------
# Per-agent descriptions
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "agent,operation,expected",
    [
        pytest.param("knowledge", "query", "Answered a knowledge question", id="knowledge_query"),
        pytest.param("knowledge", "ingest_document", "Ingested document", id="knowledge_ingest"),
        pytest.param(
            "automation", "draft_action", "Drafted automation action", id="automation_draft"
        ),
        pytest.param("performance", "compute_kpis", "Calculated performance KPIs", id="perf_kpis"),
        pytest.param("performance", "visualize", "Generated visualizations", id="perf_visualize"),
    ],
)
def test_each_agent_operation_records(
    history_file: Path,
    agent: str,
    operation: str,
    expected: str,
) -> None:
    """Every supported operation records with its own canonical description."""
    activity_store.record_operation(agent, operation, "completed")

    listed = activity_store.list_activities()

    assert len(listed) == 1
    assert listed[0]["agent"] == agent
    assert listed[0]["operation"] == operation
    assert listed[0]["description"] == expected
    assert listed[0]["status"] == "completed"


def test_failed_operation_records_a_failure(history_file: Path) -> None:
    """A failed operation records status failed with a failure description."""
    activity_store.record_operation("performance", "visualize", "failed")

    listed = activity_store.list_activities()

    assert listed[0]["status"] == "failed"
    assert listed[0]["description"] == "Visualization generation failed"


def test_unknown_operation_falls_back_without_storing_output(
    history_file: Path,
) -> None:
    """An unrecognised operation still records, using generic wording."""
    activity_store.record_operation("knowledge", "brand_new_op", "completed")

    assert activity_store.list_activities()[0]["description"] == "Completed brand_new_op"


# --------------------------------------------------------------------------
# Payload hygiene
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "forbidden",
    [
        pytest.param(SECRET_ANSWER, id="full_answer"),
        pytest.param(SECRET_EMAIL_BODY, id="email_body"),
        pytest.param(SECRET_PATH, id="filesystem_path"),
        pytest.param("result", id="result_payload_key"),
        pytest.param("payload", id="request_payload_key"),
        pytest.param("sources", id="source_contents"),
    ],
)
def test_records_contain_no_agent_output(
    history_file: Path,
    forbidden: str,
) -> None:
    """No agent output, path, or raw payload reaches the stored file."""
    activity_store.record_operation("knowledge", "query", "completed")
    activity_store.record_operation("automation", "draft_action", "completed")
    activity_store.record_operation("performance", "visualize", "completed")

    raw = history_file.read_text(encoding="utf-8")

    assert forbidden not in raw


def test_stored_record_keys_are_minimal(history_file: Path) -> None:
    """A record carries only the documented fields."""
    record = activity_store.record_operation("knowledge", "query", "completed")

    assert set(record) <= {
        "id",
        "agent",
        "operation",
        "description",
        "status",
        "timestamp",
        "duration_ms",
        "user_id",
        "organization_id",
    }


# --------------------------------------------------------------------------
# Performance: exactly one event per job
# --------------------------------------------------------------------------


class StubService:
    """Minimal service stand-in for a visualize job."""

    def generate_visualizations(
        self,
        df: Any,
        output_dir: str | None = None,
    ) -> dict[str, Any]:
        """Return chart metadata."""
        return {"generated": 7, "visualizations": ["a.png"]}

    def run_full_pipeline(
        self,
        df: Any,
        include_visualizations: bool = False,
        include_insights: bool = True,
    ) -> dict[str, Any]:
        """Return analysis results."""
        return {"analysis": {}, "successful_modules": [], "failed_modules": []}


async def drive_job(settings: Settings, manager: JobManager) -> str:
    """Submit a visualize job and wait for it to finish.

    Args:
        settings: Application settings.
        manager: The job manager to submit through.

    Returns:
        The job id.
    """
    import asyncio

    job = manager.submit(
        operation="visualize",
        file_path="performance_agent/data/Financials_standardized.csv",
        organization_id=_TestUser().organization_id,
        owner_id=_TestUser().id,
    )

    for _ in range(500):
        await asyncio.sleep(0.01)
        if job.status.value in ("completed", "failed"):
            break

    return job.job_id


async def test_polling_does_not_create_duplicate_activities(
    history_file: Path,
    settings: Settings,
) -> None:
    """Repeated status polls produce exactly one history record.

    A job is polled many times while it runs. Only the terminal transition
    should be recorded.
    """
    manager = JobManager(service_factory=StubService)
    job_id = await drive_job(settings, manager)

    async with build_client(settings, manager) as client:
        for _ in range(8):
            response = await client.get(f"/api/v1/performance/jobs/{job_id}")

            assert response.status_code == 200

    listed = activity_store.list_activities()

    assert len(listed) == 1
    assert listed[0]["operation"] == "visualize"


async def test_performance_job_records_at_most_one_activity(
    history_file: Path,
    settings: Settings,
) -> None:
    """Two jobs produce two records; one job can never produce two."""
    manager = JobManager(service_factory=StubService)

    await drive_job(settings, manager)
    await drive_job(settings, manager)

    listed = activity_store.list_activities()

    assert len(listed) == 2
    assert {r["operation"] for r in listed} == {"visualize"}


async def test_visualize_records_the_chart_count(
    history_file: Path,
    settings: Settings,
) -> None:
    """A completed visualize job records the generated chart count.

    An integer count is metadata, not content. The count is what the job
    actually wrote to disk, so it can differ from what the service claimed:
    the job manager rebuilds ``generated`` from the artifacts it found.
    """
    manager = JobManager(service_factory=StubService)

    await drive_job(settings, manager)

    listed = activity_store.list_activities()

    assert listed[0]["description"] == "Generated 1 visualizations"
    assert listed[0]["operation"] == "visualize"
    assert listed[0]["status"] == "completed"


async def test_failed_job_records_a_failure(history_file: Path, settings: Settings) -> None:
    """A job that raises records a failed activity rather than nothing."""
    import asyncio

    class Boom:
        def generate_visualizations(self, df: Any, output_dir: str | None = None) -> dict:
            """Fail the job."""
            raise RuntimeError("charts exploded")

    manager = JobManager(service_factory=Boom)
    job = manager.submit(operation="visualize", file_path="missing.csv")

    for _ in range(500):
        await asyncio.sleep(0.01)
        if job.status.value in ("completed", "failed"):
            break

    listed = activity_store.list_activities()

    assert job.status.value == "failed"
    assert len(listed) == 1
    assert listed[0]["status"] == "failed"
    # The raw failure text must not be stored either.
    assert "charts exploded" not in json.dumps(listed)


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------


async def test_empty_history_returns_an_empty_list(
    history_file: Path,
    settings: Settings,
) -> None:
    """A missing history file returns 200 with an empty list, not an error."""
    async with build_client(settings) as client:
        response = await client.get(HISTORY_URL)

    assert response.status_code == 200
    assert response.json()["data"] == []


async def test_history_endpoint_returns_records(
    history_file: Path,
    settings: Settings,
) -> None:
    """The endpoint returns stored records newest first."""
    for _ in range(3):
        activity_store.record_operation(
            "knowledge", "query", "completed",
            user_id="test-user-1", organization_id="test-org-1",
        )

    async with build_client(settings) as client:
        response = await client.get(HISTORY_URL)

    body = response.json()

    assert response.status_code == 200
    assert body["success"] is True
    assert len(body["data"]) == 3
    assert set(body["data"][0]) >= {
        "id",
        "agent",
        "operation",
        "description",
        "status",
        "timestamp",
    }


async def test_history_endpoint_rejects_a_bad_limit(
    history_file: Path,
    settings: Settings,
) -> None:
    """An out-of-range limit is a 422, not a 500."""
    async with build_client(settings) as client:
        response = await client.get(f"{HISTORY_URL}?limit=99999")

    assert response.status_code == 422


async def test_history_endpoint_never_returns_agent_output(
    history_file: Path,
    settings: Settings,
) -> None:
    """The endpoint response contains no agent output or server paths."""
    activity_store.record_operation("knowledge", "query", "completed")
    activity_store.record_operation("performance", "visualize", "completed")

    async with build_client(settings) as client:
        response = await client.get(HISTORY_URL)

    assert SECRET_ANSWER not in response.text
    assert SECRET_PATH not in response.text
    assert "results" not in response.text
