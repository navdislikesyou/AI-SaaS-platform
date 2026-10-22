"""Contract tests for the Performance dataset upload API.

These cover the browser upload path end to end over the real FastAPI, router,
upload service, and job manager stack: what is accepted, what is refused, what
the client is allowed to learn, and how a dataset id becomes the file a
background job actually reads.

The property that matters most is that a client never names a file. Every test
that touches the filesystem asserts through the upload directory or through the
job's own behavior, never through a path the client supplied, because a
dataset_id that could be turned into an arbitrary path would make every other
guarantee here worthless.

Uploaded files and the manifest are redirected into a tmp directory, so running
this suite writes nothing into the repository. Two tests intentionally exercise
the real loader against a real CSV, because the job-dispatch and sample-dataset
guarantees cannot be checked with a stub.
"""

from __future__ import annotations

import asyncio
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
    get_dataset_manifest,
    get_dataset_upload_service,
)
from app.core.config import Settings
from app.main import create_app
from app.services.dataset_upload import (
    SAMPLE_DATASET_ID,
    DatasetManifest,
    DatasetUploadService,
)
from app.services.job_manager import JobManager
from tests.fakes import FakePrincipal

DATASETS_URL = "/api/v1/performance/datasets"
JOBS_URL = "/api/v1/performance/jobs"

#: A CSV with the columns the analyzers actually look for, so a job run against
#: it produces output rather than an empty analysis.
#:
#: ``sales_target`` and ``profit_target`` are included deliberately.
#: ``CompanyAnalyzer.employee_performance`` guards only on ``employee_name`` and
#: then aggregates the two target columns unguarded, so a dataset that has
#: ``employee_name`` but no targets fails compute_kpis outright. That is existing
#: agent behaviour, not something this upload path decides, so the fixture simply
#: has the shape a real export has.
VALID_CSV = (
    b"date,sales,profit,units_sold,sales_target,profit_target,employee_id,"
    b"employee_name,department,product,region,customer_segment,sales_channel\n"
    b"2026-01-01,1000,200,4,1100,220,E-1,Aarti Rao,Sales,Widget,North,SMB,Direct\n"
    b"2026-02-01,1500,300,6,1400,280,E-2,Omkar Shenwai,Sales,Gadget,South,"
    b"Enterprise,Partner\n"
)

#: The same rows without the dimension columns, used where a minimal table is
#: clearer than a full one.
MINIMAL_CSV = b"date,sales,profit\n" b"2026-01-01,1000,200\n" b"2026-02-01,1500,300\n"

#: Path the packaged sample resolves to, relative to the backend directory.
SAMPLE_RELPATH = "performance_agent/data/Financials_standardized.csv"


@pytest.fixture
def settings() -> Settings:
    """Return settings pointed at a temporary upload directory.

    Returns:
        Settings whose upload directory and manifest live under tmp_path, so an
        upload in a test cannot pollute the repository.
    """
    return Settings(
        environment="test",
        debug=False,
        cors_origins=["http://testserver"],
        log_level="WARNING",
        api_v1_prefix="/api/v1",
    )


@pytest.fixture
def upload_dir(tmp_path: Path) -> Path:
    """Return a temporary dataset storage directory.

    Returns:
        A directory that does not exist yet, so the service creates it.
    """
    return tmp_path / "uploads" / "performance"


@pytest.fixture
def sample_csv(tmp_path: Path, settings: Settings) -> Path:
    """Create a packaged-style sample dataset for the reserved id to resolve to.

    The real sample lives inside the agent package, which is gitignored and may
    be absent in a bare checkout. Writing our own keeps the test hermetic while
    still exercising the real resolution path.

    Returns:
        The path the sample dataset id resolves to.
    """
    target = settings.resolve_upload_path(settings.performance_sample_dataset_path)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(VALID_CSV)

    return target


@pytest.fixture
def service(
    settings: Settings,
    upload_dir: Path,
) -> DatasetUploadService:
    """Return an upload service writing to the temporary directory.

    Returns:
        A service bound to the temp upload directory.
    """
    return DatasetUploadService(
        settings=settings,
        upload_dir=upload_dir,
        max_bytes=1024 * 1024,
    )


@pytest.fixture
def manifest(settings: Settings, upload_dir: Path) -> DatasetManifest:
    """Return a manifest writing to the temporary directory.

    Returns:
        A manifest bound to the temp upload directory.
    """
    return DatasetManifest(upload_dir / "datasets.json")


def build_client(
    settings: Settings,
    service: DatasetUploadService,
    manifest: DatasetManifest,
) -> AsyncClient:
    """Build an HTTP client with the real upload service and a real job manager.

    The job manager runs the real loader, so a job dispatched here genuinely
    reads the uploaded file.

    Args:
        settings: Settings for the application.
        service: The upload service to install.
        manifest: The manifest to install.

    Returns:
        An AsyncClient bound to the application.
    """
    registry = AgentRegistry()
    registry.register(PerformanceAgentAdapter())

    deps.reset_state()
    application = create_app(settings)
    application.dependency_overrides[get_dataset_upload_service] = lambda: service
    application.dependency_overrides[get_dataset_manifest] = lambda: manifest
    application.dependency_overrides[get_current_user_from_token_optional_principal] = lambda: FakePrincipal()  # noqa: E501

    return AsyncClient(
        transport=ASGITransport(app=application),  # type: ignore[arg-type]
        base_url="http://testserver",
    )


@pytest.fixture
async def client(
    settings: Settings,
    service: DatasetUploadService,
    manifest: DatasetManifest,
    sample_csv: Path,
) -> AsyncIterator[AsyncClient]:
    """Return an HTTP client over the dataset and job API.

    Args:
        settings: Test settings.
        service: Upload service under test.
        manifest: Manifest under test.
        sample_csv: Packaged-style sample dataset.

    Yields:
        An AsyncClient over ASGI transport.
    """
    manager = JobManager()
    deps.init_job_manager(manager)

    async with build_client(settings, service, manifest) as http_client:
        yield http_client

    deps.reset_state()


async def wait_for_terminal(
    http_client: AsyncClient,
    job_id: str,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Poll a job until it reaches a terminal state.

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


async def upload(client: AsyncClient, name: str, content: bytes) -> dict[str, Any]:
    """Upload one dataset and return the parsed response body.

    Args:
        client: Client bound to the application.
        name: Filename to send.
        content: File bytes to send.

    Returns:
        The decoded JSON body.
    """
    response = await client.post(
        DATASETS_URL,
        files={"file": (name, content, "application/octet-stream")},
    )

    return response.json()


def xlsx_bytes(columns: tuple[str, ...] = ("date", "sales", "profit")) -> bytes:
    """Build a small real XLSX workbook in memory.

    A hand-built ZIP would be rejected by the container check, so a genuine
    workbook is written instead. That is the point: the signature check and the
    parser check are separate layers and this exercises both.

    Args:
        columns: Column headers to write.

    Returns:
        The workbook bytes.
    """
    import io

    import pandas as pd

    buffer = io.BytesIO()

    pd.DataFrame(
        [[f"{index}-value" for index in range(len(columns))]],
        columns=list(columns),
    ).to_excel(buffer, index=False)

    return buffer.getvalue()


# --------------------------------------------------------------------------
# Successful uploads
# --------------------------------------------------------------------------


async def test_upload_csv_is_accepted(client: AsyncClient, upload_dir: Path) -> None:
    """A CSV upload returns 201 with an id and the normalized header."""
    response = await client.post(
        DATASETS_URL,
        files={"file": ("Financials.csv", VALID_CSV, "text/csv")},
    )

    assert response.status_code == 201

    body = response.json()

    assert body["success"] is True
    assert body["request_id"]

    dataset = body["data"]["dataset"]

    assert dataset["dataset_id"]
    assert dataset["filename"] == "Financials.csv"
    assert dataset["format"] == "csv"
    assert dataset["size_bytes"] == len(VALID_CSV)
    assert dataset["status"] == "ready"
    assert dataset["is_sample"] is False

    # Header names come back normalized, exactly as the analyzers see them.
    assert dataset["column_names"][:4] == ["date", "sales", "profit", "units_sold"]
    assert dataset["column_count"] == len(dataset["column_names"])

    # The file really landed in the upload directory.
    stored = list(upload_dir.glob("*.csv"))
    assert len(stored) == 1


async def test_upload_xlsx_is_accepted(client: AsyncClient, upload_dir: Path) -> None:
    """An XLSX upload is accepted and its header is read."""
    payload = xlsx_bytes()

    response = await client.post(
        DATASETS_URL,
        files={
            "file": (
                "Book1.xlsx",
                payload,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 201

    dataset = response.json()["data"]["dataset"]

    assert dataset["format"] == "xlsx"
    assert dataset["column_names"] == ["date", "sales", "profit"]
    assert len(list(upload_dir.glob("*.xlsx"))) == 1


async def test_upload_reports_the_real_column_count(client: AsyncClient) -> None:
    """A wide CSV reports every header, not a truncated sample."""
    header = ",".join(f"col_{index}" for index in range(12))
    body = f"{header}\n" + "".join(
        f"{','.join(str(value) for value in range(12))}\n" for _ in range(3)
    )

    response = await client.post(
        DATASETS_URL,
        files={"file": ("wide.csv", body.encode(), "text/csv")},
    )

    dataset = response.json()["data"]["dataset"]

    assert dataset["column_count"] == 12
    assert dataset["column_names"] == [f"col_{index}" for index in range(12)]


async def test_uploaded_dataset_can_be_selected_from_the_list(
    client: AsyncClient,
) -> None:
    """A stored dataset appears in the list with no path attached."""
    uploaded = await upload(client, "Financials.csv", VALID_CSV)

    response = await client.get(DATASETS_URL)

    assert response.status_code == 200

    body = response.json()["data"]

    uploaded_id = uploaded["data"]["dataset"]["dataset_id"]
    ids = [entry["dataset_id"] for entry in body["datasets"]]

    assert uploaded_id in ids

    listed = next(e for e in body["datasets"] if e["dataset_id"] == uploaded_id)

    assert listed["filename"] == "Financials.csv"
    assert listed["format"] == "csv"


async def test_list_reports_the_upload_limit_and_accepted_formats(
    client: AsyncClient,
    service: DatasetUploadService,
) -> None:
    """The list tells the client what it may upload and how large."""
    response = await client.get(DATASETS_URL)

    body = response.json()["data"]

    assert body["max_upload_bytes"] == service.max_bytes
    assert body["supported_extensions"] == [".csv", ".xlsx"]


# --------------------------------------------------------------------------
# Unsupported and malformed uploads
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("Book1.xls", id="legacy_xls"),
        pytest.param("Book1.XLS", id="legacy_xls_uppercase"),
        pytest.param("notes.txt", id="plain_text"),
        pytest.param("archive.zip", id="zip"),
        pytest.param("dataset", id="no_extension"),
        pytest.param("dataset.csv.exe", id="double_extension"),
    ],
)
async def test_unsupported_extensions_are_rejected(
    client: AsyncClient,
    upload_dir: Path,
    name: str,
) -> None:
    """Only .csv and .xlsx are accepted; anything else is refused.

    `.xls` matters most. The loader accepts it but needs the xlrd engine, which
    is not a dependency, so advertising it would produce a job that fails with an
    opaque error instead of a clear refusal.
    """
    response = await client.post(
        DATASETS_URL,
        files={"file": (name, VALID_CSV, "application/octet-stream")},
    )

    assert response.status_code == 422

    body = response.json()

    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"]["supported_extensions"] == [".csv", ".xlsx"]

    assert not upload_dir.exists() or not list(upload_dir.iterdir())


async def test_empty_upload_is_rejected(client: AsyncClient, upload_dir: Path) -> None:
    """A zero-byte file is refused rather than stored as an empty dataset."""
    response = await client.post(
        DATASETS_URL,
        files={"file": ("empty.csv", b"", "text/csv")},
    )

    assert response.status_code == 422
    assert "empty" in response.json()["error"]["message"].lower()

    assert not upload_dir.exists() or not list(upload_dir.iterdir())


async def test_malformed_csv_is_rejected(client: AsyncClient, upload_dir: Path) -> None:
    """A file that is not parseable as CSV is refused at upload time."""
    # Fewer fields than the header declares is not what pandas considers fatal,
    # so use content that is definitively not a table.
    payload = b"\x00\x01\x02\x03binary junk\x00"

    response = await client.post(
        DATASETS_URL,
        files={"file": ("broken.csv", payload, "text/csv")},
    )

    assert response.status_code == 422

    assert not upload_dir.exists() or not list(upload_dir.iterdir())


async def test_csv_renamed_to_xlsx_is_rejected(client: AsyncClient) -> None:
    """A CSV renamed .xlsx is caught by the container check.

    Without this the file would reach the Excel parser and fail with an error
    that names an XML problem rather than the real cause.
    """
    response = await client.post(
        DATASETS_URL,
        files={"file": ("disguised.xlsx", VALID_CSV, "application/octet-stream")},
    )

    assert response.status_code == 422
    assert "xlsx" in response.json()["error"]["message"].lower()


async def test_truncated_xlsx_is_rejected(client: AsyncClient) -> None:
    """A ZIP that is not a workbook is refused."""
    response = await client.post(
        DATASETS_URL,
        files={
            "file": (
                "broken.xlsx",
                b"PK\x03\x04 not really a workbook",
                "application/octet-stream",
            )
        },
    )

    assert response.status_code == 422


async def test_oversized_upload_is_rejected_and_leaves_nothing(
    client: AsyncClient,
    upload_dir: Path,
    service: DatasetUploadService,
) -> None:
    """An upload past the limit is refused while streaming and fully cleaned up.

    The limit is enforced during the write, so the file is abandoned rather than
    buffered, and the partial write is removed.
    """
    oversized = b"date,sales\n" + (b"2026-01-01,1\n" * 200_000)

    assert len(oversized) > service.max_bytes

    response = await client.post(
        DATASETS_URL,
        files={"file": ("big.csv", oversized, "text/csv")},
    )

    assert response.status_code == 422

    error = response.json()["error"]

    assert error["details"]["max_bytes"] == service.max_bytes

    assert not upload_dir.exists() or not list(upload_dir.iterdir())


# --------------------------------------------------------------------------
# Filename handling and traversal
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("../../etc/passwd.csv", id="relative_traversal"),
        pytest.param("..\\..\\windows\\system32.csv", id="windows_traversal"),
        pytest.param("/etc/passwd.csv", id="absolute_posix"),
        pytest.param("C:/Windows/system32.csv", id="absolute_windows"),
        pytest.param("sub/dir/nested.csv", id="nested_directories"),
    ],
)
async def test_traversal_filenames_are_flattened(
    client: AsyncClient,
    upload_dir: Path,
    name: str,
) -> None:
    """A traversal attempt survives only as a bare display name.

    The stored file name is generated, so the client's string cannot influence
    where anything is written. This checks the other half: that the traversal
    text does not leak back into a response as a path.
    """
    response = await client.post(
        DATASETS_URL,
        files={"file": (name, VALID_CSV, "text/csv")},
    )

    assert response.status_code == 201

    dataset = response.json()["data"]["dataset"]

    # Only the final component is kept, and no separator survives.
    assert "/" not in dataset["filename"]
    assert "\\" not in dataset["filename"]
    assert ".." not in dataset["filename"]

    # Everything on disk stays inside the upload directory.
    for stored in upload_dir.iterdir():
        assert stored.parent == upload_dir


async def test_traversal_upload_does_not_overwrite_a_packaged_sample(
    client: AsyncClient,
    sample_csv: Path,
) -> None:
    """An upload cannot reach the sample dataset.

    Storage names are generated and written with an exclusive create, and the
    upload directory is not the agent package, so there is no path from an upload
    to a packaged file.
    """
    original = sample_csv.read_bytes()

    await client.post(
        DATASETS_URL,
        files={"file": ("Financials_standardized.csv", VALID_CSV, "text/csv")},
    )

    assert sample_csv.read_bytes() == original


async def test_filename_is_required(client: AsyncClient) -> None:
    """A missing filename is refused rather than stored under a default."""
    response = await client.post(
        DATASETS_URL,
        files={"file": ("", VALID_CSV, "text/csv")},
    )

    assert response.status_code == 422


# --------------------------------------------------------------------------
# Dataset id resolution
# --------------------------------------------------------------------------


async def test_dataset_id_resolves_to_the_stored_file(
    client: AsyncClient,
    service: DatasetUploadService,
    manifest: DatasetManifest,
) -> None:
    """The id a client holds resolves to the file that was actually stored."""
    uploaded = await upload(client, "Financials.csv", VALID_CSV)

    dataset_id = uploaded["data"]["dataset"]["dataset_id"]

    resolved = service.resolve(dataset_id, manifest)

    assert resolved.is_file()
    assert resolved.parent == service.upload_dir
    assert resolved.read_bytes() == VALID_CSV


@pytest.mark.parametrize(
    "dataset_id",
    [
        pytest.param("does-not-exist", id="unknown"),
        pytest.param("", id="empty"),
        pytest.param("../../performance_agent/data/Financials_standardized.csv", id="traversal"),
        pytest.param("/etc/passwd", id="absolute"),
        pytest.param("C:/Windows/system.ini", id="windows_absolute"),
        pytest.param("sample/../sample", id="sample_with_traversal"),
        pytest.param("SAMPLE", id="wrong_case_reserved_id"),
    ],
)
async def test_unresolvable_dataset_ids_are_refused(
    client: AsyncClient,
    dataset_id: str,
) -> None:
    """Anything that is not a known id or the exact reserved id is refused.

    The reserved id is matched exactly, so a near miss is not a way to reach the
    filesystem.
    """
    response = await client.post(
        JOBS_URL,
        json={"operation": "compute_kpis", "dataset_id": dataset_id},
    )

    assert response.status_code == 422 or response.status_code == 404

    if response.status_code == 404:
        assert response.json()["error"]["code"] == "DATASET_NOT_FOUND"


async def test_unknown_dataset_id_creates_no_job(client: AsyncClient) -> None:
    """A job is never created for a dataset that cannot be resolved.

    Creating one and letting it fail later would report a queued analysis for a
    file that does not exist, and would invite a silent fallback.
    """
    response = await client.post(
        JOBS_URL,
        json={"operation": "analyze", "dataset_id": "does-not-exist"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DATASET_NOT_FOUND"


async def test_missing_stored_file_is_reported_as_unknown(
    client: AsyncClient,
    service: DatasetUploadService,
    upload_dir: Path,
) -> None:
    """An id whose file was deleted by hand is no longer resolvable."""
    uploaded = await upload(client, "Financials.csv", VALID_CSV)

    dataset_id = uploaded["data"]["dataset"]["dataset_id"]

    for stored in upload_dir.glob("*.csv"):
        stored.unlink()

    response = await client.post(
        JOBS_URL,
        json={"operation": "compute_kpis", "dataset_id": dataset_id},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DATASET_NOT_FOUND"


async def test_manifest_cannot_escape_the_upload_directory(
    tmp_path: Path,
    settings: Settings,
) -> None:
    """A hand-edited manifest cannot steer resolution out of the directory.

    The manifest is a plain JSON file on disk. If a row could name an arbitrary
    stored_name, editing that file would be equivalent to reading any file the
    process can open.
    """
    upload_root = tmp_path / "uploads" / "performance"
    manifest_path = upload_root / "datasets.json"

    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        "["
        '{"dataset_id": "evil", "stored_name": "../../../etc/passwd", '
        '"extension": ".csv", "size_bytes": 1, "status": "ready"}'
        "]",
        encoding="utf-8",
    )

    service = DatasetUploadService(settings=settings, upload_dir=upload_root)
    manifest = DatasetManifest(manifest_path)

    from app.core.exceptions import DatasetNotFoundError

    with pytest.raises(DatasetNotFoundError):
        service.resolve("evil", manifest)


# --------------------------------------------------------------------------
# Running analyses against an uploaded dataset
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "operation",
    ["load_dataset", "compute_kpis", "compare_periods", "analyze"],
)
async def test_each_operation_runs_against_an_uploaded_dataset(
    client: AsyncClient,
    operation: str,
) -> None:
    """Every non-chart operation completes on a file the client uploaded.

    This is the end-to-end guarantee: the id is resolved to the stored file and
    the real loader reads that file, not a packaged one.
    """
    uploaded = await upload(client, "Financials.csv", VALID_CSV)

    dataset_id = uploaded["data"]["dataset"]["dataset_id"]

    created = await client.post(
        JOBS_URL,
        json={"operation": operation, "dataset_id": dataset_id},
    )

    assert created.status_code == 202

    final = await wait_for_terminal(client, created.json()["data"]["job_id"])

    assert final["status"] == "completed", final.get("error")
    assert final["result"] is not None


async def test_load_dataset_describes_the_uploaded_file(client: AsyncClient) -> None:
    """Describe Dataset reports the uploaded file, not a server path."""
    uploaded = await upload(client, "Financials.csv", VALID_CSV)

    dataset_id = uploaded["data"]["dataset"]["dataset_id"]

    created = await client.post(
        JOBS_URL,
        json={"operation": "load_dataset", "dataset_id": dataset_id},
    )

    final = await wait_for_terminal(client, created.json()["data"]["job_id"])

    assert final["status"] == "completed"

    result = final["result"]

    # Rows and columns come from the uploaded file.
    assert result["rows"] == 2
    assert result["columns"] == 13
    assert "date" in result["column_names"]

    # The reported path is a bare filename.
    assert result["file_path"] == result["file_path"].split("/")[-1]
    assert "\\" not in result["file_path"]


async def test_compute_kpis_reads_the_uploaded_values(client: AsyncClient) -> None:
    """KPI totals come from the uploaded file.

    The numbers are computed by the real analyzer over the uploaded rows, so a
    job that silently fell back to the packaged sample could not produce them.
    """
    uploaded = await upload(client, "Financials.csv", VALID_CSV)

    created = await client.post(
        JOBS_URL,
        json={
            "operation": "compute_kpis",
            "dataset_id": uploaded["data"]["dataset"]["dataset_id"],
        },
    )

    final = await wait_for_terminal(client, created.json()["data"]["job_id"])

    assert final["status"] == "completed"

    overall = final["result"]["overall"]

    assert overall["total_sales"] == 2500
    assert overall["total_profit"] == 500


async def test_analyze_produces_output_for_an_uploaded_dataset(
    client: AsyncClient,
) -> None:
    """The full pipeline runs and reports no failing modules.

    The uploaded file carries the dimension columns the employee, department,
    product, and regional analyzers need, so a correct run has none of them
    skipped.
    """
    uploaded = await upload(client, "Financials.csv", VALID_CSV)

    created = await client.post(
        JOBS_URL,
        json={
            "operation": "analyze",
            "dataset_id": uploaded["data"]["dataset"]["dataset_id"],
        },
    )

    final = await wait_for_terminal(client, created.json()["data"]["job_id"])

    assert final["status"] == "completed", final.get("error")
    assert final["result"]["failed_modules"] == []


async def test_visualize_renders_charts_for_an_uploaded_dataset(
    client: AsyncClient,
) -> None:
    """Chart generation works on an uploaded dataset.

    Artifact serving is unchanged, so this also confirms the job-scoped
    visualization directory still holds what the result reported.
    """
    uploaded = await upload(client, "Financials.csv", VALID_CSV)

    created = await client.post(
        JOBS_URL,
        json={
            "operation": "visualize",
            "dataset_id": uploaded["data"]["dataset"]["dataset_id"],
        },
    )

    job_id = created.json()["data"]["job_id"]

    final = await wait_for_terminal(client, job_id, timeout=180.0)

    assert final["status"] == "completed", final.get("error")
    assert final["result"]["generated"] > 0

    first = final["result"]["visualizations"][0]

    served = await client.get(f"{JOBS_URL}/{job_id}/artifacts/{first['filename']}")

    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"


async def test_two_uploads_are_analyzed_separately(client: AsyncClient) -> None:
    """Each id reads its own file, so one upload cannot displace another."""
    small = b"date,sales,profit\n2026-01-01,10,1\n"
    large = b"date,sales,profit\n" + b"".join(
        f"2026-01-{day:02d},{day * 100},{day * 10}\n".encode() for day in range(1, 6)
    )

    first = await upload(client, "first.csv", small)
    second = await upload(client, "second.csv", large)

    first_id = first["data"]["dataset"]["dataset_id"]
    second_id = second["data"]["dataset"]["dataset_id"]

    assert first_id != second_id

    results = {}

    for label, dataset_id in (("first", first_id), ("second", second_id)):
        created = await client.post(
            JOBS_URL,
            json={"operation": "load_dataset", "dataset_id": dataset_id},
        )

        final = await wait_for_terminal(client, created.json()["data"]["job_id"])

        assert final["status"] == "completed"
        results[label] = final["result"]

    assert results["first"]["rows"] == 1
    assert results["second"]["rows"] == 5


# --------------------------------------------------------------------------
# Sample dataset and the existing file_path workflow
# --------------------------------------------------------------------------


async def test_sample_dataset_is_offered_without_an_upload(client: AsyncClient) -> None:
    """A fresh instance still has something selectable.

    The list route answers with the packaged dataset alone when the manifest is
    empty, so the workflow does not begin with an empty selector.
    """
    response = await client.get(DATASETS_URL)

    datasets = response.json()["data"]["datasets"]

    assert len(datasets) == 1
    assert datasets[0]["dataset_id"] == SAMPLE_DATASET_ID
    assert datasets[0]["is_sample"] is True
    assert datasets[0]["available"] is True


async def test_sample_entry_discloses_no_server_path(client: AsyncClient) -> None:
    """The reserved entry is described by basename only."""
    response = await client.get(DATASETS_URL)

    sample = response.json()["data"]["datasets"][0]

    assert sample["filename"] == "Financials_standardized.csv"
    assert "/" not in sample["filename"]
    assert "\\" not in sample["filename"]

    assert "performance_agent" not in response.text
    assert "uploads" not in response.text


async def test_sample_dataset_runs_an_analysis(client: AsyncClient) -> None:
    """The reserved id analyses the packaged dataset end to end."""
    created = await client.post(
        JOBS_URL,
        json={"operation": "load_dataset", "dataset_id": SAMPLE_DATASET_ID},
    )

    assert created.status_code == 202

    final = await wait_for_terminal(client, created.json()["data"]["job_id"])

    assert final["status"] == "completed", final.get("error")
    assert final["result"]["rows"] > 0
    assert "date" in final["result"]["column_names"]


async def test_existing_file_path_workflow_still_works(client: AsyncClient) -> None:
    """A server-side path is still accepted.

    This is the pre-existing operator workflow and it must keep working, because
    removing it would break existing callers that index a file already on disk.
    """
    created = await client.post(
        JOBS_URL,
        json={"operation": "load_dataset", "file_path": SAMPLE_RELPATH},
    )

    assert created.status_code == 202

    final = await wait_for_terminal(client, created.json()["data"]["job_id"])

    assert final["status"] == "completed", final.get("error")
    assert final["result"]["rows"] > 0


# --------------------------------------------------------------------------
# Request validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"operation": "analyze"}, id="no_reference"),
        pytest.param(
            {"operation": "analyze", "dataset_id": "sample", "file_path": SAMPLE_RELPATH},
            id="both_references",
        ),
        pytest.param({"operation": "analyze", "dataset_id": ""}, id="blank_dataset_id"),
        pytest.param(
            {"operation": "not_a_real_op", "dataset_id": "sample"},
            id="unknown_operation",
        ),
        pytest.param({"dataset_id": "sample"}, id="missing_operation"),
        pytest.param(
            {"operation": "analyze", "dataset_id": "sample", "filepath": "typo.csv"},
            id="extra_field",
        ),
    ],
)
async def test_invalid_job_requests_are_rejected(
    client: AsyncClient,
    payload: dict[str, Any],
) -> None:
    """Bad input is refused at the boundary.

    Supplying both references is refused rather than resolved: silently
    preferring one would let a job analyse a file the caller did not select.
    """
    response = await client.post(JOBS_URL, json=payload)

    assert response.status_code in (404, 422)
    assert response.json()["success"] is False


# --------------------------------------------------------------------------
# No disclosure
# --------------------------------------------------------------------------


async def test_upload_response_discloses_no_paths(client: AsyncClient, upload_dir: Path) -> None:
    """A successful upload reports no server path or stored filename."""
    response = await client.post(
        DATASETS_URL,
        files={"file": ("Financials.csv", VALID_CSV, "text/csv")},
    )

    body = response.json()

    assert str(upload_dir) not in response.text
    assert "uploads" not in response.text
    assert "\\" not in body["data"]["dataset"]["filename"]

    # The generated stored name is a UUID and never leaves the server.
    for stored in upload_dir.glob("*.csv"):
        assert stored.name not in response.text


async def test_error_responses_disclose_no_paths(client: AsyncClient) -> None:
    """A rejected upload explains itself without naming server directories."""
    response = await client.post(
        DATASETS_URL,
        files={"file": ("broken.xlsx", b"PK\x03\x04 truncated", "application/octet-stream")},
    )

    assert response.status_code == 422

    text = response.text

    assert "uploads" not in text
    assert ":\\" not in text
    assert "<path>" not in text


async def test_dataset_list_discloses_no_paths(client: AsyncClient) -> None:
    """Listing datasets returns names and ids, never locations."""
    await upload(client, "Financials.csv", VALID_CSV)

    response = await client.get(DATASETS_URL)

    assert "uploads" not in response.text
    assert "performance_agent" not in response.text


async def test_upload_response_carries_no_dataset_contents(client: AsyncClient) -> None:
    """The response carries metadata only.

    No row values may appear: the upload response is what ends up in a client's
    state and, indirectly, in activity history.
    """
    response = await client.post(
        DATASETS_URL,
        files={"file": ("Financials.csv", VALID_CSV, "text/csv")},
    )

    text = response.text

    assert "Aarti Rao" not in text
    assert "Widget" not in text
    assert "1000" not in text


async def test_failed_uploads_leave_no_orphan_files(client: AsyncClient, upload_dir: Path) -> None:
    """No rejected upload leaves anything behind.

    Each rejection is followed by an assertion that the directory is empty,
    including the oversized and malformed cases where a partial write had
    already started.
    """
    rejected = [
        ("bad.txt", b"content", "text/plain"),
        ("bad.xlsx", b"PK\x03\x04 truncated", "application/octet-stream"),
        ("empty.csv", b"", "text/csv"),
        ("big.csv", b"date,sales\n" + b"2026-01-01,1\n" * 200_000, "text/csv"),
    ]

    for name, content, content_type in rejected:
        response = await client.post(
            DATASETS_URL,
            files={"file": (name, content, content_type)},
        )

        assert response.status_code == 422, name

        remaining = list(upload_dir.iterdir()) if upload_dir.exists() else []

        assert remaining == [], f"{name} left {remaining}"


async def test_manifest_lists_only_accepted_datasets(
    client: AsyncClient,
    manifest: DatasetManifest,
) -> None:
    """A rejected upload is not recorded in the manifest either."""
    await client.post(
        DATASETS_URL,
        files={"file": ("bad.txt", b"content", "text/plain")},
    )

    assert manifest.read() == []

    await upload(client, "Financials.csv", VALID_CSV)

    rows = manifest.read()

    assert len(rows) == 1
    assert rows[0]["status"] == "ready"
