"""Smoke test for the generated `arrangements.search_vector` tsvector.

Catches typos in the GENERATED ALWAYS AS expression, which would silently
produce empty vectors and make every FTS query return nothing.
"""
from __future__ import annotations

from sqlalchemy import bindparam, func, text

from openclef.models.library import Arrangement
from tests.factories import make_arrangement


async def test_fts_finds_arrangement_by_title(session):
    await make_arrangement(session, title="Moonlight Sonata", composer=["Beethoven, Ludwig van"])
    await make_arrangement(session, title="Pathétique Sonata", composer=["Beethoven, Ludwig van"])
    await make_arrangement(session, title="Eine kleine Nachtmusik", composer=["Mozart, Wolfgang Amadeus"])

    rows = (
        await session.execute(
            text(
                "SELECT title FROM arrangements "
                "WHERE search_vector @@ websearch_to_tsquery('english', :q) "
                "ORDER BY ts_rank(search_vector, websearch_to_tsquery('english', :q)) DESC"
            ).bindparams(bindparam("q", "moonlight"))
        )
    ).scalars().all()
    assert rows == ["Moonlight Sonata"]


async def test_fts_finds_arrangement_by_composer(session):
    await make_arrangement(session, title="Symphony No. 5", composer=["Beethoven, Ludwig van"])
    await make_arrangement(session, title="Symphony No. 41 'Jupiter'", composer=["Mozart, Wolfgang Amadeus"])

    rows = (
        await session.execute(
            text(
                "SELECT title FROM arrangements "
                "WHERE search_vector @@ websearch_to_tsquery('english', :q)"
            ).bindparams(bindparam("q", "beethoven"))
        )
    ).scalars().all()
    assert rows == ["Symphony No. 5"]


async def test_fts_combines_title_and_arranger(session):
    await make_arrangement(
        session,
        title="Ave Maria",
        composer=["Schubert, Franz"],
        arranger=["Liszt, Franz"],
    )
    rows = (
        await session.execute(
            text(
                "SELECT title FROM arrangements "
                "WHERE search_vector @@ websearch_to_tsquery('english', :q)"
            ).bindparams(bindparam("q", "liszt"))
        )
    ).scalars().all()
    assert rows == ["Ave Maria"]


def _Arrangement_func_alias():  # pragma: no cover
    return Arrangement, func
