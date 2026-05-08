"""Shared column types and helpers used across the openclef ORM layer.

`pg_enum` is the canonical way to declare a PostgreSQL ENUM column from
a Python Enum: it uses the enum's `value` attribute as the wire format
(matching what's documented in enums.py) and reuses the same type across
tables instead of creating a duplicate per-column.

`utcnow_aware` is the timestamp default used everywhere — `func.now()`
emits PG's `now()` which is timezone-aware and resolves to the
transaction-start time. Don't replace with `datetime.utcnow()`; that's
naive and we'd lose tz info.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects import postgresql


def pg_enum(enum_cls: type[Enum], name: str | None = None, **kwargs: Any) -> postgresql.ENUM:
    """Build a PG ENUM column type from a Python Enum.

    Defaults to using `.value` for the wire format and a stable type name
    (kebab-cased Python class name) so Alembic autogenerate produces
    consistent migrations.
    """
    type_name = name or enum_cls.__name__.lower()
    return postgresql.ENUM(
        enum_cls,
        name=type_name,
        values_callable=lambda x: [e.value for e in x],
        create_type=True,
        **kwargs,
    )


def utcnow_aware():
    """Server-side timezone-aware now()."""
    return func.now()
