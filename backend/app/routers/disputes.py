"""GET/POST /disputes/{id}/messages, GET/POST /disputes/{id}/evidence, GET /disputes, enforce.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.dependencies import get_current_user
from app.enums import ConsensusStage, ConsensusSubjectType, StatusKey
from app.models import ConsensusJob, Dispute, DisputeEvidence, DisputeMessage, User
from app.schemas import (
    DisputeEnforceRequest,
    DisputeEvidenceCreate,
    DisputeEvidenceRead,
    DisputeMessageCreate,
    DisputeMessageRead,
    DisputeRead,
)
from app.services.consensus import run_consensus

router = APIRouter(prefix="/disputes", tags=["disputes"])


async def _get_dispute_or_404(dispute_id: int, db: AsyncSession) -> Dispute:
    result = await db.execute(
        select(Dispute)
        .where(Dispute.id == dispute_id)
        .options(selectinload(Dispute.evidence), selectinload(Dispute.messages))
    )
    dispute = result.scalar_one_or_none()
    if dispute is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispute not found.")
    return dispute


@router.get("", response_model=list[DisputeRead])
async def list_disputes(db: AsyncSession = Depends(get_db)) -> list[Dispute]:
    result = await db.execute(
        select(Dispute)
        .options(selectinload(Dispute.evidence), selectinload(Dispute.messages))
        .order_by(Dispute.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{dispute_id}", response_model=DisputeRead)
async def get_dispute(dispute_id: int, db: AsyncSession = Depends(get_db)) -> Dispute:
    return await _get_dispute_or_404(dispute_id, db)


# --- Messages -------------------------------------------------------------


@router.get("/{dispute_id}/messages", response_model=list[DisputeMessageRead])
async def list_messages(
    dispute_id: int,
    db: AsyncSession = Depends(get_db),
) -> list[DisputeMessage]:
    await _get_dispute_or_404(dispute_id, db)
    result = await db.execute(
        select(DisputeMessage)
        .where(DisputeMessage.dispute_id == dispute_id)
        .order_by(DisputeMessage.created_at.asc())
    )
    return list(result.scalars().all())


@router.post(
    "/{dispute_id}/messages",
    response_model=DisputeMessageRead,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    dispute_id: int,
    payload: DisputeMessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DisputeMessage:
    dispute = await _get_dispute_or_404(dispute_id, db)
    msg = DisputeMessage(
        dispute_id=dispute.id,
        sender_address=current_user.wallet_address,
        content=payload.content,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


# --- Evidence -------------------------------------------------------------


@router.get("/{dispute_id}/evidence", response_model=list[DisputeEvidenceRead])
async def list_evidence(
    dispute_id: int,
    db: AsyncSession = Depends(get_db),
) -> list[DisputeEvidence]:
    await _get_dispute_or_404(dispute_id, db)
    result = await db.execute(
        select(DisputeEvidence)
        .where(DisputeEvidence.dispute_id == dispute_id)
        .order_by(DisputeEvidence.created_at.asc())
    )
    return list(result.scalars().all())


@router.post(
    "/{dispute_id}/evidence",
    response_model=DisputeEvidenceRead,
    status_code=status.HTTP_201_CREATED,
)
async def submit_evidence(
    dispute_id: int,
    payload: DisputeEvidenceCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DisputeEvidenceRead:
    dispute = await _get_dispute_or_404(dispute_id, db)
    evidence = DisputeEvidence(
        dispute_id=dispute.id,
        submitter_address=current_user.wallet_address,
        description=payload.description,
        link=payload.link,
    )
    db.add(evidence)

    # Queued synchronously so the 201 response can hand back a real job_id;
    # the LLM deliberation itself runs after the response is sent.
    job = ConsensusJob(
        subject_type=ConsensusSubjectType.DISPUTE,
        subject_id=dispute.id,
        stage=int(ConsensusStage.IDLE),
    )
    db.add(job)

    await db.commit()
    await db.refresh(evidence)
    await db.refresh(job)

    background_tasks.add_task(
        run_consensus, ConsensusSubjectType.DISPUTE, dispute.id, payload.description
    )

    return DisputeEvidenceRead(
        id=evidence.id,
        dispute_id=evidence.dispute_id,
        submitter_address=evidence.submitter_address,
        description=evidence.description,
        link=evidence.link,
        created_at=evidence.created_at,
        consensus_job_id=job.id,
    )


# --- Enforce Ruling -------------------------------------------------------


@router.post("/{dispute_id}/enforce", response_model=DisputeRead)
async def enforce_ruling(
    dispute_id: int,
    payload: DisputeEnforceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dispute:
    dispute = await _get_dispute_or_404(dispute_id, db)
    if dispute.resolved_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dispute already enforced.")

    dispute.status_key = StatusKey.APPROVED if payload.approved else StatusKey.DISPUTED
    dispute.ruling = payload.ruling
    dispute.enforced_by = current_user.wallet_address
    dispute.resolved_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(dispute, attribute_names=["evidence", "messages"])
    return dispute
