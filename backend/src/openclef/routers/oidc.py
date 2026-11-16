"""OIDC sign-in endpoints under /api/v1/auth/oidc.

    GET    /config     public: is SSO on, and what to call the button
    GET    /login      redirect to the provider (?next=/path, ?link=1 to link)
    GET    /callback   provider redirects back here; signs in, then redirects
    DELETE /link       unlink SSO from the current account

With OIDC unconfigured, everything except /config returns 404.

Browser-facing endpoints answer with redirects, never JSON errors: a failed
sign-in lands on /login?sso_error=<code>, which the login page explains.

Account rules:
- A first SSO sign-in creates a regular account (admin if the user is in
  OPENCLEF_OIDC_ADMIN_GROUP). Being in that group later promotes an existing
  account; leaving it never demotes, so a native admin can't be locked out.
- Existing native accounts are linked only by their signed-in owner
  (`?link=1`), never automatically by matching email or username.
- Before first-run setup there is no SSO sign-in: the first account must be
  the native admin created by /setup.
"""
from __future__ import annotations

import re
import uuid
from typing import Annotated
from urllib.parse import urlencode

import structlog
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from openclef.auth import oidc
from openclef.auth.deps import get_current_user
from openclef.auth.sessions import SESSION_COOKIE_NAME, issue_session, parse_session
from openclef.config import get_settings
from openclef.db import get_session
from openclef.models.enums import UserRole
from openclef.models.user import User
from openclef.routers.auth import _set_session_cookie

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1/auth/oidc", tags=["auth"])

DbSession = Annotated[AsyncSession, Depends(get_session)]


def _require_enabled() -> None:
    if not get_settings().oidc_enabled:
        raise HTTPException(status_code=404, detail="oidc_not_configured")


def _fail(code: str, next_path: str = "/") -> RedirectResponse:
    query = urlencode({"sso_error": code, "next": next_path})
    response = RedirectResponse(f"/login?{query}", status_code=303)
    response.delete_cookie(oidc.FLOW_COOKIE_NAME, path=oidc.FLOW_COOKIE_PATH)
    return response


@router.get("/config")
async def oidc_config() -> dict:
    settings = get_settings()
    return {"enabled": settings.oidc_enabled, "provider_name": settings.oidc_provider_name}


@router.get("/login", dependencies=[Depends(_require_enabled)])
async def oidc_login(
    db: DbSession,
    next: str = "/",
    link: bool = False,
    session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> Response:
    next_path = oidc.safe_next(next)
    if (await db.execute(select(func.count()).select_from(User))).scalar_one() == 0:
        return RedirectResponse("/setup", status_code=303)

    link_user_id = None
    if link:
        payload = parse_session(session_cookie) if session_cookie else None
        if payload is None:
            return _fail("link_requires_login", next_path)
        link_user_id = str(payload.user_id)

    try:
        url, flow = await oidc.begin(next_path, link_user_id)
    except oidc.OidcError as exc:
        log.warning("openclef.oidc.begin_failed", code=exc.code, error=str(exc))
        return _fail(exc.code, next_path)

    settings = get_settings()
    response = RedirectResponse(url, status_code=303)
    response.set_cookie(
        oidc.FLOW_COOKIE_NAME,
        oidc.dump_flow(flow, settings),
        max_age=oidc.FLOW_MAX_AGE_SECONDS,
        httponly=True,
        secure=(settings.env != "dev"),
        # Lax: the provider's redirect back is a top-level GET, which Lax allows.
        samesite="lax",
        path=oidc.FLOW_COOKIE_PATH,
    )
    return response


def _username_base(identity: oidc.Identity) -> str:
    candidate = identity.preferred_username or (identity.email or "").split("@")[0] or "member"
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", candidate).strip("-._")[:56]
    return cleaned or "member"


async def _free_username(db: AsyncSession, base: str) -> str:
    """`base`, or `base-2`, `base-3`... SSO never takes over an existing
    native account just because the names match."""
    taken = set(
        (
            await db.execute(
                select(func.lower(User.username)).where(
                    func.lower(User.username).like(f"{base.lower()}%")
                )
            )
        ).scalars()
    )
    if base.lower() not in taken:
        return base
    suffix = 2
    while f"{base}-{suffix}".lower() in taken:
        suffix += 1
    return f"{base}-{suffix}"


def _is_admin_group_member(identity: oidc.Identity) -> bool:
    group = get_settings().oidc_admin_group
    return bool(group) and group in identity.groups


@router.get("/callback", dependencies=[Depends(_require_enabled)])
async def oidc_callback(
    db: DbSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    flow_cookie: Annotated[str | None, Cookie(alias=oidc.FLOW_COOKIE_NAME)] = None,
    session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> Response:
    try:
        flow = oidc.load_flow(flow_cookie)
    except oidc.OidcError as exc:
        return _fail(exc.code)
    if error:
        # e.g. access_denied: the user cancelled, or the provider's policy refused them.
        return _fail("access_denied" if error == "access_denied" else "provider_error", flow.next_path)
    if not code or not state:
        return _fail("provider_error", flow.next_path)

    try:
        identity = await oidc.complete(code, state, flow)
    except oidc.OidcError as exc:
        log.warning("openclef.oidc.callback_failed", code=exc.code, error=str(exc))
        return _fail(exc.code, flow.next_path)

    bound = (await db.execute(select(User).where(User.oidc_sub == identity.sub))).scalar_one_or_none()

    if flow.link_user_id:
        # Linking: the browser must still be signed in as the user who started it.
        current = parse_session(session_cookie) if session_cookie else None
        if current is None or str(current.user_id) != flow.link_user_id:
            return _fail("link_requires_login", flow.next_path)
        if bound is not None and str(bound.id) != flow.link_user_id:
            return _fail("sso_already_linked", flow.next_path)
        user = await db.get(User, uuid.UUID(flow.link_user_id))
        if user is None:
            return _fail("link_requires_login", flow.next_path)
        user.oidc_sub = identity.sub
        log.info("openclef.oidc.linked", user_id=str(user.id))
    elif bound is not None:
        user = bound
    else:
        user = User(
            username=await _free_username(db, _username_base(identity)),
            email=identity.email,
            oidc_sub=identity.sub,
            role=UserRole.ADMIN if _is_admin_group_member(identity) else UserRole.USER,
        )
        db.add(user)
        log.info("openclef.oidc.user_created", username=user.username, role=user.role.value)

    if user.role != UserRole.ADMIN and _is_admin_group_member(identity):
        user.role = UserRole.ADMIN

    try:
        await db.commit()
    except IntegrityError:
        # Two first sign-ins for the same `sub` raced; the other one won.
        await db.rollback()
        return _fail("try_again", flow.next_path)
    await db.refresh(user)

    cookie_value, _ = issue_session(user.id)
    response = RedirectResponse(flow.next_path, status_code=303)
    _set_session_cookie(response, cookie_value)
    response.delete_cookie(oidc.FLOW_COOKIE_NAME, path=oidc.FLOW_COOKIE_PATH)
    return response


@router.delete("/link", status_code=204, dependencies=[Depends(_require_enabled)])
async def oidc_unlink(user: Annotated[User, Depends(get_current_user)], db: DbSession) -> Response:
    """Remove SSO from this account. Refused for SSO-only accounts, which
    would otherwise have no way left to sign in."""
    if not user.password_hash:
        raise HTTPException(status_code=409, detail="no_password_set")
    user.oidc_sub = None
    await db.commit()
    return Response(status_code=204)
