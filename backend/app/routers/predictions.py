"""Prediction markets router — GET /predictions, GET /predictions/{id}, POST /predictions/{id}/bet.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.dependencies import get_current_user
from app.models import Prediction, PredictionPosition, User
from app.schemas import PredictionBetCreate, PredictionPositionRead, PredictionRead

router = APIRouter(prefix="/predictions", tags=["predictions"])


async def _get_prediction_or_404(prediction_id: int, db: AsyncSession) -> Prediction:
    result = await db.execute(
        select(Prediction)
        .where(Prediction.id == prediction_id)
        .options(selectinload(Prediction.positions))
    )
    prediction = result.scalar_one_or_none()
    if prediction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prediction market not found."
        )
    return prediction


@router.get("", response_model=list[PredictionRead])
async def list_predictions(
    status: str | None = "open",
    db: AsyncSession = Depends(get_db),
) -> list[Prediction]:
    """Defaults to only `status_key == "open"` markets so unreviewed drafts
    (`"pending_review"`, see services/market_generator.py) never leak into
    the public betting feed just because a caller forgot to filter.

    `status=None` or `status="all"` (case-insensitive) returns every market
    regardless of status — e.g. for an internal review queue. Any other
    value filters to that exact status, matched case-insensitively since
    status_key casing isn't consistent across the codebase today (markets
    are created as lowercase "open"/"pending_review", but
    services/prediction_oracle.py resolves them to uppercase "RESOLVED").
    """
    query = select(Prediction).options(selectinload(Prediction.positions)).order_by(Prediction.id.asc())
    if status is not None and status.strip().lower() != "all":
        query = query.where(func.lower(Prediction.status_key) == status.strip().lower())
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{prediction_id}", response_model=PredictionRead)
async def get_prediction(
    prediction_id: int, db: AsyncSession = Depends(get_db)
) -> Prediction:
    return await _get_prediction_or_404(prediction_id, db)


@router.post(
    "/{prediction_id}/bet",
    response_model=PredictionRead,
    status_code=status.HTTP_201_CREATED,
)
async def place_bet(
    prediction_id: int,
    payload: PredictionBetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Prediction:
    prediction = await _get_prediction_or_404(prediction_id, db)

    if prediction.status_key.lower() != "open":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prediction market is not open for betting.",
        )

    now = datetime.now(timezone.utc)
    res_date = (
        prediction.resolution_date
        if prediction.resolution_date.tzinfo is not None
        else prediction.resolution_date.replace(tzinfo=timezone.utc)
    )
    if now >= res_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Betting has closed for this market",
        )

    position = PredictionPosition(
        prediction_id=prediction.id,
        wallet_address=current_user.wallet_address,
        side=payload.side,
        amount=payload.amount,
    )
    prediction.volume = (prediction.volume or 0) + payload.amount

    db.add(position)
    await db.commit()
    db.expire_all()
    return await _get_prediction_or_404(prediction_id, db)


@router.post(
    "/{prediction_id}/resolve",
    response_model=PredictionRead,
)
async def resolve_prediction(
    prediction_id: int,
    db: AsyncSession = Depends(get_db),
) -> Prediction:
    prediction = await _get_prediction_or_404(prediction_id, db)

    now = datetime.now(timezone.utc)
    res_date = (
        prediction.resolution_date
        if prediction.resolution_date.tzinfo is not None
        else prediction.resolution_date.replace(tzinfo=timezone.utc)
    )
    if now < res_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Market cannot be resolved before its resolution date: {prediction.resolution_date.isoformat()}",
        )

    from app.services.prediction_oracle import resolve_prediction_market

    try:
        return await resolve_prediction_market(prediction_id, db)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        )




