"""Round-trip tests for the Phase 2 schema (annotations + setlists).

Phase 2 has no UI in Phase 1, but the schema must work — the whole
point of building these tables now is to lock the per-user-scope
columns before any data lands.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from openclef.models.annotation import Annotation, AnnotationRevision
from openclef.models.setlist import Setlist, SetlistItem
from tests.factories import (
    acreate,
    AnnotationRevisionFactory,
    SetlistItemFactory,
    make_annotation,
    make_arrangement,
    make_part,
    make_setlist,
    make_user,
)


async def test_annotation_round_trip(session):
    user = await make_user(session)
    part = await make_part(session)
    ann = await make_annotation(session, user_id=user.id, part_id=part.id, page_number=2)
    fetched = (
        await session.execute(select(Annotation).where(Annotation.id == ann.id))
    ).scalar_one()
    assert fetched.user_id == user.id
    assert fetched.part_id == part.id
    assert fetched.page_number == 2
    assert fetched.current_revision_id is None


async def test_annotation_revision_chain(session):
    ann = await make_annotation(session)
    # Two revisions linked parent → child
    r1 = await acreate(
        session, AnnotationRevisionFactory, annotation_id=ann.id, payload_jsonb={"v": 1}
    )
    r2 = await acreate(
        session,
        AnnotationRevisionFactory,
        annotation_id=ann.id,
        parent_revision_id=r1.id,
        payload_jsonb={"v": 2},
    )
    # Move HEAD to r2
    ann.current_revision_id = r2.id
    await session.flush()

    refreshed = (
        await session.execute(select(Annotation).where(Annotation.id == ann.id))
    ).scalar_one()
    assert refreshed.current_revision_id == r2.id

    # Walking parent_revision_id reaches r1
    fetched_r2 = (
        await session.execute(
            select(AnnotationRevision).where(AnnotationRevision.id == r2.id)
        )
    ).scalar_one()
    assert fetched_r2.parent_revision_id == r1.id


async def test_annotation_unique_per_user_part_page(session):
    user = await make_user(session)
    part = await make_part(session)
    await make_annotation(session, user_id=user.id, part_id=part.id, page_number=1)
    with pytest.raises(IntegrityError):
        await make_annotation(session, user_id=user.id, part_id=part.id, page_number=1)
        await session.flush()


async def test_setlist_with_items(session):
    user = await make_user(session)
    sl = await make_setlist(session, owner_id=user.id, name="Recital 2026")
    arr1 = await make_arrangement(session)
    arr2 = await make_arrangement(session)
    await acreate(
        session, SetlistItemFactory, setlist_id=sl.id, arrangement_id=arr1.id, position=0
    )
    await acreate(
        session, SetlistItemFactory, setlist_id=sl.id, arrangement_id=arr2.id, position=1
    )

    items = list(
        (
            await session.execute(
                select(SetlistItem)
                .where(SetlistItem.setlist_id == sl.id)
                .order_by(SetlistItem.position)
            )
        ).scalars()
    )
    assert [i.position for i in items] == [0, 1]
    assert {i.arrangement_id for i in items} == {arr1.id, arr2.id}


async def test_setlist_position_is_unique_per_setlist(session):
    sl = await make_setlist(session)
    arr = await make_arrangement(session)
    await acreate(
        session, SetlistItemFactory, setlist_id=sl.id, arrangement_id=arr.id, position=5
    )
    with pytest.raises(IntegrityError):
        await acreate(
            session, SetlistItemFactory, setlist_id=sl.id, arrangement_id=arr.id, position=5
        )


def _Setlist_alias():  # pragma: no cover
    return Setlist
