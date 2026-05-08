"""Unit tests for openclef.auth.hashing.

Argon2 is intentionally slow, so these tests pin the cost params low
to keep the suite fast. Verifies pepper integration, mismatch
behavior, and the prod-safety guard that requires a pepper outside
of dev.
"""
from __future__ import annotations

import pytest

from openclef.auth.hashing import (
    PasswordPolicyError,
    hash_password,
    needs_rehash,
    verify_password,
)


@pytest.fixture(autouse=True)
def fast_argon2(monkeypatch):
    """Override argon2 cost params so the test suite stays under a second."""
    monkeypatch.setenv("OPENCLEF_ARGON2_TIME_COST", "1")
    monkeypatch.setenv("OPENCLEF_ARGON2_MEMORY_COST", "8192")
    monkeypatch.setenv("OPENCLEF_ARGON2_PARALLELISM", "1")
    monkeypatch.setenv("OPENCLEF_PEPPER", "test-pepper")
    monkeypatch.setenv("OPENCLEF_ENV", "dev")


def test_hash_then_verify_round_trip():
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h) is True


def test_verify_rejects_wrong_password():
    h = hash_password("correct horse battery staple")
    assert verify_password("wrong password", h) is False


def test_pepper_changes_hash(monkeypatch):
    h_with_pepper = hash_password("hello")
    monkeypatch.setenv("OPENCLEF_PEPPER", "different-pepper")
    # A hash made with one pepper should not verify under another.
    assert verify_password("hello", h_with_pepper) is False


def test_missing_pepper_raises_outside_dev(monkeypatch):
    monkeypatch.delenv("OPENCLEF_PEPPER", raising=False)
    monkeypatch.setenv("OPENCLEF_ENV", "prod")
    with pytest.raises(PasswordPolicyError):
        hash_password("hello")


def test_missing_pepper_allowed_in_dev(monkeypatch):
    monkeypatch.delenv("OPENCLEF_PEPPER", raising=False)
    monkeypatch.setenv("OPENCLEF_ENV", "dev")
    # No exception — dev allows the empty-pepper path
    h = hash_password("hello")
    assert verify_password("hello", h) is True


def test_needs_rehash_detects_old_params(monkeypatch):
    h = hash_password("hello")
    assert needs_rehash(h) is False
    # Bump cost above the hash's stored cost
    monkeypatch.setenv("OPENCLEF_ARGON2_TIME_COST", "5")
    assert needs_rehash(h) is True
