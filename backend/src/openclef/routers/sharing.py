"""People, partners and groups: who you share with (openclef#60, #62, #63).

A partnership is one-way. When A adds B, B sees everything A owns; A sees
nothing of B's unless B adds A too. Only the sharer creates or ends it.
The partner decides one thing: whether A's pieces show in B's main
library ("Show in my library"). Either way they stay on A's page and open
from setlists, because that toggle is display, not access.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from openclef.auth.deps import get_current_user
from openclef.db import get_session
from openclef.models.library import Arrangement
from openclef.models.setlist import Setlist
from openclef.models.sharing import ArrangementShare, Group, GroupMember, Partnership, SetlistShare
from openclef.models.user import User
from openclef.routers.users import TOMBSTONE_USERNAME
from openclef.schemas import (
    GroupCreate,
    GroupMemberCreate,
    GroupRead,
    GroupUpdate,
    IncomingPartner,
    IncomingPartnerUpdate,
    PartnerCreate,
    Partners,
    Person,
)

router = APIRouter(prefix="/api/v1", tags=["sharing"])

CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[AsyncSession, Depends(get_session)]


@router.get("/people", response_model=list[Person])
async def list_people(user: CurrentUser, db: DbSession) -> list[Person]:
    """Everyone else on this server, by username, to pick a partner from.
    A family server, so the directory is open to every signed-in user."""
    rows = (
        await db.execute(
            select(User.id, User.username)
            .where(User.id != user.id, User.username != TOMBSTONE_USERNAME)
            .order_by(User.username)
        )
    ).all()
    return [Person(id=user_id, username=username) for user_id, username in rows]


@router.get("/partners", response_model=Partners)
async def list_partners(user: CurrentUser, db: DbSession) -> Partners:
    outgoing = (
        await db.execute(
            select(User.id, User.username)
            .join(Partnership, Partnership.partner_id == User.id)
            .where(Partnership.sharer_id == user.id)
            .order_by(User.username)
        )
    ).all()
    incoming = (
        await db.execute(
            select(User.id, User.username, Partnership.show_in_library)
            .join(Partnership, Partnership.sharer_id == User.id)
            .where(Partnership.partner_id == user.id)
            .order_by(User.username)
        )
    ).all()
    return Partners(
        outgoing=[Person(id=i, username=name) for i, name in outgoing],
        incoming=[
            IncomingPartner(id=i, username=name, show_in_library=shown) for i, name, shown in incoming
        ],
    )


@router.post("/partners", response_model=Person, status_code=201)
async def add_partner(body: PartnerCreate, user: CurrentUser, db: DbSession) -> Person:
    """Share my whole library with `user_id`."""
    if body.user_id == user.id:
        raise HTTPException(status_code=422, detail="cannot_partner_self")
    partner = await db.get(User, body.user_id)
    if partner is None or partner.username == TOMBSTONE_USERNAME:
        raise HTTPException(status_code=422, detail="user_not_found")
    db.add(Partnership(sharer_id=user.id, partner_id=partner.id))
    try:
        await db.commit()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="already_partners") from None
    return Person(id=partner.id, username=partner.username)


@router.delete("/partners/{user_id}", status_code=204)
async def remove_partner(user_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    """Stop sharing my library with `user_id`. Their setlists keep my
    pieces as entries they can no longer open (openclef#64 names them)."""
    result = await db.execute(
        delete(Partnership).where(Partnership.sharer_id == user.id, Partnership.partner_id == user_id)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="partner_not_found")
    await db.commit()
    return Response(status_code=204)


@router.patch("/partners/incoming/{user_id}", response_model=IncomingPartner)
async def update_incoming(
    user_id: uuid.UUID, body: IncomingPartnerUpdate, user: CurrentUser, db: DbSession
) -> IncomingPartner:
    """The receiver's "Show in my library" toggle for one sharer."""
    partnership = await db.get(Partnership, (user_id, user.id))
    if partnership is None:
        raise HTTPException(status_code=404, detail="partner_not_found")
    partnership.show_in_library = body.show_in_library
    await db.commit()
    sharer = await db.get(User, user_id)
    return IncomingPartner(id=user_id, username=sharer.username, show_in_library=body.show_in_library)


# --- Groups (openclef#63) ----------------------------------------------
#
# Anyone can create a group and so owns it; the creator is also its first
# member (the access rule reads membership only). The owner renames,
# deletes, and adds or removes members; any other member may leave. Members
# see the group, its owner and its members; to anyone else it doesn't
# exist, so every lookup is a 404 for non-members. Pieces are shared into a
# group from the piece (PUT /arrangements/{id}/shares).


async def _member_group(db: AsyncSession, group_id: uuid.UUID, user: User) -> Group:
    """The group, if `user` is in it."""
    group = (
        await db.execute(
            select(Group)
            .join(GroupMember, GroupMember.group_id == Group.id)
            .where(Group.id == group_id, GroupMember.user_id == user.id)
        )
    ).scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=404, detail="group_not_found")
    return group


async def _owned_group(db: AsyncSession, group_id: uuid.UUID, user: User) -> Group:
    group = await _member_group(db, group_id, user)
    if group.owner_id != user.id:
        raise HTTPException(status_code=403, detail="not_group_owner")
    return group


async def _read_groups(db: AsyncSession, groups: list[Group]) -> list[GroupRead]:
    if not groups:
        return []
    group_ids = [group.id for group in groups]
    members: dict[uuid.UUID, list[Person]] = {group_id: [] for group_id in group_ids}
    names: dict[uuid.UUID, str] = {}
    for group_id, member_id, username in (
        await db.execute(
            select(GroupMember.group_id, User.id, User.username)
            .join(User, User.id == GroupMember.user_id)
            .where(GroupMember.group_id.in_(group_ids))
            .order_by(User.username)
        )
    ).all():
        members[group_id].append(Person(id=member_id, username=username))
        names[member_id] = username
    owner_ids = {group.owner_id for group in groups} - names.keys()
    if owner_ids:
        names.update(
            (await db.execute(select(User.id, User.username).where(User.id.in_(owner_ids)))).all()
        )
    return [
        GroupRead(
            id=group.id,
            name=group.name,
            owner=Person(id=group.owner_id, username=names[group.owner_id]),
            members=members[group.id],
        )
        for group in groups
    ]


@router.get("/groups", response_model=list[GroupRead])
async def list_groups(user: CurrentUser, db: DbSession) -> list[GroupRead]:
    """The groups I'm in (owning one makes me a member)."""
    groups = (
        await db.execute(
            select(Group)
            .join(GroupMember, GroupMember.group_id == Group.id)
            .where(GroupMember.user_id == user.id)
            .order_by(Group.name, Group.id)
        )
    ).scalars().all()
    return await _read_groups(db, list(groups))


@router.post("/groups", response_model=GroupRead, status_code=201)
async def create_group(body: GroupCreate, user: CurrentUser, db: DbSession) -> GroupRead:
    group = Group(name=body.name, owner_id=user.id)
    db.add(group)
    await db.flush()
    db.add(GroupMember(group_id=group.id, user_id=user.id))
    await db.commit()
    return (await _read_groups(db, [group]))[0]


@router.patch("/groups/{group_id}", response_model=GroupRead)
async def rename_group(
    group_id: uuid.UUID, body: GroupUpdate, user: CurrentUser, db: DbSession
) -> GroupRead:
    group = await _owned_group(db, group_id, user)
    group.name = body.name
    await db.commit()
    return (await _read_groups(db, [group]))[0]


@router.delete("/groups/{group_id}", status_code=204)
async def delete_group(group_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    """Delete the group. Its members and shares go with it (foreign-key
    cascades); the pieces stay with their owners."""
    group = await _owned_group(db, group_id, user)
    await db.execute(delete(Group).where(Group.id == group.id))
    await db.commit()
    return Response(status_code=204)


@router.post("/groups/{group_id}/members", response_model=GroupRead, status_code=201)
async def add_member(
    group_id: uuid.UUID, body: GroupMemberCreate, user: CurrentUser, db: DbSession
) -> GroupRead:
    group = await _owned_group(db, group_id, user)
    member = await db.get(User, body.user_id)
    if member is None or member.username == TOMBSTONE_USERNAME:
        raise HTTPException(status_code=422, detail="user_not_found")
    db.add(GroupMember(group_id=group.id, user_id=member.id))
    try:
        await db.commit()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="already_member") from None
    return (await _read_groups(db, [group]))[0]


@router.delete("/groups/{group_id}/members/{user_id}", status_code=204)
async def remove_member(
    group_id: uuid.UUID, user_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> Response:
    """The owner removes a member, or a member leaves (their own id).

    The departing member's pieces and setlists stop being shared with the
    group: a share is a member handing their music to the others, so it ends
    when they go.
    The owner can't leave; they delete the group instead."""
    group = await _member_group(db, group_id, user)
    if user_id == user.id:
        if group.owner_id == user.id:
            raise HTTPException(status_code=422, detail="owner_cannot_leave")
    elif group.owner_id != user.id:
        raise HTTPException(status_code=403, detail="not_group_owner")
    result = await db.execute(
        delete(GroupMember).where(GroupMember.group_id == group.id, GroupMember.user_id == user_id)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="member_not_found")
    await db.execute(
        delete(ArrangementShare).where(
            ArrangementShare.group_id == group.id,
            ArrangementShare.arrangement_id.in_(
                select(Arrangement.id).where(Arrangement.owner_id == user_id)
            ),
        )
    )
    # Their setlists shared with the group too (openclef#64).
    await db.execute(
        delete(SetlistShare).where(
            SetlistShare.group_id == group.id,
            SetlistShare.setlist_id.in_(select(Setlist.id).where(Setlist.owner_id == user_id)),
        )
    )
    await db.commit()
    return Response(status_code=204)
