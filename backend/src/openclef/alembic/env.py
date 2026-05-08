"""Alembic environment.

The Phase 1 baseline migration is intentionally empty — it just establishes
the `alembic_version` table so subsequent tickets (starting with 0135) can
add real schema on top of a known revision.
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from openclef.config import get_settings
from openclef.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Prefer an explicit URL set on the Config (tests pass theirs via
# `alembic_cfg.set_main_option("sqlalchemy.url", url)`); fall back to
# app settings (env-driven) for the prod entrypoint path.
_explicit_url = config.get_main_option("sqlalchemy.url")
if not _explicit_url:
    config.set_main_option("sqlalchemy.url", get_settings().database_url)

# Importing the models package attaches every ORM table to Base.metadata
# so autogenerate (and the runtime check in tests that `Base.metadata`
# matches the live schema) sees the full picture.
import openclef.models  # noqa: F401, E402

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_sync_migrations() -> None:
    from sqlalchemy import engine_from_config

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        do_run_migrations(connection)
    connectable.dispose()


def run_migrations_online() -> None:
    # Tests pass a sync (psycopg2) URL; the prod entrypoint passes an
    # asyncpg URL. Pick the path based on the dialect rather than
    # forcing one or the other.
    url = config.get_main_option("sqlalchemy.url") or ""
    if "+asyncpg" in url or "+aiopg" in url:
        asyncio.run(run_async_migrations())
    else:
        run_sync_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
