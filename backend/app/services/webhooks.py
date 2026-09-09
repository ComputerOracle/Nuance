"""Webhook delivery — ROADMAP.md Part 4 6.1: "an autonomous agent doesn't
need to poll ... itself" for consensus/dispute/prediction completion.

Delivered from the exact same call sites services/realtime.py's Redis
publish already fires from (consensus DONE, dispute enforce, prediction
resolve) — a webhook subscriber and a live WS subscriber both learn about
the same event from the same place, just over a different transport. Kept
as its own module rather than folded into realtime.py since the failure
modes are genuinely different: a missed Redis publish just means a
WS-connected browser polls a beat late (nothing else in this codebase
depends on it), but a *caller-owned* HTTP endpoint being slow/down/wrong
is a much less controlled failure surface, worth its own timeout/error
handling and its own "don't let this break the request that triggered it"
boundary.

Delivery contract, deliberately simple for a first pass:
  - Fire-and-forget: call sites use `schedule_notify(...)`, never `notify`
    directly — a webhook delivery (or its failure) must never delay or
    fail the request/background job that triggered it, but a bare
    `asyncio.create_task(notify(...))` at each call site would risk the
    task being garbage-collected mid-flight the instant nothing holds a
    reference to it (a real asyncio footgun, not a hypothetical one —
    see https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task's
    own warning). `schedule_notify` keeps a strong reference in
    `_background_tasks` until the task finishes, so every call site gets
    fire-and-forget semantics without needing to know that trick itself.
  - One attempt, no retry queue. A failing webhook is NOT retried, backed
    off, or auto-disabled after N failures — `last_delivery_status` on the
    Webhook row is purely observability (a caller can see their own
    callback is unhealthy via GET /webhooks), not a queue this service
    manages the lifecycle of. A real retry/backoff/dead-letter system is
    a reasonable next step but a genuinely separate piece of work, not
    something to half-build inside this pass — flagged here rather than
    silently short-changed.
  - Every delivery is HMAC-SHA256 signed (X-Nuance-Signature: sha256=<hex>
    over the raw JSON body, using the webhook's own per-registration
    secret) so the receiving endpoint can verify a payload actually came
    from Nuance — same convention Stripe/GitHub webhooks use.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models import Webhook

logger = logging.getLogger(__name__)

DELIVERY_TIMEOUT_SECONDS = 10.0
# Sentinel statuses for a delivery that never got a real HTTP response —
# distinct from any real status code (which are always >= 100), so GET
# /webhooks can tell "the endpoint answered with an error" apart from
# "the endpoint never answered at all".
DELIVERY_TIMEOUT_STATUS = -1
DELIVERY_ERROR_STATUS = -2


def sign_payload(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


async def _deliver_one(webhook: Webhook, event_type: str, payload: dict) -> None:
    body = json.dumps({"event": event_type, "data": payload}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Nuance-Signature": sign_payload(webhook.secret, body),
        "X-Nuance-Event": event_type,
    }

    status_code: int
    try:
        async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT_SECONDS) as client:
            response = await client.post(webhook.url, content=body, headers=headers)
        status_code = response.status_code
    except httpx.TimeoutException:
        status_code = DELIVERY_TIMEOUT_STATUS
        logger.warning("Webhook %s timed out delivering %s", webhook.id, event_type)
    except Exception as exc:  # noqa: BLE001 — a bad callback URL must never propagate
        status_code = DELIVERY_ERROR_STATUS
        logger.warning("Webhook %s failed delivering %s: %s", webhook.id, event_type, exc)

    # A fresh session, not the caller's — this runs from a detached
    # asyncio task (see notify()) that may well outlive the request/
    # background-job session that scheduled it.
    async with AsyncSessionLocal() as db:
        row = await db.get(Webhook, webhook.id)
        if row is not None:
            row.last_delivered_at = datetime.now(timezone.utc)
            row.last_delivery_status = status_code
            await db.commit()


async def notify(event_type: str, payload: dict) -> None:
    """Looks up every active webhook subscribed to `event_type` and
    delivers to each independently (one slow/failing subscriber can't
    delay or break delivery to another). Awaits every delivery in turn —
    call `schedule_notify` instead from actual call sites; this exists as
    the plain awaitable `schedule_notify` schedules, and for tests that
    want to await delivery deterministically rather than race a
    fire-and-forget task.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Webhook).where(Webhook.is_active.is_(True)))
        matching = [w for w in result.scalars().all() if event_type in w.event_types]

    for webhook in matching:
        try:
            await _deliver_one(webhook, event_type, payload)
        except Exception:  # noqa: BLE001 — one bad webhook must never stop the rest
            logger.exception("Unexpected error delivering webhook %s", webhook.id)


# Strong references to in-flight fire-and-forget delivery tasks — see this
# module's own docstring on why a bare `asyncio.create_task(...)` at each
# call site isn't safe on its own (the task can be garbage-collected mid-
# flight the instant nothing references it). Each task removes itself via
# its own done-callback; this set's only job is to outlive that window.
_background_tasks: set[asyncio.Task] = set()


def schedule_notify(event_type: str, payload: dict) -> None:
    """Fire-and-forget entry point — call this from consensus/dispute/
    prediction completion, not `notify` directly. Returns immediately;
    delivery (and any failure) happens on its own, after this function
    has already returned, and can never affect the caller."""
    task = asyncio.create_task(notify(event_type, payload))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
