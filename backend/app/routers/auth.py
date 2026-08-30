"""POST /auth/nonce, POST /auth/verify, GET /auth/me — the personal_sign +
nonce sign-in flow described in plan.md section 3.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import get_current_user
from app.models import User, UserSettings
from app.schemas import (
    NonceRequest,
    NonceResponse,
    TokenResponse,
    UserRead,
    UserSettingsRead,
    UserSettingsUpdate,
    UserUpdate,
    VerifyRequest,
)
from app.security import (
    InvalidSignatureError,
    build_signin_message,
    create_access_token,
    generate_nonce,
    nonce_is_expired,
    recover_signer,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/nonce", response_model=NonceResponse)
async def request_nonce(
    payload: NonceRequest,
    db: AsyncSession = Depends(get_db),
) -> NonceResponse:
    """Issues a fresh nonce for `wallet_address`, creating the User row on
    first sign-in. Re-issuing always overwrites any prior unused nonce —
    only the most recently issued one is ever valid."""
    wallet_address = payload.wallet_address
    nonce = generate_nonce()
    issued_at = datetime.now(timezone.utc)

    user = await db.get(User, wallet_address)
    if user is None:
        user = User(wallet_address=wallet_address)
        user.settings = UserSettings(wallet_address=wallet_address)
        db.add(user)

    user.nonce = nonce
    user.nonce_issued_at = issued_at
    await db.commit()

    message = build_signin_message(wallet_address, nonce, issued_at)
    return NonceResponse(nonce=nonce, message=message)


@router.post("/verify", response_model=TokenResponse)
async def verify_signature(
    payload: VerifyRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Verifies the signed nonce message and, on success, issues a JWT.
    Every failure mode — unknown wallet, stale/expired nonce, bad
    signature, wrong signer — collapses to the same 401 so the endpoint
    doesn't leak which check failed to a would-be attacker."""
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid signature or expired nonce.",
    )

    wallet_address = payload.wallet_address
    user = await db.get(User, wallet_address)
    if user is None or not user.nonce:
        raise invalid_credentials

    # The nonce must still be present in the message the caller claims was
    # signed — this is what ties the signature back to *this* issued nonce
    # rather than some arbitrary text.
    if user.nonce not in payload.message:
        raise invalid_credentials

    if nonce_is_expired(user.nonce_issued_at):
        raise invalid_credentials

    try:
        recovered = recover_signer(payload.message, payload.signature)
    except InvalidSignatureError:
        raise invalid_credentials

    if recovered.lower() != wallet_address:
        raise invalid_credentials

    # Rotate the nonce immediately: even a captured, still-fresh
    # (message, signature) pair can't be replayed a second time.
    user.nonce = None
    user.nonce_issued_at = None
    await db.commit()

    token = create_access_token(wallet_address)
    return TokenResponse(access_token=token, wallet_address=wallet_address)


@router.get("/me", response_model=UserRead)
async def read_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch("/me", response_model=UserRead)
async def update_me(
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    if payload.display_name is not None:
        current_user.display_name = payload.display_name.strip() or None
    await db.commit()
    await db.refresh(current_user, attribute_names=["settings"])
    return current_user


@router.patch("/settings", response_model=UserSettingsRead)
async def update_settings(
    payload: UserSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserSettings:
    if current_user.settings is None:
        current_user.settings = UserSettings(wallet_address=current_user.wallet_address)
        db.add(current_user.settings)

    if payload.notify_on is not None:
        current_user.settings.notify_on = payload.notify_on
    if payload.auto_escalate_on is not None:
        current_user.settings.auto_escalate_on = payload.auto_escalate_on

    await db.commit()
    await db.refresh(current_user.settings)
    return current_user.settings

