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


async def init_db() -> None:
    """Create tables that don't exist yet.

    A stand-in for Alembic while the schema is still moving prompt-to-prompt
    — once it stabilizes, this should be replaced by an initial Alembic
    migration (`alembic upgrade head`) run before the app starts, and this
    function removed from the lifespan.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    await engine.dispose()
