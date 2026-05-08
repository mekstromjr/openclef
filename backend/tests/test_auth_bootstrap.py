"""Tests for openclef.auth.bootstrap."""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from openclef.auth.bootstrap import maybe_bootstrap_admin
from openclef.models.enums import UserRole
from openclef.models.user import User


@pytest.fixture(autouse=True)
def auth_env(monkeypatch):
    monkeypatch.setenv("OPENCLEF_PEPPER", "test-pepper")
    monkeypatch.setenv("OPENCLEF_ARGON2_TIME_COST", "1")
    monkeypatch.setenv("OPENCLEF_ARGON2_MEMORY_COST", "8192")
    monkeypatch.setenv("OPENCLEF_ARGON2_PARALLELISM", "1")
    monkeypatch.setenv("OPENCLEF_ENV", "dev")


@pytest.fixture
async def empty_engine(database_url, apply_migrations):
    """Engine pointed at an empty users table — uses TRUNCATE rather
    than per-test migration to keep it cheap."""
    from sqlalchemy import text

    eng = create_async_engine(database_url, future=True)
    async with eng.begin() as conn:
        await conn.execute(text("TRUNCATE users CASCADE"))
    yield eng
    await eng.dispose()


async def test_bootstrap_creates_admin_when_env_set(empty_engine, monkeypatch):
    monkeypatch.setenv("OPENCLEF_ADMIN_USER", "operator")
    monkeypatch.setenv("OPENCLEF_ADMIN_PASSWORD", "hunter2hunter2")
    user = await maybe_bootstrap_admin(empty_engine)
    assert user is not None
    assert user.username == "operator"
    assert user.role == UserRole.ADMIN

    SessionFactory = async_sessionmaker(empty_engine, expire_on_commit=False)
    async with SessionFactory() as s:
        rows = (await s.execute(select(User))).scalars().all()
    assert len(rows) == 1


async def test_bootstrap_no_op_when_users_exist(empty_engine, monkeypatch):
    monkeypatch.setenv("OPENCLEF_ADMIN_USER", "operator")
    monkeypatch.setenv("OPENCLEF_ADMIN_PASSWORD", "hunter2hunter2")
    # Seed an existing user (any role)
    SessionFactory = async_sessionmaker(empty_engine, expire_on_commit=False)
    async with SessionFactory() as s:
        s.add(User(username="prior", password_hash=None, role=UserRole.USER))
        await s.commit()

    user = await maybe_bootstrap_admin(empty_engine)
    assert user is None

    async with SessionFactory() as s:
        rows = (await s.execute(select(User))).scalars().all()
    assert len(rows) == 1
    assert rows[0].username == "prior"


async def test_bootstrap_no_op_when_neither_env_set(empty_engine, monkeypatch):
    monkeypatch.delenv("OPENCLEF_ADMIN_USER", raising=False)
    monkeypatch.delenv("OPENCLEF_ADMIN_PASSWORD", raising=False)
    assert (await maybe_bootstrap_admin(empty_engine)) is None


async def test_bootstrap_warns_on_partial_config(empty_engine, monkeypatch, caplog):
    monkeypatch.setenv("OPENCLEF_ADMIN_USER", "operator")
    monkeypatch.delenv("OPENCLEF_ADMIN_PASSWORD", raising=False)
    user = await maybe_bootstrap_admin(empty_engine)
    assert user is None
