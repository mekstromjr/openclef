"""Round-trip tests for openclef.storage.local.LocalStorage.

Uses pytest's tmp_path — no container needed. Verifies the streaming
put/get path, atomic rename behavior (no .tmp residue on success),
key-escape rejection, and idempotent delete.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from openclef.storage import LocalStorage
from openclef.storage._protocol import KeyNotFoundError, StorageError


async def _stream(payload: bytes, chunk: int = 17) -> AsyncIterator[bytes]:
    for i in range(0, len(payload), chunk):
        yield payload[i : i + chunk]


@pytest.fixture
def storage(tmp_path) -> LocalStorage:
    return LocalStorage(root=tmp_path / "data")


async def test_put_then_get_round_trip(storage):
    payload = b"%PDF-1.7\nfake content " + b"x" * 1000
    meta = await storage.put("scores/abc/def.pdf", _stream(payload))
    assert meta.key == "scores/abc/def.pdf"
    assert meta.size_bytes == len(payload)

    chunks = [c async for c in await storage.get("scores/abc/def.pdf")]
    assert b"".join(chunks) == payload


async def test_put_atomic_no_tmp_residue(storage, tmp_path):
    await storage.put("a/b/c", _stream(b"hello"))
    files = list((tmp_path / "data" / "a" / "b").iterdir())
    assert [f.name for f in files] == ["c"]


async def test_get_missing_raises(storage):
    with pytest.raises(KeyNotFoundError):
        await storage.get("does/not/exist")


async def test_head_returns_size(storage):
    await storage.put("foo", _stream(b"abcdef"))
    meta = await storage.head("foo")
    assert meta.size_bytes == 6


async def test_head_missing_raises(storage):
    with pytest.raises(KeyNotFoundError):
        await storage.head("nope")


async def test_exists_true_after_put(storage):
    await storage.put("foo", _stream(b"x"))
    assert await storage.exists("foo") is True
    assert await storage.exists("bar") is False


async def test_delete_idempotent(storage):
    await storage.put("foo", _stream(b"x"))
    await storage.delete("foo")
    assert await storage.exists("foo") is False
    # Second delete is a no-op, doesn't raise
    await storage.delete("foo")
    await storage.delete("never-existed")


async def test_overwrite_replaces_atomically(storage):
    await storage.put("foo", _stream(b"first"))
    await storage.put("foo", _stream(b"second"))
    chunks = [c async for c in await storage.get("foo")]
    assert b"".join(chunks) == b"second"


async def test_rejects_absolute_key(storage):
    with pytest.raises(StorageError):
        await storage.put("/etc/passwd", _stream(b"x"))


async def test_rejects_dotdot_escape(storage):
    with pytest.raises(StorageError):
        await storage.put("a/../../../etc/passwd", _stream(b"x"))


async def test_ping_true_when_writable(storage):
    assert await storage.ping() is True


async def test_streaming_handles_large_payload(storage):
    # 5 MB to exercise the chunking loop end-to-end without being huge
    payload = (b"abcdefgh" * 1024) * 640
    assert len(payload) == 5 * 1024 * 1024
    await storage.put("big", _stream(payload, chunk=8192))
    received = b"".join([c async for c in await storage.get("big")])
    assert received == payload
