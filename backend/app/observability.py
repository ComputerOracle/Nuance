"""Sentry error/performance tracking — ROADMAP.md Part 4 6.3's mainnet-
readiness checklist ("Monitoring/alerting: Sentry (backend errors +
frontend)"). Same graceful-degradation shape as every other optional
integration in this codebase (Redis in services/realtime.py, the three
LLM providers in services/consensus.py, Twitter ingestion in services/
market_generator.py): unconfigured (no SENTRY_DSN) is the expected dev/
test state and does nothing at all, not an error.

FastAPI's own auto-instrumentation (sentry_sdk.integrations.fastapi)
captures unhandled exceptions from any route automatically once
init_sentry() has actually initialized the SDK — no per-route change
needed anywhere else in this codebase.
"""

from __future__ import annotations

import logging

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from app.config import Settings

logger = logging.getLogger(__name__)


def init_sentry(settings: Settings) -> None:
    """Called once, at process start (main.py, before the FastAPI app is
    built) — Sentry's own docs recommend initializing before instrumented
    code runs, and StarletteIntegration/FastApiIntegration specifically
    hook the app at construction/request-handling time. A no-op if
    `settings.sentry_dsn` is unset, logged once at debug (not warning —
    unlike Redis/an LLM provider, "no Sentry configured" isn't a
    degraded fallback path worth a louder log line, it's simply optional)."""
    if not settings.sentry_dsn:
        logger.debug("SENTRY_DSN not configured — error tracking disabled.")
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        traces_sample_rate=settings.sentry_traces_sample_rate,
        # Real wallet addresses/deliverable text pass through this app's
        # requests — Sentry's default PII scraping (request bodies,
        # cookies) stays off; an exception's own message/traceback is
        # still fully captured either way.
        send_default_pii=False,
    )
    logger.info("Sentry error tracking initialized.")
