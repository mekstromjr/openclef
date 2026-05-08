"""Smoke tests for /health and /api/v1/version.

These tests stub the DB and storage checks rather than requiring a live
Postgres. The Compose stack covers the integrated path; this layer just
confirms the FastAPI wiring.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from openclef import main


@pytest.fixture
def client(monkeypatch):
    async def _ok_db():
        return True

    monkeypatch.setattr(main, "_check_db", _ok_db)
    monkeypatch.setattr(main, "_check_storage", lambda: True)
    transport = ASGITransport(app=main.app)
    return AsyncClient(transport=transport, base_url="http://test")


async def test_health_ok(client):
    async with client as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": "connected", "storage": "ok"}


async def test_health_db_down(monkeypatch):
    async def _bad_db():
        return False

    monkeypatch.setattr(main, "_check_db", _bad_db)
    monkeypatch.setattr(main, "_check_storage", lambda: True)
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/health")
    assert r.status_code == 503
    assert r.json()["detail"]["db"] == "down"


async def test_version(client):
    async with client as c:
        r = await c.get("/api/v1/version")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "openclef"
    assert "version" in body
