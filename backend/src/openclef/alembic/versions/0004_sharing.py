"""Sharing model: owners, partners, groups and shares (openclef#61).

Replaces the pooled library with personal libraries. Each arrangement and
setlist has one owner; others see it only through a partnership, a group
share or a setlist share (see openclef.services.access).

- arrangements.created_by becomes owner_id (same values: the creator owns it).
- New tables: partnerships, groups, group_members, arrangement_shares,
  setlist_shares (+ the share_permission enum).
- setlist_items.added_by records who put each piece on a setlist; existing
  rows are credited to the setlist's owner.

Revision ID: 0004_sharing
Revises: 0003_complete_key_signatures
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_sharing"
down_revision: str | None = "0003_complete_key_signatures"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_USER_FK = dict(ondelete="CASCADE")


def upgrade() -> None:
    op.alter_column("arrangements", "created_by", new_column_name="owner_id")
    op.create_index("ix_arrangements_owner_id", "arrangements", ["owner_id"])
    op.create_index("ix_setlists_owner_id", "setlists", ["owner_id"])

    share_permission = postgresql.ENUM("view", "contribute", name="share_permission", create_type=False)
    share_permission.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "partnerships",
        sa.Column("sharer_id", sa.Uuid(), sa.ForeignKey("users.id", **_USER_FK), primary_key=True),
        sa.Column("partner_id", sa.Uuid(), sa.ForeignKey("users.id", **_USER_FK), primary_key=True),
        sa.Column("show_in_library", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("sharer_id <> partner_id", name="ck_partnerships_not_self"),
    )
    op.create_index("ix_partnerships_partner_id", "partnerships", ["partner_id"])

    op.create_table(
        "groups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", **_USER_FK), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "group_members",
        sa.Column("group_id", sa.Uuid(), sa.ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", **_USER_FK), primary_key=True),
    )
    op.create_index("ix_group_members_user_id", "group_members", ["user_id"])

    op.create_table(
        "arrangement_shares",
        sa.Column(
            "arrangement_id", sa.Uuid(), sa.ForeignKey("arrangements.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("group_id", sa.Uuid(), sa.ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_index("ix_arrangement_shares_group_id", "arrangement_shares", ["group_id"])

    op.create_table(
        "setlist_shares",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("setlist_id", sa.Uuid(), sa.ForeignKey("setlists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", **_USER_FK), nullable=True),
        sa.Column("group_id", sa.Uuid(), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=True),
        sa.Column("permission", share_permission, nullable=False),
        sa.CheckConstraint("(user_id IS NULL) <> (group_id IS NULL)", name="ck_setlist_shares_one_target"),
    )
    op.create_index(
        "ux_setlist_shares_user", "setlist_shares", ["setlist_id", "user_id"],
        unique=True, postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index(
        "ux_setlist_shares_group", "setlist_shares", ["setlist_id", "group_id"],
        unique=True, postgresql_where=sa.text("group_id IS NOT NULL"),
    )
    op.create_index("ix_setlist_shares_user_id", "setlist_shares", ["user_id"])
    op.create_index("ix_setlist_shares_group_id", "setlist_shares", ["group_id"])

    op.add_column(
        "setlist_items",
        sa.Column("added_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.execute(
        "UPDATE setlist_items SET added_by = setlists.owner_id "
        "FROM setlists WHERE setlists.id = setlist_items.setlist_id"
    )


def downgrade() -> None:
    op.drop_column("setlist_items", "added_by")
    op.drop_table("setlist_shares")
    op.drop_table("arrangement_shares")
    op.drop_table("group_members")
    op.drop_table("groups")
    op.drop_table("partnerships")
    postgresql.ENUM(name="share_permission").drop(op.get_bind(), checkfirst=True)
    op.drop_index("ix_setlists_owner_id", table_name="setlists")
    op.drop_index("ix_arrangements_owner_id", table_name="arrangements")
    op.alter_column("arrangements", "owner_id", new_column_name="created_by")
