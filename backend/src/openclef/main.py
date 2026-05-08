import os
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis
from sqlalchemy import text

from openclef.config import get_settings
from openclef.db import engine
from openclef.routers import auth as auth_router
from openclef.routers import setup as setup_router

log = structlog.get_logger()
settings = get_settings()

STATIC_DIR = Path(os.environ.get("OPENCLEF_STATIC_DIR", "/app/static"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("openclef.startup", version=settings.version, env=settings.env)
    # Redis pool used by auth (revocation set) and rate-limit. One
    # client per app process is fine; redis-py multiplexes commands
    # over a connection pool internally.
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=False)
    try:
        yield
    finally:
        await app.state.redis.aclose()
        await engine.dispose()
        log.info("openclef.shutdown")


app = FastAPI(
    title="OpenClef",
    version=settings.version,
    lifespan=lifespan,
)

app.include_router(auth_router.router)
app.include_router(setup_router.router)


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


async def _check_redis() -> bool:
    try:
        client: Redis | None = getattr(app.state, "redis", None)
        if client is None:
            return False
        return await client.ping()
    except Exception as exc:
        log.warning("openclef.health.redis_failed", error=str(exc))
        return False


@app.get("/health")
async def health() -> dict:
    db_ok = await _check_db()
    storage_ok = _check_storage()
    redis_ok = await _check_redis()
    if not (db_ok and storage_ok and redis_ok):
        raise HTTPException(
            status_code=503,
            detail={
                "status": "degraded",
                "db": "connected" if db_ok else "down",
                "storage": "ok" if storage_ok else "unreachable",
                "redis": "connected" if redis_ok else "down",
            },
        )
    return {"status": "ok", "db": "connected", "storage": "ok", "redis": "connected"}


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
