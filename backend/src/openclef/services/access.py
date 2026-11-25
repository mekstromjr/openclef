"""Who can see what (openclef#60, TRD section 3.5).

Every arrangement and setlist has one owner and is private by default.
These functions return SQL conditions that every read path filters on, so
no endpoint decides visibility on its own.

A user can see a **setlist** if:
  1. they own it;
  2. its owner shares their library with them (a partnership, one-way);
  3. it is shared with them directly, or with a group they belong to;
  4. they are an admin (temporary: admin is meant for user management).

A user can see an **arrangement** (and so its parts, files and thumbnails) if:
  1. they own it;
  2. its owner shares their library with them;
  3. it is shared with a group they belong to;
  4. it is on a setlist they can see, **and** whoever put it there owns it.
     A shared setlist passes on what its contributors own, never a piece
     someone else shared with them;
  5. they are an admin.

Partnerships don't chain: only the direct sharer's library counts.
`show_in_library` is the partner's display preference, not an access rule.

What the **library page lists** is narrower than what a user can open
(`in_library`, openclef#62): their own pieces, pieces shared with a group
they're in, and their partners' pieces, minus partners they turned "Show
in my library" off for. Pieces reached only through a setlist open from
that setlist but aren't listed, and an admin's library lists the same as
anyone's (the admin override applies to opening, not listing).
"""
from __future__ import annotations

import uuid

from sqlalchemy import ColumnElement, Select, and_, or_, select, true

from openclef.models.enums import UserRole
from openclef.models.library import Arrangement
from openclef.models.setlist import Setlist, SetlistItem
from openclef.models.sharing import ArrangementShare, GroupMember, Partnership, SetlistShare
from openclef.models.user import User


def _sharers_of(user: User) -> Select:
    """Users whose whole library `user` can see."""
    return select(Partnership.sharer_id).where(Partnership.partner_id == user.id)


def _groups_of(user: User) -> Select:
    return select(GroupMember.group_id).where(GroupMember.user_id == user.id)


def visible_setlists(user: User) -> ColumnElement[bool]:
    """WHERE clause on `Setlist` for the setlists `user` can see."""
    if user.role == UserRole.ADMIN:
        return true()
    shared = select(SetlistShare.setlist_id).where(
        or_(SetlistShare.user_id == user.id, SetlistShare.group_id.in_(_groups_of(user)))
    )
    return or_(
        Setlist.owner_id == user.id,
        Setlist.owner_id.in_(_sharers_of(user)),
        Setlist.id.in_(shared),
    )


def visible_arrangements(user: User) -> ColumnElement[bool]:
    """WHERE clause on `Arrangement` for the pieces `user` can see.

    Correlated on `arrangements`, so it works in any query that has the
    table in its FROM (the library list, facets, joins from Part)."""
    if user.role == UserRole.ADMIN:
        return true()
    via_group = select(ArrangementShare.arrangement_id).where(
        ArrangementShare.group_id.in_(_groups_of(user))
    )
    via_setlist = (
        select(SetlistItem.setlist_id)
        .where(
            SetlistItem.arrangement_id == Arrangement.id,
            SetlistItem.added_by == Arrangement.owner_id,
            SetlistItem.setlist_id.in_(select(Setlist.id).where(visible_setlists(user))),
        )
        .exists()
    )
    return or_(
        Arrangement.owner_id == user.id,
        Arrangement.owner_id.in_(_sharers_of(user)),
        Arrangement.id.in_(via_group),
        via_setlist,
    )


def in_library(
    user: User, *, scope: str = "all", shared_by: uuid.UUID | None = None
) -> ColumnElement[bool]:
    """WHERE clause on `Arrangement` for what `user`'s library page lists.

    - `scope="mine"`: only what they own ("Only my music").
    - `shared_by`: what that one person shares with them, whatever the
      "Show in my library" toggle says (the per-sharer page).
    - otherwise: own + group shares + partners shown in the library.

    Always ANDed with `visible_arrangements`, so a listing can never show
    something the user couldn't open."""
    if scope == "mine":
        listed = Arrangement.owner_id == user.id
    else:
        partners = select(Partnership.sharer_id).where(Partnership.partner_id == user.id)
        if shared_by is None:
            partners = partners.where(Partnership.show_in_library.is_(True))
        via_group = select(ArrangementShare.arrangement_id).where(
            ArrangementShare.group_id.in_(_groups_of(user))
        )
        listed = or_(
            Arrangement.owner_id == user.id,
            Arrangement.owner_id.in_(partners),
            Arrangement.id.in_(via_group),
        )
        if shared_by is not None:
            listed = and_(listed, Arrangement.owner_id == shared_by)
    return and_(visible_arrangements(user), listed)


def can_manage(owner_id, user: User) -> bool:
    """Delete or share: the owner, or an admin."""
    return owner_id == user.id or user.role == UserRole.ADMIN


__all__ = ["can_manage", "in_library", "visible_arrangements", "visible_setlists"]
