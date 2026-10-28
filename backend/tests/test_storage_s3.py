"""Integration tests for openclef.storage.s3.S3Storage against a real
S3 server.

The s3_container fixture (in conftest.py) spins up RustFS on first use
(or uses the CI service). The session-scoped container is shared across tests
in this module; per-test bucket creation gives isolation.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import aioboto3
import pytest
import pytest_asyncio

from openclef.storage import S3Storage
from openclef.storage._protocol import KeyNotFoundError


async def _stream(payload: bytes, chunk: int = 4096) -> AsyncIterator[bytes]:
    for i in range(0, len(payload), chunk):
        yield payload[i : i + chunk]


@pytest_asyncio.fixture
async def s3(s3_config) -> S3Storage:
    bucket = f"openclef-test-{uuid.uuid4().hex[:8]}"
    # Create the bucket via aioboto3 directly (out-of-band setup).
    session = aioboto3.Session()
    async with session.client(
        "s3",
        endpoint_url=s3_config["endpoint_url"],
        region_name=s3_config["region"],
        aws_access_key_id=s3_config["access_key"],
        aws_secret_access_key=s3_config["secret_key"],
    ) as client:
        await client.create_bucket(Bucket=bucket)
    return S3Storage(bucket=bucket, **s3_config)


async def test_put_then_get_round_trip(s3):
    payload = b"%PDF-1.7\nhello world " + b"x" * 1000
    meta = await s3.put("scores/abc/def.pdf", _stream(payload))
    assert meta.size_bytes == len(payload)

    chunks = [c async for c in await s3.get("scores/abc/def.pdf")]
    assert b"".join(chunks) == payload


async def test_head_returns_size(s3):
    await s3.put("foo", _stream(b"abcdef"))
    meta = await s3.head("foo")
    assert meta.size_bytes == 6


async def test_head_missing_raises(s3):
    with pytest.raises(KeyNotFoundError):
        await s3.head("nope")


async def test_get_missing_raises(s3):
    with pytest.raises(KeyNotFoundError):
        chunks = []
        async for c in await s3.get("does/not/exist"):
            chunks.append(c)


async def test_exists_true_after_put(s3):
    await s3.put("foo", _stream(b"x"))
    assert await s3.exists("foo") is True
    assert await s3.exists("bar") is False


async def test_delete_then_exists_false(s3):
    await s3.put("foo", _stream(b"x"))
    await s3.delete("foo")
    assert await s3.exists("foo") is False


async def test_delete_missing_is_idempotent(s3):
    # S3 returns 200 on delete-of-nonexistent-key; no exception
    await s3.delete("never-existed")


async def test_overwrite_replaces(s3):
    await s3.put("foo", _stream(b"first"))
    await s3.put("foo", _stream(b"second"))
    chunks = [c async for c in await s3.get("foo")]
    assert b"".join(chunks) == b"second"


async def test_ping_true_for_existing_bucket(s3):
    assert await s3.ping() is True


async def test_ping_false_for_missing_bucket(s3_config):
    bad = S3Storage(bucket="this-bucket-does-not-exist", **s3_config)
    assert await bad.ping() is False
