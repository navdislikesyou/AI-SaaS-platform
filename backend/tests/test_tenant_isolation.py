"""Tenant isolation tests for the agent execution paths.

The audit that prompted this file found that ``/api/v1/agents/execute``
authenticated the caller but did not scope what the caller could reach. The
generic executor is the widest door in the platform: it dispatches to any
registered agent with any payload, so a missing organisation check there is a
missing organisation check everywhere.

These tests therefore drive the real retrieval, directory, and dataset paths
with two organisations and assert that neither can see the other's data. They
use fakes only where a real dependency would need a model or a network:
the vector store, the LLM, and the analysis service are replaced, while the
filtering, the authorization, and the routing are the real code.

The knowledge tests are the most direct evidence: the real
:class:`ChromaStore` filtering runs, the real
:class:`knowledge_agent.KnowledgeAgent.KnowledgeAgent` assembles the prompt,
and the assertion is on the prompt text and the returned citations. A foreign
document that leaked would show up in one or both.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.adapters.automation import AutomationAgentAdapter
from app.agents.adapters.knowledge import KnowledgeAgentAdapter
from app.agents.adapters.performance import PerformanceAgentAdapter
from app.agents.registry import AgentRegistry
from app.api import deps
from app.api.deps import (
    get_current_user_from_token_optional_principal,
    get_dataset_manifest,
    get_dataset_upload_service,
    get_document_manifest,
    get_employee_directory_manifest,
    get_job_manager,
    get_orchestrator,
    get_registry,
    get_settings_dep,
)
from app.core.config import Settings
from app.main import create_app
from app.services.dataset_upload import DatasetManifest, DatasetUploadService
from app.services.employee_directory import (
    DirectoryStatus,
    EmployeeDirectoryManifest,
    EmployeeDirectoryService,
    build_row,
    record_directory,
    set_directory_service,
    set_manifest,
)
from app.services.job_manager import JobManager
from app.services.orchestrator import Orchestrator
from knowledge_agent.knowledge_agent import KnowledgeAgent
from knowledge_agent.service import KnowledgeService
from knowledge_agent.vectordb.chroma_store import ChromaStore
from tests.fakes import FakePrincipal

EXECUTE_URL = "/api/v1/agents/execute"
DATASETS_URL = "/api/v1/performance/datasets"
JOBS_URL = "/api/v1/performance/jobs"
DIRECTORIES_URL = "/api/v1/automation/directories"

#: The two tenants used throughout. They are deliberately given distinct
#: content so that a leak is visible in the assertions rather than inferred.
ORG_A = "org-alpha"
ORG_B = "org-beta"

#: Text that only one tenant's documents contain. Its absence from the other
#: tenant's prompt is the whole point of the knowledge tests.
SECRET_A = "Alpha compensation is reviewed every March."
SECRET_B = "Beta severance requires two approvals."

#: A CSV with the columns the analyzers look for.
VALID_CSV = (
    b"date,sales,profit,units_sold,sales_target,profit_target,employee_id,"
    b"employee_name,department,product,region,customer_segment,sales_channel\n"
    b"2026-01-01,1000,200,4,1100,220,E-1,Aarti Rao,Sales,Widget,North,SMB,Direct\n"
    b"2026-02-01,1500,300,6,1400,280,E-2,Omkar Shenwai,Sales,Gadget,South,"
    b"Enterprise,Partner\n"
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeDocument:
    """A retrieved chunk, shaped like the LangChain document the store returns.

    Attributes:
        page_content: The chunk text.
        metadata: The chunk metadata, including the owning organisation.
    """

    def __init__(self, content: str, metadata: dict[str, Any]) -> None:
        """Initialize the document.

        Args:
            content: The chunk text.
            metadata: The chunk metadata.
        """
        self.page_content = content
        self.metadata = metadata


class _RecordingCollection:
    """A stand-in for the LangChain Chroma collection.

    It records the metadata filter it was called with, which is how the test
    checks that the store scoped the query inside the database rather than
    filtering afterwards.

    Attributes:
        filters: Every filter the collection was asked for, in order.
    """

    def __init__(self, documents: list[_FakeDocument]) -> None:
        """Initialize the collection.

        Args:
            documents: The documents the collection returns for any query.
        """
        self._documents = documents
        self.filters: list[Any] = []

    def max_marginal_relevance_search(
        self,
        query: str,
        k: int,
        fetch_k: int,
        filter: Any = None,
    ) -> list[_FakeDocument]:
        """Return every document, recording the filter that was applied.

        Args:
            query: The search text, unused.
            k: Number of chunks requested, unused.
            fetch_k: Candidate pool size, unused.
            filter: The metadata filter the store scoped the query with.

        Returns:
            The documents the collection holds.
        """
        self.filters.append(filter)
        return list(self._documents)


class _RecordingLLM:
    """A stand-in for the local LLM that records the prompt it was given.

    Attributes:
        prompts: Every prompt the LLM was asked to answer.
    """

    def __init__(self) -> None:
        """Initialize the recorder."""
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        """Record the prompt and return a fixed answer.

        Args:
            prompt: The prompt the agent assembled.

        Returns:
            A fixed answer, so the test reads the prompt rather than the reply.
        """
        self.prompts.append(prompt)
        return "answered from the provided context"


class _RecordingAnalysisService:
    """A stand-in for the Performance service that records what it analysed.

    Attributes:
        paths: Every file path the service was asked to analyse.
    """

    def __init__(self) -> None:
        """Initialize the recorder."""
        self.paths: list[str] = []

    def load_dataset(self, file_path: str) -> dict[str, Any]:
        """Record the path and describe the dataset.

        Args:
            file_path: The path the job resolved to.

        Returns:
            A minimal dataset description.
        """
        self.paths.append(file_path)
        return {"file_path": file_path, "rows": 2, "columns": ["sales", "profit"]}

    def operations(self) -> list[str]:
        """Return the operations this stub supports.

        Returns:
            The single operation the stub handles.
        """
        return ["load_dataset"]

    def available_analyzers(self) -> list[str]:
        """Return the analyzers this stub reports.

        Returns:
            An empty list.
        """
        return []

    def compute_kpis(self, df: Any) -> dict[str, Any]:
        """Return empty KPIs.

        Args:
            df: The prepared dataset, unused.

        Returns:
            An empty KPI block.
        """
        return {"overall": {}}

    def compare_periods(self, df: Any) -> dict[str, Any]:
        """Return an empty comparison.

        Args:
            df: The prepared dataset, unused.

        Returns:
            An empty comparison block.
        """
        return {}

    def analyze(self, df: Any) -> dict[str, Any]:
        """Return an empty analysis.

        Args:
            df: The prepared dataset, unused.

        Returns:
            An empty analysis block.
        """
        return {}

    def generate_visualizations(self, df: Any) -> dict[str, Any]:
        """Return no visualizations.

        Args:
            df: The prepared dataset, unused.

        Returns:
            An empty visualization block.
        """
        return {"charts": []}

    def generate_insights(self, df: Any) -> dict[str, Any]:
        """Return no insights.

        Args:
            df: The prepared dataset, unused.

        Returns:
            An empty insight block.
        """
        return {"insights": []}

    def run_full_pipeline(self, df: Any) -> dict[str, Any]:
        """Return an empty pipeline result.

        Args:
            df: The prepared dataset, unused.

        Returns:
            An empty pipeline block.
        """
        return {}


class _DirectoryServiceStub:
    """A stand-in for the employee directory service that only holds a path.

    The listing endpoint reads the manifest, not the files, so the service
    only has to provide the upload directory the helper writes into.

    Attributes:
        upload_dir: The directory uploaded files are written to.
    """

    def __init__(self, upload_dir: Path | None = None) -> None:
        """Initialize the stub.

        Args:
            upload_dir: The directory uploads are written to.
        """
        self.upload_dir = upload_dir if upload_dir is not None else Path(".")


class _RecordingAutomationService:
    """A stand-in for the Automation service that records the roster it got.

    Attributes:
        rosters: Every roster the service was handed, in order.
    """

    def __init__(self) -> None:
        """Initialize the recorder."""
        self.rosters: list[list[dict[str, Any]] | None] = []

    def execute(
        self,
        instruction: str,
        employees: list[dict[str, Any]] | None = None,
        user_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record the roster and return a drafted meeting.

        Args:
            instruction: The instruction to act on.
            employees: The roster the adapter resolved.
            user_context: The principal's context.

        Returns:
            A drafted meeting addressed to the roster.
        """
        self.rosters.append(employees)
        return {
            "meeting": {"title": "Standup", "date": "5 March", "time": "10 AM"},
            "recipients": list(employees or []),
            "email": "Draft body.",
            "employee_count": len(employees or []),
        }


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _principal(organization_id: str | None) -> Any:
    """Return the principal for one organisation.

    Args:
        organization_id: The organisation the caller belongs to, or None for an
            anonymous caller.

    Returns:
        A principal, or None when the caller is anonymous.
    """
    if organization_id is None:
        return None
    return FakePrincipal(
        user_id=f"user-{organization_id}",
        organization_id=organization_id,
    )


def _build_knowledge_service(
    documents: list[_FakeDocument],
) -> tuple[KnowledgeService, _RecordingCollection, _RecordingLLM]:
    """Wire the real Knowledge service to fakes for the model and the LLM.

    The store, the agent, and the service are the real classes. Only the
    LangChain collection and the LLM are replaced, so the filtering and the
    prompt assembly under test are the production code.

    Args:
        documents: The chunks the collection holds.

    Returns:
        The service, the recording collection, and the recording LLM.
    """
    collection = _RecordingCollection(documents)
    llm = _RecordingLLM()

    store = ChromaStore.__new__(ChromaStore)
    store.persist_directory = None
    store.collection_name = "test"
    store.vector_store = collection

    agent = KnowledgeAgent.__new__(KnowledgeAgent)
    agent.loader = None
    agent.splitter = None
    agent.embedding_model = None
    agent.vector_store = store
    agent.llm = llm

    service = KnowledgeService.__new__(KnowledgeService)
    service._settings = None
    service._agent = agent

    return service, collection, llm


def _build_client(
    settings: Settings,
    principal: Any,
    adapters: list[Any],
    job_manager: JobManager | None = None,
) -> AsyncClient:
    """Build a client whose requests carry one principal.

    Args:
        settings: Settings for the application.
        principal: The principal the requests are made as, or None for an
            anonymous caller.
        adapters: The adapters to register.
        job_manager: The job manager to install, when the test needs one.

    Returns:
        An AsyncClient bound to the application.
    """
    registry = AgentRegistry()
    for adapter in adapters:
        registry.register(adapter)

    deps.reset_state()
    application = create_app(settings)
    application.dependency_overrides[get_settings_dep] = lambda: settings
    application.dependency_overrides[get_registry] = lambda: registry
    application.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)
    application.dependency_overrides[get_current_user_from_token_optional_principal] = (
        lambda: principal
    )

    if job_manager is not None:
        application.dependency_overrides[get_job_manager] = lambda: job_manager

    return AsyncClient(
        transport=ASGITransport(app=application),  # type: ignore[arg-type]
        base_url="http://testserver",
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Return settings pointing every writable path at a temporary directory.

    Args:
        tmp_path: pytest's per-test temporary directory.

    Returns:
        Settings whose uploads and manifests live under tmp_path.
    """
    return Settings(
        environment="test",
        debug=False,
        log_level="WARNING",
        cors_origins=["http://testserver"],
        api_v1_prefix="/api/v1",
        performance_upload_dir=tmp_path / "performance",
        performance_upload_manifest_path=tmp_path / "performance" / "datasets.json",
        knowledge_upload_dir=tmp_path / "knowledge",
        knowledge_upload_manifest_path=tmp_path / "knowledge" / "documents.json",
        _env_file=None,
    )


@pytest.fixture
def knowledge_documents() -> list[_FakeDocument]:
    """Return one document per organisation, with distinct content.

    The two documents sit in the same collection, which is the point: the
    store holds every tenant's chunks together and has to separate them.

    Returns:
        The two documents, one owned by each organisation.
    """
    return [
        _FakeDocument(
            SECRET_A,
            {
                "source": "alpha.pdf",
                "page": 0,
                "organization_id": ORG_A,
                "owner_id": f"user-{ORG_A}",
            },
        ),
        _FakeDocument(
            SECRET_B,
            {
                "source": "beta.pdf",
                "page": 0,
                "organization_id": ORG_B,
                "owner_id": f"user-{ORG_B}",
            },
        ),
    ]


@pytest.fixture
def dataset_service(settings: Settings, tmp_path: Path) -> DatasetUploadService:
    """Return a dataset upload service writing to a temporary directory.

    Args:
        settings: Settings for the service.
        tmp_path: pytest's per-test temporary directory.

    Returns:
        A service bound to the temporary upload directory.
    """
    return DatasetUploadService(
        settings=settings,
        upload_dir=tmp_path / "datasets",
        max_bytes=1024 * 1024,
    )


@pytest.fixture
def dataset_manifest(tmp_path: Path) -> DatasetManifest:
    """Return a dataset manifest writing to a temporary directory.

    Args:
        tmp_path: pytest's per-test temporary directory.

    Returns:
        A manifest bound to the temporary directory.
    """
    return DatasetManifest(tmp_path / "datasets" / "datasets.json")


@pytest.fixture
def employee_service(settings: Settings, tmp_path: Path) -> EmployeeDirectoryService:
    """Return an employee directory service writing to a temporary directory.

    Args:
        settings: Settings for the service.
        tmp_path: pytest's per-test temporary directory.

    Returns:
        A service bound to the temporary upload directory.
    """
    return EmployeeDirectoryService(settings=settings, upload_dir=tmp_path / "directories")


@pytest.fixture
def employee_manifest(tmp_path: Path) -> EmployeeDirectoryManifest:
    """Return an employee directory manifest writing to a temporary directory.

    Args:
        tmp_path: pytest's per-test temporary directory.

    Returns:
        A manifest bound to the temporary directory.
    """
    return EmployeeDirectoryManifest(tmp_path / "directories" / "directories.json")


def _register_directory(
    service: EmployeeDirectoryService,
    manifest: EmployeeDirectoryManifest,
    organization_id: str,
    records: list[dict[str, Any]],
) -> str:
    """Record one uploaded directory owned by an organisation.

    The row is written to the manifest the same way the upload route writes
    it, so the adapter's ownership check sees exactly what it would see in
    production.

    Args:
        service: The directory service holding the uploaded files.
        manifest: The manifest to record the row in.
        organization_id: The organisation that owns the directory.
        records: The employee records the directory holds.

    Returns:
        The new directory id.
    """
    service.upload_dir.mkdir(parents=True, exist_ok=True)

    directory_id = uuid.uuid4().hex
    stored_name = f"{directory_id}_directory.json"

    (service.upload_dir / stored_name).write_text(json.dumps(records), encoding="utf-8")

    record_directory(
        build_row(
            directory_id=directory_id,
            display_filename="directory.json",
            stored_name=stored_name,
            extension=".json",
            size_bytes=len(json.dumps(records)),
            status=DirectoryStatus.READY,
            employee_count=len(records),
            organization_id=organization_id,
            owner_id=f"user-{organization_id}",
        ),
        manifest,
    )

    return directory_id


# ---------------------------------------------------------------------------
# Knowledge: the retrieval path
# ---------------------------------------------------------------------------


async def test_a_broad_query_returns_only_the_callers_own_documents(
    settings: Settings,
    knowledge_documents: list[_FakeDocument],
) -> None:
    """A query scoped to one organisation never returns the other's document.

    The question is deliberately broad enough to match both documents, so the
    only thing keeping the other tenant's text out is the organisation filter.

    Args:
        settings: Settings for the application.
        knowledge_documents: One document per organisation.
    """
    service, _collection, _llm = _build_knowledge_service(knowledge_documents)

    async with _build_client(
        settings,
        _principal(ORG_A),
        [KnowledgeAgentAdapter(service=service)],
    ) as client:
        response = await client.post(
            EXECUTE_URL,
            json={
                "agent": "knowledge",
                "operation": "query",
                "payload": {"question": "What is the policy?"},
            },
        )

    assert response.status_code == 200
    body = response.json()["data"]["data"]
    assert body["sources"] == [{"page": 1, "source": "alpha.pdf"}]
    assert SECRET_A not in body["answer"]


async def test_another_tenants_text_never_reaches_the_prompt(
    settings: Settings,
    knowledge_documents: list[_FakeDocument],
) -> None:
    """The prompt the LLM is given contains only the caller's own document.

    This is the assertion that matters for the knowledge agent: the answer is
    generated from the prompt, so a foreign document in the prompt is a foreign
    document in the answer.

    Args:
        settings: Settings for the application.
        knowledge_documents: One document per organisation.
    """
    service, _collection, llm = _build_knowledge_service(knowledge_documents)

    async with _build_client(
        settings,
        _principal(ORG_B),
        [KnowledgeAgentAdapter(service=service)],
    ) as client:
        response = await client.post(
            EXECUTE_URL,
            json={
                "agent": "knowledge",
                "operation": "query",
                "payload": {"question": "What is the policy?"},
            },
        )

    assert response.status_code == 200

    assert len(llm.prompts) == 1
    prompt = llm.prompts[0]
    assert SECRET_B in prompt
    assert SECRET_A not in prompt


async def test_the_vector_query_is_scoped_inside_the_store(
    settings: Settings,
    knowledge_documents: list[_FakeDocument],
) -> None:
    """The organisation filter reaches the vector store, not just the manifest.

    Filtering after retrieval would still let another tenant's chunks be
    ranked and returned by the database first. The filter has to be applied
    where the search happens.

    Args:
        settings: Settings for the application.
        knowledge_documents: One document per organisation.
    """
    service, collection, _llm = _build_knowledge_service(knowledge_documents)

    async with _build_client(
        settings,
        _principal(ORG_A),
        [KnowledgeAgentAdapter(service=service)],
    ) as client:
        response = await client.post(
            EXECUTE_URL,
            json={
                "agent": "knowledge",
                "operation": "query",
                "payload": {"question": "What is the policy?"},
            },
        )

    assert response.status_code == 200
    assert collection.filters == [{"organization_id": ORG_A}]


async def test_documents_without_ownership_are_inaccessible(
    settings: Settings,
) -> None:
    """A document with no recorded owner is invisible to every organisation.

    Legacy records predate ownership, so their tenant cannot be established.
    Treating them as public would hand one tenant's history to another.

    Args:
        settings: Settings for the application.
    """
    legacy = _FakeDocument(
        "An unowned legacy document.",
        {"source": "legacy.pdf", "page": 0},
    )
    service, _collection, llm = _build_knowledge_service([legacy])

    async with _build_client(
        settings,
        _principal(ORG_A),
        [KnowledgeAgentAdapter(service=service)],
    ) as client:
        response = await client.post(
            EXECUTE_URL,
            json={
                "agent": "knowledge",
                "operation": "query",
                "payload": {"question": "What is the policy?"},
            },
        )

    assert response.status_code == 200
    body = response.json()["data"]["data"]
    assert body["sources"] == []
    assert "An unowned legacy document." not in llm.prompts[0]


async def test_an_anonymous_caller_cannot_run_a_knowledge_query(
    settings: Settings,
    knowledge_documents: list[_FakeDocument],
) -> None:
    """A caller with no organisation is refused rather than served unscoped data.

    The knowledge base holds every tenant's documents, so a query that cannot
    be scoped would read all of them.

    Args:
        settings: Settings for the application.
        knowledge_documents: One document per organisation.
    """
    service, _collection, llm = _build_knowledge_service(knowledge_documents)

    async with _build_client(
        settings,
        None,
        [KnowledgeAgentAdapter(service=service)],
    ) as client:
        response = await client.post(
            EXECUTE_URL,
            json={
                "agent": "knowledge",
                "operation": "query",
                "payload": {"question": "What is the policy?"},
            },
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert llm.prompts == []


async def test_an_anonymous_caller_cannot_index_a_document(
    settings: Settings,
) -> None:
    """Indexing without an organisation would write a document nobody owns.

    Args:
        settings: Settings for the application.
    """
    service, _collection, _llm = _build_knowledge_service([])

    async with _build_client(
        settings,
        None,
        [KnowledgeAgentAdapter(service=service)],
    ) as client:
        response = await client.post(
            EXECUTE_URL,
            json={
                "agent": "knowledge",
                "operation": "ingest_document",
                "payload": {"file_path": "handbook.pdf"},
            },
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# The listing endpoints
# ---------------------------------------------------------------------------


async def test_an_anonymous_caller_sees_no_documents(
    settings: Settings,
    employee_manifest: EmployeeDirectoryManifest,
) -> None:
    """A request with no organisation is shown no uploaded documents.

    The listing used to return the whole history to an anonymous caller, which
    handed every tenant's filenames to anyone who asked.

    Args:
        settings: Settings for the application.
        employee_manifest: An unused manifest, kept for a uniform signature.
    """
    from app.services.document_manifest import (
        DocumentManifest,
        DocumentStatus,
        record_document,
    )
    from app.services.document_manifest import (
        build_row as build_document_row,
    )

    manifest = DocumentManifest(settings.resolved_knowledge_upload_manifest_path)
    record_document(
        build_document_row(
            document_id="doc-1",
            display_filename="alpha.pdf",
            stored_name="alpha.pdf",
            extension=".pdf",
            size_bytes=10,
            status=DocumentStatus.INDEXED,
            organization_id=ORG_A,
            owner_id=f"user-{ORG_A}",
        ),
        manifest,
    )

    application = create_app(settings)
    registry = AgentRegistry()
    registry.register(PerformanceAgentAdapter())

    deps.reset_state()
    application.dependency_overrides[get_settings_dep] = lambda: settings
    application.dependency_overrides[get_registry] = lambda: registry
    application.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)
    application.dependency_overrides[get_document_manifest] = lambda: manifest
    application.dependency_overrides[get_current_user_from_token_optional_principal] = (
        lambda: None
    )

    async with AsyncClient(
        transport=ASGITransport(app=application),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/knowledge/documents")

    assert response.status_code == 200
    assert response.json()["data"]["documents"] == []


async def test_a_tenant_sees_only_its_own_documents(
    settings: Settings,
) -> None:
    """The listing is scoped to the caller's organisation.

    Args:
        settings: Settings for the application.
    """
    from app.services.document_manifest import (
        DocumentManifest,
        DocumentStatus,
        record_document,
    )
    from app.services.document_manifest import (
        build_row as build_document_row,
    )

    manifest = DocumentManifest(settings.resolved_knowledge_upload_manifest_path)
    for organization_id in (ORG_A, ORG_B):
        record_document(
            build_document_row(
                document_id=f"doc-{organization_id}",
                display_filename=f"{organization_id}.pdf",
                stored_name=f"{organization_id}.pdf",
                extension=".pdf",
                size_bytes=10,
                status=DocumentStatus.INDEXED,
                organization_id=organization_id,
                owner_id=f"user-{organization_id}",
            ),
            manifest,
        )

    application = create_app(settings)
    registry = AgentRegistry()
    registry.register(PerformanceAgentAdapter())

    deps.reset_state()
    application.dependency_overrides[get_settings_dep] = lambda: settings
    application.dependency_overrides[get_registry] = lambda: registry
    application.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)
    application.dependency_overrides[get_document_manifest] = lambda: manifest
    application.dependency_overrides[get_current_user_from_token_optional_principal] = (
        lambda: _principal(ORG_A)
    )

    async with AsyncClient(
        transport=ASGITransport(app=application),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/knowledge/documents")

    assert response.status_code == 200
    documents = response.json()["data"]["documents"]
    assert [d["document_id"] for d in documents] == [f"doc-{ORG_A}"]


async def test_an_anonymous_caller_sees_no_employee_directories(
    settings: Settings,
    employee_manifest: EmployeeDirectoryManifest,
    tmp_path: Path,
) -> None:
    """A request with no organisation is shown no employee directories.

    Args:
        settings: Settings for the application.
        employee_manifest: The manifest the directory is recorded in.
        tmp_path: pytest's per-test temporary directory.
    """
    _register_directory(
        service=_DirectoryServiceStub(tmp_path),
        manifest=employee_manifest,
        organization_id=ORG_A,
        records=[{"name": "Aarti Rao", "email": "aarti@alpha.example"}],
    )

    application = create_app(settings)
    registry = AgentRegistry()
    registry.register(PerformanceAgentAdapter())

    deps.reset_state()
    application.dependency_overrides[get_settings_dep] = lambda: settings
    application.dependency_overrides[get_registry] = lambda: registry
    application.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)
    application.dependency_overrides[get_employee_directory_manifest] = (
        lambda: employee_manifest
    )
    application.dependency_overrides[get_current_user_from_token_optional_principal] = (
        lambda: None
    )

    async with AsyncClient(
        transport=ASGITransport(app=application),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/automation/directories")

    assert response.status_code == 200
    assert response.json()["data"]["directories"] == []


def _build_automation_client(
    settings: Settings,
    principal: Any,
    service: _RecordingAutomationService,
    manifest: EmployeeDirectoryManifest,
    directory_service: EmployeeDirectoryService,
) -> AsyncClient:
    """Build a client with the shared manifest and directory service installed.

    The adapter resolves a directory id through the module-level accessors in
    ``app.services.employee_directory``, and building the client resets those
    singletons. They are installed here, after the client exists, so the
    adapter and the test see the same manifest.

    Args:
        settings: Settings for the application.
        principal: The principal the requests are made as.
        service: The automation service the adapter calls.
        manifest: The manifest holding the uploaded directories.
        directory_service: The service holding the uploaded files.

    Returns:
        An AsyncClient bound to the application.
    """
    client = _build_client(
        settings,
        principal,
        [AutomationAgentAdapter(service=service)],
    )

    set_manifest(manifest)
    set_directory_service(directory_service)

    return client


# ---------------------------------------------------------------------------
# Automation: directory id substitution
# ---------------------------------------------------------------------------


async def test_a_tenant_cannot_draft_against_another_tenants_directory(
    settings: Settings,
    employee_service: EmployeeDirectoryService,
    employee_manifest: EmployeeDirectoryManifest,
) -> None:
    """Substituting another organisation's directory id is refused.

    The directory id arrives from the client, so it can be replaced with one
    belonging to a different tenant. The check happens before the roster is
    read, so the recipients never reach the draft.

    Args:
        settings: Settings for the application.
        employee_service: The directory service holding the uploaded file.
        employee_manifest: The manifest the directory is recorded in.
    """
    records = [{"name": "Aarti Rao", "email": "aarti@alpha.example"}]
    directory_id = _register_directory(
        employee_service, employee_manifest, ORG_A, records
    )

    client = _build_automation_client(
        settings,
        _principal(ORG_B),
        _RecordingAutomationService(),
        employee_manifest,
        employee_service,
    )

    try:
        async with client as http:
            response = await http.post(
                EXECUTE_URL,
                json={
                    "agent": "automation",
                    "operation": "draft_action",
                    "payload": {
                        "instruction": "Draft a standup invite",
                        "directory_id": directory_id,
                    },
                },
            )
    finally:
        set_manifest(None)
        set_directory_service(None)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DIRECTORY_NOT_FOUND"


async def test_a_tenant_can_draft_against_its_own_directory(
    settings: Settings,
    employee_service: EmployeeDirectoryService,
    employee_manifest: EmployeeDirectoryManifest,
) -> None:
    """The owning organisation is still served, with its own roster.

    Args:
        settings: Settings for the application.
        employee_service: The directory service holding the uploaded file.
        employee_manifest: The manifest the directory is recorded in.
    """
    records = [{"name": "Aarti Rao", "email": "aarti@alpha.example"}]
    directory_id = _register_directory(
        employee_service, employee_manifest, ORG_A, records
    )

    client = _build_automation_client(
        settings,
        _principal(ORG_A),
        _RecordingAutomationService(),
        employee_manifest,
        employee_service,
    )

    try:
        async with client as http:
            response = await http.post(
                EXECUTE_URL,
                json={
                    "agent": "automation",
                    "operation": "draft_action",
                    "payload": {
                        "instruction": "Draft a standup invite",
                        "directory_id": directory_id,
                    },
                },
            )
    finally:
        set_manifest(None)
        set_directory_service(None)

    assert response.status_code == 200
    body = response.json()["data"]["data"]
    assert body["directory"]["source"] == "uploaded"
    assert body["directory"]["directory_id"] == directory_id


async def test_an_anonymous_caller_cannot_draft_against_a_directory(
    settings: Settings,
    employee_service: EmployeeDirectoryService,
    employee_manifest: EmployeeDirectoryManifest,
) -> None:
    """A directory belongs to an organisation, so an anonymous caller is refused.

    Args:
        settings: Settings for the application.
        employee_service: The directory service holding the uploaded file.
        employee_manifest: The manifest the directory is recorded in.
    """
    records = [{"name": "Aarti Rao", "email": "aarti@alpha.example"}]
    directory_id = _register_directory(
        employee_service, employee_manifest, ORG_A, records
    )

    client = _build_automation_client(
        settings,
        None,
        _RecordingAutomationService(),
        employee_manifest,
        employee_service,
    )

    try:
        async with client as http:
            response = await http.post(
                EXECUTE_URL,
                json={
                    "agent": "automation",
                    "operation": "draft_action",
                    "payload": {
                        "instruction": "Draft a standup invite",
                        "directory_id": directory_id,
                    },
                },
            )
    finally:
        set_manifest(None)
        set_directory_service(None)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# Performance: dataset, job, and artifact substitution
# ---------------------------------------------------------------------------


async def test_a_tenant_cannot_run_a_job_against_another_tenants_dataset(
    settings: Settings,
    dataset_service: DatasetUploadService,
    dataset_manifest: DatasetManifest,
) -> None:
    """A dataset id belonging to another organisation is refused.

    The job would carry the caller's own organisation, so without this check
    the caller would read another tenant's numbers in a result they own.

    Args:
        settings: Settings for the application.
        dataset_service: The upload service the dataset is written through.
        dataset_manifest: The manifest the dataset is recorded in.
    """
    application = create_app(settings)
    registry = AgentRegistry()
    registry.register(PerformanceAgentAdapter())

    deps.reset_state()
    application.dependency_overrides[get_settings_dep] = lambda: settings
    application.dependency_overrides[get_registry] = lambda: registry
    application.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)
    application.dependency_overrides[get_dataset_upload_service] = lambda: dataset_service
    application.dependency_overrides[get_dataset_manifest] = lambda: dataset_manifest

    async with AsyncClient(
        transport=ASGITransport(app=application),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as client:
        application.dependency_overrides[get_current_user_from_token_optional_principal] = (
            lambda: _principal(ORG_A)
        )
        upload = await client.post(
            DATASETS_URL,
            files={"file": ("alpha.csv", VALID_CSV, "text/csv")},
        )
        assert upload.status_code == 201
        dataset_id = upload.json()["data"]["dataset"]["dataset_id"]

        application.dependency_overrides[get_current_user_from_token_optional_principal] = (
            lambda: _principal(ORG_B)
        )
        response = await client.post(
            JOBS_URL,
            json={"operation": "load_dataset", "dataset_id": dataset_id},
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DATASET_NOT_FOUND"


async def test_a_tenant_cannot_read_another_tenants_job(
    settings: Settings,
    dataset_service: DatasetUploadService,
    dataset_manifest: DatasetManifest,
) -> None:
    """A job id belonging to another organisation is refused on polling.

    Args:
        settings: Settings for the application.
        dataset_service: The upload service the dataset is written through.
        dataset_manifest: The manifest the dataset is recorded in.
    """
    manager = JobManager(service_factory=_RecordingAnalysisService)

    application = create_app(settings)
    registry = AgentRegistry()
    registry.register(PerformanceAgentAdapter())

    deps.reset_state()
    application.dependency_overrides[get_settings_dep] = lambda: settings
    application.dependency_overrides[get_registry] = lambda: registry
    application.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)
    application.dependency_overrides[get_dataset_upload_service] = lambda: dataset_service
    application.dependency_overrides[get_dataset_manifest] = lambda: dataset_manifest
    application.dependency_overrides[get_job_manager] = lambda: manager

    async with AsyncClient(
        transport=ASGITransport(app=application),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as client:
        application.dependency_overrides[get_current_user_from_token_optional_principal] = (
            lambda: _principal(ORG_A)
        )
        upload = await client.post(
            DATASETS_URL,
            files={"file": ("alpha.csv", VALID_CSV, "text/csv")},
        )
        dataset_id = upload.json()["data"]["dataset"]["dataset_id"]

        created = await client.post(
            JOBS_URL,
            json={"operation": "load_dataset", "dataset_id": dataset_id},
        )
        assert created.status_code == 202
        job_id = created.json()["data"]["job_id"]

        application.dependency_overrides[get_current_user_from_token_optional_principal] = (
            lambda: _principal(ORG_B)
        )
        response = await client.get(f"{JOBS_URL}/{job_id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"


async def test_a_tenant_cannot_download_another_tenants_artifact(
    settings: Settings,
    dataset_service: DatasetUploadService,
    dataset_manifest: DatasetManifest,
) -> None:
    """An artifact belonging to another organisation's job is refused.

    Args:
        settings: Settings for the application.
        dataset_service: The upload service the dataset is written through.
        dataset_manifest: The manifest the dataset is recorded in.
    """
    manager = JobManager(service_factory=_RecordingAnalysisService)

    application = create_app(settings)
    registry = AgentRegistry()
    registry.register(PerformanceAgentAdapter())

    deps.reset_state()
    application.dependency_overrides[get_settings_dep] = lambda: settings
    application.dependency_overrides[get_registry] = lambda: registry
    application.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)
    application.dependency_overrides[get_dataset_upload_service] = lambda: dataset_service
    application.dependency_overrides[get_dataset_manifest] = lambda: dataset_manifest
    application.dependency_overrides[get_job_manager] = lambda: manager

    async with AsyncClient(
        transport=ASGITransport(app=application),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as client:
        application.dependency_overrides[get_current_user_from_token_optional_principal] = (
            lambda: _principal(ORG_A)
        )
        upload = await client.post(
            DATASETS_URL,
            files={"file": ("alpha.csv", VALID_CSV, "text/csv")},
        )
        dataset_id = upload.json()["data"]["dataset"]["dataset_id"]

        created = await client.post(
            JOBS_URL,
            json={"operation": "load_dataset", "dataset_id": dataset_id},
        )
        job_id = created.json()["data"]["job_id"]

        application.dependency_overrides[get_current_user_from_token_optional_principal] = (
            lambda: _principal(ORG_B)
        )
        response = await client.get(f"{JOBS_URL}/{job_id}/artifacts/chart.png")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"


async def test_a_tenant_can_run_and_read_its_own_job(
    settings: Settings,
    dataset_service: DatasetUploadService,
    dataset_manifest: DatasetManifest,
) -> None:
    """The owning organisation is still served, so the fix is not a lockout.

    Args:
        settings: Settings for the application.
        dataset_service: The upload service the dataset is written through.
        dataset_manifest: The manifest the dataset is recorded in.
    """
    manager = JobManager(service_factory=_RecordingAnalysisService)

    application = create_app(settings)
    registry = AgentRegistry()
    registry.register(PerformanceAgentAdapter())

    deps.reset_state()
    application.dependency_overrides[get_settings_dep] = lambda: settings
    application.dependency_overrides[get_registry] = lambda: registry
    application.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)
    application.dependency_overrides[get_dataset_upload_service] = lambda: dataset_service
    application.dependency_overrides[get_dataset_manifest] = lambda: dataset_manifest
    application.dependency_overrides[get_job_manager] = lambda: manager

    async with AsyncClient(
        transport=ASGITransport(app=application),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as client:
        application.dependency_overrides[get_current_user_from_token_optional_principal] = (
            lambda: _principal(ORG_A)
        )
        upload = await client.post(
            DATASETS_URL,
            files={"file": ("alpha.csv", VALID_CSV, "text/csv")},
        )
        dataset_id = upload.json()["data"]["dataset"]["dataset_id"]

        created = await client.post(
            JOBS_URL,
            json={"operation": "load_dataset", "dataset_id": dataset_id},
        )
        assert created.status_code == 202
        job_id = created.json()["data"]["job_id"]

        response = await client.get(f"{JOBS_URL}/{job_id}")

    assert response.status_code == 200
    assert response.json()["data"]["job_id"] == job_id


# ---------------------------------------------------------------------------
# The generic executor
# ---------------------------------------------------------------------------


async def test_the_executor_passes_the_principal_to_the_agent(
    settings: Settings,
) -> None:
    """The organisation reaches the agent, so scoping is possible at all.

    Args:
        settings: Settings for the application.
    """
    seen: list[dict[str, Any] | None] = []

    class _RecordingAgent(AutomationAgentAdapter):
        """An adapter that records the principal it was handed."""

        def run(
            self,
            operation: str,
            payload: dict[str, Any],
            user_context: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            """Record the principal and return a draft.

            Args:
                operation: The requested operation.
                payload: The request payload.
                user_context: The principal's context.

            Returns:
                A minimal draft.
            """
            seen.append(user_context)
            return {"email": "draft"}

    async with _build_client(
        settings,
        _principal(ORG_A),
        [_RecordingAgent(service=_RecordingAutomationService())],
    ) as client:
        response = await client.post(
            EXECUTE_URL,
            json={
                "agent": "automation",
                "operation": "draft_action",
                "payload": {"instruction": "Draft a standup invite"},
            },
        )

    assert response.status_code == 200
    assert len(seen) == 1
    assert seen[0] is not None
    assert seen[0]["organization_id"] == ORG_A
    assert seen[0]["user_id"] == f"user-{ORG_A}"


async def test_the_executor_does_not_expose_unscoped_data(
    settings: Settings,
    knowledge_documents: list[_FakeDocument],
) -> None:
    """The generic executor cannot be used to reach unscoped documents.

    This is the executor-level statement of the same rule the knowledge tests
    assert in detail: a caller with no organisation is refused at the
    boundary, so the agent never runs.

    Args:
        settings: Settings for the application.
        knowledge_documents: One document per organisation.
    """
    service, _collection, llm = _build_knowledge_service(knowledge_documents)

    async with _build_client(
        settings,
        None,
        [KnowledgeAgentAdapter(service=service)],
    ) as client:
        response = await client.post(
            EXECUTE_URL,
            json={
                "agent": "knowledge",
                "operation": "query",
                "payload": {"question": "What is the policy?"},
            },
        )

    assert response.status_code == 403
    assert llm.prompts == []
    assert SECRET_A not in response.text
    assert SECRET_B not in response.text


async def test_an_ordinary_authorized_execution_still_works(
    settings: Settings,
) -> None:
    """A normal, in-scope execution is unaffected by the isolation work.

    Args:
        settings: Settings for the application.
    """
    service = _RecordingAutomationService()

    async with _build_client(
        settings,
        _principal(ORG_A),
        [AutomationAgentAdapter(service=service)],
    ) as client:
        response = await client.post(
            EXECUTE_URL,
            json={
                "agent": "automation",
                "operation": "draft_action",
                "payload": {"instruction": "Draft a standup invite"},
            },
        )

    assert response.status_code == 200
    body = response.json()["data"]["data"]
    assert body["email"] == "Draft body."
    assert body["directory"]["source"] == "default"


# ---------------------------------------------------------------------------
# Anonymous callers and tenant-owned resources
#
# The optional-principal dependency answers with no user when the request
# carries no token, an expired token, or a revoked one. A tenant-owned
# resource must not become readable in that case. The ownership check has to
# be a comparison, not a comparison that is skipped when the caller is
# anonymous: an expired token must not be a way around it.
# ---------------------------------------------------------------------------


async def test_an_anonymous_caller_cannot_read_a_tenants_job(
    settings: Settings,
    dataset_service: DatasetUploadService,
    dataset_manifest: DatasetManifest,
) -> None:
    """A job belonging to a tenant is refused to an anonymous caller.

    The token has expired, or was never sent. The job still belongs to a
    tenant, so its result must not be served.

    Args:
        settings: Settings for the application.
        dataset_service: The upload service the dataset is written through.
        dataset_manifest: The manifest the dataset is recorded in.
    """
    manager = JobManager(service_factory=_RecordingAnalysisService)

    application = create_app(settings)
    registry = AgentRegistry()
    registry.register(PerformanceAgentAdapter())

    deps.reset_state()
    application.dependency_overrides[get_settings_dep] = lambda: settings
    application.dependency_overrides[get_registry] = lambda: registry
    application.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)
    application.dependency_overrides[get_dataset_upload_service] = lambda: dataset_service
    application.dependency_overrides[get_dataset_manifest] = lambda: dataset_manifest
    application.dependency_overrides[get_job_manager] = lambda: manager

    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://testserver",
    ) as client:
        application.dependency_overrides[get_current_user_from_token_optional_principal] = (
            lambda: _principal(ORG_A)
        )
        upload = await client.post(
            DATASETS_URL,
            files={"file": ("alpha.csv", VALID_CSV, "text/csv")},
        )
        dataset_id = upload.json()["data"]["dataset"]["dataset_id"]

        created = await client.post(
            JOBS_URL,
            json={"operation": "load_dataset", "dataset_id": dataset_id},
        )
        job_id = created.json()["data"]["job_id"]

        # The token expired between the upload and the poll.
        application.dependency_overrides[get_current_user_from_token_optional_principal] = (
            lambda: _principal(None)
        )
        response = await client.get(f"{JOBS_URL}/{job_id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"


async def test_an_anonymous_caller_cannot_download_a_tenants_artifact(
    settings: Settings,
    dataset_service: DatasetUploadService,
    dataset_manifest: DatasetManifest,
) -> None:
    """A chart belonging to a tenant's job is refused to an anonymous caller.

    Args:
        settings: Settings for the application.
        dataset_service: The upload service the dataset is written through.
        dataset_manifest: The manifest the dataset is recorded in.
    """
    manager = JobManager(service_factory=_RecordingAnalysisService)

    application = create_app(settings)
    registry = AgentRegistry()
    registry.register(PerformanceAgentAdapter())

    deps.reset_state()
    application.dependency_overrides[get_settings_dep] = lambda: settings
    application.dependency_overrides[get_registry] = lambda: registry
    application.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)
    application.dependency_overrides[get_dataset_upload_service] = lambda: dataset_service
    application.dependency_overrides[get_dataset_manifest] = lambda: dataset_manifest
    application.dependency_overrides[get_job_manager] = lambda: manager

    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://testserver",
    ) as client:
        application.dependency_overrides[get_current_user_from_token_optional_principal] = (
            lambda: _principal(ORG_A)
        )
        upload = await client.post(
            DATASETS_URL,
            files={"file": ("alpha.csv", VALID_CSV, "text/csv")},
        )
        dataset_id = upload.json()["data"]["dataset"]["dataset_id"]

        created = await client.post(
            JOBS_URL,
            json={"operation": "load_dataset", "dataset_id": dataset_id},
        )
        job_id = created.json()["data"]["job_id"]

        application.dependency_overrides[get_current_user_from_token_optional_principal] = (
            lambda: _principal(None)
        )
        response = await client.get(f"{JOBS_URL}/{job_id}/artifacts/chart.png")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"


async def test_an_anonymous_caller_cannot_read_a_tenants_directory(
    settings: Settings,
    employee_service: EmployeeDirectoryService,
    employee_manifest: EmployeeDirectoryManifest,
) -> None:
    """An employee directory belonging to a tenant is refused to an anonymous caller.

    The directory holds names and addresses of the tenant's staff, so an
    expired token must not be a way to read it.

    Args:
        settings: Settings for the application.
        employee_service: The directory service holding the uploaded file.
        employee_manifest: The manifest the directory is recorded in.
    """
    records = [{"name": "Aarti Rao", "email": "aarti@alpha.example"}]
    directory_id = _register_directory(
        employee_service, employee_manifest, ORG_A, records
    )

    client = _build_automation_client(
        settings,
        _principal(None),
        _RecordingAutomationService(),
        employee_manifest,
        employee_service,
    )

    try:
        async with client as http:
            response = await http.get(f"{DIRECTORIES_URL}/{directory_id}")
    finally:
        set_manifest(None)
        set_directory_service(None)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DIRECTORY_NOT_FOUND"
    assert "aarti@alpha.example" not in response.text
