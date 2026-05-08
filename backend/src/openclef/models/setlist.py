"""Setlists + items (Phase 2 schema, locked in Phase 1).

Like the annotation tables, the schema is created now so the future
Phase 2 UI doesn't require a destructive migration. `setlist_items`
uses (setlist_id, position) as the composite PK so reordering is a
clean update of `position` values without identity churn.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, SmallInteger, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openclef.db import Base
from openclef.models._types import utcnow_aware


class Setlist(Base):
    __tablename__ = "setlists"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text(), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=utcnow_aware(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=utcnow_aware(), onupdate=utcnow_aware(), nullable=False
    )

    items: Mapped[list["SetlistItem"]] = relationship(
        back_populates="setlist",
        cascade="all, delete-orphan",
        order_by="SetlistItem.position",
        lazy="raise",
    )


class SetlistItem(Base):
    __tablename__ = "setlist_items"

    setlist_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("setlists.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(SmallInteger(), primary_key=True)
    arrangement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("arrangements.id", ondelete="RESTRICT"), nullable=False
    )
    part_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("parts.id", ondelete="SET NULL"), nullable=True
    )

    setlist: Mapped[Setlist] = relationship(back_populates="items")


__all__ = ["Setlist", "SetlistItem"]
