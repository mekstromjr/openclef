"""Pluggable storage backends.

`build_storage()` is the factory the lifespan uses — picks the
backend from settings, optionally wraps it in the thumbnail FS LRU
cache (for s3 only — the wrap doesn't help for local since the local
filesystem IS the cache).

S3Storage and ThumbnailCachedStorage land in subsequent commits of
ticket 0137.
"""
from __future__ import annotations

from openclef.config import get_settings
from openclef.storage._protocol import (
    KeyNotFoundError,
    Storage,
    StorageError,
    StorageMeta,
)
from openclef.storage.local import LocalStorage


def build_storage() -> Storage:
    s = get_settings()
    if s.storage_backend == "local":
        return LocalStorage(root=s.data_dir)
    raise StorageError(
        f"storage backend {s.storage_backend!r} not yet implemented (lands in next commit of ticket 0137)"
    )


__all__ = [
    "KeyNotFoundError",
    "LocalStorage",
    "Storage",
    "StorageError",
    "StorageMeta",
    "build_storage",
]
