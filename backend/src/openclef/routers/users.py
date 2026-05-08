"""User management endpoints.

`/users/*` is admin-only (except the /me/settings subroute, which is
self-service for the authenticated user). Delete is non-destructive
to the library: the deleted user's `arrangements.created_by` /
`parts.uploaded_by` rows are repointed to a singleton `__deleted__`
user before the original row is removed, so library content survives
operator turnover.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from openclef.auth.deps import get_current_user, require_admin
from openclef.auth.hashing import hash_password
from openclef.db import get_session
from openclef.models.enums import UserRole
from openclef.models.library import Arrangement, Part
from openclef.models.user import User, UserSettings
from openclef.schemas import (
    UserCreate,
    UserRead,
    UserSettingsRead,
    UserSettingsUpdate,
    UserUpdate,
)


router = APIRouter(prefix="/api/v1/users", tags=["users"])


# Singleton placeholder user that absorbs ownership of orphaned rows
# when a real user is deleted. Created on demand.
_TOMBSTONE_USERNAME = "__deleted__"


async def _get_or_create_tombstone(db: AsyncSession) -> User:
    existing = (
        await db.execute(select(User).where(User.username == _TOMBSTONE_USERNAME))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    tombstone = User(
        username=_TOMBSTONE_USERNAME,
        password_hash=None,
        role=UserRole.USER,
    )
    db.add(tombstone)
    await db.flush()
    return tombstone


# --- Admin CRUD --------------------------------------------------------


@router.get("", response_model=list[UserRead])
async def list_users(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
):
    rows = (await db.execute(select(User).order_by(User.username))).scalars().all()
    return [
        u for u in rows if u.username != _TOMBSTONE_USERNAME
    ]  # hide the tombstone from admin views


@router.post("", response_model=UserRead, status_code=201)
async def create_user(
    body: UserCreate,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
):
    # API clients send a plaintext password via the unused-by-other-routes
    # `password_hash` field; for symmetry with /setup we accept it,
    # then re-hash here so we never store unsalted secrets.
    if body.password_hash is None:
        raise HTTPException(status_code=422, detail="password_hash_required")
    if body.username == _TOMBSTONE_USERNAME:
        raise HTTPException(status_code=409, detail="reserved_username")

    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password_hash),
        oidc_sub=body.oidc_sub,
        role=body.role,
    )
    db.add(user)
    try:
        await db.flush()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=409, detail="username_taken")
    await db.commit()
    return user


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: str,
    body: UserUpdate,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
):
    import uuid

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid_user_id")

    user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if user is None or user.username == _TOMBSTONE_USERNAME:
        raise HTTPException(status_code=404, detail="user_not_found")

    if body.email is not None:
        user.email = body.email
    if body.role is not None:
        user.role = body.role
    await db.commit()
    # User.updated_at uses server-side onupdate=now(); refresh so the
    # response carries the new timestamp rather than triggering a lazy
    # load during serialization (which crashes outside the greenlet).
    await db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
):
    import uuid

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid_user_id")

    if uid == admin.id:
        # An admin who deletes themselves leaves the system without an
        # admin if they're the last one. Belt-and-suspenders: refuse.
        raise HTTPException(status_code=409, detail="cannot_delete_self")

    user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if user is None or user.username == _TOMBSTONE_USERNAME:
        raise HTTPException(status_code=404, detail="user_not_found")

    tombstone = await _get_or_create_tombstone(db)
    # Repoint every row that has a RESTRICT FK on this user.
    await db.execute(
        update(Arrangement).where(Arrangement.created_by == uid).values(created_by=tombstone.id)
    )
    await db.execute(
        update(Part).where(Part.uploaded_by == uid).values(uploaded_by=tombstone.id)
    )
    # CASCADE FKs (annotations, setlists, arrangement_tags.added_by via
    # CASCADE) clean themselves up on the DELETE below.
    await db.delete(user)
    await db.commit()
    return None


# --- /me/settings ------------------------------------------------------


async def _get_or_create_settings(db: AsyncSession, user: User) -> UserSettings:
    settings = (
        await db.execute(select(UserSettings).where(UserSettings.user_id == user.id))
    ).scalar_one_or_none()
    if settings is not None:
        return settings
    settings = UserSettings(user_id=user.id)
    db.add(settings)
    await db.flush()
    return settings


@router.get("/me/settings", response_model=UserSettingsRead)
async def get_my_settings(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
):
    return await _get_or_create_settings(db, user)


@router.patch("/me/settings", response_model=UserSettingsRead)
async def patch_my_settings(
    body: UserSettingsUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
):
    settings = await _get_or_create_settings(db, user)
    if body.theme is not None:
        settings.theme = body.theme
    if body.enrichment_default_enabled is not None:
        settings.enrichment_default_enabled = body.enrichment_default_enabled
    if body.enrichment_providers_jsonb is not None:
        settings.enrichment_providers_jsonb = body.enrichment_providers_jsonb
    if body.preferences_jsonb is not None:
        settings.preferences_jsonb = body.preferences_jsonb
    await db.commit()
    return settings
