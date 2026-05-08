"""First-run admin bootstrap.

Called from main.py's lifespan once per startup. If both
`OPENCLEF_ADMIN_USER` and `OPENCLEF_ADMIN_PASSWORD` are set AND no
users exist yet, creates the admin silently. Either env var alone is
ignored (with a warning log) — partial config almost always means the
operator forgot to set the second one.

If users already exist, this is a no-op regardless of the env vars —
operators can leave the env vars in place across deploys without
risking accidental overwrites.
"""
from __future__ import annotations

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from openclef.auth.hashing import hash_password
from openclef.config import get_settings
from openclef.models.enums import UserRole
from openclef.models.user import User


log = structlog.get_logger()


async def maybe_bootstrap_admin(engine: AsyncEngine) -> User | None:
    """Create the first admin from env vars, if conditions are met.

    Returns the created user, or None if no bootstrap happened.
    """
    s = get_settings()
    if not (s.admin_user or s.admin_password):
        return None
    if not (s.admin_user and s.admin_password):
        log.warning(
            "openclef.bootstrap.partial_config",
            message="OPENCLEF_ADMIN_USER and OPENCLEF_ADMIN_PASSWORD must both be set; ignoring",
            user_set=bool(s.admin_user),
            password_set=bool(s.admin_password),
        )
        return None

    SessionFactory = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionFactory() as session:
        count = (await session.execute(select(func.count()).select_from(User))).scalar_one()
        if count > 0:
            log.info("openclef.bootstrap.skipped", reason="users_exist", count=count)
            return None

        admin = User(
            username=s.admin_user,
            password_hash=hash_password(s.admin_password),
            role=UserRole.ADMIN,
        )
        session.add(admin)
        await session.commit()
        log.info("openclef.bootstrap.admin_created", username=s.admin_user)
        return admin
