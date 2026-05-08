import os
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from openclef.config import get_settings
from openclef.db import engine

log = structlog.get_logger()
settings = get_settings()

STATIC_DIR = Path(os.environ.get("OPENCLEF_STATIC_DIR", "/app/static"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("openclef.startup", version=settings.version, env=settings.env)
    yield
    await engine.dispose()
    log.info("openclef.shutdown")


app = FastAPI(
    title="OpenClef",
    version=settings.version,
    lifespan=lifespan,
)


async def _check_db() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        log.warning("openclef.health.db_failed", error=str(exc))
        return False


def _check_storage() -> bool:
    if settings.storage_backend == "local":
        return os.access(settings.data_dir, os.W_OK) if settings.data_dir.exists() else False
    # S3 reachability lands in ticket 0137 — for now report ok if configured.
    return True


@app.get("/health")
async def health() -> dict:
    db_ok = await _check_db()
    storage_ok = _check_storage()
    if not (db_ok and storage_ok):
        raise HTTPException(
            status_code=503,
            detail={
                "status": "degraded",
                "db": "connected" if db_ok else "down",
                "storage": "ok" if storage_ok else "unreachable",
            },
        )
    return {"status": "ok", "db": "connected", "storage": "ok"}


@app.get("/api/v1/version")
async def version() -> dict:
    return {"version": settings.version, "name": settings.app_name}


# --- SPA static serving (TRD §8.3) ---
# Frontend build is copied into STATIC_DIR by the Dockerfile. In local dev the
# directory may not exist yet; mount only when present so the API still boots.
if STATIC_DIR.exists():
    app.mount(
        "/_app",
        StaticFiles(directory=STATIC_DIR / "_app"),
        name="sveltekit-assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        # Serve real files when they exist; fall back to index.html for client routes.
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
