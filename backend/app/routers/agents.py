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

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.enums import ConsensusStage, ConsensusSubjectType
from app.models import ConsensusJob, Dispute, Escrow, Milestone
from app.schemas import AgentCaseRead, AgentStatRead

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


async def _agent_case_history(wallet_address: str, db: AsyncSession) -> list[dict]:
    """ROADMAP.md Part 4's Real Agent Directory item — the "transaction
    drill-down" `_agent_stats` above never provided: every individual
    judged case behind one wallet's aggregate trust score, not just the
    win-rate number. Same two-query shape as `_agent_stats` (milestone
    cases, then dispute cases), just selecting full rows instead of
    tallying them, and always including `escrow_id` so the frontend can
    link straight back to the real detail view rather than showing an
    orphaned card."""
    cases: list[dict] = []

    milestone_result = await db.execute(
        select(ConsensusJob, Milestone.name, Milestone.escrow_id)
        .select_from(ConsensusJob)
        .join(Milestone, Milestone.id == ConsensusJob.subject_id)
        .join(Escrow, Escrow.id == Milestone.escrow_id)
        .where(
            ConsensusJob.subject_type == ConsensusSubjectType.MILESTONE,
            ConsensusJob.stage == int(ConsensusStage.DONE),
            Escrow.counterparty_address == wallet_address,
        )
    )
    for job, milestone_name, escrow_id in milestone_result.all():
        cases.append(
            {
                "consensus_job_id": job.id,
                "subject_type": ConsensusSubjectType.MILESTONE.value,
                "subject_id": job.subject_id,
                "escrow_id": escrow_id,
                "dispute_id": None,
                "title": milestone_name,
                "verdict_label": job.verdict_label,
                "verdict_approved": job.verdict_approved,
                "verdict_confidence": job.verdict_confidence,
                "verdict_reasoning": job.verdict_reasoning,
                "completed_at": job.completed_at,
            }
        )

    dispute_result = await db.execute(
        select(ConsensusJob, Dispute.issue, Dispute.escrow_id, Dispute.id)
        .select_from(ConsensusJob)
        .join(Dispute, Dispute.id == ConsensusJob.subject_id)
        .where(
            ConsensusJob.subject_type == ConsensusSubjectType.DISPUTE,
            ConsensusJob.stage == int(ConsensusStage.DONE),
            Dispute.opened_by_address == wallet_address,
        )
    )
    for job, issue, escrow_id, dispute_id in dispute_result.all():
        cases.append(
            {
                "consensus_job_id": job.id,
                "subject_type": ConsensusSubjectType.DISPUTE.value,
                "subject_id": job.subject_id,
                "escrow_id": escrow_id,
                "dispute_id": dispute_id,
                "title": issue,
                "verdict_label": job.verdict_label,
                "verdict_approved": job.verdict_approved,
                "verdict_confidence": job.verdict_confidence,
                "verdict_reasoning": job.verdict_reasoning,
                "completed_at": job.completed_at,
            }
        )

    cases.sort(key=lambda c: c["completed_at"] or datetime.min, reverse=True)
    return cases


@router.get("/{wallet_address}/history", response_model=list[AgentCaseRead])
async def get_agent_history(wallet_address: str, db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Empty list (not 404) for a wallet with no judged cases — same
    reasoning as every other computed-on-read list endpoint here
    (GET /disputes/{id}/messages, GET /validators): there's no row to
    check existence against, this is purely a query over ConsensusJob
    history."""
    return await _agent_case_history(wallet_address.lower(), db)
