"""GET/POST /proposals, POST /proposals/{id}/vote, POST /proposals/{id}/finalize.

Wallet-scoped governance: 1-wallet-1-vote today. `voter_address` on every
`Vote` comes from the verified JWT (`get_current_user`) — the same
nonce -> personal_sign -> JWT flow every other write endpoint in this app
already trusts, not a new verification path. `DEFAULT_VOTING_POWER` is a
fixed placeholder for GEN-stake-weighted voting later (ROADMAP.md Part 3);
until then every wallet's ballot counts the same.

Re-voting rule: `Vote` is unique on `(proposal_id, voter_address)`, so
casting a second vote always updates that row rather than inserting a
duplicate — `_adjust_tally` first backs the old choice's weight out of the
proposal's running totals, then the new choice's weight in, in the same
transaction. This is a deliberate behavior change from the frontend's old
local mock (a flat "+4% nudge, no dedup"): re-voting now flips your prior
vote instead of stacking on top of it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import get_current_user, get_optional_current_user
from app.enums import ProposalStatus, VoteChoice
from app.models import Proposal, User, Vote
from app.schemas import ProposalCreate, ProposalDetailRead, ProposalRead, VoteCreate, VoteRead

router = APIRouter(prefix="/proposals", tags=["governance"])

# Fixed until real GEN-stake-weighted voting exists (ROADMAP.md Part 3) —
# every wallet's ballot counts the same regardless of holdings.
DEFAULT_VOTING_POWER = 1


async def _get_proposal_or_404(proposal_id: int, db: AsyncSession) -> Proposal:
    proposal = await db.get(Proposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found.")
    return proposal


async def _total_eligible_voters(db: AsyncSession) -> int:
    """Turnout's denominator: every wallet that has ever signed in. A rough
    v1 proxy for "eligible voting power" until GEN staking exists — see
    ROADMAP.md Part 1."""
    result = await db.execute(select(func.count()).select_from(User))
    return result.scalar_one()


def _aware(dt: datetime) -> datetime:
    """SQLite round-trips datetimes as naive; treat naive as UTC since
    that's what we always write — same rule security.py's
    nonce_is_expired already applies to nonce timestamps."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _progress(proposal: Proposal, eligible_voters: int) -> dict:
    """Quorum is turnout (however anyone voted) against every wallet that
    could have; pass/fail is FOR's share of *decided* ballots — abstains
    count toward quorum but don't move the pass threshold either way."""
    turnout_power = proposal.total_for + proposal.total_against + proposal.total_abstain
    turnout_pct = (100.0 * turnout_power / eligible_voters) if eligible_voters else 0.0

    decided = proposal.total_for + proposal.total_against
    for_pct = (100.0 * proposal.total_for / decided) if decided else 0.0
    against_pct = (100.0 * proposal.total_against / decided) if decided else 0.0
    abstain_pct = (100.0 * proposal.total_abstain / turnout_power) if turnout_power else 0.0

    return {
        "turnout_pct": round(turnout_pct, 1),
        "for_pct": round(for_pct, 1),
        "against_pct": round(against_pct, 1),
        "abstain_pct": round(abstain_pct, 1),
        "quorum_met": turnout_pct >= proposal.quorum_threshold,
    }


def _proposal_fields(proposal: Proposal, eligible_voters: int, user_vote: VoteChoice | None) -> dict:
    return {
        "id": proposal.id,
        "title": proposal.title,
        "description": proposal.description,
        "category": proposal.category,
        "proposer_address": proposal.proposer_address,
        "status": proposal.status,
        "start_time": proposal.start_time,
        "end_time": proposal.end_time,
        "quorum_threshold": proposal.quorum_threshold,
        "pass_threshold": proposal.pass_threshold,
        "total_for": proposal.total_for,
        "total_against": proposal.total_against,
        "total_abstain": proposal.total_abstain,
        "created_at": proposal.created_at,
        "user_vote": user_vote,
        **_progress(proposal, eligible_voters),
    }


def _adjust_tally(proposal: Proposal, choice: VoteChoice, delta: int) -> None:
    if choice == VoteChoice.FOR:
        proposal.total_for += delta
    elif choice == VoteChoice.AGAINST:
        proposal.total_against += delta
    else:
        proposal.total_abstain += delta


@router.get("", response_model=list[ProposalRead])
async def list_proposals(
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
) -> list[ProposalRead]:
    result = await db.execute(select(Proposal).order_by(Proposal.created_at.desc()))
    proposals = list(result.scalars().all())
    eligible_voters = await _total_eligible_voters(db)

    user_votes: dict[int, VoteChoice] = {}
    if current_user is not None and proposals:
        vote_result = await db.execute(
            select(Vote).where(
                Vote.voter_address == current_user.wallet_address,
                Vote.proposal_id.in_([p.id for p in proposals]),
            )
        )
        user_votes = {v.proposal_id: v.choice for v in vote_result.scalars().all()}

    return [
        ProposalRead(**_proposal_fields(p, eligible_voters, user_votes.get(p.id))) for p in proposals
    ]


@router.get("/{proposal_id}", response_model=ProposalDetailRead)
async def get_proposal(
    proposal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
) -> ProposalDetailRead:
    proposal = await _get_proposal_or_404(proposal_id, db)
    eligible_voters = await _total_eligible_voters(db)

    vote_result = await db.execute(
        select(Vote).where(Vote.proposal_id == proposal_id).order_by(Vote.created_at.asc())
    )
    votes = list(vote_result.scalars().all())
    user_vote = next(
        (v.choice for v in votes if current_user and v.voter_address == current_user.wallet_address),
        None,
    )

    fields = _proposal_fields(proposal, eligible_voters, user_vote)
    return ProposalDetailRead(**fields, votes=[VoteRead.model_validate(v) for v in votes])


@router.post("", response_model=ProposalRead, status_code=status.HTTP_201_CREATED)
async def create_proposal(
    payload: ProposalCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProposalRead:
    now = datetime.now(timezone.utc)
    proposal = Proposal(
        title=payload.title,
        description=payload.description,
        category=payload.category,
        proposer_address=current_user.wallet_address,
        status=ProposalStatus.ACTIVE,
        start_time=now,
        end_time=now + timedelta(days=payload.voting_period_days),
        quorum_threshold=payload.quorum_threshold,
        pass_threshold=payload.pass_threshold,
    )
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)

    eligible_voters = await _total_eligible_voters(db)
    return ProposalRead(**_proposal_fields(proposal, eligible_voters, user_vote=None))


@router.post("/{proposal_id}/vote", response_model=ProposalRead)
async def cast_vote(
    proposal_id: int,
    payload: VoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProposalRead:
    proposal = await _get_proposal_or_404(proposal_id, db)

    if proposal.status != ProposalStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Voting is closed for this proposal."
        )
    if datetime.now(timezone.utc) >= _aware(proposal.end_time):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Voting period has ended.")

    result = await db.execute(
        select(Vote).where(
            Vote.proposal_id == proposal_id, Vote.voter_address == current_user.wallet_address
        )
    )
    existing = result.scalar_one_or_none()

    if existing is not None:
        _adjust_tally(proposal, existing.choice, -existing.voting_power)
        existing.choice = payload.choice
        existing.voting_power = DEFAULT_VOTING_POWER
    else:
        db.add(
            Vote(
                proposal_id=proposal_id,
                voter_address=current_user.wallet_address,
                choice=payload.choice,
                voting_power=DEFAULT_VOTING_POWER,
            )
        )

    _adjust_tally(proposal, payload.choice, DEFAULT_VOTING_POWER)

    await db.commit()
    await db.refresh(proposal)

    eligible_voters = await _total_eligible_voters(db)
    return ProposalRead(**_proposal_fields(proposal, eligible_voters, user_vote=payload.choice))


@router.post("/{proposal_id}/finalize", response_model=ProposalRead)
async def finalize_proposal(
    proposal_id: int,
    db: AsyncSession = Depends(get_db),
) -> ProposalRead:
    """Idempotent — an already-finalized proposal is returned as-is rather
    than re-evaluated, so calling this twice is always safe. Raises 400 if
    `end_time` hasn't arrived yet; a future bulk sweep (ROADMAP.md Part 1's
    cron) should filter to `end_time <= now()` itself before calling this
    per-id rather than relying on the 400 to skip early proposals.
    """
    proposal = await _get_proposal_or_404(proposal_id, db)
    eligible_voters = await _total_eligible_voters(db)

    if proposal.status != ProposalStatus.ACTIVE:
        return ProposalRead(**_proposal_fields(proposal, eligible_voters, user_vote=None))

    if datetime.now(timezone.utc) < _aware(proposal.end_time):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Voting is still open; ends at {proposal.end_time.isoformat()}.",
        )

    progress = _progress(proposal, eligible_voters)
    passed = progress["quorum_met"] and progress["for_pct"] >= proposal.pass_threshold
    proposal.status = ProposalStatus.PASSED if passed else ProposalStatus.REJECTED

    await db.commit()
    await db.refresh(proposal)
    return ProposalRead(**_proposal_fields(proposal, eligible_voters, user_vote=None))
