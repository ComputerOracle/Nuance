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

engine = create_async_engine(settings.database_url, echo=False)

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
    ],
    "proposals": [("executed_by", "TEXT"), ("executed_at", "TIMESTAMP")],
    "escrows": [("contract_address", "TEXT")],
    "milestones": [
        ("on_chain_index", "INTEGER"),
        ("chain_status", "TEXT DEFAULT 'LEGACY_OFFCHAIN'"),
        ("on_chain_raw_status", "TEXT"),
        ("on_chain_tx_hash", "TEXT"),
    ],
    "disputes": [
        ("on_chain_dispute_id", "INTEGER"),
        ("chain_status", "TEXT DEFAULT 'LEGACY_OFFCHAIN'"),
        ("on_chain_raw_status", "TEXT"),
        ("on_chain_tx_hash", "TEXT"),
    ],
}


async def _patch_missing_sqlite_columns(conn) -> None:
    for table, columns in _SQLITE_COLUMN_PATCHES.items():
        result = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
        existing = {row[1] for row in result.fetchall()}
        for name, sql_type in columns:
            if name not in existing:
                await conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")


async def init_db() -> None:
    """Create tables that don't exist yet, then patch columns that a
    pre-existing local DB is missing (see _SQLITE_COLUMN_PATCHES).

    A stand-in for Alembic while the schema is still moving prompt-to-prompt
    — once it stabilizes, this should be replaced by an initial Alembic
    migration (`alembic upgrade head`) run before the app starts, and this
    function removed from the lifespan.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if engine.dialect.name == "sqlite":
            await _patch_missing_sqlite_columns(conn)


async def dispose_engine() -> None:
    await engine.dispose()
