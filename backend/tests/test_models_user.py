"""Round-trip tests for the User and UserSettings models."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from openclef.models.enums import Theme, UserRole
from openclef.models.user import User, UserSettings
from tests.factories import UserFactory, UserSettingsFactory, acreate, make_user


async def test_user_round_trip(session):
    created = await make_user(session, username="alice", email="alice@example.test")
    fetched = (await session.execute(select(User).where(User.id == created.id))).scalar_one()
    assert fetched.username == "alice"
    assert fetched.email == "alice@example.test"
    assert fetched.role == UserRole.USER
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


async def test_username_is_case_insensitive_unique(session):
    await make_user(session, username="Bob")
    with pytest.raises(Exception):  # IntegrityError variant; citext makes "BOB" collide with "Bob"
        await make_user(session, username="BOB")
        await session.flush()


async def test_user_settings_round_trip(session):
    user = await make_user(session)
    settings = await acreate(session, UserSettingsFactory, user_id=user.id, theme=Theme.DARK)
    fetched = (
        await session.execute(select(UserSettings).where(UserSettings.user_id == user.id))
    ).scalar_one()
    assert fetched.theme == Theme.DARK
    assert fetched.enrichment_providers_jsonb == [{"provider": "musicbrainz", "enabled": True}]
