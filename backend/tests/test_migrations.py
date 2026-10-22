"""Tests for the Alembic migration history.

These run the real Alembic environment against a temporary SQLite database,
so a migration that creates nothing, or an environment that never dispatches,
fails here rather than in a deployment.

The temporary database is the only database these tests touch. The local
development database is never opened.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    """Return the Alembic configuration for the backend.

    Returns:
        A configuration pointing at the backend's ``alembic.ini``.
    """
    return Config(str(BACKEND_DIR / "alembic.ini"))


@pytest.fixture
def migrated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Return the URL of a temporary database migrated to head.

    Args:
        tmp_path: The per-test temporary directory.
        monkeypatch: Fixture used to point the settings at the temporary file.

    Returns:
        The database URL of the migrated database.
    """
    url = f"sqlite:///{tmp_path / 'migrated.db'}"

    # The environment reads the URL from the application settings, so the
    # variable has to be set before the settings are resolved.
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()

    command.upgrade(_alembic_config(), "head")

    return url


def test_the_revision_chain_has_a_single_head() -> None:
    """The history has exactly one head, so ``upgrade head`` is unambiguous."""
    script = ScriptDirectory.from_config(_alembic_config())

    assert len(script.get_heads()) == 1


def test_upgrade_head_creates_the_schema(migrated_database: str) -> None:
    """Migrating an empty database creates the three tables the models use."""
    engine = create_engine(migrated_database)

    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert {"organizations", "users", "refresh_tokens"} <= tables


def test_the_migrated_schema_matches_the_models(migrated_database: str) -> None:
    """The migrated schema is the schema the models declare.

    ``alembic check`` compares the database against the model metadata and
    reports any operation the migration would still have to perform.
    """
    command.check(_alembic_config())


def test_upgrade_head_is_safe_on_a_database_that_already_has_the_tables(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A database built by ``create_all`` can still be migrated.

    The tables are created only when they are absent, so an operator who
    bootstrapped a database before the migrations existed is not stuck.
    """
    from app.models import Base

    url = f"sqlite:///{tmp_path / 'created.db'}"

    engine = create_engine(url)
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()

    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()

    command.upgrade(_alembic_config(), "head")

    verify = create_engine(url)
    try:
        assert "organizations" in inspect(verify).get_table_names()
    finally:
        verify.dispose()


def test_a_postgresql_url_is_migrated_with_the_asyncpg_driver() -> None:
    """A PostgreSQL URL is given the driver the project declares.

    The migration environment uses an asynchronous engine, so a PostgreSQL
    URL has to name ``asyncpg``. A synchronous engine would need
    ``psycopg2``, which is not a dependency of the project.
    """
    from app.core.database import to_async_url

    assert (
        to_async_url("postgresql://user:pass@host:5432/db")
        == "postgresql+asyncpg://user:pass@host:5432/db"
    )
    assert (
        to_async_url("postgres://user:pass@host:5432/db")
        == "postgresql+asyncpg://user:pass@host:5432/db"
    )
    # A URL that already names a driver is left alone.
    assert (
        to_async_url("postgresql+asyncpg://user:pass@host:5432/db")
        == "postgresql+asyncpg://user:pass@host:5432/db"
    )


def test_the_asyncpg_driver_is_installed_and_resolvable() -> None:
    """The PostgreSQL driver the migration needs is present.

    The engine is created without connecting, so this proves the driver is
    installed and the URL resolves, without needing a database server.
    """
    import asyncpg  # noqa: F401
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("postgresql+asyncpg://user:pass@host:5432/db")

    assert engine.dialect.driver == "asyncpg"
