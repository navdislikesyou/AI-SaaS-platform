"""Shared pytest fixtures.

Builds the application against fake agents so no real agent code, GPU, or
network access is required.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.registry import AgentRegistry
from app.api import deps
from app.api.deps import get_orchestrator, get_registry, get_settings_dep
from app.core.config import Settings, get_settings
from app.main import create_app
from app.services.orchestrator import Orchestrator
from tests.fakes import EchoAgent, ExplodingAgent, UnavailableAgent

_TEST_ENVIRONMENT = "test"


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    """Clear the settings cache around each test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    """Return settings pinned to test values.

    Returns:
        Settings configured for testing.
    """
    return Settings(
        app_name="AI SaaS Platform API",
        app_version="0.1.0-test",
        environment=_TEST_ENVIRONMENT,
        debug=False,
        api_v1_prefix="/api/v1",
        cors_origins=["http://testserver"],
        log_level="WARNING",
    )


@pytest.fixture
def registry() -> AgentRegistry:
    """Return a registry populated with fake agents.

    Returns:
        A registry holding an available echo agent, an unavailable agent, and
        a failing agent.
    """
    registry = AgentRegistry()
    registry.register(EchoAgent(name="knowledge", capabilities=["query", "ingest_document"]))
    registry.register(UnavailableAgent(name="automation"))
    registry.register(ExplodingAgent(name="performance"))
    return registry


@pytest.fixture
def app(settings: Settings, registry: AgentRegistry) -> Iterator[object]:
    """Return an app wired to the fake-agent registry.

    Shared services are injected through FastAPI dependency overrides instead
    of the lifespan, so the same fixtures work regardless of lifespan state.

    Args:
        settings: Test settings.
        registry: Fake-agent registry.

    Yields:
        The FastAPI application under test.
    """
    deps.reset_state()
    application = create_app(settings)
    application.dependency_overrides[get_settings_dep] = lambda: settings
    application.dependency_overrides[get_registry] = lambda: registry
    application.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)
    yield application
    application.dependency_overrides.clear()
    deps.reset_state()


@pytest.fixture
async def client(app: object) -> AsyncIterator[AsyncClient]:
    """Return an HTTP client bound to the application.

    Args:
        app: The application under test.

    Yields:
        An AsyncClient over ASGI transport; no live server is started.
    """
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client
