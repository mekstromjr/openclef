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

try:
    from testcontainers.minio import MinioContainer
except Exception:  # pragma: no cover
    MinioContainer = None


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


@pytest.fixture(scope="session")
def minio_container():
    if MinioContainer is None:
        pytest.skip("testcontainers[minio] not importable")
    try:
        # Pin to a recent stable MinIO image; matches what we'd run in
        # the meklab homelab as a Garage-compat fallback.
        container = MinioContainer(image="minio/minio:RELEASE.2024-12-13T22-19-12Z")
        container.start()
    except Exception as exc:
        pytest.skip(f"Docker unavailable for MinIO testcontainer: {exc}")
    yield container
    container.stop()


@pytest.fixture(scope="session")
def minio_config(minio_container) -> dict:
    """Connection config for the MinIO testcontainer."""
    cfg = minio_container.get_config()
    # MinioContainer.get_config() returns
    # {"endpoint": "host:port", "access_key": "...", "secret_key": "..."}
    return {
        "endpoint_url": f"http://{cfg['endpoint']}",
        "access_key": cfg["access_key"],
        "secret_key": cfg["secret_key"],
        "region": "us-east-1",
        "path_style": True,
    }


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
async def app_kit(
    database_url: str, redis_url: str, apply_migrations, monkeypatch
):
    """FastAPI test kit: AsyncClient + a sessionmaker that commits.

    Use `kit.client` to drive the API and `kit.sessionmaker()` (async
    context manager) to seed/inspect data. Tests look like:

        async def test_x(app_kit):
            async with app_kit.sessionmaker() as s:
                await _seed_user(s, ...)
            r = await app_kit.client.post(...)

    Tables are TRUNCATEd on fixture entry so each test starts with a
    clean DB. Redis is FLUSHDBed too. Tests don't need to clean up.
    """
    monkeypatch.setenv("OPENCLEF_DATABASE_URL", database_url)
    monkeypatch.setenv("OPENCLEF_REDIS_URL", redis_url)
    monkeypatch.setenv("OPENCLEF_SECRET_KEY", "test-secret-do-not-use-in-prod")
    monkeypatch.setenv("OPENCLEF_PEPPER", "test-pepper")
    monkeypatch.setenv("OPENCLEF_ARGON2_TIME_COST", "1")
    monkeypatch.setenv("OPENCLEF_ARGON2_MEMORY_COST", "8192")
    monkeypatch.setenv("OPENCLEF_ARGON2_PARALLELISM", "1")
    monkeypatch.setenv("OPENCLEF_ENV", "dev")

    from dataclasses import dataclass

    from httpx import ASGITransport, AsyncClient
    from redis.asyncio import Redis
    from sqlalchemy import text as sa_text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from openclef import main as app_main
    from openclef.auth.deps import get_redis
    from openclef.db import get_session

    test_engine = create_async_engine(database_url, future=True)
    TestSession = async_sessionmaker(test_engine, expire_on_commit=False)
    test_redis = Redis.from_url(redis_url, decode_responses=False)

    # Per-test cleanup: TRUNCATE all domain tables (preserves alembic_version).
    domain_tables = [
        "annotation_revisions",
        "annotations",
        "arrangement_tags",
        "enrichment_jobs",
        "setlist_items",
        "setlists",
        "parts",
        "tags",
        "arrangements",
        "user_settings",
        "users",
    ]
    async with test_engine.begin() as conn:
        await conn.execute(sa_text(f"TRUNCATE {', '.join(domain_tables)} CASCADE"))
    await test_redis.flushdb()

    async def _override_session():
        async with TestSession() as s:
            yield s

    async def _override_redis():
        return test_redis

    app_main.app.dependency_overrides[get_session] = _override_session
    app_main.app.dependency_overrides[get_redis] = _override_redis
    app_main.app.state.redis = test_redis

    @dataclass
    class AppKit:
        client: AsyncClient
        sessionmaker: async_sessionmaker

    transport = ASGITransport(app=app_main.app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield AppKit(client=client, sessionmaker=TestSession)
    finally:
        app_main.app.dependency_overrides.clear()
        await test_redis.aclose()
        await test_engine.dispose()


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
