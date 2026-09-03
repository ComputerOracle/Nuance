"""Idempotency-Key handling for financial/state-changing write routes.

Implemented as ASGI middleware (rather than a per-route FastAPI dependency)
specifically so a cache hit can return the stored response *without ever
invoking the route handler* — a dependency can short-circuit a request too,
but only by raising, which means every protected route would need to
duplicate the "raise the cached response back out" plumbing; doing it once
here keeps escrows.py/disputes.py/predictions.py/governance.py untouched.

Protected routes: POST /escrows, POST /escrows/{id}/release,
POST /disputes/{id}/evidence, POST /disputes/{id}/enforce,
POST /predictions/{id}/bet, POST /proposals/{id}/vote — see
app.middleware.write_routes.is_protected_write_route.

Contract:
  - No `Idempotency-Key` header -> pass through untouched. The header is
    opt-in (same convention as Stripe et al.), not mandatory.
  - No decodable bearer token -> pass through untouched; the route's own
    `get_current_user` dependency 401s it as normal.
  - A key already completed for this (key, wallet, endpoint) within
    `settings.idempotency_ttl_hours`, with the same request body -> the
    cached (status, body) is replayed immediately. No route code runs, no
    new DB rows are written.
  - Same key, different request body -> 409 (the key is already bound to a
    different request).
  - Same key currently mid-flight (another request claimed it and hasn't
    finished) -> 409 — unless that claim is older than
    `_IN_FLIGHT_STALE_SECONDS`, in which case it's treated as an abandoned
    (e.g. crashed-worker) claim and reclaimed rather than blocking a
    legitimate retry forever.
  - Otherwise this request claims the key (inserts an `in_progress` row)
    and runs the route normally; the response is captured and persisted as
    `completed` once it comes back.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.config import get_settings
from app.db import AsyncSessionLocal
from app.middleware.write_routes import extract_wallet_address, is_protected_write_route
from app.models import IdempotencyRecord

logger = logging.getLogger(__name__)

# A claim older than this with no completed response is assumed to belong
# to a crashed/hung worker rather than a request that's genuinely still
# running — ordinary requests here finish in well under a second, so this
# is a generous safety margin, not a realistic expected wait.
_IN_FLIGHT_STALE_SECONDS = 120

# Sentinels distinguishing "no cached record" (None -> caller proceeds and
# owns the claim) from the two 409 cases below.
_IN_FLIGHT = object()
_CONFLICT = object()


def _aware(dt: datetime) -> datetime:
    """SQLite round-trips datetimes as naive; treat naive as UTC since
    that's what we always write — same rule used throughout the app
    (security.py's nonce_is_expired, routers/governance.py's _aware)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


async def _claim_or_get(
    key: str, wallet: str, endpoint: str, request_hash: str
) -> IdempotencyRecord | object | None:
    """Returns:
      - an `IdempotencyRecord` if a completed, still-fresh, matching-body
        response is already cached -> caller should replay it.
      - `_IN_FLIGHT` if another request is actively holding this key.
      - `_CONFLICT` if this key was already used with a different body.
      - `None` if this call itself claimed the key -> caller should run the
        route handler and then call `_complete_record`.
    """
    ttl_hours = get_settings().idempotency_ttl_hours
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(IdempotencyRecord).where(
                IdempotencyRecord.key == key,
                IdempotencyRecord.user_address == wallet,
                IdempotencyRecord.endpoint == endpoint,
            )
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            if existing.status == "completed" and _aware(existing.created_at) >= cutoff:
                if existing.request_hash != request_hash:
                    return _CONFLICT
                return existing

            if existing.status == "in_progress":
                claimed_at = _aware(existing.created_at)
                stale = (
                    datetime.now(timezone.utc) - claimed_at
                ).total_seconds() > _IN_FLIGHT_STALE_SECONDS
                if not stale:
                    return _IN_FLIGHT
                logger.warning(
                    "Idempotency-Key %r for %s %s: reclaiming a stale in-flight claim "
                    "(older than %ss) as an abandoned request.",
                    key, wallet, endpoint, _IN_FLIGHT_STALE_SECONDS,
                )

            # Either expired-but-completed, or a stale in-flight claim we
            # just decided to reclaim -> reset it as this request's fresh
            # claim rather than inserting a second row for the same key.
            existing.request_hash = request_hash
            existing.status = "in_progress"
            existing.response_code = None
            existing.response_body = None
            existing.created_at = datetime.now(timezone.utc)
            existing.completed_at = None
            await db.commit()
            return None

        db.add(
            IdempotencyRecord(
                key=key,
                user_address=wallet,
                endpoint=endpoint,
                request_hash=request_hash,
                status="in_progress",
            )
        )
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            # Lost the race to a concurrent identical request that claimed
            # the same (key, wallet, endpoint) first — re-read its outcome.
            return await _claim_or_get(key, wallet, endpoint, request_hash)
        return None


async def _complete_record(
    key: str, wallet: str, endpoint: str, status_code: int, raw_body: bytes
) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(IdempotencyRecord).where(
                IdempotencyRecord.key == key,
                IdempotencyRecord.user_address == wallet,
                IdempotencyRecord.endpoint == endpoint,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            return  # shouldn't happen — this request is the one that claimed it
        record.response_code = status_code
        try:
            record.response_body = json.loads(raw_body) if raw_body else None
        except (ValueError, TypeError):
            record.response_body = None
        record.status = "completed"
        record.completed_at = datetime.now(timezone.utc)
        await db.commit()


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not is_protected_write_route(request.method, request.url.path):
            return await call_next(request)

        idem_key = request.headers.get("idempotency-key")
        if not idem_key:
            return await call_next(request)

        wallet = extract_wallet_address(request)
        if wallet is None:
            return await call_next(request)  # let get_current_user 401 it normally

        body = await request.body()
        request_hash = hashlib.sha256(body).hexdigest()
        endpoint = f"{request.method} {request.url.path}"

        claim = await _claim_or_get(idem_key, wallet, endpoint, request_hash)

        if claim is _IN_FLIGHT:
            return JSONResponse(
                status_code=409,
                content={"detail": "A request with this Idempotency-Key is already in progress."},
            )
        if claim is _CONFLICT:
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "This Idempotency-Key was already used with a different request body."
                },
            )
        if isinstance(claim, IdempotencyRecord):
            return JSONResponse(status_code=claim.response_code, content=claim.response_body)

        # We hold the claim — actually run the route, then persist its
        # response for future replays before handing it back to the client.
        response = await call_next(request)
        raw_body = b"".join([chunk async for chunk in response.body_iterator])
        replay = Response(
            content=raw_body,
            status_code=response.status_code,
            media_type=response.media_type,
            headers={k: v for k, v in response.headers.items() if k.lower() != "content-length"},
        )
        await _complete_record(idem_key, wallet, endpoint, response.status_code, raw_body)
        return replay
