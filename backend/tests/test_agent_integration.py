"""Opt-in integration tests against the real agent stack.

Every test here loads an actual model, opens a real Chroma directory, and calls
a real Ollama server. None of it runs as part of normal CI: each test skips
unless its agent is explicitly enabled in the environment.

To run them, start Ollama with the model pulled, install the agent
dependencies, then enable the flags:

    pip install -r requirements.txt -r requirements-agents.txt
    ollama serve
    ollama pull llama3.1:8b

    KNOWLEDGE_AGENT_ENABLED=true pytest tests/test_agent_integration.py

The flags are read directly from the environment rather than through Settings
defaults, because a Settings default of ``false`` would silently disable these
tests even when the operator intended them to run.

Skips are reported, never swallowed: run with ``-rs`` to see which agent
prerequisites are missing.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.registry import AgentRegistry
from app.api import deps
from app.api.deps import get_orchestrator, get_registry, get_settings_dep
from app.core.config import Settings
from app.main import create_app
from app.services.orchestrator import Orchestrator

EXECUTE_URL = "/api/v1/agents/execute"

KNOWLEDGE_ENABLED = os.getenv("KNOWLEDGE_AGENT_ENABLED", "").lower() == "true"
AUTOMATION_ENABLED = os.getenv("AUTOMATION_AGENT_ENABLED", "").lower() == "true"

SAMPLE_PDF = Path("knowledge_agent/data/documents/sample.pdf")

knowledge_required = pytest.mark.skipif(
    not KNOWLEDGE_ENABLED,
    reason="Set KNOWLEDGE_AGENT_ENABLED=true to run real-agent integration tests.",
)

automation_required = pytest.mark.skipif(
    not AUTOMATION_ENABLED,
    reason="Set AUTOMATION_AGENT_ENABLED=true to run real-agent integration tests.",
)


def build_client(settings: Settings) -> AsyncClient:
    """Build a client over the real default registry.

    Args:
        settings: Settings driving the agent construction.

    Returns:
        An AsyncClient bound to an application wired to the real adapters.
    """
    from app.agents.factory import build_registry

    registry: AgentRegistry = build_registry(settings)
    deps.reset_state()
    application = create_app(settings)
    application.dependency_overrides[get_settings_dep] = lambda: settings
    application.dependency_overrides[get_registry] = lambda: registry
    application.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)

    return AsyncClient(
        transport=ASGITransport(app=application),  # type: ignore[arg-type]
        base_url="http://testserver",
    )


def env_settings() -> Settings:
    """Return settings built from the current environment.

    Returns:
        Settings honouring the operator's ``.env`` and exported variables.
    """
    return Settings()


def require_knowledge_deps() -> None:
    """Skip unless the Knowledge agent's dependencies are importable.

    Enabling the flag is not sufficient on its own: without
    ``requirements-agents.txt`` installed the adapter degrades to unavailable
    and the test would fail for a missing dependency rather than for anything
    about the agent.
    """
    try:
        import knowledge_agent.service  # noqa: F401
    except Exception as exc:  # pragma: no cover - depends on local install
        pytest.skip(f"Knowledge agent dependencies not installed: {exc}")


def require_automation_deps() -> None:
    """Skip unless the Automation agent's dependencies are importable.

    Args:
        None.

    Raises:
        Nothing. Skips the test when the import fails.
    """
    try:
        import automation_agent.service  # noqa: F401
    except Exception as exc:  # pragma: no cover - depends on local install
        pytest.skip(f"Automation agent dependencies not installed: {exc}")


@knowledge_required
async def test_knowledge_agent_connects_and_answers() -> None:
    """A real query returns an answer and its sources.

    This is the end-to-end gate: real BGE embeddings, a real Chroma store, and
    a real Ollama generation behind the adapter.
    """
    settings = env_settings()

    require_knowledge_deps()

    async with build_client(settings) as client:
        catalog = await client.get("/api/v1/agents")
        agents = {a["name"]: a for a in catalog.json()["data"]["agents"]}

        assert agents["knowledge"]["available"] is True, (
            "Knowledge agent did not connect. Check that the agent "
            "dependencies are installed and Ollama is serving the model."
        )

        response = await client.post(
            EXECUTE_URL,
            json={
                "agent": "knowledge",
                "operation": "query",
                "payload": {"question": "What is this document about?"},
            },
        )

    assert response.status_code == 200, response.text
    data = response.json()["data"]["data"]

    assert isinstance(data["answer"], str)
    assert data["answer"].strip()
    assert isinstance(data["sources"], list)
    assert data["sources"], "a grounded answer must cite at least one source"

    for source in data["sources"]:
        assert set(source) == {"source", "page"}
        assert isinstance(source["page"], int)


@knowledge_required
async def test_knowledge_agent_ingests_a_real_document() -> None:
    """A real PDF ingests and reports a chunk count."""
    require_knowledge_deps()
    settings = env_settings()

    if not SAMPLE_PDF.exists():
        pytest.skip(f"sample document missing at {SAMPLE_PDF}")

    async with build_client(settings) as client:
        response = await client.post(
            EXECUTE_URL,
            json={
                "agent": "knowledge",
                "operation": "ingest_document",
                "payload": {"file_path": str(SAMPLE_PDF)},
            },
        )

    assert response.status_code == 200, response.text
    data = response.json()["data"]["data"]

    assert set(data) == {"indexed", "chunk_count"}
    assert data["indexed"] is True
    assert data["chunk_count"] > 0


@knowledge_required
async def test_real_ingest_then_query_returns_citations() -> None:
    """Ingesting then querying yields a grounded answer.

    Exercises the full round trip the frontend depends on: upload, index, ask.
    """
    require_knowledge_deps()
    settings = env_settings()

    if not SAMPLE_PDF.exists():
        pytest.skip(f"sample document missing at {SAMPLE_PDF}")

    async with build_client(settings) as client:
        ingest = await client.post(
            EXECUTE_URL,
            json={
                "agent": "knowledge",
                "operation": "ingest_document",
                "payload": {"file_path": str(SAMPLE_PDF)},
            },
        )
        assert ingest.status_code == 200, ingest.text

        query = await client.post(
            EXECUTE_URL,
            json={
                "agent": "knowledge",
                "operation": "query",
                "payload": {"question": "Summarise the key points."},
            },
        )

    assert query.status_code == 200, query.text
    data: dict[str, Any] = query.json()["data"]["data"]

    assert data["sources"]


@automation_required
async def test_automation_agent_drafts_a_real_invitation() -> None:
    """A real instruction returns a parsed meeting and a drafted body."""
    require_automation_deps()
    settings = env_settings()

    async with build_client(settings) as client:
        catalog = await client.get("/api/v1/agents")
        agents = {a["name"]: a for a in catalog.json()["data"]["agents"]}

        assert agents["automation"]["available"] is True, (
            "Automation agent did not connect. Check that the agent "
            "dependencies are installed and Ollama is serving the model."
        )

        response = await client.post(
            EXECUTE_URL,
            json={
                "agent": "automation",
                "operation": "draft_action",
                "payload": {
                    "instruction": (
                        "Schedule a sprint planning on 5 March at 10 AM "
                        "in Conference Room A and invite Navneet Verma"
                    )
                },
            },
        )

    assert response.status_code == 200, response.text
    data = response.json()["data"]["data"]

    assert set(data) == {"meeting", "recipients", "email", "directory", "employee_count"}

    meeting = data["meeting"]
    assert meeting["title"] == "Sprint Planning"
    assert meeting["attendees"] == ["Navneet Verma"]

    assert data["directory"]["source"] == "default"
    assert data["directory"]["directory_id"] is None

    assert data["email"].strip()
    assert "sent" not in data


@automation_required
async def test_automation_agent_rejects_a_blank_instruction() -> None:
    """Validation still runs in front of a real agent.

    A 422 here confirms the adapter validates before reaching the model, so a
    malformed request costs nothing and never touches Ollama.
    """
    require_automation_deps()
    settings = env_settings()

    async with build_client(settings) as client:
        response = await client.post(
            EXECUTE_URL,
            json={"agent": "automation", "operation": "draft_action", "payload": {}},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.skipif(
    not (KNOWLEDGE_ENABLED or AUTOMATION_ENABLED),
    reason="No agent enabled; set KNOWLEDGE_AGENT_ENABLED or AUTOMATION_AGENT_ENABLED.",
)
async def test_enabled_agent_that_cannot_connect_degrades_to_503() -> None:
    """An enabled but broken agent reports unavailable instead of crashing.

    Pointing Ollama at a dead port exercises the construction-failure path. The
    registry must still build and the catalog must still answer.
    """
    settings = Settings(
        ollama_base_url="http://127.0.0.1:9",
        knowledge_agent_enabled=True,
        automation_agent_enabled=True,
    )

    async with build_client(settings) as client:
        catalog = await client.get("/api/v1/agents")
        agents = {a["name"]: a for a in catalog.json()["data"]["agents"]}

        assert catalog.status_code == 200
        assert agents["knowledge"]["available"] is False

        response = await client.post(
            EXECUTE_URL,
            json={
                "agent": "knowledge",
                "operation": "query",
                "payload": {"question": "q"},
            },
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AGENT_UNAVAILABLE"
