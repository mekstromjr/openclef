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
  4. it is on a setlist they can see, **and** whoever put it there owns it
     **and** still has that setlist: they own it, or hold a share on it
     (directly or through a group they're in). A shared setlist passes on
     what its contributors own, never a piece someone else shared with
     them, and stops passing on a contributor's pieces once they lose the
     setlist (openclef#64). Being the owner's partner doesn't count;
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

from openclef.models.enums import SharePermission, UserRole
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


def adder_has_setlist() -> ColumnElement[bool]:
    """Correlated on `setlist_items`: whoever added the entry still has its
    setlist, as its owner or through a share (direct or via a group)."""
    # Correlated explicitly: left to itself, SQLAlchemy gives this nested IN
    # its own FROM setlist_items, which asks whether *anyone* who added an
    # entry is in the group, not this entry's adder.
    adder_groups = (
        select(GroupMember.group_id)
        .where(GroupMember.user_id == SetlistItem.added_by)
        .correlate(SetlistItem)
    )
    # The EXISTS are pinned to setlist_items too, so a caller that joins
    # setlists itself doesn't have its rows stand in for this entry's setlist.
    return or_(
        select(Setlist.id)
        .where(Setlist.id == SetlistItem.setlist_id, Setlist.owner_id == SetlistItem.added_by)
        .correlate(SetlistItem)
        .exists(),
        select(SetlistShare.id)
        .where(
            SetlistShare.setlist_id == SetlistItem.setlist_id,
            or_(SetlistShare.user_id == SetlistItem.added_by, SetlistShare.group_id.in_(adder_groups)),
        )
        .correlate(SetlistItem)
        .exists(),
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
            adder_has_setlist(),
            SetlistItem.setlist_id.in_(select(Setlist.id).where(visible_setlists(user))),
        )
        # Only the piece comes from outside: a caller that joins setlist
        # items itself must not have its rows stand in for these.
        .correlate(Arrangement)
        .exists()
    )
    return or_(
        Arrangement.owner_id == user.id,
        Arrangement.owner_id.in_(_sharers_of(user)),
        Arrangement.id.in_(via_group),
        via_setlist,
    )


def in_library(
    user: User,
    *,
    scope: str = "all",
    shared_by: uuid.UUID | None = None,
    group: uuid.UUID | None = None,
) -> ColumnElement[bool]:
    """WHERE clause on `Arrangement` for what `user`'s library page lists.

    - `scope="mine"`: only what they own ("Only my music").
    - `shared_by`: what that one person shares with them, whatever the
      "Show in my library" toggle says (the per-sharer page).
    - `group`: what is shared with that group, if they're in it (the group
      page, openclef#63). Nothing for a group they aren't in.
    - otherwise: own + group shares + partners shown in the library.

    Always ANDed with `visible_arrangements`, so a listing can never show
    something the user couldn't open."""
    if group is not None:
        in_group = select(ArrangementShare.arrangement_id).where(
            ArrangementShare.group_id == group,
            ArrangementShare.group_id.in_(_groups_of(user)),
        )
        listed = Arrangement.id.in_(in_group)
    elif scope == "mine":
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


def contributable_setlists(user: User) -> Select:
    """Ids of setlists `user` may add to and reorder: their own, and those
    shared with them (directly or through a group) with contribute. Admins
    may change any setlist, so they get every one."""
    if user.role == UserRole.ADMIN:
        return select(Setlist.id)
    contribute = select(SetlistShare.setlist_id).where(
        SetlistShare.permission == SharePermission.CONTRIBUTE,
        or_(SetlistShare.user_id == user.id, SetlistShare.group_id.in_(_groups_of(user))),
    )
    return select(Setlist.id).where(or_(Setlist.owner_id == user.id, Setlist.id.in_(contribute)))


__all__ = [
    "adder_has_setlist",
    "can_manage",
    "contributable_setlists",
    "in_library",
    "visible_arrangements",
    "visible_setlists",
]
