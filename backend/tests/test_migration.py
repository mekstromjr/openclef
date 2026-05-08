"""Migration up/down round-trip.

Verifies `alembic upgrade head` then `alembic downgrade base` leaves a
clean database (no leftover tables, no leftover enum types) — protects
against asymmetric upgrade/downgrade in future revisions.

Uses its OWN ephemeral container (independent of the session-scoped
test postgres) so the destructive downgrade can't poison other tests.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

# DOCKER_HOST is patched in conftest._ensure_docker_host before this
# module imports testcontainers. Importing here is fine.
try:
    from testcontainers.postgres import PostgresContainer
except Exception:  # pragma: no cover
    PostgresContainer = None


_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


@pytest.fixture(scope="module")
def fresh_postgres():
    if PostgresContainer is None:
        pytest.skip("testcontainers not importable")
    try:
        container = PostgresContainer("postgres:16.6-alpine", driver="psycopg2")
        container.start()
    except Exception as exc:
        pytest.skip(f"Docker unavailable: {exc}")
    yield container
    container.stop()


def test_upgrade_then_downgrade_is_clean(fresh_postgres):
    sync_url = fresh_postgres.get_connection_url()
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", sync_url)

    command.upgrade(cfg, "head")

    eng = create_engine(sync_url)
    with eng.connect() as conn:
        # 11 tables expected (excluding alembic_version)
        rows = conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname='public' AND tablename != 'alembic_version' "
                "ORDER BY tablename"
            )
        ).scalars().all()
        assert sorted(rows) == [
            "annotation_revisions",
            "annotations",
            "arrangement_tags",
            "arrangements",
            "enrichment_jobs",
            "parts",
            "setlist_items",
            "setlists",
            "tags",
            "user_settings",
            "users",
        ]
        # search_vector + GIN index are present
        sv_exists = conn.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_name='arrangements' AND column_name='search_vector')"
            )
        ).scalar()
        assert sv_exists is True
        gin_exists = conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname='ix_arrangements_search_vector')")
        ).scalar()
        assert gin_exists is True

    command.downgrade(cfg, "base")

    with eng.connect() as conn:
        # No domain tables should remain (alembic_version is left by alembic itself)
        rows = conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname='public' AND tablename != 'alembic_version'"
            )
        ).scalars().all()
        assert rows == []
        # Enum types are dropped
        enums = conn.execute(
            text(
                "SELECT typname FROM pg_type "
                "WHERE typname IN ('user_role','theme','key_signature','period','edition_type','part_type','enrichment_job_status')"
            )
        ).scalars().all()
        assert enums == []
