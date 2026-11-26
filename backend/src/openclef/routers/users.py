"""User management endpoints.

`/users/*` is admin-only (except the /me/settings subroute, which is
self-service for the authenticated user). Deleting an account hands
what other people can see to new owners and deletes the rest
(services.account_deletion, openclef#65).

`__deleted__` is a reserved name: older versions repointed a deleted
account's pieces to a placeholder user of that name, and installs may
still have one. It is hidden from admin views and can't be shared with.
"""
from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from openclef.auth.deps import get_current_user, require_admin
from openclef.auth.hashing import hash_password
from openclef.config import get_settings
from openclef.db import get_session
from openclef.models.user import User, UserSettings
from openclef.routers._deps import get_storage
from openclef.schemas import (
    DeletionCounts,
    DeletionPiece,
    DeletionPlan,
    DeletionSetlist,
    DeletionSetlistRef,
    DeletionGroup,
    Person,
    UserDeletion,
    UserCreate,
    UserRead,
    UserSettingsRead,
    UserSettingsUpdate,
    UserUpdate,
)
from openclef.services.account_deletion import DeletionError, build_plan, delete_account
from openclef.storage import Storage

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1/users", tags=["users"])


# Reserved: older versions gave a deleted account's pieces to a placeholder
# user of this name.
TOMBSTONE_USERNAME = "__deleted__"


# --- Admin CRUD --------------------------------------------------------


@router.get("", response_model=list[UserRead])
async def list_users(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
):
    rows = (await db.execute(select(User).order_by(User.username))).scalars().all()
    return [
        u for u in rows if u.username != TOMBSTONE_USERNAME
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
    if body.username == TOMBSTONE_USERNAME:
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
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid_user_id")

    user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if user is None or user.username == TOMBSTONE_USERNAME:
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


async def _deletable(db: AsyncSession, user_id: str, admin: User) -> User:
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid_user_id") from None
    if uid == admin.id:
        # An admin who deletes themselves leaves the system without an
        # admin if they're the last one. Belt-and-suspenders: refuse.
        raise HTTPException(status_code=409, detail="cannot_delete_self")
    user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if user is None or user.username == TOMBSTONE_USERNAME:
        raise HTTPException(status_code=404, detail="user_not_found")
    if user.username == get_settings().admin_user:
        # The bootstrap account is how an operator gets back in.
        raise HTTPException(status_code=409, detail="cannot_delete_break_glass")
    return user


@router.get("/{user_id}/deletion-plan", response_model=DeletionPlan)
async def get_deletion_plan(
    user_id: str,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
):
    """What deleting this account keeps, for whom, and what it deletes."""
    user = await _deletable(db, user_id, admin)
    plan = await build_plan(db, user, admin)

    def person(pid: uuid.UUID) -> Person:
        return Person(id=pid, username=plan.names.get(pid, ""))

    return DeletionPlan(
        user=Person(id=user.id, username=user.username),
        partners=[person(pid) for pid in plan.partners],
        arrangements=[
            DeletionPiece(
                id=p.id,
                title=p.title,
                seen_by=p.seen_by,
                suggested_owner=person(p.default_owner),
                setlists=[
                    DeletionSetlistRef(
                        id=s.id,
                        name=s.name,
                        owner=None if s.owner_id == user.id else person(s.owner_id),
                        holders=sorted(s.holders),
                    )
                    for s in p.setlists
                ],
            )
            for p in plan.pieces
        ],
        setlists=[
            DeletionSetlist(id=s.id, name=s.name, seen_by=s.seen_by, suggested_owner=person(s.default_owner))
            for s in plan.setlists
        ],
        groups=[
            DeletionGroup(
                id=g.id,
                name=g.name,
                members=[person(m) for m in g.members],
                suggested_owner=person(g.default_owner),
            )
            for g in plan.groups
        ],
        deleted=DeletionCounts(
            arrangements=len(plan.private_pieces),
            setlists=len(plan.private_setlists),
            groups=plan.private_groups,
        ),
    )


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[Storage, Depends(get_storage)],
    body: Annotated[UserDeletion | None, Body()] = None,
):
    """Delete an account (openclef#65). What someone else can see goes to
    the owner picked for it in the deletion plan, or its suggested owner;
    the rest is deleted, files included, after the commit."""
    user = await _deletable(db, user_id, admin)
    body = body or UserDeletion()
    try:
        keys = await delete_account(
            db,
            user,
            admin,
            tombstone_name=TOMBSTONE_USERNAME,
            arrangements=body.arrangements,
            setlists=body.setlists,
            groups=body.groups,
        )
        await db.commit()
    except DeletionError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except IntegrityError:
        # Something of theirs changed mid-delete (a piece added to a
        # setlist, a part uploaded). Nothing was deleted; try again.
        await db.rollback()
        raise HTTPException(status_code=409, detail="deletion_conflict") from None
    for key in keys:
        try:
            await storage.delete(key)
        except Exception as exc:  # an orphaned blob is harmless
            log.warning("openclef.storage.delete_failed", key=key, error=str(exc))
    return Response(status_code=204)


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
