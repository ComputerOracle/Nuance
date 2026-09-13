"""Weekly, durable scheduler for services/market_generator.py's real
ingestion pipeline — the recurring half of what services/
run_market_ingestion.py already does as a one-shot CLI entrypoint.

Asked directly: "something that will automatically fetch update for the
API key and update the project every week." This runs the exact same
`process_latest_events(db, auto_publish=True)` that CLI wraps (no
duplicated ingestion/extraction logic — see that function's own
docstring), but as a background task sharing this process/event loop,
same pattern services/genlayer_indexer.py::run_forever already
established for the chain indexer — one fewer moving part than depending
on an external cron this app has no way to verify actually runs on
whatever host it's deployed to (the module docstring on run_market_
ingestion.py itself pointed at an `infra/market-ingestion.cron` that
never actually existed in this repo).

Why a durable timestamp (models.AppState), not just "sleep for a week":
a literal `asyncio.sleep(604800)` can't be interrupted by a settings
change, and — more importantly — restarts (a `uvicorn --reload` reload, a
real deploy, a crash) would silently reset the wait to a full week from
whenever the process happened to come back up, so a genuinely weekly
cadence would drift arbitrarily depending on how often the process
restarts. Instead: wake up often (market_ingestion_check_interval_seconds,
default hourly — cheap, no network calls), and actually run only once
AppState's durably-stored last-run timestamp shows the real interval
(market_ingestion_interval_seconds, default 7 days) has elapsed.

Known, accepted tradeoff (same one Prediction/Escrow.deploy_attempted_at's
own docstrings already make for a much shorter window): the last-run
timestamp is recorded BEFORE the real sweep runs, not after — a crash
mid-sweep still counts as "ran this week" rather than being retried on
the very next hourly check (which would risk overlapping, duplicate
Gemini/TwitterAPI.io calls against the same batch). The real cost here is
larger than deploy_attempted_at's own 10-minute cooldown — a crash in the
right split second could genuinely cost a full week rather than 10
minutes — accepted because per-event dedup already makes overlapping runs
merely wasteful (extra API calls) rather than unsafe, whereas under-
running is invisible and cheap to notice (an ops person can just check
GET-able AppState / logs and re-trigger the CLI manually), so the
established "mark before, don't double-run" convention wins here too.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import AsyncSessionLocal, init_db
from app.models import AppState, Prediction
from app.services.market_generator import process_latest_events

logger = logging.getLogger(__name__)
settings = get_settings()

# One fixed key — this app only ever schedules one recurring ingestion
# job today. A second scheduled job would get its own key, not a shared
# row (see AppState's own docstring on why this table is key/value, not
# a singleton with named columns).
_LAST_RUN_STATE_KEY = "market_ingestion_last_run_at"


async def _get_last_run_at(db: AsyncSession) -> datetime | None:
    state = await db.get(AppState, _LAST_RUN_STATE_KEY)
    if state is None:
        return None
    try:
        return datetime.fromisoformat(state.value)
    except ValueError:
        logger.warning(
            "market_ingestion_scheduler: AppState[%r] = %r isn't a valid "
            "timestamp — treating as never run.",
            _LAST_RUN_STATE_KEY,
            state.value,
        )
        return None


async def _set_last_run_at(db: AsyncSession, when: datetime) -> None:
    state = await db.get(AppState, _LAST_RUN_STATE_KEY)
    if state is None:
        db.add(AppState(key=_LAST_RUN_STATE_KEY, value=when.isoformat()))
    else:
        state.value = when.isoformat()
    await db.commit()


def is_due(last_run_at: datetime | None, now: datetime, interval_seconds: int) -> bool:
    """Pure decision logic, deliberately split out from run_once_if_due
    below so it's directly unit-testable without a real DB/event loop —
    never run before -> due immediately (a fresh install shouldn't wait a
    full week for its first ingestion); otherwise due once `interval_
    seconds` has actually elapsed since the real last run."""
    if last_run_at is None:
        return True
    if last_run_at.tzinfo is None:
        last_run_at = last_run_at.replace(tzinfo=timezone.utc)
    return (now - last_run_at).total_seconds() >= interval_seconds


async def run_once_if_due() -> list[Prediction]:
    """One check-and-maybe-run cycle. Called on a tight interval
    (market_ingestion_check_interval_seconds, default hourly) by
    run_forever below, and directly by tests/an ops one-off check without
    needing the sleep loop. Returns whatever process_latest_events
    returned (possibly []) if a sweep ran, or [] without running one at
    all if not due yet — a caller can't tell those two [] cases apart from
    the return value alone, which is fine: the log line below is what
    distinguishes them.
    """
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        last_run_at = await _get_last_run_at(db)
        if not is_due(last_run_at, now, settings.market_ingestion_interval_seconds):
            return []

        logger.info(
            "market_ingestion_scheduler: due (last run: %s) — starting a real "
            "ingestion sweep (real Twitter/Gemini calls, real testnet GEN "
            "deploys if auto_deploy_prediction_contracts is on).",
            last_run_at.isoformat() if last_run_at else "never",
        )
        # See this module's own docstring on why this is recorded BEFORE
        # the real sweep below, not after.
        await _set_last_run_at(db, now)

    async with AsyncSessionLocal() as db:
        created = await process_latest_events(db, auto_publish=True)

    if not created:
        logger.info("market_ingestion_scheduler: sweep complete — no new markets this run.")
    else:
        for prediction in created:
            logger.info(
                "market_ingestion_scheduler: published market #%s (live now): %s",
                prediction.id,
                prediction.title,
            )
    return created


async def run_forever() -> None:
    # Mirrors genlayer_indexer.py::run_forever's own opening line and its
    # reasoning exactly: this task can start before main.py's lifespan has
    # otherwise guaranteed the schema exists yet (or if ever invoked as
    # its own standalone process later), and init_db() is a cheap no-op
    # once it already does.
    await init_db()
    check_interval = settings.market_ingestion_check_interval_seconds
    logger.info(
        "market_ingestion_scheduler: starting — checking every %ss whether "
        "%.1f day(s) have passed since the last real ingestion sweep.",
        check_interval,
        settings.market_ingestion_interval_seconds / 86400,
    )
    while True:
        try:
            await run_once_if_due()
        except Exception:  # noqa: BLE001 — one bad cycle must not kill the loop
            logger.exception("market_ingestion_scheduler: check/sweep cycle failed")
        await asyncio.sleep(check_interval)
