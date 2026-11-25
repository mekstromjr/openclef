"""People and partners: sharing your whole library (openclef#60, #62).

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
from openclef.models.sharing import Partnership
from openclef.models.user import User
from openclef.routers.users import TOMBSTONE_USERNAME
from openclef.schemas import (
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
