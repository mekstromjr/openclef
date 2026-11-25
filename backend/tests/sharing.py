"""Test helpers for the sharing model: seed partnerships, groups and shares
directly, since their API arrives in openclef#62-#64."""
from __future__ import annotations

import uuid

from openclef.models.enums import SharePermission
from openclef.models.sharing import (
    ArrangementShare,
    Group,
    GroupMember,
    Partnership,
    SetlistShare,
)


async def share_library(kit, sharer_id, partner_id) -> None:
    """`partner_id` sees everything `sharer_id` owns (one-way)."""
    async with kit.sessionmaker() as s:
        s.add(Partnership(sharer_id=_id(sharer_id), partner_id=_id(partner_id)))
        await s.commit()


async def make_group(kit, owner_id, *member_ids) -> uuid.UUID:
    async with kit.sessionmaker() as s:
        group = Group(name="Group", owner_id=_id(owner_id))
        s.add(group)
        await s.flush()
        s.add_all(GroupMember(group_id=group.id, user_id=_id(member)) for member in member_ids)
        await s.commit()
        return group.id


async def share_arrangement(kit, arrangement_id, group_id) -> None:
    async with kit.sessionmaker() as s:
        s.add(ArrangementShare(arrangement_id=_id(arrangement_id), group_id=_id(group_id)))
        await s.commit()


async def share_setlist(
    kit, setlist_id, *, user_id=None, group_id=None, permission=SharePermission.VIEW
) -> None:
    async with kit.sessionmaker() as s:
        s.add(
            SetlistShare(
                setlist_id=_id(setlist_id),
                user_id=_id(user_id) if user_id else None,
                group_id=_id(group_id) if group_id else None,
                permission=permission,
            )
        )
        await s.commit()


def _id(value) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
