"""GET /agents — computed from real ConsensusJob history, not seed data.

An "agent" here is any wallet the consensus engine has ever ruled on: a
milestone deliverable's submitter (`Escrow.counterparty_address`) or a
dispute's claimant (`Dispute.opened_by_address`). trust_score is the plain
win rate across every completed judgment involving that wallet. Only
`ConsensusJob.verdict_approved` is trusted for outcomes — not
`Dispute.status_key`, which `services/consensus.py`'s `_apply_verdict_to_
state` sets to APPROVED unconditionally regardless of verdict direction,
so it can't tell a won dispute from a lost one.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.enums import ConsensusStage, ConsensusSubjectType
from app.models import ConsensusJob, Dispute, Escrow, Milestone
from app.schemas import AgentStatRead

router = APIRouter(prefix="/agents", tags=["agents"])


async def _agent_stats(db: AsyncSession) -> list[dict]:
    stats: dict[str, dict] = {}

    def bucket(address: str) -> dict:
        return stats.setdefault(address, {"cases": 0, "wins": 0, "category": "Milestone Delivery"})

    milestone_result = await db.execute(
        select(Escrow.counterparty_address, ConsensusJob.verdict_approved)
        .select_from(ConsensusJob)
        .join(Milestone, Milestone.id == ConsensusJob.subject_id)
        .join(Escrow, Escrow.id == Milestone.escrow_id)
        .where(
            ConsensusJob.subject_type == ConsensusSubjectType.MILESTONE,
            ConsensusJob.stage == int(ConsensusStage.DONE),
        )
    )
    for address, approved in milestone_result.all():
        b = bucket(address)
        b["cases"] += 1
        b["wins"] += int(bool(approved))

    dispute_result = await db.execute(
        select(Dispute.opened_by_address, ConsensusJob.verdict_approved)
        .select_from(ConsensusJob)
        .join(Dispute, Dispute.id == ConsensusJob.subject_id)
        .where(
            ConsensusJob.subject_type == ConsensusSubjectType.DISPUTE,
            ConsensusJob.stage == int(ConsensusStage.DONE),
        )
    )
    for address, approved in dispute_result.all():
        b = bucket(address)
        b["cases"] += 1
        b["wins"] += int(bool(approved))
        # A wallet that both delivers milestones and claims disputes keeps
        # whichever category it touched most recently in this loop order —
        # good enough for v1; a wallet with a real dual history is rare.
        b["category"] = "Dispute Claimant"

    stats_list = [
        {
            "wallet_address": address,
            "category": s["category"],
            "cases_judged": s["cases"],
            "trust_score": round(100.0 * s["wins"] / s["cases"]),
        }
        for address, s in stats.items()
    ]
    stats_list.sort(key=lambda s: s["trust_score"], reverse=True)
    return stats_list


@router.get("", response_model=list[AgentStatRead])
async def list_agents(db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await _agent_stats(db)
