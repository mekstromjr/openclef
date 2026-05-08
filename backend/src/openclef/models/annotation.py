"""Annotations + revision history (Phase 2 schema, locked in Phase 1).

The schema lives in this migration so the eventual Phase 2 UI rollout
doesn't require a destructive ALTER on a populated table to add
`user_id` (per-user annotation scope) or `current_revision_id`
(undo/redo history).

Storage shape: one `annotations` row per (user, part, page); one
`annotation_revisions` row per save-point. The HEAD pointer
(`annotations.current_revision_id`) lets undo/redo walk the
parent_revision_id chain without rewriting history.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, SmallInteger, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openclef.db import Base
from openclef.models._types import utcnow_aware


class Annotation(Base):
    __tablename__ = "annotations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    part_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("parts.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(SmallInteger(), nullable=False)
    # HEAD pointer into annotation_revisions. Nullable to break the
    # chicken-and-egg with the FK (insert annotation, insert first
    # revision, then update the pointer).
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        ForeignKey("annotation_revisions.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=utcnow_aware(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=utcnow_aware(), onupdate=utcnow_aware(), nullable=False
    )

    revisions: Mapped[list["AnnotationRevision"]] = relationship(
        back_populates="annotation",
        cascade="all, delete-orphan",
        foreign_keys="AnnotationRevision.annotation_id",
        lazy="raise",
    )

    __table_args__ = (
        UniqueConstraint("user_id", "part_id", "page_number", name="uq_annotations_user_part_page"),
        Index("ix_annotations_user_part", "user_id", "part_id"),
    )


class AnnotationRevision(Base):
    __tablename__ = "annotation_revisions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    annotation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("annotations.id", ondelete="CASCADE"), nullable=False
    )
    parent_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        ForeignKey("annotation_revisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    payload_jsonb: Mapped[dict] = mapped_column(JSONB(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=utcnow_aware(), nullable=False)
    created_session_id: Mapped[str | None] = mapped_column(Text(), nullable=True)

    annotation: Mapped[Annotation] = relationship(
        back_populates="revisions", foreign_keys=[annotation_id]
    )

    __table_args__ = (
        Index("ix_annotation_revisions_annotation_id", "annotation_id"),
        Index("ix_annotation_revisions_created_at", "created_at"),
    )


__all__ = ["Annotation", "AnnotationRevision"]
