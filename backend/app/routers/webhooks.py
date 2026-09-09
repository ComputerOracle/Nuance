"""POST/GET /webhooks, DELETE /webhooks/{id} — registration and management
of callback URLs notified on consensus/dispute/prediction completion
events. ROADMAP.md Part 4 6.1. Delivery itself lives in
services/webhooks.py, fired from the same completion call sites
services/realtime.py's Redis publish already uses.

JWT-authed only (get_current_user, not require_user_with_scope) — an API
key has no webhook-management scope in schemas.core.API_KEY_SCOPES, same
reasoning routers/api_keys.py's own header gives for keys not being able
to mint more keys: a leaked key's blast radius shouldn't include
redirecting where an owner's events get delivered.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import get_current_user
from app.models import User, Webhook
from app.schemas import WebhookCreate, WebhookCreateResponse, WebhookRead
from app.security import generate_webhook_secret

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("", response_model=WebhookCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    payload: WebhookCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WebhookCreateResponse:
    secret = generate_webhook_secret()

    webhook = Webhook(
        wallet_address=current_user.wallet_address,
        url=payload.url,
        event_types=payload.event_types,
        secret=secret,
    )
    db.add(webhook)
    await db.commit()
    await db.refresh(webhook)

    return WebhookCreateResponse(
        id=webhook.id,
        url=webhook.url,
        event_types=webhook.event_types,
        is_active=webhook.is_active,
        created_at=webhook.created_at,
        last_delivered_at=webhook.last_delivered_at,
        last_delivery_status=webhook.last_delivery_status,
        secret=secret,
    )


@router.get("", response_model=list[WebhookRead])
async def list_webhooks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Webhook]:
    result = await db.execute(
        select(Webhook)
        .where(Webhook.wallet_address == current_user.wallet_address)
        .order_by(Webhook.created_at.desc())
    )
    return list(result.scalars().all())


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    webhook = await db.get(Webhook, webhook_id)
    if webhook is None or webhook.wallet_address != current_user.wallet_address:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found.")
    await db.delete(webhook)
    await db.commit()
