"""S3-compatible storage backend (AWS, Garage, MinIO, B2, R2).

Phase 1 reads the entire upload into memory before put_object. Sheet-
music PDFs are typically 2–10 MB so the memory cost is acceptable;
the streaming-multipart path will land in a follow-up if/when it
matters for performance.

aioboto3 sessions are heavy to construct but cheap to reuse — we
hold one Session for the life of the Storage instance and create a
short-lived client per call (the recommended aioboto3 pattern).
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import aioboto3
from botocore.config import Config
from botocore.exceptions import ClientError

from openclef.storage._protocol import KeyNotFoundError, StorageError, StorageMeta


class S3Storage:
    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None,
        region: str,
        access_key: str,
        secret_key: str,
        path_style: bool = False,
    ) -> None:
        self._bucket = bucket
        self._endpoint = endpoint_url or None
        self._region = region
        self._access_key = access_key
        self._secret_key = secret_key
        self._client_config = Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if path_style else "auto"},
        )
        self._session = aioboto3.Session()

    def _client(self):
        return self._session.client(
            "s3",
            endpoint_url=self._endpoint,
            region_name=self._region,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            config=self._client_config,
        )

    async def put(self, key: str, body: AsyncIterator[bytes]) -> StorageMeta:
        # Buffer the upload — see module docstring for the rationale.
        chunks: list[bytes] = []
        size = 0
        async for chunk in body:
            chunks.append(chunk)
            size += len(chunk)
        payload = b"".join(chunks)
        async with self._client() as client:
            await client.put_object(Bucket=self._bucket, Key=key, Body=payload)
        return StorageMeta(key=key, size_bytes=size)

    async def get(self, key: str) -> AsyncIterator[bytes]:
        # The aioboto3 client + body must stay open for the duration of
        # the iterator, so the generator owns the context lifetime.
        return self._stream(key)

    async def _stream(self, key: str) -> AsyncIterator[bytes]:
        async with self._client() as client:
            try:
                resp = await client.get_object(Bucket=self._bucket, Key=key)
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code")
                if code in {"NoSuchKey", "404"}:
                    raise KeyNotFoundError(key) from exc
                raise StorageError(str(exc)) from exc
            body = resp["Body"]
            async for chunk in body.iter_chunks():
                yield chunk

    async def delete(self, key: str) -> None:
        # S3 delete is idempotent already (200 even when key didn't exist).
        async with self._client() as client:
            await client.delete_object(Bucket=self._bucket, Key=key)

    async def head(self, key: str) -> StorageMeta:
        async with self._client() as client:
            try:
                resp = await client.head_object(Bucket=self._bucket, Key=key)
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code")
                if code in {"NoSuchKey", "404", "NoSuchBucket"}:
                    raise KeyNotFoundError(key) from exc
                raise StorageError(str(exc)) from exc
        return StorageMeta(key=key, size_bytes=int(resp["ContentLength"]))

    async def exists(self, key: str) -> bool:
        try:
            await self.head(key)
            return True
        except KeyNotFoundError:
            return False

    async def ping(self) -> bool:
        try:
            async with self._client() as client:
                await client.head_bucket(Bucket=self._bucket)
            return True
        except Exception:
            return False
