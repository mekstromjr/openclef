import os
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis
from sqlalchemy import text

from openclef.auth.bootstrap import maybe_bootstrap_admin
from openclef.config import get_settings
from openclef.db import engine
from openclef.routers import arrangements as arrangements_router
from openclef.routers import auth as auth_router
from openclef.routers import parts as parts_router
from openclef.routers import setup as setup_router
from openclef.routers import users as users_router
from openclef.storage import build_storage

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
    # Storage backend (LocalStorage or ThumbnailCachedStorage(S3Storage))
    # is built once per process; methods are stateless across calls.
    app.state.storage = build_storage()
    # First-run env-var bootstrap: if OPENCLEF_ADMIN_{USER,PASSWORD} are
    # set AND no users exist, create the admin silently. No-op otherwise.
    try:
        await maybe_bootstrap_admin(engine)
    except Exception as exc:
        log.error("openclef.bootstrap.failed", error=str(exc))
        # Don't crash startup on bootstrap failure — operator can still
        # use the /setup wizard.
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
    # `/docs` is the in-app user-facing documentation subtree served by
    # the SvelteKit frontend (ticket 0153). Move FastAPI's Swagger / ReDoc
    # / OpenAPI under `/api/` alongside the rest of the backend so the
    # two don't collide. Anyone hitting `localhost:8000/docs` now gets
    # the brand guide + user docs; the API surface lives at /api/docs.
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)


class UploadSizeLimit:
    """Refuse oversized uploads from Content-Length, before FastAPI parses
    (and spools to disk) the multipart body. The upload handlers re-check
    the real byte count, which also covers bodies sent without a length."""

    # Multipart framing and the small form fields ride on top of the file.
    OVERHEAD_BYTES = 1024 * 1024

    def __init__(self, app, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes + self.OVERHEAD_BYTES

    async def __call__(self, scope, receive, send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] == "POST"
            and scope["path"].startswith("/api/v1/arrangements")
        ):
            length = dict(scope["headers"]).get(b"content-length", b"")
            if length.isdigit() and int(length) > self.max_bytes:
                response = JSONResponse({"detail": "upload_too_large"}, status_code=413)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


app.add_middleware(UploadSizeLimit, max_bytes=settings.max_upload_mb * 1024 * 1024)

app.include_router(auth_router.router)
app.include_router(setup_router.router)
app.include_router(users_router.router)
app.include_router(arrangements_router.router)
app.include_router(parts_router.router)


async def _check_db() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        log.warning("openclef.health.db_failed", error=str(exc))
        return False


async def _check_storage() -> bool:
    storage = getattr(app.state, "storage", None)
    if storage is None:
        return False
    try:
        return await storage.ping()
    except Exception as exc:
        log.warning("openclef.health.storage_failed", error=str(exc))
        return False


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
    storage_ok = await _check_storage()
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
