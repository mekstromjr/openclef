"""factory-boy factories + a thin async wrapper.

factory-boy is sync-only, so `acreate(session, FactoryCls, **overrides)`
is the bridge: build a detached ORM instance via factory.build(), add to
the AsyncSession, flush. SubFactory composition isn't used here — for
parents (e.g., Arrangement.created_by → User), tests call the
`make_*` convenience helpers below which compose explicitly.

Sequence-based defaults (factory.Sequence) keep unique columns
unique across builds within a session run.
"""
from __future__ import annotations

import uuid
from typing import Any, TypeVar

import factory
from sqlalchemy.ext.asyncio import AsyncSession

from openclef.db import Base
from openclef.models.annotation import Annotation, AnnotationRevision
from openclef.models.enrichment import EnrichmentJob
from openclef.models.enums import (
    EnrichmentJobStatus,
    KeySignature,
    PartType,
    Period,
    Theme,
    UserRole,
)
from openclef.models.library import Arrangement, ArrangementTag, Part, Tag
from openclef.models.setlist import Setlist, SetlistItem
from openclef.models.user import User, UserSettings

T = TypeVar("T", bound=Base)


async def acreate(session: AsyncSession, factory_cls: type, **overrides: Any) -> Any:
    """Build a detached factory instance and persist it via the AsyncSession."""
    obj = factory_cls.build(**overrides)
    session.add(obj)
    await session.flush()
    return obj


# --- Factories (build-only; persistence via acreate) -----------------


class UserFactory(factory.Factory):
    class Meta:
        model = User

    id = factory.LazyFunction(uuid.uuid4)
    username = factory.Sequence(lambda n: f"user_{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.test")
    role = UserRole.USER


class UserSettingsFactory(factory.Factory):
    class Meta:
        model = UserSettings

    theme = Theme.SYSTEM
    enrichment_default_enabled = False
    enrichment_providers_jsonb = factory.LazyFunction(
        lambda: [{"provider": "musicbrainz", "enabled": True}]
    )
    preferences_jsonb = factory.LazyFunction(dict)


class ArrangementFactory(factory.Factory):
    class Meta:
        model = Arrangement

    id = factory.LazyFunction(uuid.uuid4)
    title = factory.Sequence(lambda n: f"Arrangement {n}")
    composer = factory.LazyFunction(lambda: ["Anonymous"])
    key_signature = KeySignature.C_MAJOR
    period = Period.CLASSICAL


class PartFactory(factory.Factory):
    class Meta:
        model = Part

    id = factory.LazyFunction(uuid.uuid4)
    part_type = PartType.FULL_SCORE
    label = factory.Sequence(lambda n: f"Part {n}")
    page_count = 4
    file_size_bytes = 12_345
    storage_key = factory.Sequence(lambda n: f"local/parts/part_{n}.pdf")


class TagFactory(factory.Factory):
    class Meta:
        model = Tag

    id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"tag_{n}")


class ArrangementTagFactory(factory.Factory):
    class Meta:
        model = ArrangementTag


class AnnotationFactory(factory.Factory):
    class Meta:
        model = Annotation

    id = factory.LazyFunction(uuid.uuid4)
    page_number = 1


class AnnotationRevisionFactory(factory.Factory):
    class Meta:
        model = AnnotationRevision

    id = factory.LazyFunction(uuid.uuid4)
    payload_jsonb = factory.LazyFunction(lambda: {"strokes": []})


class SetlistFactory(factory.Factory):
    class Meta:
        model = Setlist

    id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"Setlist {n}")


class SetlistItemFactory(factory.Factory):
    class Meta:
        model = SetlistItem

    position = factory.Sequence(int)


class EnrichmentJobFactory(factory.Factory):
    class Meta:
        model = EnrichmentJob

    id = factory.LazyFunction(uuid.uuid4)
    status = EnrichmentJobStatus.PENDING
    attempts = 0


# --- Convenience composers ------------------------------------------


async def make_user(session: AsyncSession, **kwargs: Any) -> User:
    return await acreate(session, UserFactory, **kwargs)


async def make_arrangement(session: AsyncSession, **kwargs: Any) -> Arrangement:
    if "created_by" not in kwargs:
        kwargs["created_by"] = (await make_user(session)).id
    return await acreate(session, ArrangementFactory, **kwargs)


async def make_part(session: AsyncSession, **kwargs: Any) -> Part:
    if "arrangement_id" not in kwargs:
        kwargs["arrangement_id"] = (await make_arrangement(session)).id
    if "uploaded_by" not in kwargs:
        kwargs["uploaded_by"] = (await make_user(session)).id
    return await acreate(session, PartFactory, **kwargs)


async def make_tag(session: AsyncSession, **kwargs: Any) -> Tag:
    return await acreate(session, TagFactory, **kwargs)


async def make_annotation(session: AsyncSession, **kwargs: Any) -> Annotation:
    if "user_id" not in kwargs:
        kwargs["user_id"] = (await make_user(session)).id
    if "part_id" not in kwargs:
        kwargs["part_id"] = (await make_part(session)).id
    return await acreate(session, AnnotationFactory, **kwargs)


async def make_setlist(session: AsyncSession, **kwargs: Any) -> Setlist:
    if "owner_id" not in kwargs:
        kwargs["owner_id"] = (await make_user(session)).id
    return await acreate(session, SetlistFactory, **kwargs)


async def make_enrichment_job(session: AsyncSession, **kwargs: Any) -> EnrichmentJob:
    if "arrangement_id" not in kwargs:
        kwargs["arrangement_id"] = (await make_arrangement(session)).id
    return await acreate(session, EnrichmentJobFactory, **kwargs)


__all__ = [
    "AnnotationFactory",
    "AnnotationRevisionFactory",
    "ArrangementFactory",
    "ArrangementTagFactory",
    "EnrichmentJobFactory",
    "PartFactory",
    "SetlistFactory",
    "SetlistItemFactory",
    "TagFactory",
    "UserFactory",
    "UserSettingsFactory",
    "acreate",
    "make_annotation",
    "make_arrangement",
    "make_enrichment_job",
    "make_part",
    "make_setlist",
    "make_tag",
    "make_user",
]
