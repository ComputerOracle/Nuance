"""Async in-memory token-bucket rate limiter for financial/state-changing
write routes — max `settings.write_rate_limit_per_minute` requests per
rolling minute, per wallet address (see
app.middleware.write_routes.is_protected_write_route for the exact route
set, shared with idempotency.py).

A plain custom middleware rather than slowapi: slowapi's `@limiter.limit`
decorator needs a `Request` parameter threaded through every protected
route function and keys by remote address by default, not wallet — reusing
the same path-matching + wallet-extraction helpers as idempotency.py here
keeps both middlewares consistent and leaves the routers themselves
untouched.

In-memory only, per process — fine for this single-worker deployment;
would need a shared store (Redis, same as slowapi's own recommendation for
anything horizontally scaled) once this runs behind more than one worker,
matching the same single-process scaling caveat services/consensus.py's
lack of row-locking already carries (see models/governance.py's
docstring).
"""

from __future__ import annotations

import asyncio
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import get_settings
from app.middleware.write_routes import extract_wallet_address, is_protected_write_route

_WINDOW_SECONDS = 60.0


class _TokenBucket:
    __slots__ = ("tokens", "updated_at")

    def __init__(self, tokens: float, updated_at: float) -> None:
        self.tokens = tokens
        self.updated_at = updated_at


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self._buckets: dict[str, _TokenBucket] = {}
        self._lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next):
        if not is_protected_write_route(request.method, request.url.path):
            return await call_next(request)

        wallet = extract_wallet_address(request)
        # Unauthenticated attempts on these routes 401 out immediately
        # anyway, but bucketing them by IP still caps trivial hammering of
        # that 401 path itself rather than leaving it unlimited.
        client_host = request.client.host if request.client else "unknown"
        bucket_key = wallet or f"anon:{client_host}"

        limit = get_settings().write_rate_limit_per_minute
        refill_rate = limit / _WINDOW_SECONDS
        now = time.monotonic()

        async with self._lock:
            bucket = self._buckets.get(bucket_key)
            if bucket is None:
                bucket = _TokenBucket(tokens=float(limit), updated_at=now)
                self._buckets[bucket_key] = bucket
            else:
                elapsed = now - bucket.updated_at
                bucket.tokens = min(float(limit), bucket.tokens + elapsed * refill_rate)
                bucket.updated_at = now

            if bucket.tokens < 1.0:
                retry_after = max(1, round((1.0 - bucket.tokens) / refill_rate))
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": f"Rate limit exceeded: max {limit} write requests per "
                        "minute per wallet."
                    },
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.tokens -= 1.0

        return await call_next(request)
