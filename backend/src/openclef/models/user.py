"""User and UserSettings ORM models.

`User.username` is `citext` so case-insensitive uniqueness comes "for
free" from the citext extension's index behavior. `password_hash` is
nullable because OIDC-only users have no local password (auth landing
in ticket 0136 fills this in; the column shape is locked here).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Text, Uuid
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openclef.db import Base
from openclef.models._types import pg_enum, utcnow_aware
from openclef.models.enums import Theme, UserRole

if TYPE_CHECKING:
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(CITEXT(), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(CITEXT(), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(Text(), nullable=True)
    oidc_sub: Mapped[str | None] = mapped_column(Text(), nullable=True, unique=True)
    role: Mapped[UserRole] = mapped_column(
        pg_enum(UserRole, name="user_role"), nullable=False, default=UserRole.USER
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=utcnow_aware(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=utcnow_aware(), onupdate=utcnow_aware(), nullable=False
    )

    settings: Mapped["UserSettings | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_users_oidc_sub", "oidc_sub", unique=True, postgresql_where="oidc_sub IS NOT NULL"),
    )


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    theme: Mapped[Theme] = mapped_column(
        pg_enum(Theme, name="theme"), nullable=False, default=Theme.SYSTEM
    )
    enrichment_default_enabled: Mapped[bool] = mapped_column(nullable=False, default=False)
    enrichment_providers_jsonb: Mapped[list] = mapped_column(
        JSONB(),
        nullable=False,
        default=lambda: [{"provider": "musicbrainz", "enabled": True}],
    )
    preferences_jsonb: Mapped[dict] = mapped_column(JSONB(), nullable=False, default=dict)

    user: Mapped[User] = relationship(back_populates="settings")
