"""Weekly, durable scheduler for services/governance_generator.py's real
ingestion pipeline — the governance equivalent of services/
market_ingestion_scheduler.py, built for the identical reason once asked
directly for Governance too: "refresh and update the Governance use the
API key." Structurally an exact mirror of that module (own AppState key,
own settings, own docstrings) rather than a generalization of it — see
this codebase's own established per-entity-type convention (retry_
undeployed_escrows / retry_undeployed_predictions / retry_uncreated_
proposals is the same shape) for why a shared "generic scheduler" class
isn't how this repo does this. Read market_ingestion_scheduler.py's own
docstring first for the full reasoning behind the durable-timestamp
design (AppState, not a literal `asyncio.sleep(a week)`) and the
mark-before-not-after tradeoff — every word of it applies here unchanged;
it isn't repeated below.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import AsyncSessionLocal, init_db
from app.models import AppState, Proposal
from app.services.governance_generator import process_latest_events

logger = logging.getLogger(__name__)
settings = get_settings()

# Own key, own AppState row — deliberately not sharing market_ingestion_
# scheduler.py's own _LAST_RUN_STATE_KEY, same reasoning
# GovernanceEventLog isn't a shared table with MarketEventLog (see that
# model's own docstring): the two schedulers run independently, on
# independently configurable cadences, and must be able to be due at
# different times.
_LAST_RUN_STATE_KEY = "governance_ingestion_last_run_at"


async def _get_last_run_at(db: AsyncSession) -> datetime | None:
    state = await db.get(AppState, _LAST_RUN_STATE_KEY)
    if state is None:
        return None
    try:
        return datetime.fromisoformat(state.value)
    except ValueError:
        logger.warning(
            "governance_ingestion_scheduler: AppState[%r] = %r isn't a valid "
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
    """Same pure decision logic as market_ingestion_scheduler.py::is_due
    (kept as its own copy, not a shared import, for the same reason the
    two AppState keys above are independent — see that function's own
    docstring for the reasoning, unchanged here)."""
    if last_run_at is None:
        return True
    if last_run_at.tzinfo is None:
        last_run_at = last_run_at.replace(tzinfo=timezone.utc)
    return (now - last_run_at).total_seconds() >= interval_seconds


async def run_once_if_due() -> list[Proposal]:
    """One check-and-maybe-run cycle. Called on a tight interval
    (governance_ingestion_check_interval_seconds, default hourly) by
    run_forever below, and directly by tests/an ops one-off check without
    needing the sleep loop."""
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        last_run_at = await _get_last_run_at(db)
        if not is_due(last_run_at, now, settings.governance_ingestion_interval_seconds):
            return []

        logger.info(
            "governance_ingestion_scheduler: due (last run: %s) — starting a "
            "real ingestion sweep (real Twitter/Gemini calls, real testnet "
            "GEN on-chain proposal creation if auto_create_proposals_on_chain "
            "is on).",
            last_run_at.isoformat() if last_run_at else "never",
        )
        # See market_ingestion_scheduler.py's own docstring on why this is
        # recorded BEFORE the real sweep below, not after.
        await _set_last_run_at(db, now)

    async with AsyncSessionLocal() as db:
        created = await process_latest_events(db, auto_publish=True)

    if not created:
        logger.info(
            "governance_ingestion_scheduler: sweep complete — no new "
            "proposals this run (expected far more often than not — see "
            "governance_generator.py's own module docstring on why its bar "
            "for 'actionable' is deliberately much higher than "
            "market_generator's own)."
        )
    else:
        for proposal in created:
            logger.info(
                "governance_ingestion_scheduler: published proposal #%s "
                "(live now): %s",
                proposal.id,
                proposal.title,
            )
    return created


async def run_forever() -> None:
    # Mirrors genlayer_indexer.py::run_forever's own opening line and its
    # reasoning exactly: this task can start before main.py's lifespan has
    # otherwise guaranteed the schema exists yet, and init_db() is a cheap
    # no-op once it already does.
    await init_db()
    check_interval = settings.governance_ingestion_check_interval_seconds
    logger.info(
        "governance_ingestion_scheduler: starting — checking every %ss "
        "whether %.1f day(s) have passed since the last real ingestion "
        "sweep.",
        check_interval,
        settings.governance_ingestion_interval_seconds / 86400,
    )
    while True:
        try:
            await run_once_if_due()
        except Exception:  # noqa: BLE001 — one bad cycle must not kill the loop
            logger.exception("governance_ingestion_scheduler: check/sweep cycle failed")
        await asyncio.sleep(check_interval)
