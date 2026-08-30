"""Auth guards shared by every router — decode the bearer JWT, resolve the
`User` row from the async session.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.models import User
from app.security import TokenError, decode_access_token

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
