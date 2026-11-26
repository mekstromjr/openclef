"""Setlist entries outliving their piece (openclef#64, openclef#65)."""
from __future__ import annotations

import uuid
from collections.abc import Collection

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from openclef.models.library import Arrangement
from openclef.models.setlist import Setlist, SetlistItem


async def mark_entries_deleted(
    db: AsyncSession,
    arrangement_ids: Collection[uuid.UUID],
    *,
    deleted_by: uuid.UUID | None,
    locked_setlists: Collection[uuid.UUID],
) -> None:
    """Turn every entry for these pieces into a "deleted" entry, before the
    pieces themselves are deleted (the entry's key on the piece is RESTRICT).

    The caller has locked the setlists holding the pieces, then the pieces,
    in that order. Title and owner come from the locked piece row in the same
    statement, so a rename that committed before the lock is what's recorded.
    `deleted_by` is null when the piece went with its owner's account."""
    if not arrangement_ids:
        return
    marked = await db.execute(
        update(SetlistItem)
        .where(SetlistItem.arrangement_id == Arrangement.id, Arrangement.id.in_(arrangement_ids))
        .values(
            arrangement_id=None,
            part_id=None,
            title_snapshot=Arrangement.title,
            piece_owner_id=Arrangement.owner_id,
            deleted_by=deleted_by,
            deleted_at=func.now(),
        )
        .returning(SetlistItem.setlist_id)
        .execution_options(synchronize_session=False)
    )
    # The setlists changed, so a tab holding an older copy gets 409 on save.
    # Only the locked ones: locking another now would invert the lock order.
    changed = set(marked.scalars()) & set(locked_setlists)
    if changed:
        await db.execute(
            update(Setlist)
            .where(Setlist.id.in_(changed))
            .values(updated_at=func.clock_timestamp())
            .execution_options(synchronize_session=False)
        )


__all__ = ["mark_entries_deleted"]
