"""Round-trip tests for Arrangement / Part / Tag / ArrangementTag."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from openclef.models.enums import EditionType, KeySignature, PartType, Period
from openclef.models.library import Arrangement, ArrangementTag, Part, Tag
from tests.factories import (
    ArrangementTagFactory,
    acreate,
    make_arrangement,
    make_part,
    make_tag,
    make_user,
)


async def test_arrangement_round_trip(session):
    arr = await make_arrangement(
        session,
        title="Eine kleine Nachtmusik",
        composer=["Mozart, Wolfgang Amadeus"],
        key_signature=KeySignature.G_MAJOR,
        period=Period.CLASSICAL,
        edition_type=EditionType.URTEXT,
        difficulty=3,
        external_links_jsonb=[{"type": "imslp", "url": "https://imslp.org/..."}],
    )
    fetched = (
        await session.execute(select(Arrangement).where(Arrangement.id == arr.id))
    ).scalar_one()
    assert fetched.title == "Eine kleine Nachtmusik"
    assert fetched.composer == ["Mozart, Wolfgang Amadeus"]
    assert fetched.key_signature == KeySignature.G_MAJOR
    assert fetched.period == Period.CLASSICAL
    assert fetched.edition_type == EditionType.URTEXT
    assert fetched.difficulty == 3
    assert fetched.external_links_jsonb == [
        {"type": "imslp", "url": "https://imslp.org/..."}
    ]
    # Server defaults populate empty arrays for unset multi-value fields
    assert fetched.alternative_titles == []
    assert fetched.lyricist == []


async def test_arrangement_array_defaults(session):
    arr = await make_arrangement(session)
    assert arr.composer == ["Anonymous"]  # factory default
    assert arr.arranger == []
    assert arr.language == []


async def test_part_round_trip(session):
    arr = await make_arrangement(session)
    part = await make_part(
        session,
        arrangement_id=arr.id,
        part_type=PartType.PIANO_REDUCTION,
        label="Piano Reduction",
        instrument="piano",
        page_count=12,
        file_size_bytes=987_654,
        storage_key="local/parts/abc.pdf",
        file_hash_sha256="a" * 64,
    )
    fetched = (await session.execute(select(Part).where(Part.id == part.id))).scalar_one()
    assert fetched.arrangement_id == arr.id
    assert fetched.part_type == PartType.PIANO_REDUCTION
    assert fetched.label == "Piano Reduction"
    assert fetched.page_count == 12
    assert fetched.file_size_bytes == 987_654
    assert fetched.file_hash_sha256 == "a" * 64


async def test_tag_and_m2m(session):
    user = await make_user(session)
    arr = await make_arrangement(session, created_by=user.id)
    tag = await make_tag(session, name="Wedding")
    await acreate(
        session,
        ArrangementTagFactory,
        arrangement_id=arr.id,
        tag_id=tag.id,
        added_by=user.id,
    )
    pivot = (
        await session.execute(
            select(ArrangementTag).where(
                ArrangementTag.arrangement_id == arr.id,
                ArrangementTag.tag_id == tag.id,
            )
        )
    ).scalar_one()
    assert pivot.added_by == user.id


async def test_tag_name_is_case_insensitive_unique(session):
    await make_tag(session, name="Wedding")
    import pytest
    with pytest.raises(Exception):
        await make_tag(session, name="WEDDING")
        await session.flush()


def _ArrangementTag_alias():  # pragma: no cover — silences unused-import lint via reference
    return ArrangementTag, uuid.uuid4
