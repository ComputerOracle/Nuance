"""POST/GET /auth/api-keys, DELETE /auth/api-keys/{id} — issuance,
listing, and revocation of scoped API keys for non-browser agents.
ROADMAP.md Part 4 6.1.

Every endpoint here is JWT-authed (get_current_user) — issuing a key
requires already being logged in as a real wallet the normal
nonce/personal_sign way; an API key itself is never usable to create
*more* API keys (there's no `apikey:manage` scope in schemas.core.
API_KEY_SCOPES), so a leaked key's blast radius can't include minting
itself replacements.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import get_current_user
from app.models import ApiKey, User
from app.schemas import ApiKeyCreate, ApiKeyIssueResponse, ApiKeyRead
from app.security import generate_api_key

router = APIRouter(prefix="/auth/api-keys", tags=["api-keys"])


@router.post("", response_model=ApiKeyIssueResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiKeyIssueResponse:
    full_key, key_id, secret_hash = generate_api_key()
    api_key = ApiKey(
        key_id=key_id,
        secret_hash=secret_hash,
        wallet_address=current_user.wallet_address,
        scopes=payload.scopes,
        label=payload.label,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return ApiKeyIssueResponse(
        id=api_key.id,
        key_id=api_key.key_id,
        api_key=full_key,
        label=api_key.label,
        scopes=api_key.scopes,
        created_at=api_key.created_at,
    )


@router.get("", response_model=list[ApiKeyRead])
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ApiKey]:
    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.wallet_address == current_user.wallet_address)
        .order_by(ApiKey.created_at.desc())
    )
    return list(result.scalars().all())


@router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    api_key_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    api_key = await db.get(ApiKey, api_key_id)
    if api_key is None or api_key.wallet_address != current_user.wallet_address:
        # Same 404 either way — a key belonging to someone else doesn't
        # exist as far as this caller is concerned, not "403 forbidden"
        # (which would confirm the id refers to a real key at all).
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found.")
    if api_key.revoked_at is None:
        api_key.revoked_at = datetime.now(timezone.utc)
        await db.commit()
