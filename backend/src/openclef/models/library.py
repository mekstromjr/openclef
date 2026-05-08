"""Arrangement, Part, Tag — the core library entities.

`Arrangement.search_vector` exists in the DB as a generated tsvector
column with a GIN index, but is intentionally **not declared on the
ORM model** — it's read-only from the app's perspective and only ever
used inside FTS WHERE clauses (raw SQL or `func.to_tsvector`). Keeping
it out of the ORM avoids accidental SELECT-ing the large vector blob
and keeps `Base.metadata` aligned with hand-written migration logic.

`Part.file_hash_sha256` is indexed but reserved — no UI consumer in
v1. Kept indexed because adding the index later on a populated table
would require a downtime maintenance window.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, SmallInteger, Text, Uuid, text
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openclef.db import Base
from openclef.models._types import pg_enum, utcnow_aware
from openclef.models.enums import EditionType, KeySignature, PartType, Period
from openclef.models.user import User


class Arrangement(Base):
    __tablename__ = "arrangements"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(Text(), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(Text(), nullable=True)
    alternative_titles: Mapped[list[str]] = mapped_column(
        ARRAY(Text()), nullable=False, server_default=text("'{}'")
    )
    composer: Mapped[list[str]] = mapped_column(
        ARRAY(Text()), nullable=False, server_default=text("'{}'")
    )
    arranger: Mapped[list[str]] = mapped_column(
        ARRAY(Text()), nullable=False, server_default=text("'{}'")
    )
    lyricist: Mapped[list[str]] = mapped_column(
        ARRAY(Text()), nullable=False, server_default=text("'{}'")
    )
    instrumentation: Mapped[list[str]] = mapped_column(
        ARRAY(Text()), nullable=False, server_default=text("'{}'")
    )
    key_signature: Mapped[KeySignature | None] = mapped_column(
        pg_enum(KeySignature, name="key_signature"), nullable=True
    )
    opus_catalog_number: Mapped[str | None] = mapped_column(Text(), nullable=True)
    period: Mapped[Period | None] = mapped_column(pg_enum(Period, name="period"), nullable=True)
    difficulty: Mapped[int | None] = mapped_column(SmallInteger(), nullable=True)
    edition_type: Mapped[EditionType | None] = mapped_column(
        pg_enum(EditionType, name="edition_type"), nullable=True
    )
    publisher: Mapped[str | None] = mapped_column(Text(), nullable=True)
    publication_year: Mapped[int | None] = mapped_column(SmallInteger(), nullable=True)
    composition_year: Mapped[int | None] = mapped_column(SmallInteger(), nullable=True)
    language: Mapped[list[str]] = mapped_column(
        ARRAY(Text()), nullable=False, server_default=text("'{}'")
    )
    duration_minutes: Mapped[int | None] = mapped_column(SmallInteger(), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    external_links_jsonb: Mapped[list | None] = mapped_column(JSONB(), nullable=True)
    musicbrainz_work_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), nullable=True)
    source_metadata_jsonb: Mapped[dict | None] = mapped_column(JSONB(), nullable=True)
    field_origins_jsonb: Mapped[dict | None] = mapped_column(JSONB(), nullable=True)
    movements: Mapped[list | None] = mapped_column(JSONB(), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=utcnow_aware(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=utcnow_aware(), onupdate=utcnow_aware(), nullable=False
    )

    parts: Mapped[list["Part"]] = relationship(
        back_populates="arrangement", cascade="all, delete-orphan", lazy="raise"
    )
    tags: Mapped[list["Tag"]] = relationship(
        secondary="arrangement_tags", back_populates="arrangements", lazy="raise"
    )

    __table_args__ = (
        Index("ix_arrangements_musicbrainz_work_id", "musicbrainz_work_id"),
    )


class Part(Base):
    __tablename__ = "parts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    arrangement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("arrangements.id", ondelete="CASCADE"), nullable=False
    )
    part_type: Mapped[PartType] = mapped_column(
        pg_enum(PartType, name="part_type"), nullable=False
    )
    label: Mapped[str] = mapped_column(Text(), nullable=False)
    instrument: Mapped[str | None] = mapped_column(Text(), nullable=True)
    page_count: Mapped[int] = mapped_column(SmallInteger(), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text(), nullable=False)
    thumbnail_storage_key: Mapped[str | None] = mapped_column(Text(), nullable=True)
    file_hash_sha256: Mapped[str | None] = mapped_column(Text(), nullable=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=utcnow_aware(), nullable=False)

    arrangement: Mapped[Arrangement] = relationship(back_populates="parts")

    __table_args__ = (
        Index("ix_parts_arrangement_id", "arrangement_id"),
        Index("ix_parts_file_hash_sha256", "file_hash_sha256"),
    )


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(CITEXT(), unique=True, nullable=False)

    arrangements: Mapped[list[Arrangement]] = relationship(
        secondary="arrangement_tags", back_populates="tags", lazy="raise"
    )


class ArrangementTag(Base):
    __tablename__ = "arrangement_tags"

    arrangement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("arrangements.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
    added_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # No `relationship` here — Arrangement.tags / Tag.arrangements use
    # `secondary="arrangement_tags"` and treat this as a pure join table.


__all__ = ["Arrangement", "Part", "Tag", "ArrangementTag"]
