"""Setlist entries get ids and outlive their pieces (openclef#64).

- setlist_items.id: a stable id per entry, so an editor can send back
  entries it isn't allowed to see and the server keeps them as they were.
  Existing rows get one here. (setlist_id, position) stays the primary key.
- arrangement_id becomes nullable. Deleting a piece no longer refuses when
  it's on a setlist: its entries stay as "*Title* was deleted by *user*",
  recorded in title_snapshot, deleted_by, deleted_at and piece_owner_id
  (whose piece it was, which decides who may still see the title). The FK
  stays RESTRICT: the delete clears these entries itself before the row goes.
- A CHECK keeps every entry either on a piece or marked deleted.

Revision ID: 0005_setlist_entry_ids
Revises: 0004_sharing
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_setlist_entry_ids"
down_revision: str | None = "0004_sharing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("setlist_items", sa.Column("id", sa.Uuid(), nullable=True))
    op.execute("UPDATE setlist_items SET id = gen_random_uuid()")
    op.alter_column("setlist_items", "id", nullable=False)
    op.create_unique_constraint("uq_setlist_items_id", "setlist_items", ["id"])

    op.alter_column("setlist_items", "arrangement_id", nullable=True)
    op.add_column("setlist_items", sa.Column("title_snapshot", sa.Text(), nullable=True))
    op.add_column(
        "setlist_items",
        sa.Column("deleted_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("setlist_items", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "setlist_items",
        sa.Column("piece_owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_check_constraint(
        "ck_setlist_items_piece_or_deleted",
        "setlist_items",
        "arrangement_id IS NOT NULL OR deleted_at IS NOT NULL",
    )
    op.create_index("ix_setlist_items_arrangement_id", "setlist_items", ["arrangement_id"])


def downgrade() -> None:
    op.drop_index("ix_setlist_items_arrangement_id", table_name="setlist_items")
    op.drop_constraint("ck_setlist_items_piece_or_deleted", "setlist_items", type_="check")
    # Entries for deleted pieces have nothing to point at in the old schema.
    # Drop them and close the gaps they leave in each running order.
    op.execute("DELETE FROM setlist_items WHERE arrangement_id IS NULL")
    op.execute(
        "UPDATE setlist_items SET position = -1 - ranked.new_position FROM ("
        " SELECT setlist_id, position,"
        " row_number() OVER (PARTITION BY setlist_id ORDER BY position) - 1 AS new_position"
        " FROM setlist_items) AS ranked"
        " WHERE setlist_items.setlist_id = ranked.setlist_id AND setlist_items.position = ranked.position"
    )
    op.execute("UPDATE setlist_items SET position = -1 - position")
    op.drop_column("setlist_items", "piece_owner_id")
    op.drop_column("setlist_items", "deleted_at")
    op.drop_column("setlist_items", "deleted_by")
    op.drop_column("setlist_items", "title_snapshot")
    op.alter_column("setlist_items", "arrangement_id", nullable=False)
    op.drop_constraint("uq_setlist_items_id", "setlist_items", type_="unique")
    op.drop_column("setlist_items", "id")
