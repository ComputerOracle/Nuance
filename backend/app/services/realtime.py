"""Redis pub/sub behind the consensus WebSocket channel (routers/
consensus.py) — see that router's own docstring on why a WS channel
exists at all (a single long-lived connection beats HTTP polling every
500ms), and app/config.py's `redis_url` docstring on why this degrades
gracefully rather than being a hard dependency: every other external
integration in this codebase (Gemini/Anthropic/OpenAI, market_generator's
ingestion sources) already falls back to a simpler path when
unconfigured or unreachable, and Redis is no different here — an
unreachable Redis just means the WS handler polls the db directly
instead of subscribing, exactly like it always did before this file
existed.

Why this matters at all: app/middleware/rate_limit.py's own docstring
already flagged it — the WS channel's original implementation polled the
db from *within each connection's own process*, which only reaches
subscribers connected to that same worker. Behind `uvicorn --workers N`
(or any horizontally-scaled deployment), a consensus job advanced by
whichever worker handled the original POST would never notify a WS
connection accepted by a *different* worker any faster than that
connection's own independent poll cycle happened to catch up — each
worker was already polling on its own, so the WS "channel" wasn't
actually shared state, just a coincidence of every worker asking the
same question on the same cadence. Redis pub/sub gives every worker
process a single shared channel to publish into and subscribe from,
which is the actual fix, not just a latency optimization.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

import redis.asyncio as redis

from app.config import get_settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None
# Sticky: one failed connection attempt is enough to stop retrying for the
# rest of this process's life. Without this, a Redis outage would cost
# every single consensus tick (potentially many per second across
# multiple in-flight jobs) its own fresh connect-timeout, which is worse
# than just falling back once and staying there — the process already
# has to restart to pick up Redis coming back regardless, same as any
# other "checked once at import/first-use" config in this codebase.
_client_failed = False


def _get_client() -> redis.Redis | None:
    global _client
    if _client_failed:
        return None
    if _client is None:
        _client = redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


def _mark_unavailable(job_id: int, action: str, exc: Exception) -> None:
    global _client_failed
    _client_failed = True
    logger.warning(
        "Redis %s failed for consensus job %s (%s) — falling back to DB polling for "
        "the rest of this process's life.",
        action,
        job_id,
        exc,
    )


async def publish_update(channel: str, payload: dict[str, Any]) -> None:
    """Generic publish, extracted 2026-09-08 from what used to be
    consensus-only (publish_consensus_update below is now a thin
    wrapper) so subscribe_dispute_messages could reuse the exact same
    connection-management/fallback logic instead of duplicating it —
    same "one failed attempt disables Redis for this process's life"
    behavior either way (see _mark_unavailable). Best-effort: a publish
    failure never breaks the caller — every channel here has its own db-
    polling fallback that still reaches every subscriber eventually,
    just on a polling cadence instead of instantly."""
    client = _get_client()
    if client is None:
        return
    try:
        await client.publish(channel, json.dumps(payload))
    except Exception as exc:  # noqa: BLE001 — see module docstring: Redis is optional
        _mark_unavailable(channel, "publish", exc)


async def subscribe_updates(channel: str) -> AsyncIterator[dict[str, Any]] | None:
    """Generic subscribe — see publish_update's own docstring for why
    this was extracted. None if Redis isn't reachable at all — the
    caller falls back to db polling in that case. Otherwise an async
    generator yielding each published payload as it arrives, already
    subscribed *before* this returns — call this before doing anything
    else (including your own "what's the current state" read), so no
    update published between your state read and this call can be
    missed. The generator unsubscribes and closes its own pubsub
    connection in a `finally` when the caller stops iterating it (breaks,
    returns, or the connection drops) — no separate cleanup call needed."""
    client = _get_client()
    if client is None:
        return None

    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(channel)
    except Exception as exc:  # noqa: BLE001
        _mark_unavailable(channel, "subscribe", exc)
        with suppress(Exception):
            await pubsub.close()
        return None

    async def _iterate() -> AsyncIterator[dict[str, Any]]:
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue  # the subscribe confirmation itself, not a publish
                try:
                    yield json.loads(message["data"])
                except (TypeError, ValueError):
                    logger.warning("Dropped malformed pub/sub message on %s", channel)
        finally:
            with suppress(Exception):
                await pubsub.unsubscribe(channel)
            with suppress(Exception):
                await pubsub.close()

    return _iterate()


async def publish_consensus_update(job_id: int, payload: dict[str, Any]) -> None:
    """Called from services/consensus.py after every stage commit."""
    await publish_update(f"consensus:{job_id}", payload)


async def subscribe_consensus_updates(job_id: int) -> AsyncIterator[dict[str, Any]] | None:
    return await subscribe_updates(f"consensus:{job_id}")


async def publish_dispute_message(dispute_id: int, payload: dict[str, Any]) -> None:
    """Called from routers/disputes.py's send_message, right after commit
    — added 2026-09-08 (ROADMAP.md Part 3 5.5's "live dispute-message
    updates over the same realtime channel"). Reuses the exact same
    Redis connection/fallback machinery the consensus channel already
    proved live — a distinct channel namespace (`dispute_messages:`, not
    `consensus:`) is all that's actually different."""
    await publish_update(f"dispute_messages:{dispute_id}", payload)


async def subscribe_dispute_messages(dispute_id: int) -> AsyncIterator[dict[str, Any]] | None:
    return await subscribe_updates(f"dispute_messages:{dispute_id}")
