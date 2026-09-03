"""GET /validators — computed from real ConsensusJob history, not seed data.

Accuracy is "how often did this validator persona's own vote agree with
the final majority verdict" across every completed job it appeared in.
`VALIDATOR_NAMES` is imported from services/consensus.py rather than
redeclared here, so the two can't drift apart.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.enums import ConsensusStage
from app.models import ConsensusJob
from app.schemas import ValidatorStatRead
from app.services.consensus import VALIDATOR_NAMES

router = APIRouter(prefix="/validators", tags=["validators"])


async def _validator_stats(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(ConsensusJob.validator_results, ConsensusJob.verdict_approved, ConsensusJob.completed_at)
        .where(
            ConsensusJob.stage == int(ConsensusStage.DONE),
            ConsensusJob.validator_results.is_not(None),
        )
    )

    stats = {
        name: {"cases": 0, "matched": 0, "last_active_at": None, "last_provider": None}
        for name in VALIDATOR_NAMES
    }

    for validator_results, verdict_approved, completed_at in result.all():
        for entry in validator_results or []:
            name = entry.get("name")
            bucket = stats.get(name)
            if bucket is None:
                continue  # an unrecognized/legacy persona name — ignore rather than crash
            bucket["cases"] += 1
            voted_approve = entry.get("vote") == "approve"
            if voted_approve == bool(verdict_approved):
                bucket["matched"] += 1
            if completed_at is not None and (
                bucket["last_active_at"] is None or completed_at > bucket["last_active_at"]
            ):
                bucket["last_active_at"] = completed_at
                # "provider" is a newer field (see ValidatorResult) — a job
                # persisted before it existed just leaves this None rather
                # than crashing on the missing key.
                bucket["last_provider"] = entry.get("provider")

    stats_list = [
        {
            "name": name,
            "cases_judged": s["cases"],
            "accuracy_pct": round(100.0 * s["matched"] / s["cases"], 1) if s["cases"] else 0.0,
            "is_active": s["cases"] > 0,
            "last_active_at": s["last_active_at"],
            "last_provider": s["last_provider"],
        }
        for name, s in stats.items()
    ]
    stats_list.sort(key=lambda s: s["accuracy_pct"], reverse=True)
    return stats_list


@router.get("", response_model=list[ValidatorStatRead])
async def list_validators(db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await _validator_stats(db)
