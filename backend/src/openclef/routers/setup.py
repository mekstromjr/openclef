"""First-run setup endpoint.

`/api/v1/setup` is the only mutation endpoint that doesn't require
authentication — it creates the *first* admin and is gated by
`count(users) == 0`. Once the first user exists, this endpoint always
returns 409 Conflict.

A Postgres advisory lock guards the count + insert against the
hypothetical race where two operators POST /setup at the same instant.
The lock is per-database, lightweight, and releases at end of
transaction.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from openclef.auth.deps import get_redis
from openclef.auth.hashing import hash_password
from openclef.auth.sessions import SESSION_COOKIE_NAME, issue_session
from openclef.config import get_settings
from openclef.db import get_session
from openclef.models.enums import UserRole
from openclef.models.user import User
from openclef.schemas import UserRead


router = APIRouter(prefix="/api/v1", tags=["setup"])


# Arbitrary 64-bit constant used as the advisory-lock key for /setup.
# Don't change after launch — a different value would let a concurrent
# /setup slip through during a deploy that mixes versions.
_SETUP_ADVISORY_LOCK = 7244717854310105459


class SetupRequest(BaseModel):
    model_config = {"extra": "forbid"}
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8)
    email: str | None = None


@router.get("/setup/status")
async def setup_status(db: Annotated[AsyncSession, Depends(get_session)]):
    """Anonymous probe used by the SPA to decide whether to render the
    setup wizard or the login page. Returns `{users_exist: bool}` —
    intentionally minimal."""
    count = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    return {"users_exist": count > 0}


@router.post("/setup", response_model=UserRead, status_code=201)
async def setup(
    body: SetupRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
):
    # Advisory lock + count check + insert, all in one transaction.
    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _SETUP_ADVISORY_LOCK})
    count = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    if count > 0:
        raise HTTPException(status_code=409, detail="setup_already_complete")

    admin = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        role=UserRole.ADMIN,
    )
    db.add(admin)
    await db.flush()

    # Sign the operator straight in — no point making them log in
    # immediately after they typed the password.
    s = get_settings()
    cookie_value, _ = issue_session(admin.id)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=cookie_value,
        max_age=s.session_max_age_days * 24 * 60 * 60,
        httponly=True,
        secure=(s.env != "dev"),
        samesite="lax",
        path="/",
    )
    await db.commit()
    return admin
