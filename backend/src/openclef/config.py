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

    # Redis (Dramatiq broker — no jobs registered until later tickets)
    redis_url: str = "redis://localhost:6379/0"


def get_settings() -> Settings:
    return Settings()
