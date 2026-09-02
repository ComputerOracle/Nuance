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

    # --- used starting the multi-model consensus prompt ---
    # Validator-Beta's (The Realist) primary provider and Validator-Alpha /
    # Validator-Gamma's first fallback. See services/consensus.py.
    anthropic_api_key: str | None = None
    # Validator-Gamma's (The Auditor) primary provider and Validator-Alpha /
    # Validator-Beta's fallback.
    openai_api_key: str | None = None

    # --- used starting the market-generator prompt ---
    # Primary Twitter/X ingestion path: TwitterAPI.io (a third-party proxy,
    # not the official X API — verified working against a real account with
    # a real key; unlike `twitter_bearer_token` below, this doesn't need a
    # paid X developer tier). Unset -> falls through to the legacy tweepy
    # path, then RSS/web.
    twitterapi_io_key: str | None = None
    # Legacy/secondary path via tweepy + the official X API — kept for
    # anyone who does have a paid bearer token, but not what this app is
    # actually configured with. Twitter/X ingestion overall is optional:
    # if neither this nor twitterapi_io_key is set, market_generator.py
    # skips straight to the RSS/web fallback rather than erroring.
    twitter_bearer_token: str | None = None
    # Comma-separated account handles (no @) treated as authoritative GenLayer
    # sources for the Twitter search query and as a trust signal generally.
    market_generator_accounts: str = "genlayer"
    # Comma-separated RSS/Atom feed URLs to poll as the no-API-key fallback.
    # Empty by default — GenLayer doesn't publish a discoverable RSS feed as
    # of this writing (checked genlayerlabs.com / docs.genlayer.com; only
    # Discord/Telegram/X were found) — populate with a real feed URL
    # (blog, Substack, Mirror.xyz, etc.) if/when one exists.
    market_generator_rss_feeds: str = ""
    # Comma-separated webpage URLs scraped generically (headline <a> tags)
    # one tier below RSS, for sources with no feed at all.
    market_generator_web_pages: str = ""

    # --- used starting the idempotency/rate-limit prompt ---
    # How long a completed Idempotency-Key response stays cached and
    # replayable. See app/middleware/idempotency.py.
    idempotency_ttl_hours: int = 24
    # Max write requests per rolling minute, per wallet address (falls back
    # to remote IP for unauthenticated attempts). See app/middleware/rate_limit.py.
    write_rate_limit_per_minute: int = 10

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def _csv_list(self, value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]

    @property
    def market_generator_accounts_list(self) -> list[str]:
        return self._csv_list(self.market_generator_accounts)

    @property
    def market_generator_rss_feeds_list(self) -> list[str]:
        return self._csv_list(self.market_generator_rss_feeds)

    @property
    def market_generator_web_pages_list(self) -> list[str]:
        return self._csv_list(self.market_generator_web_pages)


@lru_cache
def get_settings() -> Settings:
    # lru_cache -> .env is read once per process, not once per request.
    return Settings()
