"""Argon2id password hashing with per-install pepper.

The pepper is mixed in by appending to the password before hashing.
That keeps the hash format compatible with argon2-cffi's PHC string
(`$argon2id$...`) so we can rotate Argon2 cost params without
re-hashing — the library handles version/parameter detection on
verify automatically.

Pepper rotation, by contrast, requires re-hashing every password,
which is why the pepper lives in env (the operator decides when to
rotate) rather than in the DB.
"""
from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from openclef.config import get_settings


class PasswordPolicyError(RuntimeError):
    """Raised when no pepper is configured in a non-dev environment."""


def _hasher() -> PasswordHasher:
    s = get_settings()
    return PasswordHasher(
        time_cost=s.argon2_time_cost,
        memory_cost=s.argon2_memory_cost,
        parallelism=s.argon2_parallelism,
    )


def _peppered(password: str) -> str:
    s = get_settings()
    if not s.pepper:
        if s.env != "dev":
            raise PasswordPolicyError(
                "OPENCLEF_PEPPER is required when OPENCLEF_ENV is not 'dev'."
            )
        # Dev-only: empty pepper is allowed for local convenience.
        return password
    return password + s.pepper


def hash_password(password: str) -> str:
    """Return an argon2id PHC string for the given plaintext password."""
    return _hasher().hash(_peppered(password))


def verify_password(password: str, hashed: str) -> bool:
    """Constant-time verify; returns False on mismatch, raises on malformed input."""
    try:
        _hasher().verify(hashed, _peppered(password))
        return True
    except VerifyMismatchError:
        return False


def needs_rehash(hashed: str) -> bool:
    """True when stored hash uses outdated cost params and should be rehashed on next login."""
    return _hasher().check_needs_rehash(hashed)
