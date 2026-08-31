"""GET/POST /escrows, GET /escrows/{id}, deliverable submission, release.

The AI-validator consensus step that normally follows a deliverable
submission (see plan.md section 4) lands with the consensus-engine prompt;
`submit_deliverable` here just records the submission and moves the
milestone to IN_REVIEW so that prompt has a real row to pick up.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.dependencies import get_current_user, get_optional_current_user
from app.enums import ConsensusStage, ConsensusSubjectType, StatusKey
from app.models import ConsensusJob, DeliverableSubmission, Escrow, Milestone, User, UserSettings
from app.schemas import (
    DeliverableSubmissionCreate,
    DeliverableSubmissionRead,
    EscrowCreate,
    EscrowRead,
)
from app.services.consensus import run_consensus

router = APIRouter(prefix="/escrows", tags=["escrows"])

DEFAULT_CRITERIA = "Deliverable meets the agreed brief."


async def _get_escrow_or_404(escrow_id: int, db: AsyncSession) -> Escrow:
    result = await db.execute(
        select(Escrow).where(Escrow.id == escrow_id).options(selectinload(Escrow.milestones))
    )
    escrow = result.scalar_one_or_none()
    if escrow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Escrow not found.")
    return escrow


def _active_milestone(escrow: Escrow) -> Milestone | None:
    """First not-yet-APPROVED milestone by order_index — a stand-in for the
    frontend's `activeMilestoneIndex` (status.ts) until that logic is
    ported server-side verbatim."""
    for milestone in escrow.milestones:
        if milestone.status_key != StatusKey.APPROVED:
            return milestone
    return None


@router.get("", response_model=list[EscrowRead])
async def list_escrows(
    participant_address: str | None = None,
    creator_address: str | None = None,
    counterparty_address: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
) -> list[Escrow]:
    query = select(Escrow).options(selectinload(Escrow.milestones)).order_by(Escrow.created_at.desc())
    if creator_address:
        query = query.where(Escrow.creator_address == creator_address.lower())
    if counterparty_address:
        query = query.where(Escrow.counterparty_address == counterparty_address.lower())
    if participant_address:
        addr = participant_address.lower()
        query = query.where((Escrow.creator_address == addr) | (Escrow.counterparty_address == addr))
    result = await db.execute(query)
    return list(result.scalars().all())


@router.post("", response_model=EscrowRead, status_code=status.HTTP_201_CREATED)
async def create_escrow(
    payload: EscrowCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Escrow:
    # Ensure counterparty user exists so foreign key is satisfied
    counterparty = await db.get(User, payload.counterparty_address)
    if counterparty is None:
        counterparty = User(wallet_address=payload.counterparty_address)
        counterparty.settings = UserSettings(wallet_address=payload.counterparty_address)
        db.add(counterparty)

    escrow = Escrow(
        creator_address=current_user.wallet_address,
        counterparty_address=payload.counterparty_address,
        title=payload.title,
        total=payload.total,
        status_key=StatusKey.IN_PROGRESS,
    )
    escrow.milestones.append(
        Milestone(
            name="Milestone 1",
            amount=payload.total,
            status_key=StatusKey.PENDING,
            criteria=payload.criteria or DEFAULT_CRITERIA,
            order_index=0,
        )
    )
    db.add(escrow)
    await db.commit()
    await db.refresh(escrow, attribute_names=["milestones"])
    return escrow


@router.get("/{escrow_id}", response_model=EscrowRead)
async def get_escrow(escrow_id: int, db: AsyncSession = Depends(get_db)) -> Escrow:
    return await _get_escrow_or_404(escrow_id, db)


@router.post(
    "/{escrow_id}/deliverable",
    response_model=DeliverableSubmissionRead,
    status_code=status.HTTP_201_CREATED,
)
async def submit_deliverable(
    escrow_id: int,
    payload: DeliverableSubmissionCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DeliverableSubmissionRead:
    escrow = await _get_escrow_or_404(escrow_id, db)
    milestone = _active_milestone(escrow)
    if milestone is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This escrow has no active milestone to submit against.",
        )

    submission = DeliverableSubmission(
        milestone_id=milestone.id,
        wallet=current_user.wallet_address,
        text=payload.text,
    )
    milestone.status_key = StatusKey.IN_REVIEW
    db.add(submission)

    # Queued synchronously so the 201 response can hand back a real job_id;
    # the LLM deliberation itself runs after the response is sent.
    job = ConsensusJob(
        subject_type=ConsensusSubjectType.MILESTONE,
        subject_id=milestone.id,
        stage=int(ConsensusStage.IDLE),
    )
    db.add(job)

    await db.commit()
    await db.refresh(submission)
    await db.refresh(job)

    background_tasks.add_task(
        run_consensus, ConsensusSubjectType.MILESTONE, milestone.id, payload.text
    )

    return DeliverableSubmissionRead(
        id=submission.id,
        milestone_id=submission.milestone_id,
        wallet=submission.wallet,
        text=submission.text,
        submitted_at=submission.submitted_at,
        consensus_job_id=job.id,
    )


@router.post("/{escrow_id}/release", response_model=EscrowRead)
async def release_milestone(
    escrow_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Escrow:
    escrow = await _get_escrow_or_404(escrow_id, db)
    if current_user.wallet_address != escrow.creator_address:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the escrow creator can release milestone funds.",
        )

    milestone = _active_milestone(escrow)
    if milestone is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This escrow has no active milestone to release.",
        )

    milestone.status_key = StatusKey.APPROVED
    if all(m.status_key == StatusKey.APPROVED for m in escrow.milestones):
        escrow.status_key = StatusKey.APPROVED

    await db.commit()
    await db.refresh(escrow, attribute_names=["milestones"])
    return escrow

