"""OIDC sign-in against an in-process fake provider.

The fake provider has its own RSA key and serves discovery, JWKS and a
token endpoint through httpx.MockTransport, so the real code path runs:
redirect, PKCE, code exchange, signature and claim checks.
"""
from __future__ import annotations

import base64
import hashlib
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from joserfc import jwt
from joserfc.jwk import RSAKey
from sqlalchemy import select

from openclef.auth import oidc
from openclef.auth.hashing import hash_password
from openclef.models.enums import UserRole
from openclef.models.user import User

ISSUER = "https://idp.example.test/application/o/openclef"
CLIENT_ID = "openclef-client"
CLIENT_SECRET = "test-client-secret"
REDIRECT_URI = "http://test/api/v1/auth/oidc/callback"
PASSWORD = "hunter2hunter2"


class FakeProvider:
    def __init__(self) -> None:
        self.key = RSAKey.generate_key(2048, parameters={"kid": "key-1", "use": "sig"})
        self.issued_codes: dict[str, dict] = {}
        self.claims: dict = {}
        self.sign_with: RSAKey | None = None  # override to forge a signature
        self.claim_overrides: dict = {}

    def authorize(self, url: str, code: str = "code-1") -> dict:
        """Play the user approving at the provider; returns the callback params."""
        params = {key: values[0] for key, values in parse_qs(urlparse(url).query).items()}
        assert params["code_challenge_method"] == "S256"
        assert params["redirect_uri"] == REDIRECT_URI
        self.issued_codes[code] = params
        return {"code": code, "state": params["state"]}

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json={
                "issuer": ISSUER + "/",
                "authorization_endpoint": "https://idp.example.test/application/o/authorize/",
                "token_endpoint": "https://idp.example.test/application/o/token/",
                "jwks_uri": f"{ISSUER}/jwks/",
            })
        if path.endswith("/jwks/"):
            return httpx.Response(200, json={"keys": [self.key.as_dict(private=False)]})
        if path.endswith("/token/"):
            return self._token(request)
        return httpx.Response(404)

    def _token(self, request: httpx.Request) -> httpx.Response:
        expected = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
        if request.headers.get("authorization") != f"Basic {expected}":
            return httpx.Response(401, json={"error": "invalid_client"})
        form = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
        issued = self.issued_codes.pop(form.get("code"), None)
        if issued is None:
            return httpx.Response(400, json={"error": "invalid_grant"})
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(form["code_verifier"].encode()).digest()
        ).rstrip(b"=").decode()
        if challenge != issued["code_challenge"]:
            return httpx.Response(400, json={"error": "invalid_grant", "detail": "pkce"})
        now = int(time.time())
        claims = {
            "iss": ISSUER + "/",
            "aud": CLIENT_ID,
            "iat": now,
            "exp": now + 300,
            "nonce": issued["nonce"],
            **self.claims,
            **self.claim_overrides,
        }
        signing_key = self.sign_with or self.key
        token = jwt.encode({"alg": "RS256", "kid": "key-1"}, claims, signing_key)
        return httpx.Response(200, json={"id_token": token, "access_token": "x", "token_type": "Bearer"})


@pytest.fixture
def provider(monkeypatch):
    fake = FakeProvider()
    monkeypatch.setenv("OPENCLEF_OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("OPENCLEF_OIDC_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("OPENCLEF_OIDC_CLIENT_SECRET", CLIENT_SECRET)
    monkeypatch.setenv("OPENCLEF_OIDC_REDIRECT_URI", REDIRECT_URI)
    monkeypatch.setenv("OPENCLEF_OIDC_PROVIDER_NAME", "Authentik")
    monkeypatch.setenv("OPENCLEF_OIDC_ADMIN_GROUP", "openclef-admins")
    monkeypatch.setattr(oidc, "http_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)))
    oidc.reset_cache()
    yield fake
    oidc.reset_cache()


async def _seed(kit, username="owner", role=UserRole.ADMIN, oidc_sub=None, password=True):
    async with kit.sessionmaker() as s:
        user = User(
            username=username,
            role=role,
            oidc_sub=oidc_sub,
            password_hash=hash_password(PASSWORD) if password else None,
        )
        s.add(user)
        await s.commit()
        return user


async def _sign_in_with_sso(kit, provider, claims, next_path="/", link=False):
    provider.claims = claims
    params = {"next": next_path}
    if link:
        params["link"] = "1"
    start = await kit.client.get("/api/v1/auth/oidc/login", params=params)
    assert start.status_code == 303, start.text
    callback = provider.authorize(start.headers["location"])
    return await kit.client.get("/api/v1/auth/oidc/callback", params=callback)


def _sso_error(response) -> str | None:
    query = parse_qs(urlparse(response.headers["location"]).query)
    return query.get("sso_error", [None])[0]


# --- Configuration ----------------------------------------------------------


async def test_disabled_without_config(app_kit):
    r = await app_kit.client.get("/api/v1/auth/oidc/config")
    assert r.json() == {"enabled": False, "provider_name": "SSO"}
    assert (await app_kit.client.get("/api/v1/auth/oidc/login")).status_code == 404
    assert (await app_kit.client.get("/api/v1/auth/oidc/callback")).status_code == 404


async def test_config_when_enabled(app_kit, provider):
    r = await app_kit.client.get("/api/v1/auth/oidc/config")
    assert r.json() == {"enabled": True, "provider_name": "Authentik"}


async def test_no_sso_before_first_run_setup(app_kit, provider):
    r = await app_kit.client.get("/api/v1/auth/oidc/login")
    assert r.status_code == 303 and r.headers["location"] == "/setup"


# --- Sign-in ----------------------------------------------------------------


async def test_first_sign_in_creates_regular_user(app_kit, provider):
    await _seed(app_kit)
    r = await _sign_in_with_sso(
        app_kit, provider,
        {"sub": "sub-relative", "preferred_username": "relative"},
        next_path="/arrangements/abc",
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/arrangements/abc"
    me = (await app_kit.client.get("/api/v1/auth/me")).json()
    assert me["username"] == "relative"
    assert me["role"] == "user"
    assert me["sso_linked"] is True and me["has_password"] is False


async def test_second_sign_in_matches_by_sub(app_kit, provider):
    await _seed(app_kit)
    await _sign_in_with_sso(app_kit, provider, {"sub": "sub-1", "preferred_username": "first-name"})
    await app_kit.client.post("/api/v1/auth/logout")
    # Same person, renamed at the provider: still the same account.
    await _sign_in_with_sso(app_kit, provider, {"sub": "sub-1", "preferred_username": "renamed"})
    me = (await app_kit.client.get("/api/v1/auth/me")).json()
    assert me["username"] == "first-name"
    async with app_kit.sessionmaker() as s:
        assert len((await s.execute(select(User).where(User.oidc_sub == "sub-1"))).all()) == 1


async def test_admin_group_grants_admin(app_kit, provider):
    await _seed(app_kit)
    await _sign_in_with_sso(app_kit, provider, {"sub": "sub-2", "preferred_username": "helper", "groups": ["openclef-admins"]})
    assert (await app_kit.client.get("/api/v1/auth/me")).json()["role"] == "admin"


async def test_leaving_admin_group_never_demotes(app_kit, provider):
    await _seed(app_kit, "owner", UserRole.ADMIN, oidc_sub="sub-owner")
    await _sign_in_with_sso(app_kit, provider, {"sub": "sub-owner", "groups": []})
    assert (await app_kit.client.get("/api/v1/auth/me")).json()["role"] == "admin"


async def test_name_clash_never_takes_over_native_account(app_kit, provider):
    await _seed(app_kit, "owner")
    await _sign_in_with_sso(app_kit, provider, {"sub": "sub-x", "preferred_username": "owner"})
    me = (await app_kit.client.get("/api/v1/auth/me")).json()
    assert me["username"] == "owner-2"
    async with app_kit.sessionmaker() as s:
        native = (await s.execute(select(User).where(User.username == "owner"))).scalar_one()
        assert native.oidc_sub is None


async def test_open_redirect_is_neutralised(app_kit, provider):
    await _seed(app_kit)
    r = await _sign_in_with_sso(app_kit, provider, {"sub": "sub-3"}, next_path="//evil.example/steal")
    assert r.headers["location"] == "/"


# --- Rejections -------------------------------------------------------------


async def test_state_mismatch_is_rejected(app_kit, provider):
    await _seed(app_kit)
    provider.claims = {"sub": "sub-4"}
    start = await app_kit.client.get("/api/v1/auth/oidc/login")
    callback = provider.authorize(start.headers["location"])
    r = await app_kit.client.get("/api/v1/auth/oidc/callback", params={**callback, "state": "forged"})
    assert _sso_error(r) == "state_mismatch"
    assert (await app_kit.client.get("/api/v1/auth/me")).status_code == 401


async def test_wrong_nonce_is_rejected(app_kit, provider):
    await _seed(app_kit)
    provider.claim_overrides = {"nonce": "replayed-from-another-login"}
    r = await _sign_in_with_sso(app_kit, provider, {"sub": "sub-5"})
    assert _sso_error(r) == "invalid_token"


async def test_forged_signature_is_rejected(app_kit, provider):
    await _seed(app_kit)
    provider.sign_with = RSAKey.generate_key(2048, parameters={"kid": "key-1"})
    r = await _sign_in_with_sso(app_kit, provider, {"sub": "sub-6"})
    assert _sso_error(r) == "invalid_token"


async def test_token_for_another_client_is_rejected(app_kit, provider):
    await _seed(app_kit)
    provider.claim_overrides = {"aud": "some-other-app"}
    r = await _sign_in_with_sso(app_kit, provider, {"sub": "sub-7"})
    assert _sso_error(r) == "invalid_token"


async def test_expired_token_is_rejected(app_kit, provider):
    await _seed(app_kit)
    provider.claim_overrides = {"exp": int(time.time()) - 3600}
    r = await _sign_in_with_sso(app_kit, provider, {"sub": "sub-8"})
    assert _sso_error(r) == "invalid_token"


async def test_user_cancelling_at_provider(app_kit, provider):
    await _seed(app_kit)
    await app_kit.client.get("/api/v1/auth/oidc/login")
    r = await app_kit.client.get("/api/v1/auth/oidc/callback", params={"error": "access_denied", "state": "x"})
    assert _sso_error(r) == "access_denied"


async def test_callback_without_flow_cookie(app_kit, provider):
    await _seed(app_kit)
    r = await app_kit.client.get("/api/v1/auth/oidc/callback", params={"code": "c", "state": "s"})
    assert _sso_error(r) == "session_expired"


# --- Linking ----------------------------------------------------------------


async def _native_login(kit, username="owner"):
    r = await kit.client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200


async def test_link_existing_account_then_sign_in_with_sso(app_kit, provider):
    await _seed(app_kit, "owner")
    await _native_login(app_kit)
    r = await _sign_in_with_sso(app_kit, provider, {"sub": "sub-owner"}, next_path="/settings", link=True)
    assert r.headers["location"] == "/settings"
    assert (await app_kit.client.get("/api/v1/auth/me")).json()["sso_linked"] is True

    await app_kit.client.post("/api/v1/auth/logout")
    await _sign_in_with_sso(app_kit, provider, {"sub": "sub-owner", "preferred_username": "whoever"})
    me = (await app_kit.client.get("/api/v1/auth/me")).json()
    assert me["username"] == "owner" and me["role"] == "admin"


async def test_link_requires_being_signed_in(app_kit, provider):
    await _seed(app_kit)
    r = await app_kit.client.get("/api/v1/auth/oidc/login", params={"link": "1"})
    assert _sso_error(r) == "link_requires_login"


async def test_cannot_link_an_identity_already_bound_elsewhere(app_kit, provider):
    await _seed(app_kit, "owner")
    await _seed(app_kit, "relative", UserRole.USER, oidc_sub="sub-taken")
    await _native_login(app_kit)
    r = await _sign_in_with_sso(app_kit, provider, {"sub": "sub-taken"}, link=True)
    assert _sso_error(r) == "sso_already_linked"


async def test_unlink(app_kit, provider):
    await _seed(app_kit, "owner", oidc_sub="sub-owner")
    await _native_login(app_kit)
    assert (await app_kit.client.delete("/api/v1/auth/oidc/link")).status_code == 204
    assert (await app_kit.client.get("/api/v1/auth/me")).json()["sso_linked"] is False


async def test_sso_only_account_cannot_unlink(app_kit, provider):
    await _seed(app_kit)
    await _sign_in_with_sso(app_kit, provider, {"sub": "sub-9", "preferred_username": "member"})
    r = await app_kit.client.delete("/api/v1/auth/oidc/link")
    assert r.status_code == 409 and r.json()["detail"] == "no_password_set"


def test_safe_next():
    assert oidc.safe_next("/arrangements/1?x=2") == "/arrangements/1?x=2"
    for hostile in ("//evil.example", "https://evil.example", "/\\evil.example", "", None, "settings"):
        assert oidc.safe_next(hostile) == "/"
