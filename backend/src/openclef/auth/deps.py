"""FastAPI dependencies for the auth subsystem.

`get_redis` yields a Redis connection from the app-state pool created
in main.py's lifespan. `get_current_user` reads the session cookie,
verifies the signature + revocation, loads the user. `require_admin`
is a thin wrapper that 403s non-admins.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openclef.auth.sessions import (
    SESSION_COOKIE_NAME,
    is_revoked,
    parse_session,
)
from openclef.db import get_session
from openclef.models.enums import UserRole
from openclef.models.user import User


async def get_redis(request: Request) -> Redis:
    """Yield the app-scoped Redis client. Raises 503 if the pool is
    unset (lifespan didn't run, or Redis was unreachable at startup)."""
    redis: Redis | None = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="redis_unavailable",
        )
    return redis


async def get_current_user(
    session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> User:
    """Resolve the current user from the session cookie. 401 on any failure."""
    if not session_cookie:
        raise HTTPException(status_code=401, detail="not_authenticated")
    payload = parse_session(session_cookie)
    if payload is None:
        raise HTTPException(status_code=401, detail="invalid_session")
    if await is_revoked(redis, payload.session_id):
        raise HTTPException(status_code=401, detail="session_revoked")
    user = (
        await db.execute(select(User).where(User.id == payload.user_id))
    ).scalar_one_or_none()
    if user is None:
        # User was deleted while session was live; treat as auth failure.
        raise HTTPException(status_code=401, detail="user_not_found")
    return user


async def get_optional_current_user(
    session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> User | None:
    """Like get_current_user but returns None instead of 401 — used by
    routes that behave differently for authenticated vs anonymous
    callers (e.g., the setup wizard's "is anyone here yet?" probe)."""
    if not session_cookie:
        return None
    payload = parse_session(session_cookie)
    if payload is None:
        return None
    if await is_revoked(redis, payload.session_id):
        return None
    return (
        await db.execute(select(User).where(User.id == payload.user_id))
    ).scalar_one_or_none()


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="admin_required")
    return user
