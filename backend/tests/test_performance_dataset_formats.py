"""Contract tests for the Performance dataset formats.

These exercise the dataset API the way a browser reaches it: through the
application's own dependency wiring, with no test double standing in for the
upload service. That matters because the wiring is what decides *which* uploader
runs, and the Performance dataset API and the Knowledge document API have
different allowlists (``.csv`` and ``.xlsx`` against ``.pdf``, ``.docx``, and
``.txt``). A test that overrides the upload service proves the service works; it
cannot prove the route reaches it.

What is checked here:

* a CSV is accepted, listed, and analysed end to end;
* an XLSX workbook is accepted and analysed the same way;
* a file whose content does not match its name is refused with a message that
  says why, whether it is the wrong extension, the wrong encoding, a missing
  header, or no data at all;
* the size limit is enforced;
* one tenant cannot reach another tenant's dataset.
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
    get_orchestrator,
    get_registry,
    get_settings_dep,
)
from app.core.config import Settings
from app.main import create_app
from app.services.job_manager import JobManager
from app.services.orchestrator import Orchestrator
from tests.fakes import FakePrincipal

DATASETS_URL = "/api/v1/performance/datasets"
JOBS_URL = "/api/v1/performance/jobs"

#: A CSV with the columns the analyzers look for, so a job over it produces
#: numbers rather than an empty analysis.
VALID_CSV = (
    b"date,sales,profit,units_sold,sales_target,profit_target,employee_id,"
    b"employee_name,department,product,region,customer_segment,sales_channel\n"
    b"2026-01-01,1000,200,4,1100,220,E-1,Aarti Rao,Sales,Widget,North,SMB,Direct\n"
    b"2026-02-01,1500,300,6,1400,280,E-2,Omkar Shenwai,Sales,Gadget,South,"
    b"Enterprise,Partner\n"
)

#: The organisation the first tenant owns resources under.
ORG_A = "test-org-a"

#: The organisation the second tenant owns resources under.
ORG_B = "test-org-b"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Return settings pointed at a temporary dataset directory.

    The upload directory and the manifest both live under tmp_path, so a test
    using the application's real wiring writes nothing into the repository.

    Returns:
        Settings whose dataset storage is temporary.
    """
    upload_dir = tmp_path / "performance"

    return Settings(
        environment="test",
        debug=False,
        cors_origins=["http://testserver"],
        log_level="WARNING",
        api_v1_prefix="/api/v1",
        performance_upload_dir=upload_dir,
        performance_upload_manifest_path=upload_dir / "datasets.json",
        performance_max_upload_bytes=1024 * 1024,
    )


@pytest.fixture
def upload_dir(settings: Settings) -> Path:
    """Return the temporary dataset storage directory.

    Returns:
        The directory the application under test writes datasets into.
    """
    return settings.resolved_performance_upload_dir


@pytest.fixture
def principal() -> Any:
    """Return a mutable holder for the current principal.

    The holder lets a test switch tenants between two requests over one client,
    which is what a cross-tenant attempt looks like from the server's side.

    Returns:
        A mutable object whose attributes the principal override reads.
    """
    return FakePrincipal(user_id="user-a", organization_id=ORG_A)


@pytest.fixture
async def client(
    settings: Settings,
    principal: Any,
) -> AsyncIterator[AsyncClient]:
    """Return a client over the application's real dataset wiring.

    The upload service and the manifest are deliberately *not* overridden: the
    point is to test the wiring the application actually ships.

    Args:
        settings: Test settings.
        principal: The mutable principal holder.

    Yields:
        An AsyncClient over ASGI transport.
    """
    registry = AgentRegistry()
    registry.register(PerformanceAgentAdapter())

    deps.reset_state()
    application = create_app(settings)
    application.dependency_overrides[get_settings_dep] = lambda: settings
    application.dependency_overrides[get_registry] = lambda: registry
    application.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)
    application.dependency_overrides[get_current_user_from_token_optional_principal] = (
        lambda: principal
    )
    deps.init_job_manager(JobManager())

    async with AsyncClient(
        transport=ASGITransport(app=application),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as http_client:
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


def xlsx_bytes(columns: tuple[str, ...] = ("date", "sales", "profit")) -> bytes:
    """Build a small real XLSX workbook in memory.

    A hand-built ZIP would be refused by the container check, so a genuine
    workbook is written instead.

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
# The application's own wiring
# --------------------------------------------------------------------------


async def test_a_csv_upload_is_accepted_through_the_real_wiring(
    client: AsyncClient,
    upload_dir: Path,
) -> None:
    """A CSV is stored by the dataset API, not refused as a document type.

    This is the guard against the upload service being wired to the Knowledge
    document uploader, whose allowlist is ``.pdf``, ``.docx``, and ``.txt``.
    """
    response = await client.post(
        DATASETS_URL,
        files={"file": ("Financials_standardized.csv", VALID_CSV, "text/csv")},
    )

    assert response.status_code == 201, response.text

    dataset = response.json()["data"]["dataset"]

    assert dataset["filename"] == "Financials_standardized.csv"
    assert dataset["format"] == "csv"
    assert dataset["status"] == "ready"
    assert dataset["column_names"][:3] == ["date", "sales", "profit"]

    assert len(list(upload_dir.glob("*.csv"))) == 1


async def test_the_dataset_list_works_through_the_real_wiring(
    client: AsyncClient,
) -> None:
    """The listing answers with the accepted formats and the uploaded dataset."""
    await client.post(
        DATASETS_URL,
        files={"file": ("Financials.csv", VALID_CSV, "text/csv")},
    )

    response = await client.get(DATASETS_URL)

    assert response.status_code == 200, response.text

    body = response.json()["data"]

    assert body["supported_extensions"] == [".csv", ".xlsx"]
    assert body["max_upload_bytes"] == 1024 * 1024

    filenames = [entry["filename"] for entry in body["datasets"]]

    assert "Financials.csv" in filenames


async def test_an_uploaded_csv_is_analysed_through_the_real_wiring(
    client: AsyncClient,
) -> None:
    """The uploaded rows are the ones the analysis reports.

    The totals are the uploaded rows' own, so a job that silently read a
    packaged dataset instead could not produce them.
    """
    uploaded = await client.post(
        DATASETS_URL,
        files={"file": ("Financials.csv", VALID_CSV, "text/csv")},
    )

    dataset_id = uploaded.json()["data"]["dataset"]["dataset_id"]

    created = await client.post(
        JOBS_URL,
        json={"operation": "compute_kpis", "dataset_id": dataset_id},
    )

    assert created.status_code == 202, created.text

    final = await wait_for_terminal(client, created.json()["data"]["job_id"])

    assert final["status"] == "completed", final.get("error")

    overall = final["result"]["overall"]

    assert overall["total_sales"] == 2500
    assert overall["total_profit"] == 500


async def test_a_document_type_is_refused_with_the_dataset_formats_named(
    client: AsyncClient,
    upload_dir: Path,
) -> None:
    """A document is refused, and the message names the dataset formats.

    The refusal has to be about datasets. A message about document types would
    mean the request reached the wrong uploader.
    """
    response = await client.post(
        DATASETS_URL,
        files={"file": ("notes.txt", b"plain text", "text/plain")},
    )

    assert response.status_code == 422

    error = response.json()["error"]

    assert error["details"]["supported_extensions"] == [".csv", ".xlsx"]
    assert "document type" not in error["message"]

    assert not upload_dir.exists() or not list(upload_dir.iterdir())


# --------------------------------------------------------------------------
# CSV content
# --------------------------------------------------------------------------


async def test_a_csv_that_is_not_utf8_is_refused(client: AsyncClient) -> None:
    """A CSV in another encoding is refused with a message about encoding.

    The reader decodes a CSV as UTF-8, so a file that is not UTF-8 has to be
    re-saved. Saying so is more useful than reporting it as unreadable.
    """
    payload = "date,café\n2026-01-01,1\n".encode("latin-1")

    response = await client.post(
        DATASETS_URL,
        files={"file": ("accents.csv", payload, "text/csv")},
    )

    assert response.status_code == 422

    error = response.json()["error"]

    assert "utf-8" in error["message"].lower()
    assert error["details"]["expected_encoding"] == "utf-8"


async def test_a_csv_without_column_names_is_refused(client: AsyncClient) -> None:
    """A header row of blank cells is refused as a missing header."""
    response = await client.post(
        DATASETS_URL,
        files={"file": ("headerless.csv", b",,\n1,2,3\n", "text/csv")},
    )

    assert response.status_code == 422

    assert "no column names" in response.json()["error"]["message"].lower()


async def test_a_csv_without_data_rows_is_refused(client: AsyncClient) -> None:
    """A header with nothing under it is refused as an empty dataset."""
    response = await client.post(
        DATASETS_URL,
        files={"file": ("headeronly.csv", b"date,sales,profit\n", "text/csv")},
    )

    assert response.status_code == 422

    assert "no data rows" in response.json()["error"]["message"].lower()


async def test_a_malformed_csv_is_refused(client: AsyncClient) -> None:
    """Content that is not a table at all is refused."""
    response = await client.post(
        DATASETS_URL,
        files={"file": ("broken.csv", b"\x00\x01\x02binary junk\x00", "text/csv")},
    )

    assert response.status_code == 422


async def test_a_refused_csv_leaves_nothing_on_disk(
    client: AsyncClient,
    upload_dir: Path,
) -> None:
    """A rejected upload leaves no file and no manifest row behind."""
    await client.post(
        DATASETS_URL,
        files={"file": ("headerless.csv", b",,\n1,2,3\n", "text/csv")},
    )

    assert not upload_dir.exists() or not list(upload_dir.iterdir())

    manifest = upload_dir / "datasets.json"

    assert not manifest.exists() or manifest.read_text(encoding="utf-8").strip() == "[]"


# --------------------------------------------------------------------------
# Workbooks
# --------------------------------------------------------------------------


async def test_an_xlsx_workbook_is_accepted_and_analysed(
    client: AsyncClient,
    upload_dir: Path,
) -> None:
    """A workbook is stored and read like a CSV.

    The workbook path is the same one the job runner uses, so an upload cannot
    appear to work and then read a different sheet.
    """
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

    assert response.status_code == 201, response.text

    dataset = response.json()["data"]["dataset"]

    assert dataset["format"] == "xlsx"
    assert dataset["column_names"] == ["date", "sales", "profit"]

    created = await client.post(
        JOBS_URL,
        json={"operation": "load_dataset", "dataset_id": dataset["dataset_id"]},
    )

    assert created.status_code == 202, created.text

    final = await wait_for_terminal(client, created.json()["data"]["job_id"])

    assert final["status"] == "completed", final.get("error")
    assert final["result"]["columns"] == 3

    assert len(list(upload_dir.glob("*.xlsx"))) == 1


async def test_a_csv_renamed_to_xlsx_is_refused(client: AsyncClient) -> None:
    """The container check catches a CSV wearing a workbook's extension."""
    response = await client.post(
        DATASETS_URL,
        files={"file": ("disguised.xlsx", VALID_CSV, "application/octet-stream")},
    )

    assert response.status_code == 422

    assert "xlsx" in response.json()["error"]["message"].lower()


# --------------------------------------------------------------------------
# Size limit
# --------------------------------------------------------------------------


async def test_an_oversized_csv_is_refused(client: AsyncClient, upload_dir: Path) -> None:
    """A file past the limit is refused while streaming and fully cleaned up."""
    oversized = b"date,sales\n" + (b"2026-01-01,1\n" * 200_000)

    response = await client.post(
        DATASETS_URL,
        files={"file": ("big.csv", oversized, "text/csv")},
    )

    assert response.status_code == 422

    error = response.json()["error"]

    assert error["details"]["max_bytes"] == 1024 * 1024

    assert not upload_dir.exists() or not list(upload_dir.iterdir())


# --------------------------------------------------------------------------
# Tenancy
# --------------------------------------------------------------------------


async def test_a_tenant_cannot_use_another_tenants_dataset(
    client: AsyncClient,
    principal: Any,
) -> None:
    """A dataset id belonging to another organisation is refused.

    The job would carry the caller's own organisation, so without this check
    the caller would read another tenant's numbers in a result they own.
    """
    uploaded = await client.post(
        DATASETS_URL,
        files={"file": ("alpha.csv", VALID_CSV, "text/csv")},
    )

    assert uploaded.status_code == 201

    dataset_id = uploaded.json()["data"]["dataset"]["dataset_id"]

    principal.organization_id = ORG_B

    response = await client.post(
        JOBS_URL,
        json={"operation": "load_dataset", "dataset_id": dataset_id},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DATASET_NOT_FOUND"


async def test_a_tenant_cannot_see_another_tenants_dataset_in_the_list(
    client: AsyncClient,
    principal: Any,
) -> None:
    """The listing offers a caller only the datasets its own tenant uploaded."""
    await client.post(
        DATASETS_URL,
        files={"file": ("alpha.csv", VALID_CSV, "text/csv")},
    )

    principal.organization_id = ORG_B

    response = await client.get(DATASETS_URL)

    assert response.status_code == 200

    filenames = [entry["filename"] for entry in response.json()["data"]["datasets"]]

    assert "alpha.csv" not in filenames
