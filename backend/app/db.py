"""Async SQLAlchemy 2.0 engine/session plumbing."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

# SQLite (dev/tests) only: raise the driver's lock-wait timeout well above
# its 5s default. Plain file-mode SQLite serializes writers behind one
# global lock with no queueing beyond that timeout, and this app's test
# suite runs ~150 tests worth of concurrent-session consensus/webhook code
# against one shared on-disk db (see every test file's own
# os.environ.setdefault("DATABASE_URL", ...) convention) — under full-suite
# load that occasionally pushes a writer past 5s and surfaces as a flaky
# "database is locked" OperationalError with no code-level bug behind it.
# Postgres (prod) has its own real MVCC concurrency and ignores this kwarg
# name entirely, so it's applied conditionally rather than unconditionally.
_connect_args = {"timeout": 30} if settings.database_url.startswith("sqlite") else {}

engine = create_async_engine(settings.database_url, echo=False, connect_args=_connect_args)

# expire_on_commit=False: read-model responses are built from ORM objects
# right after commit (e.g. returning the created Escrow) — with the default
# True, SQLAlchemy would re-issue a SELECT for every attribute access.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Declarative base every model in models.py inherits from."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a session, guarantees it's closed."""
    async with AsyncSessionLocal() as session:
        yield session


# Columns added to an *existing* table after that table was already
# created elsewhere (a dev's local nuance.db, predating the column) —
# `create_all` below only creates missing tables, never missing columns on
# ones that already exist. {table: [(column, sqlite type), ...]}. A no-op
# per column once it's actually present. Sqlite-only (see init_db) —
# Postgres gets a real Alembic migration once the schema stabilizes.
#
# chain_status columns carry an explicit SQL DEFAULT (not just the ORM's
# Python-side `default=`) specifically so ALTER TABLE backfills existing
# rows with LEGACY_OFFCHAIN immediately rather than leaving them NULL —
# this repo has twice already hit a real bug from a schema addition
# landing without the running sqlite db being migrated alongside it
# (resolution_source_url, this file's own history), which is exactly the
# "chain_status: legacy_offchain default on every existing/new escrow"
# case ROADMAP.md 4.6 deliberately deferred until there was a real
# indexer to drive it (services/genlayer_indexer.py) rather than adding
# it speculatively ahead of one. The literal default is the enum
# MEMBER NAME ('LEGACY_OFFCHAIN'), not its .value ('legacy_offchain') —
# SQLAlchemy's auto-generated Enum type for a bare `Mapped[SomeStrEnum]`
# column (no explicit `values_callable`) stores/reads by member name, not
# value, same as this file's pre-existing StatusKey columns already do
# (a live column holds literal 'PENDING', not 'pending') — confirmed by
# hitting `LookupError: 'legacy_offchain' is not among the defined enum
# values` against a real query before this comment was corrected.
_SQLITE_COLUMN_PATCHES: dict[str, list[tuple[str, str]]] = {
    "predictions": [
        ("resolution_source_url", "TEXT"),
        ("contract_address", "TEXT"),
        ("chain_status", "TEXT DEFAULT 'LEGACY_OFFCHAIN'"),
        ("on_chain_raw_status", "TEXT"),
        ("on_chain_tx_hash", "TEXT"),
        ("resolution_trigger_tx_hash", "TEXT"),
    ],
    "proposals": [("executed_by", "TEXT"), ("executed_at", "TIMESTAMP")],
    "escrows": [
        ("contract_address", "TEXT"),
        ("funded_tx_hash", "TEXT"),
        ("cancelled_tx_hash", "TEXT"),
        # ROADMAP.md Part 4 6.2 — DEFAULT 1, not NULL: asset_id is NOT NULL
        # in the model (every escrow has exactly one settlement asset), so
        # every pre-existing row needs a real value the instant this
        # column appears, not a backfill step. 1 is _seed_assets()'s
        # guaranteed native-GEN row id — the correct interpretation for
        # every escrow created before this feature existed, which were
        # always GEN-denominated even though nothing recorded that
        # explicitly.
        ("asset_id", "INTEGER DEFAULT 1"),
    ],
    "milestones": [
        ("on_chain_index", "INTEGER"),
        ("chain_status", "TEXT DEFAULT 'LEGACY_OFFCHAIN'"),
        ("on_chain_raw_status", "TEXT"),
        ("on_chain_tx_hash", "TEXT"),
        ("reasoning", "TEXT"),
        ("released_at", "TIMESTAMP"),
    ],
    "disputes": [
        ("on_chain_dispute_id", "INTEGER"),
        ("chain_status", "TEXT DEFAULT 'LEGACY_OFFCHAIN'"),
        ("on_chain_raw_status", "TEXT"),
        ("on_chain_tx_hash", "TEXT"),
        ("adjudication_tx_hash", "TEXT"),
    ],
}


async def _patch_missing_sqlite_columns(conn) -> None:
    for table, columns in _SQLITE_COLUMN_PATCHES.items():
        result = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
        existing = {row[1] for row in result.fetchall()}
        for name, sql_type in columns:
            if name not in existing:
                await conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")


# ROADMAP.md Part 4 6.2 — id=1 is guaranteed GEN by explicit id, not
# insertion order: Escrow.asset_id's own server_default='1' (and this
# file's escrows.asset_id sqlite patch above) both hard-code that a bare
# "1" means native GEN, so this must be the row that actually gets id 1,
# not "whichever asset happened to be inserted first". `INSERT OR IGNORE`
# makes re-running this on every startup a no-op once seeded, same
# idempotency contract _patch_missing_sqlite_columns already has above.
async def _seed_assets(conn) -> None:
    await conn.exec_driver_sql(
        "INSERT OR IGNORE INTO assets (id, symbol, decimals, contract_address, is_native) "
        "VALUES (1, 'GEN', 18, NULL, 1)"
    )
    await conn.exec_driver_sql(
        "INSERT OR IGNORE INTO assets (id, symbol, decimals, contract_address, is_native) "
        "VALUES (2, 'USDC', 6, NULL, 0)"
    )


async def init_db() -> None:
    """SQLite (local dev/test, the default `database_url`): create tables
    that don't exist yet, then patch columns a pre-existing local DB is
    missing (see _SQLITE_COLUMN_PATCHES) — zero-config convenience for a
    throwaway dev db that's fine to keep auto-migrating this way forever.

    Postgres (real deployments): does nothing here — alembic/ (see
    alembic/env.py) is now the actual source of truth for schema, per
    ROADMAP.md Part 3 5.1. Running `Base.metadata.create_all` against
    Postgres too would create the right tables on a fresh db, but silently
    — with no `alembic_version` row recorded — so this file and every
    future migration would have no idea the schema already matches head,
    and `alembic upgrade head` run afterward would either no-op by luck
    (if `alembic stamp head` was also run manually) or attempt to
    recreate tables that already exist and fail. Run
    `alembic upgrade head` yourself before starting the app against
    Postgres — same as any other Alembic-managed service; see
    docker-compose.yml's `migrate` service for how CI/prod do this
    automatically.
    """
    if engine.dialect.name != "sqlite":
        return
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _patch_missing_sqlite_columns(conn)
        await _seed_assets(conn)


async def dispose_engine() -> None:
    await engine.dispose()
