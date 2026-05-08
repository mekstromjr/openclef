"""Auth endpoints: /api/v1/auth/login, /logout, /me.

Login does the rate-limit check first against the *attempted* username
(even nonexistent ones — leaks no info about which usernames are real
because the timing path is identical). On success, mints a session
cookie, clears the user's rate-limit bucket, and may transparently
rotate the password hash if Argon2 cost params drifted.

Logout is idempotent — logging out twice or with no cookie returns 204
both times. Revokes the session_id in Redis and clears the cookie.

`/me` is a thin echo of `current_user` — the SPA hits this on every
page load to confirm the cookie is still valid.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openclef.auth.deps import get_current_user, get_redis
from openclef.auth.hashing import hash_password, needs_rehash, verify_password
from openclef.auth.ratelimit import check_and_consume, reset
from openclef.auth.sessions import (
    SESSION_COOKIE_NAME,
    issue_session,
    parse_session,
    revoke,
)
from openclef.config import get_settings
from openclef.db import get_session
from openclef.models.user import User
from openclef.schemas import UserRead


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    model_config = {"extra": "forbid"}
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1)


def _set_session_cookie(response: Response, cookie_value: str) -> None:
    s = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=cookie_value,
        max_age=s.session_max_age_days * 24 * 60 * 60,
        httponly=True,
        secure=(s.env != "dev"),
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=UserRead)
async def login(
    body: LoginRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
):
    rate = await check_and_consume(redis, "login", body.username.lower())
    if not rate.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "retry_after_seconds": rate.retry_after_seconds,
            },
            headers={"Retry-After": str(rate.retry_after_seconds)},
        )

    user = (
        await db.execute(select(User).where(User.username == body.username))
    ).scalar_one_or_none()

    # Same response shape for "no such user" and "wrong password" so
    # we don't leak which usernames are real.
    if (
        user is None
        or not user.password_hash
        or not verify_password(body.password, user.password_hash)
    ):
        raise HTTPException(status_code=401, detail="invalid_credentials")

    # Rotate hash if Argon2 cost params drifted since last login.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
        await db.flush()

    # Clear the bucket so a successful login doesn't carry over earlier
    # failures into the next session.
    await reset(redis, "login", body.username.lower())

    cookie_value, _ = issue_session(user.id)
    _set_session_cookie(response, cookie_value)
    await db.commit()
    return user


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    redis: Annotated[Redis, Depends(get_redis)],
    session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
):
    # Idempotent — logging out twice or with no cookie is fine.
    if session_cookie:
        payload = parse_session(session_cookie)
        if payload is not None:
            await revoke(redis, payload.session_id)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return Response(status_code=204)


@router.get("/me", response_model=UserRead)
async def me(user: Annotated[User, Depends(get_current_user)]):
    return user
