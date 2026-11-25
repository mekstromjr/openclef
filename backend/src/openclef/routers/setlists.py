"""Setlists: an ordered running order of pieces for a rehearsal or service.

Who sees a setlist, and which of its pieces, is decided in
openclef.services.access. Only its owner or an admin can change it for now;
contributor permission comes with openclef#64. An entry whose piece the
viewer can't see comes back redacted (`available: false`).

Every change takes a row lock on the setlist (SELECT ... FOR UPDATE), so
concurrent saves and appends are serialized. Clients may send the
`updated_at` they loaded as `expected_updated_at`; a stale value gets 409
instead of silently overwriting an edit made in another tab or device.

Items are keyed by (setlist_id, position). Saving a new order replaces the
item rows in one transaction rather than renumbering them in place, which
would collide on the primary key mid-update.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from openclef.auth.deps import get_current_user
from openclef.db import get_session
from openclef.models.enums import UserRole
from openclef.models.library import Arrangement, Part
from openclef.models.setlist import Setlist, SetlistItem
from openclef.models.user import User
from openclef.schemas import (
    SETLIST_MAX_ITEMS,
    SetlistCreate,
    SetlistDetail,
    SetlistEntry,
    SetlistItemsReplace,
    SetlistItemWrite,
    SetlistSummary,
    SetlistUpdate,
)
from openclef.services.access import visible_arrangements, visible_setlists

router = APIRouter(prefix="/api/v1/setlists", tags=["setlists"])

CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[AsyncSession, Depends(get_session)]


def _can_edit(setlist: Setlist, user: User) -> bool:
    return setlist.owner_id == user.id or user.role == UserRole.ADMIN


async def _get(
    db: AsyncSession, setlist_id: uuid.UUID, user: User, *, for_update: bool = False
) -> Setlist:
    """The setlist, if `user` can see it (hidden is a 404, not a 403)."""
    query = select(Setlist).where(Setlist.id == setlist_id, visible_setlists(user))
    if for_update:
        query = query.with_for_update()
    setlist = (await db.execute(query)).scalar_one_or_none()
    if setlist is None:
        raise HTTPException(status_code=404, detail="setlist_not_found")
    return setlist


async def _get_for_change(
    db: AsyncSession, setlist_id: uuid.UUID, user: User, expected: datetime | None
) -> Setlist:
    setlist = await _get(db, setlist_id, user, for_update=True)
    if not _can_edit(setlist, user):
        raise HTTPException(status_code=403, detail="not_setlist_owner")
    if expected is not None and expected != setlist.updated_at:
        raise HTTPException(status_code=409, detail="setlist_changed")
    return setlist


async def _touch(db: AsyncSession, setlist: Setlist) -> None:
    """Stamp updated_at with the wall clock at write time. Not now(): that is
    the transaction's START, so a save that waited on the row lock would
    record a time older than the edit it waited for, and the stale-version
    check would stop working. Also bumps it when only the items changed."""
    setlist.updated_at = func.clock_timestamp()
    await db.flush()


async def _owner_names(db: AsyncSession, owner_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not owner_ids:
        return {}
    rows = await db.execute(select(User.id, User.username).where(User.id.in_(owner_ids)))
    return {user_id: username for user_id, username in rows}


async def _detail(db: AsyncSession, setlist: Setlist, user: User) -> SetlistDetail:
    items = (
        await db.execute(
            select(SetlistItem).where(SetlistItem.setlist_id == setlist.id).order_by(SetlistItem.position)
        )
    ).scalars().all()
    arrangement_ids = {item.arrangement_id for item in items}

    # Only the pieces this viewer may see; the rest come back redacted.
    arrangements: dict[uuid.UUID, Arrangement] = {}
    parts_by_arrangement: dict[uuid.UUID, list[Part]] = {}
    if arrangement_ids:
        for arrangement in (
            await db.execute(
                select(Arrangement).where(Arrangement.id.in_(arrangement_ids), visible_arrangements(user))
            )
        ).scalars():
            arrangements[arrangement.id] = arrangement
        for part in (
            await db.execute(
                select(Part)
                .where(Part.arrangement_id.in_(arrangements.keys()))
                .order_by(Part.created_at, Part.id)
            )
        ).scalars():
            parts_by_arrangement.setdefault(part.arrangement_id, []).append(part)

    entries = []
    for item in items:
        arrangement = arrangements.get(item.arrangement_id)
        if arrangement is None:
            entries.append(SetlistEntry(position=item.position, available=False))
            continue
        parts = parts_by_arrangement.get(item.arrangement_id, [])
        chosen = next((part for part in parts if part.id == item.part_id), None)
        # A chosen part that was deleted is SET NULL by the FK, so this only
        # falls back to the cover when no part was chosen.
        effective = chosen or (parts[0] if parts else None)
        entries.append(
            SetlistEntry(
                position=item.position,
                arrangement_id=arrangement.id,
                title=arrangement.title,
                subtitle=arrangement.subtitle,
                composer=arrangement.composer,
                part_id=item.part_id,
                effective_part_id=effective.id if effective else None,
                part_label=effective.label if effective else None,
                page_count=effective.page_count if effective else None,
                thumbnail_ready=bool(effective and effective.thumbnail_storage_key),
            )
        )

    owners = await _owner_names(db, {setlist.owner_id})
    return SetlistDetail(
        id=setlist.id,
        name=setlist.name,
        owner_id=setlist.owner_id,
        owner_username=owners.get(setlist.owner_id, ""),
        item_count=len(entries),
        created_at=setlist.created_at,
        updated_at=setlist.updated_at,
        can_edit=_can_edit(setlist, user),
        items=entries,
    )


async def _check_items(db: AsyncSession, items: list[SetlistItemWrite], user: User) -> None:
    """Every arrangement must exist and be visible to the person adding it
    (a hidden one is reported as not found), and every chosen part must
    belong to its arrangement."""
    arrangement_ids = {item.arrangement_id for item in items}
    if not arrangement_ids:
        return
    found = set(
        (
            await db.execute(
                select(Arrangement.id).where(Arrangement.id.in_(arrangement_ids), visible_arrangements(user))
            )
        ).scalars()
    )
    if found != arrangement_ids:
        raise HTTPException(status_code=422, detail="arrangement_not_found")
    part_ids = {item.part_id for item in items if item.part_id is not None}
    if part_ids:
        owner_of = dict(
            (await db.execute(select(Part.id, Part.arrangement_id).where(Part.id.in_(part_ids)))).all()
        )
        for item in items:
            if item.part_id is not None and owner_of.get(item.part_id) != item.arrangement_id:
                raise HTTPException(status_code=422, detail="part_not_in_arrangement")


async def _commit(db: AsyncSession) -> None:
    try:
        await db.commit()
    except IntegrityError:
        # An arrangement or part was deleted between the check and the write.
        await db.rollback()
        raise HTTPException(status_code=409, detail="arrangement_not_found") from None


async def _reload(db: AsyncSession, setlist_id: uuid.UUID, user: User) -> SetlistDetail:
    setlist = await _get(db, setlist_id, user)
    await db.refresh(setlist)
    return await _detail(db, setlist, user)


@router.get("", response_model=list[SetlistSummary])
async def list_setlists(user: CurrentUser, db: DbSession) -> list[SetlistSummary]:
    """The setlists `user` can see, most recently changed first."""
    counts = (
        select(SetlistItem.setlist_id, func.count().label("item_count"))
        .group_by(SetlistItem.setlist_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(Setlist, func.coalesce(counts.c.item_count, 0))
            .outerjoin(counts, counts.c.setlist_id == Setlist.id)
            .where(visible_setlists(user))
            .order_by(Setlist.updated_at.desc(), Setlist.id)
        )
    ).all()
    owners = await _owner_names(db, {setlist.owner_id for setlist, _ in rows})
    return [
        SetlistSummary(
            id=setlist.id,
            name=setlist.name,
            owner_id=setlist.owner_id,
            owner_username=owners.get(setlist.owner_id, ""),
            item_count=item_count,
            created_at=setlist.created_at,
            updated_at=setlist.updated_at,
            can_edit=_can_edit(setlist, user),
        )
        for setlist, item_count in rows
    ]


@router.post("", response_model=SetlistDetail, status_code=201)
async def create_setlist(payload: SetlistCreate, user: CurrentUser, db: DbSession) -> SetlistDetail:
    setlist = Setlist(name=payload.name.strip() or payload.name, owner_id=user.id)
    db.add(setlist)
    await db.commit()
    return await _reload(db, setlist.id, user)


@router.get("/{setlist_id}", response_model=SetlistDetail)
async def get_setlist(setlist_id: uuid.UUID, user: CurrentUser, db: DbSession) -> SetlistDetail:
    return await _detail(db, await _get(db, setlist_id, user), user)


@router.patch("/{setlist_id}", response_model=SetlistDetail)
async def rename_setlist(
    setlist_id: uuid.UUID, payload: SetlistUpdate, user: CurrentUser, db: DbSession
) -> SetlistDetail:
    setlist = await _get_for_change(db, setlist_id, user, payload.expected_updated_at)
    setlist.name = payload.name.strip() or payload.name
    await _touch(db, setlist)
    await db.commit()
    return await _reload(db, setlist_id, user)


@router.delete("/{setlist_id}", status_code=204)
async def delete_setlist(setlist_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    await _get_for_change(db, setlist_id, user, None)
    # Items go with it (ON DELETE CASCADE).
    await db.execute(sql_delete(Setlist).where(Setlist.id == setlist_id))
    await db.commit()
    return Response(status_code=204)


@router.put("/{setlist_id}/items", response_model=SetlistDetail)
async def replace_items(
    setlist_id: uuid.UUID, payload: SetlistItemsReplace, user: CurrentUser, db: DbSession
) -> SetlistDetail:
    """Save the whole running order. The same piece may appear more than once.

    Each kept piece keeps its `added_by` (it decides who the piece reaches
    through a shared setlist); new ones are credited to the editor."""
    setlist = await _get_for_change(db, setlist_id, user, payload.expected_updated_at)
    current = (
        await db.execute(
            select(SetlistItem.arrangement_id, SetlistItem.added_by)
            .where(SetlistItem.setlist_id == setlist_id)
            .order_by(SetlistItem.position)
        )
    ).all()
    visible = set(
        (
            await db.execute(
                select(Arrangement.id).where(
                    Arrangement.id.in_({arrangement_id for arrangement_id, _ in current}),
                    visible_arrangements(user),
                )
            )
        ).scalars()
    )
    if any(arrangement_id not in visible for arrangement_id, _ in current):
        # The editor can't send back entries it can't see, so saving would
        # silently drop them. Refuse until openclef#64 handles them.
        raise HTTPException(status_code=409, detail="setlist_has_hidden_items")
    await _check_items(db, payload.items, user)
    adders: dict[uuid.UUID, list[uuid.UUID | None]] = defaultdict(list)
    for arrangement_id, added_by in current:
        adders[arrangement_id].append(added_by)

    def credit(arrangement_id: uuid.UUID) -> uuid.UUID | None:
        return adders[arrangement_id].pop(0) if adders[arrangement_id] else user.id

    await db.execute(sql_delete(SetlistItem).where(SetlistItem.setlist_id == setlist_id))
    db.add_all(
        SetlistItem(
            setlist_id=setlist_id,
            position=position,
            arrangement_id=item.arrangement_id,
            part_id=item.part_id,
            added_by=credit(item.arrangement_id),
        )
        for position, item in enumerate(payload.items)
    )
    await _touch(db, setlist)
    await _commit(db)
    return await _reload(db, setlist_id, user)


@router.post("/{setlist_id}/items", response_model=SetlistDetail, status_code=201)
async def append_item(
    setlist_id: uuid.UUID, payload: SetlistItemWrite, user: CurrentUser, db: DbSession
) -> SetlistDetail:
    """Add one piece to the end (the "Add to setlist" action)."""
    setlist = await _get_for_change(db, setlist_id, user, None)
    await _check_items(db, [payload], user)
    last = (
        await db.execute(
            select(func.max(SetlistItem.position), func.count()).where(SetlistItem.setlist_id == setlist_id)
        )
    ).one()
    if last[1] >= SETLIST_MAX_ITEMS:
        raise HTTPException(status_code=422, detail="setlist_full")
    db.add(
        SetlistItem(
            setlist_id=setlist_id,
            position=0 if last[0] is None else last[0] + 1,
            arrangement_id=payload.arrangement_id,
            part_id=payload.part_id,
            added_by=user.id,
        )
    )
    await _touch(db, setlist)
    await _commit(db)
    return await _reload(db, setlist_id, user)
