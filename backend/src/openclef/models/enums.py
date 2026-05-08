"""Controlled vocabularies for the openclef data model.

These enums correspond to PostgreSQL ENUM types created in the Phase 1
migration. The names (UPPER_SNAKE_CASE) are what's stored on the wire
and in the DB; the values are display strings consumers can use as-is
or translate.

Adding a value: append to the enum, write a new migration that does
`ALTER TYPE … ADD VALUE …`. PG enum additions are non-destructive.

Renaming/removing a value: requires a full enum rebuild (create new
type, swap column, drop old). Treat as a breaking change and follow
the migration policy in TRD §10.1.
"""
from __future__ import annotations

from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"


class Theme(str, Enum):
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class KeySignature(str, Enum):
    """24 tonal keys (12 majors + 12 minors) plus 4 catch-all values.

    Enharmonic spellings collapse to a canonical form per circle-of-fifths
    convention: sharp-side keys use sharps, flat-side keys use flats.
    Users entering an unusual enharmonic spelling at upload pick the
    closest canonical key; the original spelling lives in `notes`.
    """

    # Majors
    C_MAJOR = "C major"
    G_MAJOR = "G major"
    D_MAJOR = "D major"
    A_MAJOR = "A major"
    E_MAJOR = "E major"
    B_MAJOR = "B major"
    F_SHARP_MAJOR = "F# major"
    D_FLAT_MAJOR = "Db major"
    A_FLAT_MAJOR = "Ab major"
    E_FLAT_MAJOR = "Eb major"
    B_FLAT_MAJOR = "Bb major"
    F_MAJOR = "F major"

    # Minors
    A_MINOR = "A minor"
    E_MINOR = "E minor"
    B_MINOR = "B minor"
    F_SHARP_MINOR = "F# minor"
    C_SHARP_MINOR = "C# minor"
    G_SHARP_MINOR = "G# minor"
    E_FLAT_MINOR = "Eb minor"
    B_FLAT_MINOR = "Bb minor"
    F_MINOR = "F minor"
    C_MINOR = "C minor"
    G_MINOR = "G minor"
    D_MINOR = "D minor"

    # Non-tonal / unspecified
    ATONAL = "Atonal"
    MODAL = "Modal"
    NONE = "None"
    MULTIPLE = "Multiple"


class Period(str, Enum):
    """IMSLP-aligned period taxonomy. Ten values per TRD §3."""

    MEDIEVAL = "Medieval"
    RENAISSANCE = "Renaissance"
    BAROQUE = "Baroque"
    CLASSICAL = "Classical"
    EARLY_ROMANTIC = "Early Romantic"
    ROMANTIC = "Romantic"
    LATE_ROMANTIC = "Late Romantic"
    MODERN = "Modern"
    CONTEMPORARY = "Contemporary"
    VARIOUS = "Various"


class EditionType(str, Enum):
    URTEXT = "Urtext"
    PERFORMANCE = "Performance"
    CRITICAL = "Critical"
    FACSIMILE = "Facsimile"
    ARRANGEMENT = "Arrangement"


class PartType(str, Enum):
    FULL_SCORE = "Full Score"
    CONDUCTOR_SCORE = "Conductor Score"
    PIANO_REDUCTION = "Piano Reduction"
    VOCAL_SCORE = "Vocal Score"
    OTHER = "Other"


class EnrichmentJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    NO_MATCH = "no_match"
    FAILED = "failed"
