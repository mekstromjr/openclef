"""Unit tests for openclef.storage.cache.ThumbnailCachedStorage.

Uses a counting in-memory upstream so we can verify cache hits don't
trigger an upstream get. No container needed.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from openclef.storage import ThumbnailCachedStorage
from openclef.storage._protocol import KeyNotFoundError, StorageMeta


class CountingMemoryStorage:
    """Tiny in-memory Storage that records get/put counts for assertions."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}
        self.gets = 0
        self.puts = 0
        self.deletes = 0

    async def put(self, key: str, body: AsyncIterator[bytes]) -> StorageMeta:
        self.puts += 1
        chunks: list[bytes] = []
        async for c in body:
            chunks.append(c)
        payload = b"".join(chunks)
        self._objects[key] = payload
        return StorageMeta(key=key, size_bytes=len(payload))

    async def get(self, key: str) -> AsyncIterator[bytes]:
        self.gets += 1
        if key not in self._objects:
            raise KeyNotFoundError(key)

        async def _stream() -> AsyncIterator[bytes]:
            yield self._objects[key]

        return _stream()

    async def delete(self, key: str) -> None:
        self.deletes += 1
        self._objects.pop(key, None)

    async def head(self, key: str) -> StorageMeta:
        if key not in self._objects:
            raise KeyNotFoundError(key)
        return StorageMeta(key=key, size_bytes=len(self._objects[key]))

    async def exists(self, key: str) -> bool:
        return key in self._objects

    async def ping(self) -> bool:
        return True


async def _stream(payload: bytes) -> AsyncIterator[bytes]:
    yield payload


@pytest.fixture
def upstream() -> CountingMemoryStorage:
    return CountingMemoryStorage()


@pytest.fixture
def cache(tmp_path, upstream) -> ThumbnailCachedStorage:
    return ThumbnailCachedStorage(
        upstream=upstream, cache_dir=tmp_path / "cache", max_size_bytes=10_000
    )


# --- Pass-through (non-thumbnail keys) -------------------------------


async def test_non_thumbnail_keys_pass_through(cache, upstream):
    await cache.put("scores/abc/def.pdf", _stream(b"pdfbytes"))
    chunks = [c async for c in await cache.get("scores/abc/def.pdf")]
    assert b"".join(chunks) == b"pdfbytes"
    # Two gets through upstream (both pass-through), no cache involvement
    assert upstream.gets == 1


# --- Thumbnail caching ----------------------------------------------


async def test_thumbnail_first_get_hits_upstream(cache, upstream):
    await cache.put("thumbnails/abc.png", _stream(b"thumbpayload"))
    assert upstream.puts == 1

    chunks = [c async for c in await cache.get("thumbnails/abc.png")]
    assert b"".join(chunks) == b"thumbpayload"
    assert upstream.gets == 1


async def test_thumbnail_subsequent_gets_serve_from_cache(cache, upstream):
    await cache.put("thumbnails/abc.png", _stream(b"thumbpayload"))

    # First get hits upstream and warms the cache
    chunks = [c async for c in await cache.get("thumbnails/abc.png")]
    assert b"".join(chunks) == b"thumbpayload"
    assert upstream.gets == 1

    # Subsequent 49 gets stay at upstream.gets == 1
    for _ in range(49):
        chunks = [c async for c in await cache.get("thumbnails/abc.png")]
        assert b"".join(chunks) == b"thumbpayload"
    assert upstream.gets == 1, "subsequent thumbnail gets must serve from cache"


async def test_delete_evicts_cache(cache, upstream):
    await cache.put("thumbnails/abc.png", _stream(b"v1"))
    [_ async for _ in await cache.get("thumbnails/abc.png")]  # warm cache
    assert upstream.gets == 1

    await cache.delete("thumbnails/abc.png")
    # Re-fetch should hit upstream again — but upstream now has it deleted too
    with pytest.raises(KeyNotFoundError):
        [_ async for _ in await cache.get("thumbnails/abc.png")]


async def test_put_evicts_old_cached_version(cache, upstream):
    # Warm the cache with v1
    await cache.put("thumbnails/abc.png", _stream(b"v1"))
    [_ async for _ in await cache.get("thumbnails/abc.png")]  # cache it
    assert upstream.gets == 1

    # Overwrite via put — cache must drop the old entry
    await cache.put("thumbnails/abc.png", _stream(b"v2"))

    chunks = [c async for c in await cache.get("thumbnails/abc.png")]
    assert b"".join(chunks) == b"v2"
    # Second upstream get because cache was evicted on put
    assert upstream.gets == 2


# --- LRU eviction ----------------------------------------------------


async def test_evicts_oldest_when_over_cap(tmp_path, upstream):
    # Cap = 30 bytes; each thumbnail is 10 bytes; only 3 can fit
    cache = ThumbnailCachedStorage(
        upstream=upstream, cache_dir=tmp_path / "cache", max_size_bytes=30
    )

    for i in range(4):
        key = f"thumbnails/{i}.png"
        await cache.put(key, _stream(b"x" * 10))
        # Warm the cache so each entry is recorded
        [_ async for _ in await cache.get(key)]

    # 4 thumbnails warmed, cap = 30 bytes; the oldest (thumbnails/0)
    # should have been evicted from the on-disk cache.
    pre_get_count = upstream.gets
    [_ async for _ in await cache.get("thumbnails/0.png")]
    # The evicted entry now requires an upstream fetch
    assert upstream.gets == pre_get_count + 1


async def test_pass_through_methods(cache, upstream):
    await cache.put("scores/foo.pdf", _stream(b"x"))
    assert await cache.exists("scores/foo.pdf") is True
    assert (await cache.head("scores/foo.pdf")).size_bytes == 1
    assert await cache.ping() is True
