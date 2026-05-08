"""baseline

Revision ID: 0001_baseline
Revises:
Create Date: 2026-05-07

Empty baseline migration. Establishes the alembic_version table so that
ticket 0135 (data model) can layer real schema on top of a known revision.
"""
from __future__ import annotations

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
