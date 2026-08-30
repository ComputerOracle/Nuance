"""GET /consensus/{job_id} — the frontend polls this every ~500ms after a
deliverable/evidence submission to drive the ConsensusPanel UI, replacing
the local stage timers plan.md describes in nuance-app.tsx today.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import ConsensusJob
from app.schemas import ConsensusStatus, ConsensusVerdict

router = APIRouter(prefix="/consensus", tags=["consensus"])


@router.get("/{job_id}", response_model=ConsensusStatus)
async def get_consensus_status(job_id: int, db: AsyncSession = Depends(get_db)) -> ConsensusStatus:
    job = await db.get(ConsensusJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consensus job not found.")

    verdict = None
    if job.verdict_label is not None:
        verdict = ConsensusVerdict(
            label=job.verdict_label,
            approved=job.verdict_approved,
            confidence=job.verdict_confidence,
            reasoning=job.verdict_reasoning,
        )

    return ConsensusStatus(stage=job.stage, validator_results=job.validator_results, verdict=verdict)
