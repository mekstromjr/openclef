"""Filesystem-backed storage.

Writes go through a sibling .tmp file then atomic rename, so a crash
mid-upload leaves either the previous file (if it existed) or nothing
— never a partial. Atomic rename requires temp + final on the same
filesystem; LocalStorage rejects keys that would escape `root`.

Reads stream in 64 KiB chunks (configurable) so a 100 MB PDF doesn't
materialize in memory.
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import aiofiles

from openclef.storage._protocol import KeyNotFoundError, StorageError, StorageMeta


_CHUNK_SIZE = 64 * 1024


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        # Reject absolute keys and any path that resolves outside root.
        if key.startswith("/") or ".." in key.split("/"):
            raise StorageError(f"invalid storage key: {key!r}")
        path = (self._root / key).resolve()
        if not str(path).startswith(str(self._root) + os.sep) and path != self._root:
            raise StorageError(f"invalid storage key (escapes root): {key!r}")
        return path

    async def put(self, key: str, body: AsyncIterator[bytes]) -> StorageMeta:
        final = self._resolve(key)
        final.parent.mkdir(parents=True, exist_ok=True)
        tmp = final.with_suffix(final.suffix + ".tmp")
        size = 0
        async with aiofiles.open(tmp, "wb") as f:
            async for chunk in body:
                size += len(chunk)
                await f.write(chunk)
        # Atomic rename: tmp → final. Same filesystem required.
        await asyncio.to_thread(os.replace, tmp, final)
        return StorageMeta(key=key, size_bytes=size)

    async def get(self, key: str) -> AsyncIterator[bytes]:
        path = self._resolve(key)
        if not path.is_file():
            raise KeyNotFoundError(key)
        return self._stream(path)

    async def _stream(self, path: Path) -> AsyncIterator[bytes]:
        async with aiofiles.open(path, "rb") as f:
            while True:
                chunk = await f.read(_CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk

    async def delete(self, key: str) -> None:
        path = self._resolve(key)
        try:
            await asyncio.to_thread(path.unlink)
        except FileNotFoundError:
            pass  # delete is idempotent

    async def head(self, key: str) -> StorageMeta:
        path = self._resolve(key)
        if not path.is_file():
            raise KeyNotFoundError(key)
        return StorageMeta(key=key, size_bytes=path.stat().st_size)

    async def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    async def ping(self) -> bool:
        try:
            return os.access(self._root, os.W_OK)
        except OSError:
            return False
