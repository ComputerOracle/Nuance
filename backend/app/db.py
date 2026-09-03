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
_SQLITE_COLUMN_PATCHES: dict[str, list[tuple[str, str]]] = {
    "predictions": [("resolution_source_url", "TEXT")],
    "proposals": [("executed_by", "TEXT"), ("executed_at", "TIMESTAMP")],
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
