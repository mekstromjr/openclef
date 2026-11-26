"""Deleting an account without losing what other people use (openclef#65).

What the account owns splits in two:

- **Kept**: anything someone else can see under the sharing rules. Pieces
  through a partner, a group with other members, or a setlist that passes
  them on (services.access); setlists through a partner or a share; groups
  that have other members. Each kept item gets a new owner.
- **Deleted**: everything else, with its files.

"Someone else" never counts the admin override: an admin can open
everything, so counting it would keep everything.

The suggested new owner is whoever already sees the item, so the people it
was kept for don't lose it when the account's partnerships and setlist
shares go with it: the first partner; for a piece reached only through a
setlist, that setlist's owner; otherwise the admin doing the delete. A
group goes to one of its members. The plan and the delete call the same
`build_plan`, and the delete calls it again after taking its locks, so an
item made visible after the dialog opened is kept with its default owner.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from openclef.models.library import Arrangement, ArrangementTag, Part
from openclef.models.setlist import Setlist, SetlistItem
from openclef.models.sharing import ArrangementShare, Group, GroupMember, Partnership, SetlistShare
from openclef.models.user import User
from openclef.services.access import adder_has_setlist
from openclef.services.setlist_entries import mark_entries_deleted
from openclef.services.uploads import thumbnail_key


@dataclass
class PlannedSetlist:
    id: uuid.UUID
    name: str
    owner_id: uuid.UUID
    holders: set[uuid.UUID]  # share holders other than the account


@dataclass
class KeptPiece:
    id: uuid.UUID
    title: str
    seen_by: list[str]
    default_owner: uuid.UUID
    setlists: list[PlannedSetlist]
    # Set when the default is "whoever gets this setlist of the account's":
    # the delete then follows the admin's pick for that setlist.
    follows_setlist: uuid.UUID | None = None


@dataclass
class KeptSetlist:
    id: uuid.UUID
    name: str
    seen_by: list[str]
    default_owner: uuid.UUID


@dataclass
class KeptGroup:
    id: uuid.UUID
    name: str
    members: list[uuid.UUID]  # other members, by username
    default_owner: uuid.UUID


@dataclass
class Plan:
    pieces: list[KeptPiece] = field(default_factory=list)
    setlists: list[KeptSetlist] = field(default_factory=list)
    groups: list[KeptGroup] = field(default_factory=list)
    private_pieces: list[uuid.UUID] = field(default_factory=list)
    private_setlists: list[uuid.UUID] = field(default_factory=list)
    private_groups: int = 0
    partners: list[uuid.UUID] = field(default_factory=list)  # by username
    # Everyone named anywhere above, for the response.
    names: dict[uuid.UUID, str] = field(default_factory=dict)


class DeletionError(ValueError):
    """A chosen owner the delete can't honour; the value is the API detail."""


async def _usernames(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = await db.execute(select(User.id, User.username).where(User.id.in_(ids)))
    return dict(rows.all())


async def build_plan(db: AsyncSession, account: User, admin: User) -> Plan:
    uid = account.id
    plan = Plan()

    partners = [
        pid
        for pid, _ in (
            await db.execute(
                select(User.id, User.username)
                .join(Partnership, Partnership.partner_id == User.id)
                .where(Partnership.sharer_id == uid)
                .order_by(User.username)
            )
        ).all()
    ]
    plan.partners = partners
    fallback = partners[0] if partners else admin.id

    # Groups: kept when someone else is in them.
    members: dict[uuid.UUID, list[uuid.UUID]] = {}
    group_rows = (
        await db.execute(
            select(Group.id, Group.name, GroupMember.user_id)
            .outerjoin(
                GroupMember, and_(GroupMember.group_id == Group.id, GroupMember.user_id != uid)
            )
            .outerjoin(User, User.id == GroupMember.user_id)
            .where(Group.owner_id == uid)
            .order_by(Group.name, Group.id, User.username)
        )
    ).all()
    group_names: dict[uuid.UUID, str] = {}
    for gid, name, member in group_rows:
        group_names[gid] = name
        if member is not None:
            members.setdefault(gid, []).append(member)
    for gid, name in group_names.items():
        if gid not in members:
            plan.private_groups += 1
            continue
        others = members[gid]
        default = fallback if fallback in others else others[0]
        plan.groups.append(KeptGroup(gid, name, others, default))

    # Who holds each setlist through a share, other than the account. A
    # group the account owns stays, so its other members still count.
    async def holders_of(setlist_ids: set[uuid.UUID]) -> dict[uuid.UUID, set[uuid.UUID]]:
        held: dict[uuid.UUID, set[uuid.UUID]] = {sid: set() for sid in setlist_ids}
        if not setlist_ids:
            return held
        direct = await db.execute(
            select(SetlistShare.setlist_id, SetlistShare.user_id).where(
                SetlistShare.setlist_id.in_(setlist_ids),
                SetlistShare.user_id.is_not(None),
                SetlistShare.user_id != uid,
            )
        )
        via_group = await db.execute(
            select(SetlistShare.setlist_id, GroupMember.user_id)
            .join(GroupMember, GroupMember.group_id == SetlistShare.group_id)
            .where(SetlistShare.setlist_id.in_(setlist_ids), GroupMember.user_id != uid)
        )
        for sid, holder in [*direct.all(), *via_group.all()]:
            held[sid].add(holder)
        return held

    # Setlists the account owns: kept with a partner or a share holder.
    own_setlists = (
        await db.execute(
            select(Setlist.id, Setlist.name).where(Setlist.owner_id == uid).order_by(Setlist.name, Setlist.id)
        )
    ).all()
    held = await holders_of({sid for sid, _ in own_setlists})
    setlist_owner: dict[uuid.UUID, uuid.UUID] = {}
    for sid, name in own_setlists:
        seen_by = (["partner"] if partners else []) + (["share"] if held[sid] else [])
        if seen_by:
            plan.setlists.append(KeptSetlist(sid, name, seen_by, fallback))
            setlist_owner[sid] = fallback
        else:
            plan.private_setlists.append(sid)

    # Setlists passing on the account's pieces: entries the account added of
    # its own pieces, on a setlist it still has (services.access, rule 4).
    passing = (
        await db.execute(
            select(SetlistItem.arrangement_id, Setlist.id, Setlist.name, Setlist.owner_id)
            .join(Setlist, Setlist.id == SetlistItem.setlist_id)
            .join(Arrangement, Arrangement.id == SetlistItem.arrangement_id)
            .where(
                Arrangement.owner_id == uid,
                SetlistItem.added_by == uid,
                adder_has_setlist(),
            )
            .distinct()
            .order_by(Setlist.name, Setlist.id)
        )
    ).all()
    passing_held = await holders_of({sid for _, sid, _, owner in passing if owner != uid}) | held
    on_setlists: dict[uuid.UUID, list[PlannedSetlist]] = {}
    for piece, sid, name, owner in passing:
        holders = passing_held.get(sid, set())
        # A setlist only the account can see passes nothing to anyone.
        if owner == uid and sid not in setlist_owner:
            continue
        on_setlists.setdefault(piece, []).append(PlannedSetlist(sid, name, owner, holders))

    shared_in_groups = set(
        (
            await db.execute(
                select(ArrangementShare.arrangement_id)
                .join(Arrangement, Arrangement.id == ArrangementShare.arrangement_id)
                .join(GroupMember, GroupMember.group_id == ArrangementShare.group_id)
                .where(Arrangement.owner_id == uid, GroupMember.user_id != uid)
            )
        ).scalars()
    )

    pieces = (
        await db.execute(
            select(Arrangement.id, Arrangement.title)
            .where(Arrangement.owner_id == uid)
            .order_by(Arrangement.title, Arrangement.id)
        )
    ).all()
    for aid, title in pieces:
        via = on_setlists.get(aid, [])
        seen_by = (
            (["partner"] if partners else [])
            + (["group"] if aid in shared_in_groups else [])
            + (["setlist"] if via else [])
        )
        if not seen_by:
            plan.private_pieces.append(aid)
            continue
        follows = None
        if partners:
            default = fallback
        elif via:
            # The setlist's owner already holds it, so the piece keeps
            # reaching everyone it reached. Someone else's setlist first.
            first = next((s for s in via if s.owner_id != uid), via[0])
            if first.owner_id == uid:
                follows = first.id
            default = setlist_owner.get(first.id, first.owner_id)
        else:
            default = fallback
        plan.pieces.append(KeptPiece(aid, title, seen_by, default, via, follows))

    named = {admin.id, *partners}
    named |= {p.default_owner for p in plan.pieces} | {g.default_owner for g in plan.groups}
    named |= {m for g in plan.groups for m in g.members}
    named |= {s.owner_id for p in plan.pieces for s in p.setlists if s.owner_id != uid}
    plan.names = await _usernames(db, named)
    return plan


async def _resolve(
    db: AsyncSession,
    account: User,
    tombstone_name: str,
    chosen: dict[uuid.UUID, uuid.UUID],
    defaults: dict[uuid.UUID, uuid.UUID],
    owned: set[uuid.UUID],
) -> dict[uuid.UUID, uuid.UUID]:
    """New owner per kept item: the pick, else the default. A pick for a
    private item keeps it too (the admin chose to keep it)."""
    if set(chosen) - owned:
        raise DeletionError("item_not_found")
    result = {**defaults, **chosen}
    people = set(chosen.values())
    if people:
        found = await db.execute(select(User.id, User.username).where(User.id.in_(people)))
        valid = {pid for pid, name in found.all() if name != tombstone_name and pid != account.id}
        if people - valid:
            raise DeletionError("user_not_found")
    return result


async def delete_account(
    db: AsyncSession,
    account: User,
    admin: User,
    *,
    tombstone_name: str,
    arrangements: dict[uuid.UUID, uuid.UUID],
    setlists: dict[uuid.UUID, uuid.UUID],
    groups: dict[uuid.UUID, uuid.UUID],
) -> list[str]:
    """Hand on what others use, delete the rest, then the account. Returns
    the storage keys to delete once the caller has committed."""
    uid = account.id
    # Locks in the order setlist saves and appends take them: setlists, then
    # pieces, each by id. The account's row comes last: an append inserts
    # added_by = this account, and that key check share-locks the row while
    # the append holds its setlist, so locking the row first would deadlock.
    holding = select(SetlistItem.setlist_id).join(
        Arrangement, Arrangement.id == SetlistItem.arrangement_id
    ).where(Arrangement.owner_id == uid)
    locked = set(
        (
            await db.execute(
                select(Setlist.id)
                .where((Setlist.owner_id == uid) | Setlist.id.in_(holding))
                .order_by(Setlist.id)
                .with_for_update()
            )
        ).scalars()
    )
    await db.execute(
        select(Arrangement.id).where(Arrangement.owner_id == uid).order_by(Arrangement.id).with_for_update()
    )
    await db.execute(select(User.id).where(User.id == uid).with_for_update())

    plan = await build_plan(db, account, admin)

    own_pieces = {p.id for p in plan.pieces} | set(plan.private_pieces)
    own_setlists = {s.id for s in plan.setlists} | set(plan.private_setlists)
    kept_groups = {g.id: g for g in plan.groups}
    setlist_owner = await _resolve(
        db, account, tombstone_name, setlists, {s.id: s.default_owner for s in plan.setlists}, own_setlists
    )
    piece_defaults = {
        p.id: setlist_owner.get(p.follows_setlist, p.default_owner) if p.follows_setlist else p.default_owner
        for p in plan.pieces
    }
    piece_owner = await _resolve(db, account, tombstone_name, arrangements, piece_defaults, own_pieces)
    if set(groups) - set(kept_groups):
        raise DeletionError("group_not_found")
    for gid, new_owner in groups.items():
        if new_owner not in kept_groups[gid].members:
            raise DeletionError("not_a_member")
    group_owner = {gid: g.default_owner for gid, g in kept_groups.items()} | groups

    for gid, new_owner in group_owner.items():
        await db.execute(update(Group).where(Group.id == gid).values(owner_id=new_owner))

    private_setlists = own_setlists - set(setlist_owner)
    if private_setlists:
        # Their entries cascade, so they don't need marking below.
        await db.execute(delete(Setlist).where(Setlist.id.in_(private_setlists)))
    for sid, new_owner in setlist_owner.items():
        await db.execute(update(Setlist).where(Setlist.id == sid).values(owner_id=new_owner))
        # An owner isn't also shared with.
        await db.execute(
            delete(SetlistShare).where(SetlistShare.setlist_id == sid, SetlistShare.user_id == new_owner)
        )

    for aid, new_owner in piece_owner.items():
        await db.execute(update(Arrangement).where(Arrangement.id == aid).values(owner_id=new_owner))
        # Entries the account added now come from the new owner, so the
        # piece keeps passing on wherever the new owner holds the setlist.
        await db.execute(
            update(SetlistItem)
            .where(SetlistItem.arrangement_id == aid, SetlistItem.added_by == uid)
            .values(added_by=new_owner)
        )

    # Parts and tags the account added to pieces that stay are credited to
    # each piece's owner; their keys on the account are RESTRICT.
    await db.execute(
        update(Part)
        .where(Part.uploaded_by == uid, Part.arrangement_id == Arrangement.id)
        .values(uploaded_by=Arrangement.owner_id)
        .execution_options(synchronize_session=False)
    )
    await db.execute(
        update(ArrangementTag)
        .where(ArrangementTag.added_by == uid, ArrangementTag.arrangement_id == Arrangement.id)
        .values(added_by=Arrangement.owner_id)
        .execution_options(synchronize_session=False)
    )

    doomed = [aid for aid in own_pieces if aid not in piece_owner]
    keys: list[str] = []
    if doomed:
        await mark_entries_deleted(db, doomed, deleted_by=None, locked_setlists=locked)
        rows = await db.execute(
            select(Part.storage_key, Part.id, Part.thumbnail_storage_key).where(
                Part.arrangement_id.in_(doomed)
            )
        )
        keys = [k for storage_key, pid, thumb in rows.all() for k in (storage_key, thumb or thumbnail_key(pid))]
        await db.execute(delete(Arrangement).where(Arrangement.id.in_(doomed)))

    # Partnerships, memberships, shares, annotations and empty groups
    # cascade; entries it added of other people's pieces lose their adder.
    await db.execute(delete(User).where(User.id == uid))
    return keys


__all__ = ["DeletionError", "Plan", "build_plan", "delete_account"]
