"""Storage interface shared by all backends.

Methods take/return `AsyncIterator[bytes]` for streaming bodies. The
caller is responsible for choosing the key (we treat it as opaque
text); current convention from the upload router (ticket 0138):

  PDFs       → "scores/{arrangement_id}/{part_id}.pdf"
  Thumbnails → "thumbnails/{part_id}.png"

`StorageMeta` is the small descriptor returned by `head()` and `put()`.
We keep it minimal — anything more elaborate (etags, content-types) is
backend-specific and would leak abstraction.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class StorageMeta:
    key: str
    size_bytes: int


class StorageError(RuntimeError):
    """Generic storage failure. Backends translate library errors here."""


class KeyNotFoundError(StorageError):
    """Requested key doesn't exist."""


@runtime_checkable
class Storage(Protocol):
    async def put(self, key: str, body: AsyncIterator[bytes]) -> StorageMeta:
        ...

    async def get(self, key: str) -> AsyncIterator[bytes]:
        ...

    async def delete(self, key: str) -> None:
        ...

    async def head(self, key: str) -> StorageMeta:
        ...

    async def exists(self, key: str) -> bool:
        ...

    async def ping(self) -> bool:
        """Backend reachability check used by /health. Swallows
        exceptions; returns False on any failure."""
        ...
