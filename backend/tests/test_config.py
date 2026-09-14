"""Tests for app/config.py::Settings._add_asyncpg_driver.

Written deploying to Render: its managed Postgres hands you a plain
`postgres://`/`postgresql://` connection string with no driver suffix, and
both db.py's create_async_engine and alembic/env.py read database_url
verbatim — an un-normalized URL would resolve to the sync psycopg2 dialect
(not installed, and wrong for an AsyncEngine either way) instead of
asyncpg. No real Postgres connection involved here, just the string
rewrite itself.
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

from app.config import Settings  # noqa: E402


def test_postgres_scheme_gets_asyncpg_driver_added():
    settings = Settings(database_url="postgres://user:pw@host:5432/db")
    assert settings.database_url == "postgresql+asyncpg://user:pw@host:5432/db"


def test_postgresql_scheme_gets_asyncpg_driver_added():
    settings = Settings(database_url="postgresql://user:pw@host:5432/db")
    assert settings.database_url == "postgresql+asyncpg://user:pw@host:5432/db"


def test_already_suffixed_url_is_left_alone():
    settings = Settings(database_url="postgresql+asyncpg://user:pw@host:5432/db")
    assert settings.database_url == "postgresql+asyncpg://user:pw@host:5432/db"


def test_sqlite_url_passes_through_untouched():
    settings = Settings(database_url="sqlite+aiosqlite:///./nuance.db")
    assert settings.database_url == "sqlite+aiosqlite:///./nuance.db"
