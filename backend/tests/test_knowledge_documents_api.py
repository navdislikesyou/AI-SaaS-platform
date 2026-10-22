"""Tests for the Knowledge document upload API and its supporting services.

The Knowledge Agent is replaced by a fake service, so no model is downloaded, no
Chroma collection is written, and no Ollama server is contacted. Uploads go to a
temporary directory and the manifest to a temporary file, so the repository's own
storage is never touched.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.adapters.knowledge import KnowledgeAgentAdapter
from app.agents.registry import AgentRegistry
from app.api import deps
from app.api.deps import (
    get_current_user_from_token_optional_principal,
    get_document_manifest,
    get_document_upload_service,
    get_orchestrator,
    get_registry,
    get_settings_dep,
)
from app.core.config import Settings
from app.main import create_app
from app.services.document_manifest import DocumentManifest, DocumentStatus
from app.services.document_upload import DocumentUploadService
from app.services.orchestrator import Orchestrator
from tests.fakes import FakePrincipal

DOCUMENTS_URL = "/api/v1/knowledge/documents"

#: Bytes that pass the PDF signature check. Content is irrelevant because the
#: agent is faked, but the signature is checked before the agent is reached.
PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n"

TEXT_BYTES = b"Employee leave policy: 25 days of annual leave per year.\n"


def docx_bytes() -> bytes:
    """Build a minimal DOCX archive containing a Word document part.

    Returns:
        DOCX bytes that pass the archive checks in the upload service.
    """
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(
            "word/document.xml",
            "<w:document><w:body><w:p><w:r><w:t>Leave policy text.</w:t>"
            "</w:r></w:p></w:body></w:document>",
        )

    return buffer.getvalue()


class FakeKnowledgeService:
    """Stand-in for ``knowledge_agent.service.KnowledgeService``.

    Attributes:
        ingest_result: Value returned by :meth:`ingest`.
        ingest_error: Exception raised by :meth:`ingest`, when set.
        query_result: Value returned by :meth:`query`.
        received_paths: Server paths passed to :meth:`ingest`, in order.
    """

    def __init__(
        self,
        ingest_result: dict[str, Any] | None = None,
        ingest_error: Exception | None = None,
        query_result: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the fake.

        Args:
            ingest_result: Chunk result to report. Defaults to 3 chunks.
            ingest_error: Error to raise instead of returning a result.
            query_result: Value returned by :meth:`query`.
        """
        self.ingest_result = ingest_result or {"indexed": True, "chunk_count": 3}
        self.ingest_error = ingest_error
        self.query_result = query_result or {"answer": "ok", "sources": []}
        self.received_paths: list[str] = []

    def ingest(
        self,
        file_path: str,
        user_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record the path and report a canned indexing result.

        Args:
            file_path: Server path chosen by the upload service.
            user_context: Principal context forwarded by the adapter.

        Returns:
            The configured ingest result.

        Raises:
            Exception: The configured error, when one was set.
        """
        self.received_paths.append(file_path)

        if self.ingest_error is not None:
            raise self.ingest_error

        return self.ingest_result

    def query(
        self,
        question: str,
        user_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return the configured query result.

        Args:
            question: The question, unused.
            user_context: Principal context forwarded by the adapter.

        Returns:
            The configured query result.
        """
        return self.query_result


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
        knowledge_upload_dir=tmp_path / "uploads",
        knowledge_upload_manifest_path=tmp_path / "uploads" / "documents.json",
        _env_file=None,
    )


@pytest.fixture
def upload_dir(settings: Settings) -> Path:
    """Return the directory uploads are written to.

    Args:
        settings: Test settings.

    Returns:
        The absolute upload directory.
    """
    return settings.resolved_knowledge_upload_dir


@pytest.fixture
def manifest(settings: Settings) -> Iterator[DocumentManifest]:
    """Return a manifest backed by a temporary file.

    Args:
        settings: Test settings.

    Yields:
        The temporary manifest store.
    """
    store = DocumentManifest(settings.resolved_knowledge_upload_manifest_path)

    try:
        yield store

    finally:
        store.path.unlink(missing_ok=True)


@pytest.fixture
def service() -> FakeKnowledgeService:
    """Return the fake Knowledge service.

    Returns:
        A service reporting three indexed chunks.
    """
    return FakeKnowledgeService()


def build_client(
    settings: Settings,
    manifest: DocumentManifest,
    service: FakeKnowledgeService,
) -> AsyncClient:
    """Build an HTTP client with fakes installed for every seam.

    Args:
        settings: Test settings.
        manifest: Temporary manifest store.
        service: Fake Knowledge service.

    Returns:
        An AsyncClient bound to an application wired to the fakes.
    """
    adapter = KnowledgeAgentAdapter(service=service)
    registry = AgentRegistry()
    registry.register(adapter)

    application = create_app(settings)
    application.dependency_overrides[get_settings_dep] = lambda: settings
    application.dependency_overrides[get_registry] = lambda: registry
    application.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)
    application.dependency_overrides[get_current_user_from_token_optional_principal] = lambda: FakePrincipal()  # noqa: E501
    application.dependency_overrides[get_document_manifest] = lambda: manifest
    application.dependency_overrides[get_document_upload_service] = lambda: (
        DocumentUploadService(settings)
    )

    transport = ASGITransport(app=application)

    return AsyncClient(transport=transport, base_url="http://testserver")


@pytest.fixture
async def http(
    settings: Settings,
    manifest: DocumentManifest,
    service: FakeKnowledgeService,
) -> AsyncIterator[AsyncClient]:
    """Return an HTTP client with every dependency replaced.

    Args:
        settings: Test settings.
        manifest: Temporary manifest store.
        service: Fake Knowledge service.

    Yields:
        The configured AsyncClient.
    """
    client = build_client(settings, manifest, service)

    async with client as http_client:
        yield http_client


@pytest.fixture(autouse=True)
def _reset_deps() -> Iterator[None]:
    """Clear shared singletons around each test.

    Yields:
        Nothing. The reset runs after the test.
    """
    deps.reset_state()

    yield

    deps.reset_state()


def stored_files(upload_dir: Path) -> list[Path]:
    """Return the files currently in the upload directory.

    Args:
        upload_dir: The upload directory.

    Returns:
        Every regular file in the directory, excluding the manifest.
    """
    if not upload_dir.is_dir():
        return []

    return [path for path in upload_dir.iterdir() if path.is_file() and path.suffix != ".json"]


# ---------------------------------------------------------------------------
# Successful upload
# ---------------------------------------------------------------------------


async def test_a_pdf_upload_is_indexed_and_recorded(
    http: AsyncClient,
    service: FakeKnowledgeService,
    upload_dir: Path,
    manifest: DocumentManifest,
) -> None:
    """A valid PDF returns 201 and appears in the manifest as indexed."""
    response = await http.post(
        DOCUMENTS_URL,
        files={"file": ("Employee Handbook.pdf", PDF_BYTES, "application/pdf")},
    )

    assert response.status_code == 201
    body = response.json()

    assert body["success"] is True
    assert body["data"]["document"]["filename"] == "Employee Handbook.pdf"
    assert body["data"]["document"]["status"] == "indexed"
    assert body["data"]["document"]["chunk_count"] == 3
    assert body["data"]["document"]["document_id"]
    assert body["request_id"]

    assert len(stored_files(upload_dir)) == 1
    assert len(manifest.read()) == 1
    assert manifest.read()[0]["filename"] == "Employee Handbook.pdf"


async def test_a_docx_upload_is_indexed(
    http: AsyncClient,
    upload_dir: Path,
) -> None:
    """A structurally valid DOCX is accepted."""
    response = await http.post(
        DOCUMENTS_URL,
        files={"file": ("policy.docx", docx_bytes(), "application/octet-stream")},
    )

    assert response.status_code == 201
    assert response.json()["data"]["document"]["extension"] == ".docx"
    assert len(stored_files(upload_dir)) == 1


async def test_a_txt_upload_is_indexed(http: AsyncClient) -> None:
    """A valid UTF-8 text file is accepted."""
    response = await http.post(
        DOCUMENTS_URL,
        files={"file": ("notes.txt", TEXT_BYTES, "text/plain")},
    )

    assert response.status_code == 201
    assert response.json()["data"]["document"]["extension"] == ".txt"


async def test_the_agent_receives_a_server_generated_path(
    http: AsyncClient,
    service: FakeKnowledgeService,
    upload_dir: Path,
) -> None:
    """Ingestion is handed a path on disk, not the client's filename."""
    await http.post(
        DOCUMENTS_URL,
        files={"file": ("Employee Handbook.pdf", PDF_BYTES, "application/pdf")},
    )

    assert len(service.received_paths) == 1
    received = Path(service.received_paths[0])

    assert received.is_absolute()
    assert received.parent == upload_dir
    assert received.suffix == ".pdf"


async def test_the_response_never_exposes_a_filesystem_path(
    http: AsyncClient,
    upload_dir: Path,
) -> None:
    """No absolute server path appears anywhere in the response body."""
    response = await http.post(
        DOCUMENTS_URL,
        files={"file": ("Employee Handbook.pdf", PDF_BYTES, "application/pdf")},
    )

    serialized = response.text

    assert str(upload_dir) not in serialized
    assert "stored_name" not in serialized
    assert "\\" not in serialized


async def test_the_response_carries_the_standard_envelope(
    http: AsyncClient,
) -> None:
    """The upload response uses the shared APIResponse envelope."""
    response = await http.post(
        DOCUMENTS_URL,
        files={"file": ("notes.txt", TEXT_BYTES, "text/plain")},
    )

    body = response.json()

    assert set(body) == {"success", "data", "message", "request_id"}
    assert set(body["data"]) == {"document", "message"}
    assert set(body["data"]["document"]) == {
        "document_id",
        "filename",
        "extension",
        "size_bytes",
        "status",
        "chunk_count",
        "uploaded_at",
    }


# ---------------------------------------------------------------------------
# Document listing
# ---------------------------------------------------------------------------


async def test_documents_are_listed_newest_first(http: AsyncClient) -> None:
    """Two uploads are returned most recent first."""
    await http.post(DOCUMENTS_URL, files={"file": ("first.txt", TEXT_BYTES, "text/plain")})
    await http.post(DOCUMENTS_URL, files={"file": ("second.txt", TEXT_BYTES, "text/plain")})

    response = await http.get(DOCUMENTS_URL)

    assert response.status_code == 200
    documents = response.json()["data"]["documents"]

    assert response.json()["data"]["total"] == 2
    assert [document["filename"] for document in documents] == ["second.txt", "first.txt"]


async def test_an_empty_store_returns_an_empty_list(http: AsyncClient) -> None:
    """Listing before any upload succeeds with an empty list."""
    response = await http.get(DOCUMENTS_URL)

    assert response.status_code == 200
    assert response.json()["data"]["documents"] == []
    assert response.json()["data"]["total"] == 0


async def test_the_list_does_not_expose_stored_filenames(
    http: AsyncClient,
    manifest: DocumentManifest,
) -> None:
    """The internal stored name stays out of the API response."""
    await http.post(DOCUMENTS_URL, files={"file": ("notes.txt", TEXT_BYTES, "text/plain")})

    stored_name = manifest.read()[0]["stored_name"]

    assert stored_name
    assert stored_name not in (await http.get(DOCUMENTS_URL)).text


# ---------------------------------------------------------------------------
# Rejected uploads
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        pytest.param("malware.exe", b"MZ\x90\x00", id="unsupported_extension"),
        pytest.param("archive.zip", b"PK\x03\x04", id="archive_not_supported"),
        pytest.param("noextension", TEXT_BYTES, id="no_extension"),
        pytest.param(".hidden", TEXT_BYTES, id="dotfile_no_extension"),
    ],
)
async def test_an_unsupported_file_type_is_rejected(
    http: AsyncClient,
    upload_dir: Path,
    filename: str,
    content: bytes,
) -> None:
    """Only PDF, DOCX, and TXT are accepted."""
    response = await http.post(
        DOCUMENTS_URL,
        files={"file": (filename, content, "application/octet-stream")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert stored_files(upload_dir) == []


async def test_an_empty_file_is_rejected(http: AsyncClient, upload_dir: Path) -> None:
    """A zero-byte upload is a 422 and leaves nothing on disk."""
    response = await http.post(DOCUMENTS_URL, files={"file": ("empty.txt", b"", "text/plain")})

    assert response.status_code == 422
    assert "empty" in response.json()["error"]["message"].lower()
    assert stored_files(upload_dir) == []


async def test_an_oversized_file_is_rejected_and_removed(
    settings: Settings,
    manifest: DocumentManifest,
    service: FakeKnowledgeService,
    tmp_path: Path,
) -> None:
    """Exceeding the size limit fails the upload without leaving a file."""
    limited = Settings(
        environment="test",
        log_level="WARNING",
        knowledge_upload_dir=tmp_path / "uploads",
        knowledge_upload_manifest_path=tmp_path / "uploads" / "documents.json",
        knowledge_max_upload_bytes=512,
        _env_file=None,
    )

    async with build_client(limited, manifest, service) as http:
        response = await http.post(
            DOCUMENTS_URL,
            files={"file": ("big.txt", b"a" * 4096, "text/plain")},
        )

    assert response.status_code == 422
    assert response.json()["error"]["details"]["max_bytes"] == 512
    assert stored_files(limited.resolved_knowledge_upload_dir) == []


async def test_a_file_lying_about_its_extension_is_rejected(
    http: AsyncClient,
    upload_dir: Path,
) -> None:
    """Text renamed to .pdf fails the signature check, not the agent."""
    response = await http.post(
        DOCUMENTS_URL,
        files={"file": ("pretend.pdf", TEXT_BYTES, "application/pdf")},
    )

    assert response.status_code == 422
    assert stored_files(upload_dir) == []


async def test_a_malformed_docx_is_rejected(http: AsyncClient, upload_dir: Path) -> None:
    """A ZIP without a Word document part is rejected before the agent."""
    response = await http.post(
        DOCUMENTS_URL,
        files={"file": ("broken.docx", b"PK\x03\x04 not really a zip", "application/octet-stream")},
    )

    assert response.status_code == 422
    assert stored_files(upload_dir) == []


async def test_a_binary_file_named_txt_is_rejected(
    http: AsyncClient,
    upload_dir: Path,
) -> None:
    """A .txt containing NUL bytes is not decodable text."""
    response = await http.post(
        DOCUMENTS_URL,
        files={"file": ("binary.txt", b"\x00\x01\x02\x03", "text/plain")},
    )

    assert response.status_code == 422
    assert stored_files(upload_dir) == []


async def test_whitespace_only_text_is_rejected(http: AsyncClient, upload_dir: Path) -> None:
    """A file with no actual text is rejected."""
    response = await http.post(
        DOCUMENTS_URL,
        files={"file": ("blank.txt", b"   \n\t  \n", "text/plain")},
    )

    assert response.status_code == 422
    assert stored_files(upload_dir) == []


async def test_a_missing_file_is_rejected(http: AsyncClient) -> None:
    """A request with no file field is a validation error."""
    response = await http.post(DOCUMENTS_URL, data={})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Ingestion failure
# ---------------------------------------------------------------------------


async def test_a_failed_ingestion_returns_502_and_removes_the_file(
    settings: Settings,
    manifest: DocumentManifest,
    upload_dir: Path,
) -> None:
    """An agent failure surfaces as 502 with no orphaned file left behind."""
    service = FakeKnowledgeService(ingest_error=RuntimeError("chroma exploded at /secret/path"))

    async with build_client(settings, manifest, service) as http:
        response = await http.post(
            DOCUMENTS_URL,
            files={"file": ("Employee Handbook.pdf", PDF_BYTES, "application/pdf")},
        )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AGENT_EXECUTION_FAILED"
    assert stored_files(upload_dir) == []

    rows = manifest.read()

    assert len(rows) == 1
    assert rows[0]["status"] == DocumentStatus.FAILED.value
    assert rows[0].get("chunk_count") is None


async def test_a_failed_ingestion_error_text_hides_the_server_path(
    settings: Settings,
    manifest: DocumentManifest,
) -> None:
    """The failure message returned to a client carries no internal path."""
    service = FakeKnowledgeService(ingest_error=RuntimeError("could not open C:/secret/x.pdf"))

    async with build_client(settings, manifest, service) as http:
        response = await http.post(
            DOCUMENTS_URL,
            files={"file": ("Employee Handbook.pdf", PDF_BYTES, "application/pdf")},
        )

    assert response.status_code == 502
    assert "/secret/" not in response.text
    assert "chroma" not in response.text


async def test_a_document_with_no_chunks_is_not_reported_as_indexed(
    settings: Settings,
    manifest: DocumentManifest,
    upload_dir: Path,
) -> None:
    """Zero chunks is a failure, not a success with an empty result."""
    service = FakeKnowledgeService(ingest_result={"indexed": False, "chunk_count": 0})

    async with build_client(settings, manifest, service) as http:
        response = await http.post(
            DOCUMENTS_URL,
            files={"file": ("scanned.txt", TEXT_BYTES, "text/plain")},
        )

    assert response.status_code == 422
    assert stored_files(upload_dir) == []
    assert manifest.read()[0]["status"] == DocumentStatus.FAILED.value


async def test_a_failed_upload_is_absent_from_the_document_list(
    settings: Settings,
    manifest: DocumentManifest,
) -> None:
    """A failed upload is recorded as failed, never listed as indexed."""
    service = FakeKnowledgeService(ingest_error=RuntimeError("boom"))

    async with build_client(settings, manifest, service) as http:
        await http.post(
            DOCUMENTS_URL,
            files={"file": ("broken.pdf", PDF_BYTES, "application/pdf")},
        )

        listing = await http.get(DOCUMENTS_URL)

    documents = listing.json()["data"]["documents"]

    assert len(documents) == 1
    assert documents[0]["status"] == DocumentStatus.FAILED.value
    assert documents[0]["chunk_count"] is None


async def test_an_unavailable_agent_returns_503_and_removes_the_file(
    settings: Settings,
    manifest: DocumentManifest,
    upload_dir: Path,
) -> None:
    """A disconnected Knowledge Agent is a 503, not a 502."""
    from tests.fakes import UnavailableAgent

    registry = AgentRegistry()
    registry.register(UnavailableAgent(name="knowledge"))

    application = create_app(settings)
    application.dependency_overrides[get_settings_dep] = lambda: settings
    application.dependency_overrides[get_registry] = lambda: registry
    application.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)
    application.dependency_overrides[get_current_user_from_token_optional_principal] = lambda: FakePrincipal()  # noqa: E501
    application.dependency_overrides[get_document_manifest] = lambda: manifest
    application.dependency_overrides[get_document_upload_service] = lambda: (
        DocumentUploadService(settings)
    )

    transport = ASGITransport(app=application)

    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        response = await http.post(
            DOCUMENTS_URL,
            files={"file": ("notes.txt", TEXT_BYTES, "text/plain")},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AGENT_UNAVAILABLE"
    assert stored_files(upload_dir) == []


# ---------------------------------------------------------------------------
# Storage naming and path traversal
# ---------------------------------------------------------------------------


async def test_the_stored_filename_is_generated_not_client_supplied(
    http: AsyncClient,
    upload_dir: Path,
) -> None:
    """The stored name is a UUID-prefixed form of the client's stem."""
    await http.post(
        DOCUMENTS_URL,
        files={"file": ("Employee Handbook.pdf", PDF_BYTES, "application/pdf")},
    )

    stored = stored_files(upload_dir)[0]

    assert stored.name != "Employee Handbook.pdf"
    assert stored.name.endswith("_Employee_Handbook.pdf")
    assert stored.stem.split("_", 1)[0] == stored.stem.split("_", 1)[0].strip()
    assert len(stored.stem.split("_")[0]) == 32


async def test_duplicate_filenames_produce_separate_documents(
    http: AsyncClient,
    upload_dir: Path,
) -> None:
    """The same filename twice yields two distinct stored documents."""
    first = await http.post(
        DOCUMENTS_URL,
        files={"file": ("handbook.pdf", PDF_BYTES, "application/pdf")},
    )
    second = await http.post(
        DOCUMENTS_URL,
        files={"file": ("handbook.pdf", PDF_BYTES, "application/pdf")},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert (
        first.json()["data"]["document"]["document_id"]
        != second.json()["data"]["document"]["document_id"]
    )
    assert len(stored_files(upload_dir)) == 2


async def test_a_traversal_filename_cannot_escape_the_upload_directory(
    http: AsyncClient,
    upload_dir: Path,
) -> None:
    """A traversal attempt in the filename is stripped to its basename."""
    response = await http.post(
        DOCUMENTS_URL,
        files={"file": ("../../../etc/passwd.pdf", PDF_BYTES, "application/pdf")},
    )

    assert response.status_code == 201
    assert response.json()["data"]["document"]["filename"] == "passwd.pdf"

    stored = stored_files(upload_dir)

    assert len(stored) == 1
    assert stored[0].parent == upload_dir


async def test_a_windows_traversal_filename_is_also_neutralized(
    http: AsyncClient,
    upload_dir: Path,
) -> None:
    """Backslash separators are treated as path separators too."""
    response = await http.post(
        DOCUMENTS_URL,
        files={"file": ("..\\..\\windows\\system32\\notes.txt", TEXT_BYTES, "text/plain")},
    )

    assert response.status_code == 201
    assert response.json()["data"]["document"]["filename"] == "notes.txt"
    assert stored_files(upload_dir)[0].parent == upload_dir


async def test_an_upload_does_not_overwrite_an_existing_file(
    http: AsyncClient,
    upload_dir: Path,
    manifest: DocumentManifest,
) -> None:
    """Generated names never collide with an earlier upload."""
    await http.post(DOCUMENTS_URL, files={"file": ("handbook.pdf", PDF_BYTES, "application/pdf")})

    stored = stored_files(upload_dir)[0]
    stored.write_bytes(b"%PDF-1.7 untouched\n")

    await http.post(DOCUMENTS_URL, files={"file": ("handbook.pdf", PDF_BYTES, "application/pdf")})

    assert stored.read_bytes() == b"%PDF-1.7 untouched\n"
    assert len(stored_files(upload_dir)) == 2


# ---------------------------------------------------------------------------
# Deferred cleanup
# ---------------------------------------------------------------------------


async def test_a_file_left_by_a_failed_upload_is_swept_on_the_next_upload(
    settings: Settings,
    manifest: DocumentManifest,
    upload_dir: Path,
) -> None:
    """Cleanup that could not finish is completed by a later upload.

    On Windows the traceback of a loader failure keeps the file handle open, so
    the delete during the failing request cannot succeed. The handle is gone by
    the next request, so the sweep there finishes the job.
    """
    failing = FakeKnowledgeService(ingest_error=RuntimeError("loader failed"))

    async with build_client(settings, manifest, failing) as http:
        await http.post(
            DOCUMENTS_URL,
            files={"file": ("broken.pdf", PDF_BYTES, "application/pdf")},
        )

    failed_row = manifest.read()[0]
    leftover = upload_dir / failed_row["stored_name"]

    # Simulate the leftover surviving the failed request.
    leftover.write_bytes(PDF_BYTES)
    assert leftover.is_file()

    working = FakeKnowledgeService()

    async with build_client(settings, manifest, working) as http:
        await http.post(DOCUMENTS_URL, files={"file": ("notes.txt", TEXT_BYTES, "text/plain")})

    assert not leftover.exists()


async def test_the_sweep_never_deletes_an_indexed_document(
    settings: Settings,
    manifest: DocumentManifest,
    upload_dir: Path,
) -> None:
    """A later upload leaves files belonging to indexed documents alone."""
    async with build_client(settings, manifest, FakeKnowledgeService()) as http:
        await http.post(
            DOCUMENTS_URL,
            files={"file": ("handbook.pdf", PDF_BYTES, "application/pdf")},
        )
        await http.post(DOCUMENTS_URL, files={"file": ("notes.txt", TEXT_BYTES, "text/plain")})

    assert len(stored_files(upload_dir)) == 2


# ---------------------------------------------------------------------------
# Citation sanitization
# ---------------------------------------------------------------------------


async def test_query_citations_never_expose_the_stored_path(
    settings: Settings,
    manifest: DocumentManifest,
) -> None:
    """An absolute source from an uploaded document is reduced to a filename."""
    service = FakeKnowledgeService(
        query_result={
            "answer": "Leave is 25 days.",
            "sources": [
                {"source": "C:/srv/backend/uploads/knowledge/abc123_handbook.pdf", "page": 2},
                {"source": "relative/path/notes.txt", "page": 1},
            ],
        }
    )

    async with build_client(settings, manifest, service) as http:
        response = await http.post(
            "/api/v1/agents/execute",
            json={
                "agent": "knowledge",
                "operation": "query",
                "payload": {"question": "How much leave?"},
            },
        )

    sources = response.json()["data"]["data"]["sources"]

    assert sources[0]["source"] == "abc123_handbook.pdf"
    assert sources[0]["page"] == 2
    assert sources[1]["source"] == "relative/path/notes.txt"


# ---------------------------------------------------------------------------
# Manifest store
# ---------------------------------------------------------------------------


def test_a_missing_manifest_reads_as_empty(tmp_path: Path) -> None:
    """A manifest that was never written is empty, not an error."""
    assert DocumentManifest(tmp_path / "absent.json").read() == []


def test_a_corrupt_manifest_reads_as_empty(tmp_path: Path) -> None:
    """Unparseable manifest content degrades to empty rather than raising."""
    path = tmp_path / "documents.json"
    path.write_text("{not json", encoding="utf-8")

    assert DocumentManifest(path).read() == []


def test_a_non_list_manifest_reads_as_empty(tmp_path: Path) -> None:
    """Manifest content of the wrong shape is ignored."""
    path = tmp_path / "documents.json"
    path.write_text('{"document_id": "x"}', encoding="utf-8")

    assert DocumentManifest(path).read() == []


def test_an_empty_manifest_reads_as_empty(tmp_path: Path) -> None:
    """A whitespace-only manifest is empty."""
    path = tmp_path / "documents.json"
    path.write_text("   \n", encoding="utf-8")

    assert DocumentManifest(path).read() == []


def test_appended_rows_are_persisted(tmp_path: Path) -> None:
    """An appended row survives a fresh read of the same file."""
    store = DocumentManifest(tmp_path / "documents.json")

    store.append({"document_id": "abc", "status": "indexed"})

    assert DocumentManifest(tmp_path / "documents.json").read() == [
        {"document_id": "abc", "status": "indexed"}
    ]


def test_manifest_rows_are_capped(tmp_path: Path) -> None:
    """The manifest does not grow without bound."""
    from app.services.document_manifest import MAX_RECORDS

    store = DocumentManifest(tmp_path / "documents.json")

    for index in range(MAX_RECORDS + 10):
        store.append({"document_id": str(index)})

    rows = store.read()

    assert len(rows) == MAX_RECORDS
    assert rows[-1]["document_id"] == str(MAX_RECORDS + 9)


async def test_a_failed_upload_is_recorded_with_a_reason(
    settings: Settings,
    manifest: DocumentManifest,
) -> None:
    """The manifest keeps a failed row so the attempt is not silently lost."""
    service = FakeKnowledgeService(ingest_error=RuntimeError("boom"))

    async with build_client(settings, manifest, service) as http:
        await http.post(
            DOCUMENTS_URL,
            files={"file": ("broken.pdf", PDF_BYTES, "application/pdf")},
        )

    row = manifest.read()[0]

    assert row["status"] == DocumentStatus.FAILED.value
    assert row["error"]
    assert "chunk_count" not in row
