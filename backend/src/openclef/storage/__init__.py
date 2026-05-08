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
from openclef.storage.s3 import S3Storage


def build_storage() -> Storage:
    s = get_settings()
    if s.storage_backend == "local":
        return LocalStorage(root=s.data_dir)
    if s.storage_backend == "s3":
        missing = [
            name
            for name, val in {
                "OPENCLEF_S3_BUCKET": s.s3_bucket,
                "OPENCLEF_S3_ACCESS_KEY": s.s3_access_key,
                "OPENCLEF_S3_SECRET_KEY": s.s3_secret_key,
            }.items()
            if not val
        ]
        if missing:
            raise StorageError(
                f"storage_backend=s3 requires these env vars: {', '.join(missing)}"
            )
        return S3Storage(
            bucket=s.s3_bucket,
            endpoint_url=s.s3_endpoint,
            region=s.s3_region,
            access_key=s.s3_access_key,
            secret_key=s.s3_secret_key,
            path_style=s.s3_path_style,
        )
    raise StorageError(f"unknown storage backend: {s.storage_backend!r}")


__all__ = [
    "KeyNotFoundError",
    "LocalStorage",
    "S3Storage",
    "Storage",
    "StorageError",
    "StorageMeta",
    "build_storage",
]
