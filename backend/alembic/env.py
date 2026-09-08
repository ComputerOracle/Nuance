"""Alembic environment — async-aware (SQLAlchemy 2.0 AsyncEngine), reading
the real connection string from app.config.get_settings() rather than a
static alembic.ini URL, so `alembic upgrade head` targets the exact same
database the running app would (DATABASE_URL env var / .env), whether
that's local sqlite or a real Postgres. No separate sync driver
(psycopg2) needed — migrations run via AsyncEngine.run_sync(), the same
pattern app/db.py's own engine already uses.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import every model so it registers on Base.metadata before `target_metadata`
# is read below — mirrors app/models/__init__.py's own reason for existing
# (app/main.py needs the same guarantee for create_all/table reflection).
from app.config import get_settings
from app.db import Base
from app import models  # noqa: F401 — import side effect only, registers tables

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Overrides alembic.ini's (deliberately unset) sqlalchemy.url with the
# app's real settings — see this file's own docstring.
config.set_main_option("sqlalchemy.url", get_settings().database_url)


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql` — emits SQL without a live DB
    connection. Used by the CI migration gate (see .github/workflows) to
    check a migration is generatable/renderable without needing a
    Postgres service in that job."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
