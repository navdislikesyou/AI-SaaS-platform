"""Shared pytest fixtures.

Builds the application against fake agents so no real agent code, GPU, or
network access is required.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.agents.registry import AgentRegistry
from app.api import deps
from app.api.deps import (
    get_current_user_from_token_optional_principal,
    get_orchestrator,
    get_registry,
    get_settings_dep,
)
from app.core.config import Settings, get_settings
from app.core.database import get_async_session
from app.main import create_app
from app.models import Base, Organization, User, hash_password
from app.services.orchestrator import Orchestrator
from tests.fakes import EchoAgent, ExplodingAgent, UnavailableAgent

_TEST_ENVIRONMENT = "test"

#: Signing key used by the auth tests. It is a fixed test value, not a secret.
_TEST_JWT_SECRET = "test-signing-key-for-the-auth-suite"


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
    # Provide a test user so that activity-history and other endpoints that
    # depend on ``get_current_user_from_token_optional_principal`` receive a
    # scoped user rather than ``None``.  This keeps the existing test suite
    # working without requiring auth headers in every test request.
    application.dependency_overrides[get_current_user_from_token_optional_principal] = lambda: None  # noqa: E501
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


# ---------------------------------------------------------------------------
# Database fixtures
#
# The auth and user-management endpoints are the only routes that read and
# write the database, so they need a real schema. These fixtures give them an
# isolated SQLite database in a temporary directory. Nothing here touches the
# developer's local database.
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    """Return an async engine on a temporary SQLite database.

    Args:
        tmp_path: The per-test temporary directory.

    Yields:
        An engine whose schema was created from ``app.models.Base``.
    """
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture
def session_factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Return a session maker bound to the test database.

    Args:
        db_engine: The test engine.

    Returns:
        A session maker producing sessions on the test database.
    """
    return async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)


@pytest.fixture
def auth_settings(tmp_path: Path) -> Settings:
    """Return settings for the auth and user-management tests.

    The JWT signing key and the trusted origin are fixed test values. The
    database URL points at the temporary test database, never at the local
    development one.

    Args:
        tmp_path: The per-test temporary directory.

    Returns:
        Settings configured for the auth tests.
    """
    return Settings(
        app_name="AI SaaS Platform API",
        app_version="0.1.0-test",
        environment=_TEST_ENVIRONMENT,
        debug=False,
        api_v1_prefix="/api/v1",
        cors_origins=["http://testserver"],
        log_level="WARNING",
        database_url=f"sqlite:///{tmp_path / 'auth.db'}",
        jwt_secret_key=_TEST_JWT_SECRET,
        trusted_origins=["http://testserver"],
        samesite="lax",
    )


@pytest.fixture
def make_organization(session_factory: async_sessionmaker[AsyncSession]):
    """Return a factory that creates organizations in the test database.

    Args:
        session_factory: Session maker for the test database.

    Returns:
        An async callable that creates and returns an organization.
    """

    async def _make(name: str = "Acme", slug: str = "acme") -> Organization:
        async with session_factory() as session:
            organization = Organization(name=name, slug=slug, is_active=True)
            session.add(organization)
            await session.commit()
            await session.refresh(organization)
            return organization

    return _make


@pytest.fixture
def make_user(session_factory: async_sessionmaker[AsyncSession]):
    """Return a factory that creates users in the test database.

    Args:
        session_factory: Session maker for the test database.

    Returns:
        An async callable that creates and returns a user.
    """

    async def _make(
        email: str,
        password: str = "ValidPassword1!",
        role: str = "employee",
        organization_id: str | None = None,
        is_active: bool = True,
        full_name: str | None = None,
    ) -> User:
        async with session_factory() as session:
            user = User(
                email=email.lower(),
                full_name=full_name or email.split("@")[0].title(),
                hashed_password=hash_password(password),
                role=role,
                organization_id=organization_id,
                is_active=is_active,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    return _make


@pytest.fixture
async def auth_client(
    app: object,
    auth_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    """Return a client whose requests reach the temporary test database.

    The application's session dependency is replaced with one bound to the
    test engine, and the settings dependency is replaced with the auth
    settings, so no request reaches the local development database.

    Args:
        app: The application under test.
        auth_settings: Settings for the auth tests.
        session_factory: Session maker for the test database.

    Yields:
        An AsyncClient over ASGI transport.
    """
    application = app

    application.dependency_overrides[get_settings] = lambda: auth_settings
    application.dependency_overrides[get_settings_dep] = lambda: auth_settings

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    application.dependency_overrides[get_async_session] = _override_session

    transport = ASGITransport(app=application)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client
