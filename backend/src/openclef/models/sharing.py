"""Sharing: partners, groups, and what is shared with them (openclef#60).

Every arrangement and setlist has one owner and is private by default.
Others reach it through one of these tables; the rule that combines them
lives in `openclef.services.access`, and every read goes through it.

- `partnerships` is one-way: a row (sharer, partner) gives the partner the
  sharer's whole library. It does not chain to the partner's partners.
- `groups` are sets of members. Owners share individual arrangements
  (`arrangement_shares`) or setlists (`setlist_shares`) with a group.
- `setlist_shares` may also target a single user, with view or contribute
  permission.

The API for creating these rows arrives with openclef#62-#64; the schema
lands first so the access rule is complete and testable.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from openclef.db import Base
from openclef.models._types import pg_enum, utcnow_aware
from openclef.models.enums import SharePermission


class Partnership(Base):
    __tablename__ = "partnerships"

    sharer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    partner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # The partner's choice: show these items in my main library.
    show_in_library: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=utcnow_aware(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("sharer_id <> partner_id", name="ck_partnerships_not_self"),
        Index("ix_partnerships_partner_id", "partner_id"),
    )


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text(), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=utcnow_aware(), nullable=False
    )


class GroupMember(Base):
    __tablename__ = "group_members"

    group_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (Index("ix_group_members_user_id", "user_id"),)


class ArrangementShare(Base):
    __tablename__ = "arrangement_shares"

    arrangement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("arrangements.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (Index("ix_arrangement_shares_group_id", "group_id"),)


class SetlistShare(Base):
    __tablename__ = "setlist_shares"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    setlist_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("setlists.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("groups.id", ondelete="CASCADE"), nullable=True
    )
    permission: Mapped[SharePermission] = mapped_column(
        pg_enum(SharePermission, name="share_permission"), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "(user_id IS NULL) <> (group_id IS NULL)", name="ck_setlist_shares_one_target"
        ),
        Index(
            "ux_setlist_shares_user", "setlist_id", "user_id",
            unique=True, postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index(
            "ux_setlist_shares_group", "setlist_id", "group_id",
            unique=True, postgresql_where=text("group_id IS NOT NULL"),
        ),
        Index("ix_setlist_shares_user_id", "user_id"),
        Index("ix_setlist_shares_group_id", "group_id"),
    )


__all__ = ["ArrangementShare", "Group", "GroupMember", "Partnership", "SetlistShare"]
