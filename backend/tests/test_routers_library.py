"""GET /api/v1/arrangements: search, filters, facets, cover parts."""
from __future__ import annotations

from openclef.auth.hashing import hash_password
from openclef.models.enums import KeySignature, Period
from openclef.models.library import ArrangementTag
from openclef.models.user import User
from openclef.services.library_search import prefix_tsquery
from tests.factories import make_arrangement, make_part, make_tag

PASSWORD = "hunter2hunter2"


async def _sign_in(kit) -> User:
    async with kit.sessionmaker() as s:
        user = User(username="member", password_hash=hash_password(PASSWORD))
        s.add(user)
        await s.commit()
    r = await kit.client.post(
        "/api/v1/auth/login", json={"username": "member", "password": PASSWORD}
    )
    assert r.status_code == 200
    return user


async def _seed_library(kit, user: User) -> dict:
    """A small family library. Returns arrangement ids by short name."""
    async with kit.sessionmaker() as s:
        rows = {
            "moonlight": await make_arrangement(
                s, created_by=user.id, title="Moonlight Sonata",
                composer=["Beethoven, Ludwig van"], instrumentation=["Piano"],
                key_signature=KeySignature.C_SHARP_MINOR, period=Period.CLASSICAL, difficulty=4,
            ),
            "phantom": await make_arrangement(
                s, created_by=user.id, title="The Phantom of the Opera",
                composer=["Lloyd Webber, Andrew"], instrumentation=["Piano", "Voice"],
                key_signature=None, period=Period.CONTEMPORARY, difficulty=3,
            ),
            "swan": await make_arrangement(
                s, created_by=user.id, title="The Swan",
                composer=["Saint-Saëns, Camille"], instrumentation=["Cello", "Piano"],
                key_signature=None, period=Period.ROMANTIC, difficulty=3,
            ),
            "carol": await make_arrangement(
                s, created_by=user.id, title="Carol of the Bells",
                composer=["Leontovych, Mykola"], arranger=["A. Arranger"],
                instrumentation=["Violin", "Cello", "Piano"],
                key_signature=None, period=None,
            ),
        }
        holiday = await make_tag(s, name="holiday")
        s.add(ArrangementTag(arrangement_id=rows["carol"].id, tag_id=holiday.id, added_by=user.id))
        await s.commit()
        return {name: str(row.id) for name, row in rows.items()}


async def _list(kit, **params):
    r = await kit.client.get("/api/v1/arrangements", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _titles(body) -> list[str]:
    return [item["title"] for item in body["items"]]


def _facet(body, name) -> dict[str, int]:
    return {entry["value"]: entry["count"] for entry in body["facets"][name]}


def test_prefix_tsquery_keeps_only_words():
    assert prefix_tsquery("Moonlight son") == "moonlight:* & son:*"
    assert prefix_tsquery("a & !b | (c") == "a:* & b:* & c:*"
    assert prefix_tsquery("  !!! ") is None


async def test_list_requires_login(app_kit):
    r = await app_kit.client.get("/api/v1/arrangements")
    assert r.status_code == 401


async def test_empty_library(app_kit):
    await _sign_in(app_kit)
    body = await _list(app_kit)
    assert body["items"] == [] and body["total"] == 0
    assert body["facets"]["instrument"] == []


async def test_search_matches_word_prefixes(app_kit):
    user = await _sign_in(app_kit)
    await _seed_library(app_kit, user)
    assert _titles(await _list(app_kit, q="moon")) == ["Moonlight Sonata"]
    assert _titles(await _list(app_kit, q="phantom opera")) == ["The Phantom of the Opera"]
    assert _titles(await _list(app_kit, q="beethoven")) == ["Moonlight Sonata"]


async def test_hostile_query_is_harmless(app_kit):
    user = await _sign_in(app_kit)
    await _seed_library(app_kit, user)
    body = await _list(app_kit, q="') OR 1=1; -- & | !")
    assert body["total"] == 0


async def test_instrument_filter_and_combined_query(app_kit):
    user = await _sign_in(app_kit)
    await _seed_library(app_kit, user)
    assert sorted(_titles(await _list(app_kit, instrument="Cello"))) == [
        "Carol of the Bells", "The Swan",
    ]
    # Repeated instrument params mean "has all of these".
    assert _titles(await _list(app_kit, instrument=["Cello", "Violin"])) == ["Carol of the Bells"]
    assert _titles(await _list(app_kit, q="swan", instrument="Piano")) == ["The Swan"]
    assert _titles(await _list(app_kit, q="swan", instrument="Violin")) == []


async def test_facet_counts_ignore_their_own_filter(app_kit):
    user = await _sign_in(app_kit)
    await _seed_library(app_kit, user)
    body = await _list(app_kit, period="Romantic")
    assert _titles(body) == ["The Swan"]
    # Period facet still lists the alternatives...
    assert _facet(body, "period") == {"Classical": 1, "Contemporary": 1, "Romantic": 1}
    # ...while other facets narrow to the filtered set.
    assert _facet(body, "instrument") == {"Cello": 1, "Piano": 1}
    assert _facet(body, "difficulty") == {"3": 1}


async def test_full_facets_on_unfiltered_library(app_kit):
    user = await _sign_in(app_kit)
    await _seed_library(app_kit, user)
    body = await _list(app_kit)
    assert body["total"] == 4
    assert _facet(body, "instrument") == {"Piano": 4, "Cello": 2, "Violin": 1, "Voice": 1}
    assert _facet(body, "key") == {"C# minor": 1}
    assert _facet(body, "tag") == {"holiday": 1}


async def test_tag_and_key_filters(app_kit):
    user = await _sign_in(app_kit)
    await _seed_library(app_kit, user)
    assert _titles(await _list(app_kit, tag="holiday")) == ["Carol of the Bells"]
    assert _titles(await _list(app_kit, key="C# minor")) == ["Moonlight Sonata"]


async def test_sort_by_title_and_pagination(app_kit):
    user = await _sign_in(app_kit)
    await _seed_library(app_kit, user)
    first = await _list(app_kit, sort="title", page_size=3)
    assert _titles(first) == ["Carol of the Bells", "Moonlight Sonata", "The Phantom of the Opera"]
    assert first["total"] == 4
    second = await _list(app_kit, sort="title", page_size=3, page=2)
    assert _titles(second) == ["The Swan"]


async def test_cover_part_is_first_upload_with_thumbnail_flag(app_kit):
    user = await _sign_in(app_kit)
    ids = await _seed_library(app_kit, user)
    # Separate transactions: Postgres now() is the transaction start time, so
    # parts inserted together would share created_at (real uploads never do).
    async with app_kit.sessionmaker() as s:
        score = await make_part(
            s, arrangement_id=ids["swan"], uploaded_by=user.id, label="Score",
            thumbnail_storage_key="thumbnails/x.png",
        )
        await s.commit()
    async with app_kit.sessionmaker() as s:
        await make_part(s, arrangement_id=ids["swan"], uploaded_by=user.id, label="Cello")
        await s.commit()
    body = await _list(app_kit, q="swan")
    card = body["items"][0]
    assert card["part_count"] == 2
    assert card["cover_part_id"] == str(score.id)
    assert card["cover_thumbnail_ready"] is True

    moonlight = (await _list(app_kit, q="moonlight"))["items"][0]
    assert moonlight["part_count"] == 0 and moonlight["cover_part_id"] is None
