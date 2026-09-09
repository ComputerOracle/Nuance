"""Isolated unit test for the analytics endpoint's zero-rows edge case.

A genuinely separate, throwaway engine/db — NOT the shared app db every
other test file (including test_analytics.py) ends up on, per that
file's own docstring on why: the whole `pytest -q` run shares one SQLite
file across modules (app/db.py's engine is built once, at first import,
from an `lru_cache`d Settings), so nothing in this suite can assume the
shared db is ever actually empty. Constructing a fresh engine here,
scoped to just this test, is what makes "empty" a testable claim at all.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")
# This file never touches app.main/AsyncSessionLocal itself — only the
# analytics module's own db-agnostic helper functions, called against a
# throwaway engine this test builds and tears down itself below. Still a
# real file path here, not `:memory:` — if this module's import happens
# to win the cross-file DATABASE_URL race (see test_analytics.py's own
# docstring on why that race exists at all), `:memory:` would silently
# hand every *other* test file's own AsyncSessionLocal a fresh, empty db
# on every new connection (SQLite's `:memory:` is connection-scoped, and
# aiosqlite doesn't pool a single connection) — confirmed live: this
# exact placeholder broke test_agent_history.py's second test when
# pytest happened to collect this file first.
_TMP_DIR = tempfile.mkdtemp(prefix="nuance-analytics-empty-db-placeholder-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/placeholder.db")

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

import app.routers.analytics as analytics  # noqa: E402
from app.db import Base  # noqa: E402


def test_analytics_helpers_handle_zero_rows_without_crashing():
    """The three arithmetic paths that would naively divide by zero or
    call `statistics.median([])` (which raises `StatisticsError`) on an
    empty result: TVL sum, dispute-resolution median, prediction volume.
    A fresh install with no escrows/disputes/predictions yet must not
    500 on any of them."""

    async def _run() -> None:
        tmp_dir = tempfile.mkdtemp(prefix="nuance-analytics-empty-db-test-")
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_dir}/empty.db", echo=False)
        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as db:
            tvl, open_count = await analytics._tvl_open_escrows(db)
            assert tvl == 0
            assert open_count == 0

            median_hours, resolved_count = await analytics._dispute_resolution_stats(db)
            assert median_hours is None
            assert resolved_count == 0

            volume, market_count = await analytics._prediction_market_volume(db)
            assert volume == 0
            assert market_count == 0

        await engine.dispose()

    asyncio.run(_run())
