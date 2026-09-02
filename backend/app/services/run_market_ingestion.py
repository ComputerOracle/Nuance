"""Scheduled/production entrypoint for the GenLayer market-generator
ingestion pipeline.

Unlike `market_generator.py`'s own `__main__` block (`_dry_run()`, always
`auto_publish=False` so results land as `pending_review` drafts for manual
review), this always calls `_process_events(..., auto_publish=True)` — new
markets go straight to `status_key="open"` and are immediately live and
bettable. That's a deliberate product choice (confirmed with the user,
2026-09-02) to trade the review step for a hands-off feed; there's still no
undo button beyond hand-editing the db, so a bad extraction goes live as-is.

Meant to be run on a recurring schedule (cron — see infra/market-ingestion.cron
in this same repo, or the equivalent on whatever host runs this backend),
not invoked ad hoc. For a one-off manual check without publishing anything,
use `python -m app.services.market_generator` instead.
"""

from __future__ import annotations

import asyncio
import logging

from google import genai

from app.config import get_settings
from app.db import AsyncSessionLocal
from app.services.market_generator import _ensure_schema, _ingest_events, _process_events

logger = logging.getLogger(__name__)


async def run() -> None:
    await _ensure_schema()
    settings = get_settings()

    gemini_client = genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key else None
    trusted = {handle.lower() for handle in settings.market_generator_accounts_list}

    events = await _ingest_events(
        accounts=settings.market_generator_accounts_list,
        twitterapi_io_key=settings.twitterapi_io_key,
        bearer_token=settings.twitter_bearer_token,
        rss_feeds=settings.market_generator_rss_feeds_list,
        web_pages=settings.market_generator_web_pages_list,
    )
    logger.info(
        "Fetched %d raw event(s) (%s extraction).",
        len(events),
        "Gemini" if gemini_client else "offline heuristic — GEMINI_API_KEY not set",
    )

    async with AsyncSessionLocal() as db:
        created = await _process_events(
            db, events, auto_publish=True, gemini_client=gemini_client, trusted_accounts=trusted
        )

    if not created:
        logger.info("No new markets this run (noise, irrelevant, or already processed).")
        return
    for prediction in created:
        logger.info("Published market #%s (live now): %s", prediction.id, prediction.title)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(run())
