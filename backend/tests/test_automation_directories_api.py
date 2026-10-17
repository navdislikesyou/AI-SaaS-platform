"""Tests for the Automation employee directory API.

Uploads go to a temporary directory and the manifest to a temporary file, so the
repository's own storage is never touched. No agent is contacted: this file
covers the HTTP boundary only.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.registry import AgentRegistry
from app.api import deps
from app.api.deps import (
    get_employee_directory_manifest,
    get_employee_directory_service,
    get_orchestrator,
    get_registry,
    get_settings_dep,
)
from app.core.config import Settings
from app.main import create_app
from app.services.employee_directory import (
    EmployeeDirectoryManifest,
    EmployeeDirectoryService,
)
from app.services.orchestrator import Orchestrator

DIRECTORIES_URL = "/api/v1/automation/directories"

VALID_CSV = b"Name,Email\r\nAarti Rao,aarti@example.com\r\nOmkar Shenwai,omkar@example.com\r\n"

VALID_JSON = json.dumps(
    [
        {"name": "Aarti Rao", "email": "aarti@example.com"},
        {"name": "Omkar Shenwai", "email": "omkar@example.com"},
    ]
).encode("utf-8")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Return test settings pointed at a temporary upload directory.

    Args:
        tmp_path: pytest's per-test temporary directory.

    Returns:
        Settings whose upload directory and manifest live under ``tmp_path``.
    """
    return Settings(
        environment="test",
        log_level="WARNING",
        automation_upload_dir=tmp_path / "uploads",
        automation_upload_manifest_path=tmp_path / "uploads" / "directories.json",
        automation_max_upload_bytes=4096,
        _env_file=None,
    )


@pytest.fixture
def manifest(settings: Settings) -> EmployeeDirectoryManifest:
    """Return a manifest backed by a temporary file.

    Args:
        settings: Test settings.

    Returns:
        The temporary manifest store.
    """
    return EmployeeDirectoryManifest(settings.resolved_automation_upload_manifest_path)


@pytest.fixture
async def http(
    settings: Settings,
    manifest: EmployeeDirectoryManifest,
) -> AsyncIterator[AsyncClient]:
    """Return an HTTP client wired to the temporary storage.

    Args:
        settings: Test settings.
        manifest: Temporary manifest store.

    Yields:
        The configured AsyncClient.
    """
    application = create_app(settings)

    registry = AgentRegistry()
    deps.reset_state()
    application.dependency_overrides[get_settings_dep] = lambda: settings
    application.dependency_overrides[get_registry] = lambda: registry
    application.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)
    application.dependency_overrides[get_employee_directory_manifest] = lambda: manifest
    application.dependency_overrides[get_employee_directory_service] = lambda: (
        EmployeeDirectoryService(settings)
    )

    transport = ASGITransport(app=application)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture(autouse=True)
def _reset_deps() -> Iterator[None]:
    """Clear shared singletons around each test.

    Yields:
        Nothing. The reset runs after the test.
    """
    deps.reset_state()

    yield

    deps.reset_state()


async def upload(http: AsyncClient, content: bytes, filename: str) -> dict[str, Any]:
    """Upload one directory and return its decoded response body.

    Args:
        http: The test client.
        content: Raw file bytes.
        filename: Name the client claims.

    Returns:
        The decoded JSON body.
    """
    response = await http.post(DIRECTORIES_URL, files={"file": (filename, content)})

    return {"status": response.status_code, "body": response.json()}


# --------------------------------------------------------------------------
# Upload
# --------------------------------------------------------------------------


async def test_upload_returns_201_with_a_preview(http: AsyncClient) -> None:
    """A valid CSV becomes a selectable directory with a record preview."""
    result = await upload(http, VALID_CSV, "engineering.csv")

    assert result["status"] == 201

    directory = result["body"]["data"]["directory"]
    assert directory["filename"] == "engineering.csv"
    assert directory["format"] == "csv"
    assert directory["employee_count"] == 2
    assert directory["status"] == "ready"
    assert directory["directory_id"]

    assert result["body"]["data"]["preview"] == [
        {"name": "Aarti Rao", "email": "aarti@example.com"},
        {"name": "Omkar Shenwai", "email": "omkar@example.com"},
    ]


async def test_upload_accepts_json(http: AsyncClient) -> None:
    """A JSON array of employees is accepted like a CSV."""
    result = await upload(http, VALID_JSON, "engineering.json")

    assert result["status"] == 201
    assert result["body"]["data"]["directory"]["format"] == "json"
    assert result["body"]["data"]["directory"]["employee_count"] == 2


async def test_preview_is_capped(http: AsyncClient, settings: Settings) -> None:
    """A long directory previews its first records rather than the whole file."""
    records = [{"name": f"Person {i}", "email": f"p{i}@example.com"} for i in range(30)]

    result = await upload(http, json.dumps(records).encode(), "big.json")

    assert result["status"] == 201
    assert result["body"]["data"]["directory"]["employee_count"] == 30
    assert len(result["body"]["data"]["preview"]) == 20


async def test_upload_discards_columns_the_agent_does_not_read(
    http: AsyncClient,
) -> None:
    """An extra column never reaches the client."""
    content = b"name,email,salary\r\nAarti Rao,aarti@example.com,420000\r\n"

    result = await upload(http, content, "roster.csv")

    assert result["status"] == 201
    assert result["body"]["data"]["preview"] == [
        {"name": "Aarti Rao", "email": "aarti@example.com"}
    ]
    assert "salary" not in json.dumps(result["body"])


async def test_response_never_exposes_a_path_or_stored_name(
    http: AsyncClient,
) -> None:
    """No filesystem detail escapes through any route."""
    uploaded = await upload(http, VALID_CSV, "engineering.csv")
    directory_id = uploaded["body"]["data"]["directory"]["directory_id"]

    detail = await http.get(f"{DIRECTORIES_URL}/{directory_id}")

    for body in (json.dumps(uploaded["body"]), json.dumps(detail.json())):
        assert "stored_name" not in body
        assert "uploads" not in body
        assert "\\" not in body
        assert "/" not in body.replace("http://", "").replace("https://", "")


# --------------------------------------------------------------------------
# Upload rejections
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "filename", "expected"),
    [
        pytest.param(b"x", "roster.xlsx", "not a supported employee directory", id="xlsx"),
        pytest.param(b"x", "roster.txt", "not a supported employee directory", id="txt"),
        pytest.param(b"", "roster.csv", "is empty", id="empty"),
        pytest.param(b"{oops", "r.json", "is not valid JSON", id="malformed_json"),
        pytest.param(b"[]", "r.json", "no employee records", id="no_records"),
        pytest.param(
            b"name\r\nAarti\r\n", "r.csv", "missing the 'email' column", id="no_email_col"
        ),
        pytest.param(
            b'[{"name":"A","email":"nope"}]', "r.json", "valid 'email' address", id="bad_email"
        ),
        pytest.param(
            b'[{"name":"A","email":"a@b.com"},{"name":"a","email":"c@d.com"}]',
            "r.json",
            "repeats the 'name' of entry 1",
            id="duplicate_name",
        ),
        pytest.param(
            b'[{"name":"A","email":"a@b.com"},{"name":"C","email":"A@B.com"}]',
            "r.json",
            "repeats the 'email' of entry 1",
            id="duplicate_email",
        ),
    ],
)
async def test_invalid_upload_returns_422(
    http: AsyncClient,
    content: bytes,
    filename: str,
    expected: str,
) -> None:
    """A rejected file returns 422 with an actionable message.

    Args:
        http: The test client.
        content: Raw file bytes.
        filename: Name the client claims.
        expected: Text the error message must contain.
    """
    result = await upload(http, content, filename)

    assert result["status"] == 422
    assert expected in result["body"]["error"]["message"]
    assert result["body"]["error"]["code"] == "VALIDATION_ERROR"


async def test_oversized_upload_returns_422_with_the_limit(http: AsyncClient) -> None:
    """An oversized file is rejected and the limit is reported."""
    content = b"name,email\r\n" + b"A,a@example.com\r\n" * 500

    result = await upload(http, content, "huge.csv")

    assert result["status"] == 422
    assert result["body"]["error"]["details"]["max_bytes"] == 4096


async def test_rejected_upload_is_not_listed(
    http: AsyncClient,
    manifest: EmployeeDirectoryManifest,
) -> None:
    """A file that failed validation leaves no usable entry behind.

    Args:
        http: The test client.
        manifest: The manifest the router writes to.
    """
    await upload(http, b'[{"name":"A"}]', "r.json")

    assert manifest.read() == []


async def test_traversal_filename_is_handled_without_escaping(
    http: AsyncClient,
    settings: Settings,
) -> None:
    """A hostile filename cannot write outside the configured directory."""
    result = await upload(http, VALID_CSV, "../../etc/passwd.csv")

    assert result["status"] == 201
    assert result["body"]["data"]["directory"]["filename"] == "passwd.csv"

    stored = list(settings.resolved_automation_upload_dir.glob("*.csv"))
    assert len(stored) == 1
    assert stored[0].parent == settings.resolved_automation_upload_dir


# --------------------------------------------------------------------------
# Listing
# --------------------------------------------------------------------------


async def test_list_is_empty_before_any_upload(http: AsyncClient) -> None:
    """An instance with no uploads returns an empty list, not an error."""
    response = await http.get(DIRECTORIES_URL)

    assert response.status_code == 200
    assert response.json()["data"]["directories"] == []
    assert response.json()["data"]["total"] == 0


async def test_list_returns_newest_first(http: AsyncClient) -> None:
    """The most recent upload is the first choice offered."""
    await upload(http, VALID_CSV, "first.csv")
    second = await upload(http, VALID_JSON, "second.json")

    response = await http.get(DIRECTORIES_URL)

    directories = response.json()["data"]["directories"]
    assert [entry["filename"] for entry in directories] == ["second.json", "first.csv"]
    assert directories[0]["directory_id"] == second["body"]["data"]["directory"]["directory_id"]


# --------------------------------------------------------------------------
# Retrieval
# --------------------------------------------------------------------------


async def test_detail_returns_every_record(http: AsyncClient) -> None:
    """The detail route returns the whole directory, not just the preview."""
    records = [{"name": f"Person {i}", "email": f"p{i}@example.com"} for i in range(30)]

    uploaded = await upload(http, json.dumps(records).encode(), "big.json")
    directory_id = uploaded["body"]["data"]["directory"]["directory_id"]

    response = await http.get(f"{DIRECTORIES_URL}/{directory_id}")

    assert response.status_code == 200
    detail = response.json()["data"]
    assert detail["employees"] == records
    assert detail["employees_truncated"] is False


async def test_detail_of_an_unknown_id_returns_404(http: AsyncClient) -> None:
    """An id that was never issued is a 404 with the directory error code."""
    response = await http.get(f"{DIRECTORIES_URL}/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DIRECTORY_NOT_FOUND"


async def test_detail_of_a_deleted_file_returns_404(
    http: AsyncClient,
    settings: Settings,
) -> None:
    """A registered id whose file is gone is reported as unavailable.

    Args:
        http: The test client.
        settings: Test settings, for the upload directory location.
    """
    uploaded = await upload(http, VALID_CSV, "roster.csv")
    directory_id = uploaded["body"]["data"]["directory"]["directory_id"]

    for path in settings.resolved_automation_upload_dir.iterdir():
        path.unlink()

    response = await http.get(f"{DIRECTORIES_URL}/{directory_id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DIRECTORY_NOT_FOUND"


async def test_detail_of_a_corrupted_file_returns_422(
    http: AsyncClient,
    settings: Settings,
) -> None:
    """A file changed after upload fails loudly rather than silently.

    Args:
        http: The test client.
        settings: Test settings, for the upload directory location.
    """
    uploaded = await upload(http, VALID_CSV, "roster.csv")
    directory_id = uploaded["body"]["data"]["directory"]["directory_id"]

    for path in settings.resolved_automation_upload_dir.glob("*.csv"):
        path.write_text("name,email\r\n", encoding="utf-8")

    response = await http.get(f"{DIRECTORIES_URL}/{directory_id}")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
