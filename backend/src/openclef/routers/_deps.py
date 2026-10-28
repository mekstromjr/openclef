"""Small FastAPI dependencies shared by the library routers."""
from __future__ import annotations

from fastapi import HTTPException, Request

from openclef.storage import Storage


def get_storage(request: Request) -> Storage:
    storage: Storage | None = getattr(request.app.state, "storage", None)
    if storage is None:
        raise HTTPException(status_code=503, detail="storage_unavailable")
    return storage
