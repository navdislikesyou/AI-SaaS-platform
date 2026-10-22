"""Alembic environment configuration for the AI SaaS Platform.

Binds the migration ``target_metadata`` to the SQLAlchemy ``Base``
defined in ``app.models`` and resolves the database URL from the
application ``Settings`` so that ``alembic upgrade head`` works
both offline and online without hardcoding connection strings.

The migration runs through the same asynchronous driver as the application:
``aiosqlite`` for SQLite and ``asyncpg`` for PostgreSQL. A synchronous engine
would need a second driver for the same database (``psycopg2``), which is not
a dependency of the project, so the environment uses the asynchronous engine
instead.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import model Base and target_metadata so Alembic can
# detect changes and generate migrations automatically.
from app.models import Base  # type: ignore[import-not-found]

target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Support reading the database URL from the application Settings
# so that ``alembic upgrade head`` uses the same URL the FastAPI
# app uses at runtime.
# ---------------------------------------------------------------------------

from app.core.config import Settings, get_settings  # type: ignore[import-not-found]
from app.core.database import to_async_url  # type: ignore[import-not-found]


def _load_settings() -> Settings:  # type: ignore[valid-type]
    """Load application settings, favouring the process-wide cache."""
    return get_settings()


def get_database_url() -> str:
    """Return the ``DATABASE_URL`` from application Settings.

    The URL is returned in its asynchronous form, because the engine below is
    an asynchronous one. Falls back to the ``sqlalchemy.url`` value in
    ``alembic.ini`` when the Settings instance does not supply one (e.g.
    during early boot or test fixtures that override ``get_settings``).
    """
    try:
        return to_async_url(_load_settings().database_url)
    except Exception:
        fallback = config.get_main_option("sqlalchemy.url") or "sqlite:///./app.db"
        return to_async_url(fallback)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to ``context.execute()`` here emit the given string to
    the script output.

    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    An asynchronous engine is created and the migrations are run through it,
    so the migration and the application talk to the database with the same
    driver.
    """
    url = get_database_url()
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async def _run() -> None:
        """Open a connection and run the migrations through it."""
        async with connectable.connect() as connection:
            await connection.run_sync(_run_sync)

    def _run_sync(connection) -> None:
        """Configure the context and run the migrations.

        Args:
            connection: The synchronous connection behind the async one.
        """
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Entry point
#
# Alembic calls this module and then waits for it to run the migrations.
# Without this block the connection is opened, the context is configured, and
# the command exits successfully without applying anything, which is why
# ``alembic upgrade head`` used to report success on an empty database.
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
