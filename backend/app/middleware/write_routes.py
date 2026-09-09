"""Shared route-matching + wallet-extraction helpers for the write-path
middlewares (idempotency.py, rate_limit.py) — both need to recognize the
same set of financial/state-changing routes and the same "which wallet is
this request from" logic, so it lives in one place instead of twice.
"""

from __future__ import annotations

import re

from fastapi import Request

from app.security import TokenError, decode_access_token, parse_api_key

# (method, path pattern) for every write route both middlewares protect —
# every write that either spends LLM-provider tokens (triggers a consensus
# job) or moves/locks escrowed funds. Matched against `request.url.path`
# (no query string) — path params are left as \d+ since none of these
# routes take anything but an integer id.
_WRITE_ROUTES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("POST", re.compile(r"^/escrows/?$")),
    ("POST", re.compile(r"^/escrows/\d+/release/?$")),
    ("POST", re.compile(r"^/disputes/\d+/evidence/?$")),
    ("POST", re.compile(r"^/disputes/\d+/enforce/?$")),
    ("POST", re.compile(r"^/predictions/\d+/bet/?$")),
    ("POST", re.compile(r"^/proposals/\d+/vote/?$")),
)


def is_protected_write_route(method: str, path: str) -> bool:
    return any(method == m and pattern.match(path) for m, pattern in _WRITE_ROUTES)


def extract_wallet_address(request: Request) -> str | None:
    """Best-effort JWT decode straight from the Authorization header — a
    lighter version of app.dependencies.get_current_user that doesn't hit
    the DB, since middleware only needs the wallet address to scope
    idempotency/rate-limit state, not a full User row. Returns None for any
    missing/malformed/invalid/expired token; the route's own
    `get_current_user` dependency is what actually enforces auth and
    returns 401 — this never rejects a request by itself.
    """
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header[len("bearer ") :].strip()
    if not token:
        return None
    try:
        return decode_access_token(token)
    except TokenError:
        return None


def extract_api_key_id(request: Request) -> str | None:
    """Best-effort, DB-free parse of the X-Api-Key header — same spirit
    as extract_wallet_address above (middleware-layer bucketing only,
    never an auth decision by itself; app.dependencies.require_user_with_
    scope is what actually validates the secret half and enforces scope).
    Returns the public key_id half only (never the secret), which is all
    rate_limit.py needs to bucket per-key (ROADMAP.md Part 4 6.1's "per-
    key rate limits distinct from per-wallet UI limits").

    Known gap, flagged rather than silently left: idempotency.py still
    keys exclusively off extract_wallet_address, so an API-key-
    authenticated request currently skips idempotency protection entirely
    (same "no decodable bearer token -> pass through untouched" path a
    request with no Authorization header at all takes) — closing that
    needs a real DB lookup (key_id -> wallet_address) this deliberately
    cheap, DB-free helper doesn't do. Rate limiting doesn't have the same
    problem since it only needs the key_id itself as a bucket key, not
    the wallet behind it.
    """
    header = request.headers.get("x-api-key")
    if not header:
        return None
    parsed = parse_api_key(header)
    return parsed[0] if parsed else None
