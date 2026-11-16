"""OIDC relying-party logic: discovery, the authorization redirect, the code
exchange and ID-token verification. Provider-agnostic (Authentik, Keycloak,
Google, ...); the router in `routers/oidc.py` turns this into endpoints.

Security choices, all standard for a confidential web client:

- Authorization code flow with PKCE (S256), plus `state` (CSRF) and `nonce`
  (ID-token replay). All three live in one short-lived signed cookie, so the
  server keeps no login state between the redirect and the callback.
- The ID token's signature is checked against the provider's JWKS, and its
  `iss`, `aud`, `exp` and `nonce` are checked before any claim is trusted.
- Users are matched on `sub` only, never on email or username.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from itsdangerous import BadSignature, URLSafeTimedSerializer
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet

from openclef.config import Settings, get_settings

FLOW_COOKIE_NAME = "openclef_oidc"
FLOW_COOKIE_PATH = "/api/v1/auth/oidc"
FLOW_MAX_AGE_SECONDS = 600
ALLOWED_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "PS256"]
_DISCOVERY_TTL_SECONDS = 3600


class OidcError(Exception):
    """Sign-in failed. `code` is a short machine-readable reason that the
    login page turns into a message; details stay in the server log."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


@dataclass(frozen=True)
class FlowState:
    state: str
    nonce: str
    code_verifier: str
    next_path: str
    # Set when a signed-in user is linking their account to SSO.
    link_user_id: str | None = None


@dataclass(frozen=True)
class Identity:
    sub: str
    preferred_username: str | None
    email: str | None
    groups: list[str]


# --- HTTP + discovery -------------------------------------------------------


def http_client() -> httpx.AsyncClient:
    """Indirection so tests can swap in a fake provider transport."""
    return httpx.AsyncClient(timeout=10.0)


@dataclass
class _ProviderCache:
    issuer: str
    metadata: dict[str, Any]
    keys: KeySet | None
    fetched_at: float


_cache: _ProviderCache | None = None


def reset_cache() -> None:
    global _cache
    _cache = None


async def _metadata(settings: Settings) -> dict[str, Any]:
    global _cache
    issuer = settings.oidc_issuer.rstrip("/")
    fresh = _cache and _cache.issuer == issuer and time.monotonic() - _cache.fetched_at < _DISCOVERY_TTL_SECONDS
    if not fresh:
        async with http_client() as client:
            response = await client.get(f"{issuer}/.well-known/openid-configuration")
        if response.status_code != 200:
            raise OidcError("provider_unreachable", f"discovery HTTP {response.status_code}")
        metadata = response.json()
        # The issuer in the document must be the one we were configured with,
        # or tokens could be validated against the wrong authority.
        if metadata.get("issuer", "").rstrip("/") != issuer:
            raise OidcError("provider_misconfigured", "discovery issuer mismatch")
        _cache = _ProviderCache(issuer=issuer, metadata=metadata, keys=None, fetched_at=time.monotonic())
    return _cache.metadata


async def _key_set(settings: Settings, refresh: bool = False) -> KeySet:
    metadata = await _metadata(settings)
    if _cache.keys is None or refresh:
        async with http_client() as client:
            response = await client.get(metadata["jwks_uri"])
        if response.status_code != 200:
            raise OidcError("provider_unreachable", f"jwks HTTP {response.status_code}")
        _cache.keys = KeySet.import_key_set(response.json())
    return _cache.keys


# --- Flow cookie ------------------------------------------------------------


def _flow_serializer(settings: Settings) -> URLSafeTimedSerializer:
    secret = settings.secret_key or "openclef-dev-secret-do-not-use-in-prod"
    return URLSafeTimedSerializer(secret, salt="oidc-flow")


def dump_flow(flow: FlowState, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return _flow_serializer(settings).dumps(flow.__dict__)


def load_flow(cookie_value: str | None, settings: Settings | None = None) -> FlowState:
    settings = settings or get_settings()
    if not cookie_value:
        raise OidcError("session_expired", "no flow cookie")
    try:
        raw = _flow_serializer(settings).loads(cookie_value, max_age=FLOW_MAX_AGE_SECONDS)
        return FlowState(**raw)
    except (BadSignature, TypeError) as exc:
        raise OidcError("session_expired", str(exc)) from exc


def safe_next(value: str | None) -> str:
    """Only same-site absolute paths: '/x' yes, '//evil.com' or 'https://..' no."""
    if value and value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value
    return "/"


# --- The flow ---------------------------------------------------------------


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


async def begin(next_path: str, link_user_id: str | None = None) -> tuple[str, FlowState]:
    """Return (provider authorization URL, flow state to store in the cookie)."""
    settings = get_settings()
    metadata = await _metadata(settings)
    flow = FlowState(
        state=secrets.token_urlsafe(32),
        nonce=secrets.token_urlsafe(32),
        code_verifier=secrets.token_urlsafe(64),
        next_path=safe_next(next_path),
        link_user_id=link_user_id,
    )
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.oidc_client_id,
            "redirect_uri": settings.oidc_redirect_uri,
            "scope": settings.oidc_scopes,
            "state": flow.state,
            "nonce": flow.nonce,
            "code_challenge": _pkce_challenge(flow.code_verifier),
            "code_challenge_method": "S256",
        }
    )
    return f"{metadata['authorization_endpoint']}?{query}", flow


async def complete(code: str, returned_state: str, flow: FlowState) -> Identity:
    """Exchange the code and verify the ID token. Raises OidcError."""
    settings = get_settings()
    if not secrets.compare_digest(returned_state, flow.state):
        raise OidcError("state_mismatch", "state does not match flow cookie")

    metadata = await _metadata(settings)
    async with http_client() as client:
        response = await client.post(
            metadata["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.oidc_redirect_uri,
                "code_verifier": flow.code_verifier,
            },
            auth=(settings.oidc_client_id, settings.oidc_client_secret),
            headers={"Accept": "application/json"},
        )
    if response.status_code != 200:
        raise OidcError("token_exchange_failed", f"token HTTP {response.status_code}")
    id_token = response.json().get("id_token")
    if not id_token:
        raise OidcError("token_exchange_failed", "no id_token in response")

    claims = await _verify_id_token(id_token, flow.nonce, settings)
    groups = claims.get("groups") or []
    return Identity(
        sub=str(claims["sub"]),
        preferred_username=claims.get("preferred_username") or claims.get("nickname"),
        email=claims.get("email") if claims.get("email_verified", True) else None,
        groups=[str(group) for group in groups] if isinstance(groups, list) else [],
    )


async def _verify_id_token(id_token: str, nonce: str, settings: Settings) -> dict[str, Any]:
    keys = await _key_set(settings)
    try:
        token = jwt.decode(id_token, keys, algorithms=ALLOWED_ALGORITHMS)
    except JoseError:
        # The provider may have rotated keys since we cached them: refetch once.
        keys = await _key_set(settings, refresh=True)
        try:
            token = jwt.decode(id_token, keys, algorithms=ALLOWED_ALGORITHMS)
        except JoseError as exc:
            raise OidcError("invalid_token", f"signature: {exc}") from exc

    registry = jwt.JWTClaimsRegistry(
        leeway=60,
        iss={"essential": True, "value": settings.oidc_issuer.rstrip("/")},
        aud={"essential": True, "value": settings.oidc_client_id},
        sub={"essential": True},
        exp={"essential": True},
        nonce={"essential": True, "value": nonce},
    )
    claims = dict(token.claims)
    # Some providers publish the issuer with a trailing slash; compare without it.
    if isinstance(claims.get("iss"), str):
        claims["iss"] = claims["iss"].rstrip("/")
    try:
        registry.validate(claims)
    except JoseError as exc:
        raise OidcError("invalid_token", f"claims: {exc}") from exc
    return claims
