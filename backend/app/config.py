"""App settings, loaded from environment / .env via pydantic-settings.

Only `database_url` and `cors_origins` are consumed by this prompt's code
(db.py, main.py). The rest are declared now — rather than added piecemeal
later — so .env.example stays the single source of truth for every setting
the backend will ever need, and so later prompts don't have to touch this
file at all.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- used starting this prompt ---
    database_url: str = "sqlite+aiosqlite:///./nuance.db"
    cors_origins: str = "http://localhost:3000"

    # --- used starting the auth prompt ---
    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_expires_minutes: int = 60 * 24

    # --- used starting the consensus-engine prompt ---
    gemini_api_key: str | None = None

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    # lru_cache -> .env is read once per process, not once per request.
    return Settings()
