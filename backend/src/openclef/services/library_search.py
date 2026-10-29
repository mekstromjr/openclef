"""Library listing: full-text search, facet filters, facet counts.

Search uses the generated `arrangements.search_vector` (title, subtitle,
alternative titles, composer, arranger, instrumentation). Every word of
the query becomes a prefix match, so results narrow while the user is
still typing ("moon" finds "Moonlight Sonata").
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import Select, and_, func, literal_column, select
from sqlalchemy.sql.elements import ColumnElement

from openclef.models.enums import KeySignature, Period
from openclef.models.library import Arrangement, ArrangementTag, Tag

SEARCH_VECTOR = literal_column("arrangements.search_vector")
MAX_QUERY_WORDS = 8
FACET_LIMIT = 30


def prefix_tsquery(q: str) -> str | None:
    """'Moonlight son' -> 'moonlight:* & son:*' for to_tsquery. Only word
    characters survive, so user input can't inject tsquery operators."""
    words = re.findall(r"\w+", q.lower())[:MAX_QUERY_WORDS]
    return " & ".join(f"{word}:*" for word in words) or None


@dataclass
class LibraryFilters:
    q: str | None = None
    instrument: list[str] = field(default_factory=list)
    composer: str | None = None
    key: KeySignature | None = None
    period: Period | None = None
    difficulty: int | None = None
    tag: str | None = None

    def tsquery(self) -> str | None:
        return prefix_tsquery(self.q) if self.q else None

    def conditions(self, *, skip: str | None = None) -> list[ColumnElement[bool]]:
        """WHERE clauses for every active filter, except the facet `skip`."""
        clauses: list[ColumnElement[bool]] = []
        if (tsq := self.tsquery()) is not None:
            clauses.append(SEARCH_VECTOR.op("@@")(func.to_tsquery("english", tsq)))
        if self.instrument and skip != "instrument":
            clauses.append(Arrangement.instrumentation.contains(self.instrument))
        if self.composer and skip != "composer":
            clauses.append(Arrangement.composer.contains([self.composer]))
        if self.key and skip != "key":
            clauses.append(Arrangement.key_signature == self.key)
        if self.period and skip != "period":
            clauses.append(Arrangement.period == self.period)
        if self.difficulty and skip != "difficulty":
            clauses.append(Arrangement.difficulty == self.difficulty)
        if self.tag and skip != "tag":
            clauses.append(
                select(ArrangementTag.arrangement_id)
                .join(Tag, Tag.id == ArrangementTag.tag_id)
                .where(ArrangementTag.arrangement_id == Arrangement.id, Tag.name == self.tag)
                .exists()
            )
        return clauses


def _array_facet(column, filters: LibraryFilters, name: str) -> Select:
    value = func.unnest(column).label("value")
    inner = select(value).where(and_(True, *filters.conditions(skip=name))).subquery()
    return (
        select(inner.c.value, func.count().label("count"))
        .group_by(inner.c.value)
        .order_by(func.count().desc(), inner.c.value)
        .limit(FACET_LIMIT)
    )


def _scalar_facet(column, filters: LibraryFilters, name: str) -> Select:
    return (
        select(column.label("value"), func.count().label("count"))
        .where(column.is_not(None), *filters.conditions(skip=name))
        .group_by(column)
        .order_by(func.count().desc(), column)
        .limit(FACET_LIMIT)
    )


def _tag_facet(filters: LibraryFilters) -> Select:
    return (
        select(Tag.name.label("value"), func.count().label("count"))
        .join(ArrangementTag, ArrangementTag.tag_id == Tag.id)
        .join(Arrangement, Arrangement.id == ArrangementTag.arrangement_id)
        .where(and_(True, *filters.conditions(skip="tag")))
        .group_by(Tag.name)
        .order_by(func.count().desc(), Tag.name)
        .limit(FACET_LIMIT)
    )


def facet_queries(filters: LibraryFilters) -> dict[str, Select]:
    return {
        "instrument": _array_facet(Arrangement.instrumentation, filters, "instrument"),
        "composer": _array_facet(Arrangement.composer, filters, "composer"),
        "key": _scalar_facet(Arrangement.key_signature, filters, "key"),
        "period": _scalar_facet(Arrangement.period, filters, "period"),
        "difficulty": _scalar_facet(Arrangement.difficulty, filters, "difficulty"),
        "tag": _tag_facet(filters),
    }


def order_by(filters: LibraryFilters, sort: str):
    if sort == "title":
        return [func.lower(Arrangement.title), Arrangement.id]
    if sort == "recent" or (tsq := filters.tsquery()) is None:
        return [Arrangement.created_at.desc(), Arrangement.id]
    rank = func.ts_rank(SEARCH_VECTOR, func.to_tsquery("english", tsq))
    return [rank.desc(), func.lower(Arrangement.title), Arrangement.id]
