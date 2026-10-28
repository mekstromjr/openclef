"""Filesystem LRU cache wrapper for thumbnails.

Wraps any upstream `Storage`. For keys matching the thumbnail prefix,
serves from a local on-disk cache; for everything else, passes
through unchanged. Only meaningful when the upstream is remote (S3) —
when the upstream is the local filesystem, the wrap is a no-op.

Bookkeeping lives in a small SQLite index at
`{cache_dir}/index.db` — one row per cached entry holding key,
size, last_accessed. SQLite gives us atomic LRU eviction without
the in-memory state sync hassles of a JSON-based index. WAL mode
keeps reads non-blocking.

Eviction triggers on put when total size > cap; oldest-access-first.
Delete is best-effort (cache miss is fine).
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import sqlite3
import time
from collections.abc import AsyncIterator
from pathlib import Path

import aiofiles

from openclef.storage._protocol import Storage, StorageMeta


THUMBNAIL_PREFIX = "thumbnails/"
_CHUNK_SIZE = 64 * 1024


def _key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _cache_path(root: Path, key: str) -> Path:
    h = _key_hash(key)
    return root / h[:2] / h[2:]


class ThumbnailCachedStorage:
    def __init__(
        self,
        upstream: Storage,
        cache_dir: Path,
        max_size_bytes: int,
    ) -> None:
        self._upstream = upstream
        self._cache_dir = cache_dir.resolve()
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._max = max_size_bytes
        self._index_path = self._cache_dir / "index.db"
        self._init_index()

    # --- index -----------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._index_path, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_index(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS entries ("
                "  key_hash TEXT PRIMARY KEY,"
                "  size_bytes INTEGER NOT NULL,"
                "  last_accessed REAL NOT NULL"
                ")"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_last_accessed ON entries(last_accessed)"
            )

    def _index_record(self, key_hash: str, size: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO entries(key_hash, size_bytes, last_accessed) VALUES (?, ?, ?) "
                "ON CONFLICT(key_hash) DO UPDATE SET size_bytes=excluded.size_bytes, "
                "last_accessed=excluded.last_accessed",
                (key_hash, size, time.time()),
            )

    def _index_touch(self, key_hash: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE entries SET last_accessed=? WHERE key_hash=?",
                (time.time(), key_hash),
            )

    def _index_remove(self, key_hash: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM entries WHERE key_hash=?", (key_hash,))

    def _index_total(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COALESCE(SUM(size_bytes), 0) FROM entries").fetchone()
            return int(row[0])

    def _index_evict_oldest(self) -> tuple[str, int] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT key_hash, size_bytes FROM entries ORDER BY last_accessed ASC LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            conn.execute("DELETE FROM entries WHERE key_hash=?", (row[0],))
            return row[0], int(row[1])

    # --- Storage protocol ------------------------------------------

    async def put(self, key: str, body: AsyncIterator[bytes]) -> StorageMeta:
        # Pass through to upstream first; cache evict any old version.
        meta = await self._upstream.put(key, body)
        if key.startswith(THUMBNAIL_PREFIX):
            await asyncio.to_thread(self._evict_one, key)
        return meta

    async def get(self, key: str) -> AsyncIterator[bytes]:
        if not key.startswith(THUMBNAIL_PREFIX):
            return await self._upstream.get(key)
        return self._cached_get(key)

    async def _cached_get(self, key: str) -> AsyncIterator[bytes]:
        path = _cache_path(self._cache_dir, key)
        if path.is_file():
            await asyncio.to_thread(self._index_touch, _key_hash(key))
            async for chunk in self._stream_file(path):
                yield chunk
            return

        # Miss — fetch from upstream, tee into cache, yield to caller.
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        size = 0
        async with aiofiles.open(tmp, "wb") as f:
            async for chunk in await self._upstream.get(key):
                size += len(chunk)
                await f.write(chunk)
                yield chunk
        await asyncio.to_thread(os.replace, tmp, path)
        await asyncio.to_thread(self._index_record, _key_hash(key), size)
        await asyncio.to_thread(self._enforce_cap)

    async def _stream_file(self, path: Path) -> AsyncIterator[bytes]:
        async with aiofiles.open(path, "rb") as f:
            while True:
                chunk = await f.read(_CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk

    async def delete(self, key: str) -> None:
        await self._upstream.delete(key)
        if key.startswith(THUMBNAIL_PREFIX):
            await asyncio.to_thread(self._evict_one, key)

    async def head(self, key: str) -> StorageMeta:
        return await self._upstream.head(key)

    async def exists(self, key: str) -> bool:
        return await self._upstream.exists(key)

    async def ping(self) -> bool:
        return await self._upstream.ping()

    # --- eviction --------------------------------------------------

    def _evict_one(self, key: str) -> None:
        path = _cache_path(self._cache_dir, key)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        self._index_remove(_key_hash(key))

    def _enforce_cap(self) -> None:
        while self._index_total() > self._max:
            evicted = self._index_evict_oldest()
            if evicted is None:
                return
            key_hash, _ = evicted
            path = self._cache_dir / key_hash[:2] / key_hash[2:]
            try:
                path.unlink()
            except FileNotFoundError:
                pass
