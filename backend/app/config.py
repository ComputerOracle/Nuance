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

    # --- used starting the chain-indexer prompt ---
    # NuanceDisputeCourt is a single shared registry, not one-per-row (see
    # that contract's own header) — one global address for every dispute's
    # on_chain_dispute_id lookup. Same env var scripts/deploy.ts already
    # writes to this file; unlike escrow/prediction contract addresses
    # (which are per-row — Escrow.contract_address / Prediction.
    # contract_address — since a real deploy-per-agreement flow doesn't
    # exist yet), this one genuinely is global config.
    dispute_court_contract_address: str | None = None
    # The bootstrap NuanceEscrow/NuancePredictionMarket instances
    # scripts/deploy.ts creates (placeholder data, not a real agreement —
    # see that script's header) — not read by the indexer's normal poll
    # loop, only by `python -m app.services.genlayer_indexer --link-demo`,
    # an opt-in way to point one real DB row at a real live contract for
    # an end-to-end smoke test without guessing at fake addresses. Same
    # env vars deploy.ts already writes.
    escrow_contract_address: str | None = None
    prediction_market_contract_address: str | None = None
    # How often services/genlayer_indexer.py's poll loop runs a full cycle.
    genlayer_indexer_poll_seconds: int = 15
    # Whether main.py's lifespan launches the indexer as a background task
    # alongside the API server. True by default (dev/prod both want the
    # read-cache kept warm without a second terminal to babysit) —
    # tests/conftest.py's autouse fixture forces this False for every test
    # regardless of what's in .env, so the whole suite never spins up a
    # real polling loop (which itself would try to shell out to `npx tsx`
    # per cycle) just because a test happened to instantiate the app.
    enable_chain_indexer: bool = True
    # NuanceDisputeCourt.file_dispute assigns its dispute's id on-chain and
    # returns it — but genlayer-js's writeContract only surfaces a decoded
    # return value for a *deploy* (DecodedDeployData.contractAddress); a
    # regular call's DecodedCallData has no equivalent field for what the
    # function actually returned (confirmed against the installed
    # genlayer-js@1.1.8 .d.ts directly). Rather than reverse-engineer the
    # raw undocumented receipt shape against the live, non-disposable
    # shared DisputeCourt registry (deploy.ts had to do exactly that,
    # repeatedly, against its own bootstrap instances — not something to
    # redo against shared infra without being asked), services/
    # genlayer_indexer.py's resolve_pending_dispute_ids resolves the id
    # asynchronously instead: scan the last N on-chain disputes and match
    # by (claimant, escrow_address, claim_statement). This bounds how far
    # back that scan looks.
    dispute_id_scan_window: int = 50
    # Whether routers/escrows.py::create_escrow queues services/
    # genlayer_deploy.py's deploy_escrow_contract as a background task for
    # every new escrow — the actual Part 2 finish line: a real per-escrow
    # NuanceEscrow instance, deployed automatically, no --link-demo
    # needed. True by default; tests/conftest.py's autouse fixture forces
    # this False for the whole suite (same reasoning as
    # enable_chain_indexer) — an ordinary test creating an escrow has no
    # business firing a real ~3-minute Bradbury deployment costing real
    # testnet GEN from the deployer key.
    auto_deploy_escrow_contracts: bool = True
    # Same idea as auto_deploy_escrow_contracts, for NuancePredictionMarket —
    # services/market_generator.py's _process_events deploys a fresh
    # instance for every market it auto-publishes (auto_publish=True,
    # status_key="open" immediately). Markets created as "pending_review"
    # drafts are NOT deployed — see deploy_prediction_contract's own
    # docstring on why a draft that might still be discarded shouldn't
    # spend real testnet GEN. tests/conftest.py forces this False for the
    # whole suite (same reasoning) — test_market_generator.py calls
    # _process_events directly, many times, and has no business firing
    # real deployments.
    auto_deploy_prediction_contracts: bool = True

    # --- used starting the Part 3 hardening prompt (Postgres/Redis/security) ---
    # Redis pub/sub behind the consensus WebSocket channel (routers/
    # consensus.py) — see app/services/realtime.py. Optional: if Redis is
    # unreachable (connection refused, wrong URL, not running at all — the
    # default local-dev state before `docker compose up redis`), the WS
    # channel degrades to the same per-connection DB polling it always
    # did, exactly like every other "no key configured" fallback already
    # in this codebase (Gemini/Anthropic/OpenAI, market_generator's
    # offline heuristic) — not a hard dependency.
    redis_url: str = "redis://localhost:6379/0"
    # Sybil-resistant governance voting weight (routers/governance.py) —
    # a wallet's ballot counts more the older its Nuance account is, up to
    # a cap, rather than every wallet flatly counting 1 regardless of age.
    # A heuristic placeholder, same spirit as DEFAULT_VOTING_POWER's own
    # docstring: real GEN-stake-weighted voting is the eventual answer
    # (ROADMAP.md Part 4), not a wallet-age proxy — but a proxy that costs
    # a sybil attacker real elapsed time per disposable wallet is a
    # meaningful deterrent today, where a flat weight of 1 is free to
    # defeat with N fresh wallets. See routers/governance.py::_voting_power.
    sybil_vote_weight_max: int = 5
    # A wallet must be at least this many days old to get any weight above
    # the 1-point floor every signed-in wallet starts at; each additional
    # full period of this length adds 1 more point, up to the cap above.
    sybil_vote_weight_period_days: int = 7

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
