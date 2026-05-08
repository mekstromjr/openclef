"""Shared test infrastructure: real Postgres via testcontainers,
schema migrated once per session, per-test transaction rollback for
isolation.

The container is session-scoped; the async engine is per-test
(function-scoped) so fixture and test share the same event loop —
pytest-asyncio rejects mixing function-scoped tests with
session-scoped async fixtures with a "Future attached to a different
loop" error.

Skipped automatically (with a clear marker) when Docker isn't
reachable, so simple unit tests still run on machines without Docker.
"""
from __future__ import annotations

import os
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path


def _ensure_docker_host() -> None:
    """Discover the active Docker context's socket if DOCKER_HOST is unset.

    Colima, Rancher, and Lima all park their socket somewhere other
    than `/var/run/docker.sock`. The Python `docker` client (used by
    testcontainers) only checks the default location unless
    DOCKER_HOST is set, so without this patch tests skip on any
    non-Docker-Desktop Mac with the misleading "Docker unavailable"
    error.
    """
    if os.environ.get("DOCKER_HOST"):
        return
    try:
        result = subprocess.run(
            ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return
    endpoint = result.stdout.strip()
    if endpoint:
        os.environ["DOCKER_HOST"] = endpoint


_ensure_docker_host()

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

try:
    from testcontainers.postgres import PostgresContainer
    from testcontainers.redis import RedisContainer
except Exception:  # pragma: no cover - import error path
    PostgresContainer = None
    RedisContainer = None


_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


@pytest.fixture(scope="session")
def postgres_container():
    if PostgresContainer is None:
        pytest.skip("testcontainers not importable")
    try:
        container = PostgresContainer("postgres:16.6-alpine", driver="asyncpg")
        container.start()
    except Exception as exc:
        pytest.skip(f"Docker unavailable for testcontainers: {exc}")
    yield container
    container.stop()


@pytest.fixture(scope="session")
def database_url(postgres_container) -> str:
    """Async URL (postgresql+asyncpg://...) usable by the test engine."""
    return postgres_container.get_connection_url()


@pytest.fixture(scope="session")
def sync_database_url(database_url: str) -> str:
    """Sync URL (postgresql://...) for Alembic, which doesn't speak asyncpg."""
    return database_url.replace("+asyncpg", "")


@pytest.fixture(scope="session")
def apply_migrations(postgres_container, sync_database_url: str):
    """Run alembic upgrade head once per test session against the
    container's database. Sync; consumes the same DB the async engine
    later reaches via asyncpg.
    """
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", sync_database_url)
    command.upgrade(cfg, "head")
    return True


@pytest.fixture(scope="session")
def redis_container():
    if RedisContainer is None:
        pytest.skip("testcontainers[redis] not importable")
    try:
        container = RedisContainer("redis:7.4-alpine")
        container.start()
    except Exception as exc:
        pytest.skip(f"Docker unavailable for Redis testcontainer: {exc}")
    yield container
    container.stop()


@pytest.fixture(scope="session")
def redis_url(redis_container) -> str:
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"


@pytest_asyncio.fixture
async def redis_client(redis_url: str):
    """Per-test Redis client with FLUSHDB on entry so buckets and
    revocation sets don't leak between tests."""
    from redis.asyncio import Redis

    client = Redis.from_url(redis_url, decode_responses=False)
    await client.flushdb()
    try:
        yield client
    finally:
        await client.aclose()


@pytest_asyncio.fixture
async def session(database_url: str, apply_migrations) -> AsyncIterator[AsyncSession]:
    """Per-test async session with transaction-rollback isolation.

    The engine is created per-test (rather than session-scoped) so the
    fixture lives in the same event loop as the test body — required
    by pytest-asyncio's per-function loop policy.
    """
    engine = create_async_engine(database_url, future=True)
    try:
        async with engine.connect() as connection:
            outer = await connection.begin()
            SessionFactory = async_sessionmaker(
                bind=connection, expire_on_commit=False, class_=AsyncSession
            )
            async with SessionFactory() as sess:
                try:
                    yield sess
                finally:
                    await sess.close()
            await outer.rollback()
    finally:
        await engine.dispose()
