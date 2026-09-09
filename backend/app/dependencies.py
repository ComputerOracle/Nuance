"""Auth guards shared by every router — decode the bearer JWT (or, for a
handful of write routes, an X-Api-Key credential — ROADMAP.md Part 4 6.1),
resolve the `User` row from the async session.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.models import ApiKey, User
from app.security import TokenError, decode_access_token, hash_api_key_secret, parse_api_key

# auto_error=False: get_optional_current_user needs the chance to treat "no
# Authorization header" as "anonymous" rather than have HTTPBearer raise
# 403 before either dependency body runs.
bearer_scheme = HTTPBearer(auto_error=False)


def _credentials_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Required auth. Raises 401 if the token is missing, invalid, expired,
    or no longer maps to a User row."""
    if credentials is None:
        raise _credentials_error()

    try:
        wallet_address = decode_access_token(credentials.credentials)
    except TokenError:
        raise _credentials_error()

    result = await db.execute(
        select(User).where(User.wallet_address == wallet_address).options(selectinload(User.settings))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise _credentials_error()
    return user


async def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Best-effort auth for public read routes: a missing/invalid token
    means "anonymous", not an error — never raises."""
    if credentials is None:
        return None

    try:
        wallet_address = decode_access_token(credentials.credentials)
    except TokenError:
        return None

    result = await db.execute(
        select(User).where(User.wallet_address == wallet_address).options(selectinload(User.settings))
    )
    return result.scalar_one_or_none()


def _api_key_error(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


async def _resolve_api_key(x_api_key: str, required_scope: str, db: AsyncSession) -> User:
    parsed = parse_api_key(x_api_key)
    if parsed is None:
        raise _api_key_error("Malformed API key.")
    key_id, secret = parsed

    result = await db.execute(select(ApiKey).where(ApiKey.key_id == key_id))
    api_key = result.scalar_one_or_none()
    if api_key is None or api_key.secret_hash != hash_api_key_secret(secret):
        # Same 401 either way — a real key_id with a wrong secret and a
        # made-up key_id are indistinguishable to the caller, same reasoning
        # get_current_user's _credentials_error collapses every JWT failure
        # mode into one response for.
        raise _api_key_error("Invalid API key.")
    if api_key.revoked_at is not None:
        raise _api_key_error("This API key has been revoked.")
    if required_scope not in api_key.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This API key doesn't have the '{required_scope}' scope.",
        )

    # Best-effort — a failed write here must never fail the actual
    # request it's just bookkeeping for.
    try:
        api_key.last_used_at = datetime.now(timezone.utc)
        await db.commit()
    except Exception:  # noqa: BLE001
        await db.rollback()

    result = await db.execute(
        select(User)
        .where(User.wallet_address == api_key.wallet_address)
        .options(selectinload(User.settings))
    )
    user = result.scalar_one_or_none()
    if user is None:
        # Shouldn't happen (ApiKey.wallet_address is a FK to users) — but
        # collapsing to the same 401 rather than a 500 if it somehow does.
        raise _api_key_error("Invalid API key.")
    return user


def require_user_with_scope(scope: str):
    """Dependency factory — swap `Depends(get_current_user)` for
    `Depends(require_user_with_scope("escrow:create"))` on the specific
    write routes ROADMAP.md Part 4 6.1 names as agent-accessible
    (currently: escrow:create, bet:place, evidence:submit, vote:cast —
    see schemas.core.API_KEY_SCOPES). Every other route (dispute enforce,
    escrow release, governance finalize, ...) deliberately keeps using
    plain `get_current_user` — JWT-only, unchanged — since opening every
    write path to API-key auth wasn't what was asked for, just these four.

    Accepts EITHER an X-Api-Key header (checked first, and if present,
    exclusively — a request can't fall back to a JWT if its API key was
    invalid) OR the normal bearer JWT, unscoped (a browser session can do
    anything its own routes already allow; scopes are an API-key-only
    concept). Returns the same `User` `get_current_user` would, so the
    route body needs zero changes beyond swapping which dependency it
    calls.
    """

    async def _dependency(
        x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        if x_api_key is not None:
            return await _resolve_api_key(x_api_key, scope, db)

        if credentials is None:
            raise _credentials_error()
        try:
            wallet_address = decode_access_token(credentials.credentials)
        except TokenError:
            raise _credentials_error()

        result = await db.execute(
            select(User).where(User.wallet_address == wallet_address).options(selectinload(User.settings))
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise _credentials_error()
        return user

    return _dependency
