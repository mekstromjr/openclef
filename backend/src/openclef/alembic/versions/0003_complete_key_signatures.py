"""Complete the key_signature enum: all 30 standard key signatures.

The Phase 1 enum folded enharmonic keys into one spelling (G-flat major
into F-sharp major, and so on). That suits audio metadata, but sheet
music is about notation: a six-flat score and a six-sharp score are
written differently, so the spelling is part of the data. This adds the
six missing keys, placed in circle-of-fifths order so enum sorting stays
musical:

    major: ... F#, C#, Cb, Gb, Db ...
    minor: ... G#, D#, A#, Ab, Eb ...

Revision ID: 0003_complete_key_signatures
Revises: 0002_phase1_schema
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_complete_key_signatures"
down_revision: str | None = "0002_phase1_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (new value, existing value it goes after). Order matters: each anchor
# exists by the time its line runs.
_ADDITIONS = [
    ("C# major", "F# major"),
    ("Cb major", "C# major"),
    ("Gb major", "Cb major"),
    ("D# minor", "G# minor"),
    ("A# minor", "D# minor"),
    ("Ab minor", "A# minor"),
]


def upgrade() -> None:
    for value, after in _ADDITIONS:
        op.execute(f"ALTER TYPE key_signature ADD VALUE IF NOT EXISTS '{value}' AFTER '{after}'")


def downgrade() -> None:
    # Postgres can't drop a value from an enum type. Leaving the extra
    # values is harmless to 0002; a full downgrade drops the type anyway.
    pass
