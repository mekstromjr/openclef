"""Setlists + items.

Like the annotation tables, the schema is created now so the future
Phase 2 UI doesn't require a destructive migration. `setlist_items`
uses (setlist_id, position) as the composite PK; each entry also has a
stable `id` so an editor can send back entries it can't see (openclef#64).
An entry outlives its piece: deleting the piece marks the entry deleted and
keeps the title it had.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, SmallInteger, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openclef.db import Base
from openclef.models._types import utcnow_aware


class Setlist(Base):
    __tablename__ = "setlists"
    __table_args__ = (Index("ix_setlists_owner_id", "owner_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text(), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=utcnow_aware(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=utcnow_aware(), onupdate=utcnow_aware(), nullable=False
    )

    items: Mapped[list["SetlistItem"]] = relationship(
        back_populates="setlist",
        cascade="all, delete-orphan",
        order_by="SetlistItem.position",
        lazy="raise",
    )


class SetlistItem(Base):
    __tablename__ = "setlist_items"
    __table_args__ = (
        CheckConstraint(
            "arrangement_id IS NOT NULL OR deleted_at IS NOT NULL", name="ck_setlist_items_piece_or_deleted"
        ),
        Index("ix_setlist_items_arrangement_id", "arrangement_id"),
        UniqueConstraint("id", name="uq_setlist_items_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False, default=uuid.uuid4)
    setlist_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("setlists.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(SmallInteger(), primary_key=True)
    # None once the piece is deleted (see the deleted_* columns).
    arrangement_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("arrangements.id", ondelete="RESTRICT"), nullable=True
    )
    part_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("parts.id", ondelete="SET NULL"), nullable=True
    )
    # Who put the piece here. A shared setlist passes a piece on to its
    # audience only when the person who added it owns it (openclef#60).
    added_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Set together when the piece is deleted: its title then, who deleted it
    # and when, and whose piece it was (that decides who may still see the
    # title, see routers.setlists).
    title_snapshot: Mapped[str | None] = mapped_column(Text(), nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    piece_owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    setlist: Mapped[Setlist] = relationship(back_populates="items")


__all__ = ["Setlist", "SetlistItem"]
