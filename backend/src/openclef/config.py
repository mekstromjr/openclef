from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPENCLEF_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Identity
    app_name: str = "openclef"
    version: str = Field(default="dev", description="Build SHA or semver tag (set by CI)")
    env: Literal["dev", "staging", "prod"] = "dev"

    # Database
    database_url: str = "postgresql+asyncpg://openclef:openclef@localhost:5432/openclef"
    auto_migrate: bool = True

    # Storage (Phase 1: stub — real backends arrive in ticket 0137)
    storage_backend: Literal["local", "s3"] = "local"
    data_dir: Path = Path("/var/lib/openclef/data")

    # Redis (Dramatiq broker — no jobs registered until later tickets;
    # also used for session revocation set + login rate-limit buckets)
    redis_url: str = "redis://localhost:6379/0"

    # --- Auth ---
    # Cookie signing key. Required in prod; auto-generated with a warning
    # in dev if unset (regenerated each restart, so dev sessions don't
    # survive container restarts — that's a feature, not a bug).
    secret_key: str | None = None
    # Per-install pepper appended to passwords before Argon2 hashing.
    # Same prod/dev semantics as secret_key.
    pepper: str | None = None
    # Argon2 cost params — defaults matched to argon2-cffi's hardened defaults.
    # Operators can override on weaker hardware via env.
    argon2_time_cost: int = 3
    argon2_memory_cost: int = 65536  # 64 MiB
    argon2_parallelism: int = 4
    # Session lifetime: 30-day rolling.
    session_max_age_days: int = 30
    # Login rate-limit: 5 tokens, refilled at 1 per 3 minutes (≈ 5/15min sustained).
    login_rate_limit_max: int = 5
    login_rate_limit_refill_seconds: int = 180
    # First-run admin bootstrap (optional). When BOTH are set, the
    # lifespan creates an admin silently if no users exist yet.
    admin_user: str | None = None
    admin_password: str | None = None


def get_settings() -> Settings:
    return Settings()
