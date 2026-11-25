"""Migration up/down round-trip.

Verifies `alembic upgrade head` then `alembic downgrade base` leaves a
clean database (no leftover tables, no leftover enum types) — protects
against asymmetric upgrade/downgrade in future revisions.

Uses its OWN ephemeral container (independent of the session-scoped
test postgres) so the destructive downgrade can't poison other tests.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, make_url, text

# DOCKER_HOST is patched in conftest._ensure_docker_host before this
# module imports testcontainers. Importing here is fine.
try:
    from testcontainers.postgres import PostgresContainer
except Exception:  # pragma: no cover
    PostgresContainer = None


_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


@pytest.fixture(scope="module")
def fresh_database_url():
    """Sync URL of an empty database this module may destroy.

    In CI (OPENCLEF_TEST_DATABASE_URL set) a scratch database is created on
    the shared service Postgres and dropped afterwards; locally a dedicated
    container is started.
    """
    external_url = os.environ.get("OPENCLEF_TEST_DATABASE_URL")
    if external_url:
        server_url = make_url(external_url.replace("+asyncpg", ""))
        scratch_name = f"openclef_migration_{uuid.uuid4().hex[:8]}"
        admin_engine = create_engine(server_url, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{scratch_name}"'))
        try:
            yield server_url.set(database=scratch_name).render_as_string(hide_password=False)
        finally:
            with admin_engine.connect() as conn:
                conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch_name}" WITH (FORCE)'))
            admin_engine.dispose()
        return

    if PostgresContainer is None:
        pytest.skip("testcontainers not importable")
    try:
        container = PostgresContainer("postgres:16.6-alpine", driver="psycopg2")
        container.start()
    except Exception as exc:
        pytest.skip(f"Docker unavailable: {exc}")
    yield container.get_connection_url()
    container.stop()


def test_upgrade_then_downgrade_is_clean(fresh_database_url):
    sync_url = fresh_database_url
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", sync_url)

    command.upgrade(cfg, "head")

    eng = create_engine(sync_url)
    with eng.connect() as conn:
        # 16 tables expected (excluding alembic_version)
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
            "arrangement_shares",
            "arrangement_tags",
            "arrangements",
            "enrichment_jobs",
            "group_members",
            "groups",
            "partnerships",
            "parts",
            "setlist_items",
            "setlist_shares",
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
                "WHERE typname IN ('user_role','theme','key_signature','period','edition_type','part_type','enrichment_job_status','share_permission')"
            )
        ).scalars().all()
        assert enums == []


def test_sharing_migration_keeps_existing_rows(fresh_database_url):
    """0004 renames the owner column and credits existing setlist items to
    the setlist's owner, without touching the data."""
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", fresh_database_url)
    command.upgrade(cfg, "0003_complete_key_signatures")

    eng = create_engine(fresh_database_url)
    user_id, arrangement_id, setlist_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with eng.begin() as conn:
        conn.execute(text("INSERT INTO users (id, username, role) VALUES (:id, 'owner', 'user')"), {"id": user_id})
        conn.execute(
            text("INSERT INTO arrangements (id, title, created_by) VALUES (:id, 'Trio', :owner)"),
            {"id": arrangement_id, "owner": user_id},
        )
        conn.execute(
            text("INSERT INTO setlists (id, name, owner_id) VALUES (:id, 'Recital', :owner)"),
            {"id": setlist_id, "owner": user_id},
        )
        conn.execute(
            text("INSERT INTO setlist_items (setlist_id, position, arrangement_id) VALUES (:s, 0, :a)"),
            {"s": setlist_id, "a": arrangement_id},
        )

    command.upgrade(cfg, "head")
    with eng.connect() as conn:
        assert conn.execute(text("SELECT owner_id FROM arrangements")).scalar_one() == user_id
        assert conn.execute(text("SELECT added_by FROM setlist_items")).scalar_one() == user_id

    command.downgrade(cfg, "0003_complete_key_signatures")
    with eng.connect() as conn:
        assert conn.execute(text("SELECT created_by FROM arrangements")).scalar_one() == user_id
    command.downgrade(cfg, "base")
    eng.dispose()


def test_entry_ids_migration_backfills_and_downgrades(fresh_database_url):
    """0005 gives existing entries ids; going back drops entries for deleted
    pieces and closes the gaps they leave in the running order."""
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", fresh_database_url)
    command.upgrade(cfg, "0004_sharing")

    eng = create_engine(fresh_database_url)
    user_id, arrangement_id, setlist_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with eng.begin() as conn:
        conn.execute(text("INSERT INTO users (id, username, role) VALUES (:id, 'owner', 'user')"), {"id": user_id})
        conn.execute(
            text("INSERT INTO arrangements (id, title, owner_id) VALUES (:id, 'Trio', :owner)"),
            {"id": arrangement_id, "owner": user_id},
        )
        conn.execute(
            text("INSERT INTO setlists (id, name, owner_id) VALUES (:id, 'Recital', :owner)"),
            {"id": setlist_id, "owner": user_id},
        )
        for position in range(3):
            conn.execute(
                text("INSERT INTO setlist_items (setlist_id, position, arrangement_id) VALUES (:s, :p, :a)"),
                {"s": setlist_id, "p": position, "a": arrangement_id},
            )

    command.upgrade(cfg, "head")
    with eng.begin() as conn:
        ids = conn.execute(text("SELECT id FROM setlist_items")).scalars().all()
        assert len(set(ids)) == 3 and None not in ids
        # An entry needs a piece or a deletion record.
        failed = False
        try:
            with conn.begin_nested():
                conn.execute(text("UPDATE setlist_items SET arrangement_id = NULL WHERE position = 1"))
        except Exception:  # noqa: BLE001 - the CHECK constraint
            failed = True
        assert failed
        conn.execute(
            text(
                "UPDATE setlist_items SET arrangement_id = NULL, title_snapshot = 'Trio', "
                "deleted_at = now() WHERE position = 1"
            )
        )

    command.downgrade(cfg, "0004_sharing")
    with eng.connect() as conn:
        positions = conn.execute(text("SELECT position FROM setlist_items ORDER BY position")).scalars().all()
        assert positions == [0, 1]
    command.downgrade(cfg, "base")
    eng.dispose()
