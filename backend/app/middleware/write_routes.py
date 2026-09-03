"""Shared route-matching + wallet-extraction helpers for the write-path
middlewares (idempotency.py, rate_limit.py) — both need to recognize the
same set of financial/state-changing routes and the same "which wallet is
this request from" logic, so it lives in one place instead of twice.
"""

from __future__ import annotations

import re

from fastapi import Request

from app.security import TokenError, decode_access_token

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
