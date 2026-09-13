"""GET/POST /proposals, POST /proposals/{id}/vote(+/on-chain),
POST /proposals/{id}/retract-vote/on-chain, POST /proposals/{id}/finalize.

Wallet-scoped governance. `voter_address` on every `Vote` comes from the
verified JWT (`get_current_user`) — the same nonce -> personal_sign ->
JWT flow every other write endpoint in this app already trusts, not a new
verification path.

Two voting models now coexist, split by whether a Proposal is linked to
the shared on-chain NuanceGovernance registry (`on_chain_proposal_id`
set) — see models/governance.py's own Proposal docstring for the full
account of why nothing retroactively converts an existing proposal:

  - LEGACY (every proposal created before 2026-09-13, and any new one
    created while GOVERNANCE_CONTRACT_ADDRESS/auto_create_proposals_on_
    chain is off): the original off-chain scheme below, weight from
    `_voting_power`'s account-age sybil-resistance placeholder (ROADMAP.md
    Part 3 5.4) — no real GEN behind any of it, and no way to "unvote",
    only to change your choice (cast_vote again).
  - ON-CHAIN (asked directly: "any user that vote and unvote you will
    have to use Gen token ... like a real Governance"): cast_vote/vote
    (POST .../vote/on-chain) is a real, wallet-signed, payable
    NuanceGovernance.cast_vote transaction — the GEN sent IS the ballot's
    weight — and retract_vote (POST .../retract-vote/on-chain) is the new
    real unvote, refunding that exact stake. The two off-chain write
    endpoints below (cast_vote, plain vote) refuse outright
    (ChainUnavailableError, 503) once a proposal is linked or even
    queued to link (`deploy_attempted_at` set) — see cast_vote's own
    guard for why that's checked instead of only on_chain_proposal_id.

Re-voting rule: `Vote` is unique on `(proposal_id, voter_address)`, so
casting a second vote always updates that row rather than inserting a
duplicate — `_adjust_tally` first backs the old choice's weight out of the
proposal's running totals, then the new choice's weight in, in the same
transaction. This is a deliberate behavior change from the frontend's old
local mock (a flat "+4% nudge, no dedup"): re-voting now flips your prior
vote instead of stacking on top of it. Note re-voting locks in whatever
weight applies *at re-vote time* (a wallet that ages into a higher tier
between votes gets the new, higher weight on its next vote, replacing the
old one in the tally rather than keeping the original) — consistent with
"your current standing determines your current ballot's weight", not a
grandfather clause.

Row locking: every write here that reads a Proposal it's about to mutate
(cast_vote, finalize_proposal, execute_proposal) does so via
`_get_proposal_for_update_or_404`, a `SELECT ... FOR UPDATE` — closes the
concurrent-vote-tally race models/governance.py's own docstring already
flagged ("concurrent votes ... read-modify-write Proposal's tally columns
with no row lock"). A silent no-op on SQLite (confirmed: no error, no
actual locking — SQLite's own effectively-serialized writes cover local
dev/test), a real row lock once this runs on Postgres.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.dependencies import get_current_user, get_optional_current_user, require_user_with_scope
from app.enums import ProposalStatus, VoteChoice
from app.models import Proposal, User, Vote
from app.schemas import (
    ProposalCreate,
    ProposalDetailRead,
    ProposalRead,
    RetractVoteOnChainAck,
    VoteCreate,
    VoteOnChainAck,
    VoteRead,
)
from app.services.consensus import ChainUnavailableError
from app.services.genlayer_indexer import create_proposal_on_chain

router = APIRouter(prefix="/proposals", tags=["governance"])

# See Proposal.quorum_threshold_gen's own model docstring — applied
# whenever a new proposal queues for on-chain creation and the client
# didn't supply its own value (no create-proposal UI does yet). 1 GEN is
# a deliberately modest, real, non-trivial floor — nowhere near "20 wei"
# (what forwarding the old percentage field produced), but also not so
# high that testing this on a low-balance testnet wallet is impractical.
_DEFAULT_ON_CHAIN_QUORUM_GEN = Decimal("1")


def _voting_power(user: User) -> int:
    """Sybil-resistance placeholder (see module docstring): 1 point for
    any signed-in wallet, +1 more for every full `sybil_vote_weight_
    period_days` its account has existed, capped at `sybil_vote_weight_
    max`. A wallet created seconds before casting a vote gets the same
    weight of 1 a flat-DEFAULT_VOTING_POWER scheme always gave everyone —
    the deterrent is that *scaling* a sybil attack (many wallets, each
    voting meaningfully) now costs real elapsed time per wallet, not that
    any single fresh wallet is blocked outright."""
    settings = get_settings()
    created_at = user.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - created_at).days
    tiers_earned = age_days // settings.sybil_vote_weight_period_days
    return min(1 + tiers_earned, settings.sybil_vote_weight_max)


async def _get_proposal_or_404(proposal_id: int, db: AsyncSession) -> Proposal:
    proposal = await db.get(Proposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found.")
    return proposal


async def _get_proposal_for_update_or_404(proposal_id: int, db: AsyncSession) -> Proposal:
    """Same as _get_proposal_or_404, but holds a row lock for the rest of
    this transaction — use for every write that reads-then-mutates a
    Proposal (see module docstring's "Row locking" section). Never use
    for a plain read (list_proposals/get_proposal) — locking rows a GET
    request has no intention of writing to would only add contention.
    """
    result = await db.execute(select(Proposal).where(Proposal.id == proposal_id).with_for_update())
    proposal = result.scalar_one_or_none()
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
    """Pass/fail is FOR's share of *decided* ballots either way — abstains
    count toward quorum but don't move the pass threshold. Quorum itself
    branches by chain linkage, and the two are NOT interchangeable
    concepts (see Proposal.quorum_threshold_gen's own model docstring for
    the live bug this split fixes):

      - LEGACY_OFFCHAIN: turnout as a PERCENTAGE of every wallet that's
        ever signed in, compared against quorum_threshold (also a
        percentage). No on-chain equivalent exists for "every wallet
        that's ever signed in" — GenVM has no wallet registry.
      - on-chain (quorum_threshold_gen set): turnout is real GEN,
        compared directly against quorum_threshold_gen (also GEN) — a
        percentage of eligible_voters would be meaningless here. turnout_
        pct instead reports how close real turnout is to the real GEN
        quorum (100% == quorum exactly met), which is what finalize_
        proposal on the contract actually decides against.

    Only ever a *display* computation either way — for an on-chain
    proposal the real, authoritative pass/fail decision is NuanceGovernance.
    finalize_proposal's own on-chain result, synced back by _apply_
    proposal_view; this never drives that outcome, only presents it
    consistently before/after it's known.

    FIXED 2026-09-13 — total_for/against/abstain are now Decimal (see
    Proposal.total_for's own model docstring), and Python refuses to mix
    float and Decimal in the same expression (`100.0 * Decimal(...)`
    raises TypeError). Converted to float once, up front — this function
    only ever produces a *display* percentage, where float precision loss
    is irrelevant; the stored Proposal columns themselves stay exact
    Decimal, untouched by this conversion."""
    total_for = float(proposal.total_for)
    total_against = float(proposal.total_against)
    total_abstain = float(proposal.total_abstain)

    turnout_power = total_for + total_against + total_abstain

    if proposal.quorum_threshold_gen is not None:
        quorum_gen = float(proposal.quorum_threshold_gen)
        turnout_pct = (100.0 * turnout_power / quorum_gen) if quorum_gen else 0.0
        quorum_met = turnout_power >= quorum_gen
    else:
        turnout_pct = (100.0 * turnout_power / eligible_voters) if eligible_voters else 0.0
        quorum_met = turnout_pct >= proposal.quorum_threshold

    decided = total_for + total_against
    for_pct = (100.0 * total_for / decided) if decided else 0.0
    against_pct = (100.0 * total_against / decided) if decided else 0.0
    abstain_pct = (100.0 * total_abstain / turnout_power) if turnout_power else 0.0

    return {
        "turnout_pct": round(turnout_pct, 1),
        "for_pct": round(for_pct, 1),
        "against_pct": round(against_pct, 1),
        "abstain_pct": round(abstain_pct, 1),
        "quorum_met": quorum_met,
    }


def _finalize_if_due(proposal: Proposal, eligible_voters: int) -> bool:
    """The actual PASSED/REJECTED state transition, shared by the explicit
    POST /proposals/{id}/finalize endpoint below and the lazy auto-
    finalize in list_proposals/get_proposal (added 2026-09-10 — closing a
    real gap found during an integration audit: nothing in this app,
    frontend or backend, ever called finalize_proposal automatically or
    exposed a button for it, so every proposal stayed stuck at ACTIVE
    forever once voting closed, even though this function's own
    docstring already anticipated "a future bulk sweep" that was never
    built). Mutates `proposal` in place and returns whether it changed
    anything; the caller is responsible for committing — a plain GET
    auto-finalizing a stale proposal as a side effect is a deliberate,
    low-risk write (see list_proposals' own comment on why no row lock
    is needed here specifically), not something every caller should
    re-derive.
    """
    if proposal.status != ProposalStatus.ACTIVE:
        return False
    # FIXED 2026-09-13 — an on-chain-linked proposal's real outcome is
    # decided by NuanceGovernance.finalize_proposal itself (triggered by
    # services/genlayer_indexer.py::trigger_pending_proposal_finalizations,
    # synced back via _apply_proposal_view), not by this off-chain
    # arithmetic. Running this too would risk the DB briefly disagreeing
    # with the chain (or, worse, permanently — this function's own
    # "status only ever leaves ACTIVE once" guarantee would then block
    # the real on-chain result from ever landing).
    if proposal.on_chain_proposal_id is not None:
        return False
    if datetime.now(timezone.utc) < _aware(proposal.end_time):
        return False

    progress = _progress(proposal, eligible_voters)
    passed = progress["quorum_met"] and progress["for_pct"] >= proposal.pass_threshold
    proposal.status = ProposalStatus.PASSED if passed else ProposalStatus.REJECTED
    return True


def _proposal_fields(
    proposal: Proposal,
    eligible_voters: int,
    user_vote: VoteChoice | None,
    user_vote_stake_amount: Decimal | None = None,
) -> dict:
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
        "quorum_threshold_gen": proposal.quorum_threshold_gen,
        "pass_threshold": proposal.pass_threshold,
        "total_for": proposal.total_for,
        "total_against": proposal.total_against,
        "total_abstain": proposal.total_abstain,
        "executed_by": proposal.executed_by,
        "executed_at": proposal.executed_at,
        "created_at": proposal.created_at,
        "user_vote": user_vote,
        # Only meaningful alongside an on-chain user_vote — None for a
        # legacy off-chain vote (see Vote.stake_amount's own docstring),
        # which real GEN never backed in the first place.
        "user_vote_stake_amount": user_vote_stake_amount,
        "on_chain_proposal_id": proposal.on_chain_proposal_id,
        "chain_status": proposal.chain_status,
        "on_chain_tx_hash": proposal.on_chain_tx_hash,
        "is_queued_for_on_chain": (
            proposal.deploy_attempted_at is not None and proposal.on_chain_proposal_id is None
        ),
        "governance_contract_address": get_settings().governance_contract_address,
        **_progress(proposal, eligible_voters),
    }


def _adjust_tally(proposal: Proposal, choice: VoteChoice, delta: int | Decimal) -> None:
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

    # Lazy auto-finalize (see _finalize_if_due's own docstring). No row
    # lock here on purpose — a GET has no business contending with a
    # concurrent voter/finalizer for the row, and a racing double-
    # finalize converges on the same deterministic PASSED/REJECTED value
    # either way (the tally it's computed from doesn't change), unlike
    # vote-casting's read-modify-write, which genuinely needs the lock
    # _get_proposal_for_update_or_404 gives it.
    # A list comprehension, not any(...) directly on the generator — any()
    # short-circuits on the first True, which here would silently skip
    # calling _finalize_if_due (a real mutation, not a pure predicate) on
    # every proposal after the first one due.
    any_finalized = [_finalize_if_due(p, eligible_voters) for p in proposals]
    if any(any_finalized):
        await db.commit()

    user_votes: dict[int, Vote] = {}
    if current_user is not None and proposals:
        vote_result = await db.execute(
            select(Vote).where(
                Vote.voter_address == current_user.wallet_address,
                Vote.proposal_id.in_([p.id for p in proposals]),
                # FIXED 2026-09-13 — a retracted on-chain vote (see
                # retract_vote_on_chain) keeps its Vote row (retracted_at
                # set, not deleted — see model docstring), so this must
                # exclude it explicitly or a wallet that unvoted would
                # still see its old, no-longer-active choice reported
                # back as "your current vote".
                Vote.retracted_at.is_(None),
            )
        )
        user_votes = {v.proposal_id: v for v in vote_result.scalars().all()}

    return [
        ProposalRead(
            **_proposal_fields(
                p,
                eligible_voters,
                user_votes[p.id].choice if p.id in user_votes else None,
                user_votes[p.id].stake_amount if p.id in user_votes else None,
            )
        )
        for p in proposals
    ]


@router.get("/{proposal_id}", response_model=ProposalDetailRead)
async def get_proposal(
    proposal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
) -> ProposalDetailRead:
    proposal = await _get_proposal_or_404(proposal_id, db)
    eligible_voters = await _total_eligible_voters(db)

    if _finalize_if_due(proposal, eligible_voters):
        await db.commit()
        await db.refresh(proposal)

    vote_result = await db.execute(
        select(Vote).where(Vote.proposal_id == proposal_id).order_by(Vote.created_at.asc())
    )
    votes = list(vote_result.scalars().all())
    # See list_proposals' identical fix note just above — a retracted
    # vote's row stays but must not be reported as the current one.
    user_vote_row = next(
        (
            v
            for v in votes
            if current_user
            and v.voter_address == current_user.wallet_address
            and v.retracted_at is None
        ),
        None,
    )

    fields = _proposal_fields(
        proposal,
        eligible_voters,
        user_vote_row.choice if user_vote_row else None,
        user_vote_row.stake_amount if user_vote_row else None,
    )
    return ProposalDetailRead(**fields, votes=[VoteRead.model_validate(v) for v in votes])


@router.post("", response_model=ProposalRead, status_code=status.HTTP_201_CREATED)
async def create_proposal(
    payload: ProposalCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProposalRead:
    settings = get_settings()
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
        # See Proposal.quorum_threshold_gen's own model docstring — a
        # client-supplied value is used as-is; otherwise (no create-
        # proposal UI collects this yet) a sensible default is applied
        # right below, but only once we know this proposal is actually
        # going on-chain — a purely off-chain proposal has no use for it
        # at all and should keep it null.
        quorum_threshold_gen=payload.quorum_threshold_gen,
    )
    # FIXED 2026-09-13 — asked directly to make voting/unvoting real GEN
    # actions ("like a real Governance"): a proposal needs an on-chain
    # NuanceGovernance entry to vote on at all, so new proposals now
    # queue a real create_proposal call. deploy_attempted_at is set HERE,
    # synchronously, in the SAME transaction as the row's own creation —
    # not only inside create_proposal_on_chain's own background task —
    # closing a real race found live in the predictions equivalent of
    # this exact problem (routers/predictions.py::place_bet's own
    # 2026-09-13 fix note): without this, a brand-new proposal would be
    # briefly indistinguishable from a legacy off-chain one (both show
    # deploy_attempted_at as null) during the gap before the background
    # task's own first write lands, and cast_vote below would wrongly
    # accept a real off-chain vote into a ledger this proposal is about
    # to outgrow. Existing proposals never get this set retroactively —
    # confirmed directly: only new proposals go on-chain.
    if settings.auto_create_proposals_on_chain and settings.governance_contract_address:
        proposal.deploy_attempted_at = now
        if proposal.quorum_threshold_gen is None:
            proposal.quorum_threshold_gen = _DEFAULT_ON_CHAIN_QUORUM_GEN
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)

    if proposal.deploy_attempted_at is not None:
        background_tasks.add_task(create_proposal_on_chain, proposal.id)

    eligible_voters = await _total_eligible_voters(db)
    return ProposalRead(**_proposal_fields(proposal, eligible_voters, user_vote=None))


@router.post("/{proposal_id}/vote", response_model=ProposalRead)
async def cast_vote(
    proposal_id: int,
    payload: VoteCreate,
    db: AsyncSession = Depends(get_db),
    # ROADMAP.md Part 4 6.1 — see routers/escrows.py::create_escrow's own
    # note on require_user_with_scope.
    current_user: User = Depends(require_user_with_scope("vote:cast")),
) -> ProposalRead:
    proposal = await _get_proposal_for_update_or_404(proposal_id, db)

    # FIXED 2026-09-13 — a linked (or queued-to-link, see create_proposal's
    # own note on why this checks deploy_attempted_at rather than only
    # on_chain_proposal_id) proposal's real vote tally is real, GEN-staked
    # GEN — an off-chain Vote mirrored in here for it would be notional
    # bookkeeping with no real stake behind it, and would be orphaned the
    # moment the real on-chain link lands. Same ChainUnavailableError
    # shape routers/predictions.py::place_bet already uses for the
    # identical reason.
    if proposal.deploy_attempted_at is not None:
        raise ChainUnavailableError(
            f"Proposal {proposal_id} is on-chain governance — use POST "
            f"/proposals/{proposal_id}/vote/on-chain instead of this off-chain endpoint."
        )

    if proposal.status != ProposalStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Voting is closed for this proposal."
        )
    if datetime.now(timezone.utc) >= _aware(proposal.end_time):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Voting period has ended.")

    weight = _voting_power(current_user)

    result = await db.execute(
        select(Vote).where(
            Vote.proposal_id == proposal_id, Vote.voter_address == current_user.wallet_address
        )
    )
    existing = result.scalar_one_or_none()

    if existing is not None:
        _adjust_tally(proposal, existing.choice, -existing.voting_power)
        existing.choice = payload.choice
        existing.voting_power = weight
    else:
        db.add(
            Vote(
                proposal_id=proposal_id,
                voter_address=current_user.wallet_address,
                choice=payload.choice,
                voting_power=weight,
            )
        )

    _adjust_tally(proposal, payload.choice, weight)

    await db.commit()
    await db.refresh(proposal)

    eligible_voters = await _total_eligible_voters(db)
    return ProposalRead(**_proposal_fields(proposal, eligible_voters, user_vote=payload.choice))


@router.post(
    "/{proposal_id}/vote/on-chain",
    response_model=ProposalRead,
    status_code=status.HTTP_201_CREATED,
)
async def cast_vote_on_chain(
    proposal_id: int,
    payload: VoteOnChainAck,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user_with_scope("vote:cast")),
) -> ProposalRead:
    """The on-chain counterpart to cast_vote above — reached once
    components/app/genlayer-write-client.ts's castVoteOnChain has already
    signed and sent a real, payable NuanceGovernance.cast_vote transaction
    directly to the chain. Doesn't verify the hash is real (same
    reasoning routers/predictions.py::place_bet_on_chain's own docstring
    gives — nothing here is a trust boundary for the proposal's actual
    outcome, which services/genlayer_indexer.py's real get_proposal sync
    is); this only mirrors the stake into a Vote row so "my votes" keeps
    working, since that sync doesn't track individual voters' on-chain
    stakes, only the proposal's own tallies as a whole.

    Matches contracts/nuance_governance.py::cast_vote's own "exactly one
    active vote per wallet per proposal, retract first to change it" rule
    — an existing NOT-retracted Vote row is rejected here the same way
    the contract itself would reject the real transaction, so a client
    that got this ack call wrong at least fails obviously rather than
    silently doubling a mirrored stake.
    """
    proposal = await _get_proposal_for_update_or_404(proposal_id, db)
    if proposal.on_chain_proposal_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This proposal isn't linked to the on-chain governance registry yet.",
        )
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
    if existing is not None and existing.retracted_at is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have an active vote on this proposal — retract it first to change your vote.",
        )

    if existing is not None:
        # A previously retracted row — reuse it (same reuse-not-delete
        # choice the contract itself makes for its own TreeMap entry).
        existing.choice = payload.choice
        existing.stake_amount = payload.stake_amount
        existing.on_chain_tx_hash = payload.tx_hash
        existing.retracted_at = None
        existing.retract_tx_hash = None
    else:
        db.add(
            Vote(
                proposal_id=proposal_id,
                voter_address=current_user.wallet_address,
                choice=payload.choice,
                # Unused for an on-chain vote — see model docstring;
                # stake_amount below is this ballot's real weight.
                voting_power=0,
                stake_amount=payload.stake_amount,
                on_chain_tx_hash=payload.tx_hash,
            )
        )

    _adjust_tally(proposal, payload.choice, payload.stake_amount)

    await db.commit()
    await db.refresh(proposal)

    eligible_voters = await _total_eligible_voters(db)
    return ProposalRead(
        **_proposal_fields(proposal, eligible_voters, payload.choice, payload.stake_amount)
    )


@router.post("/{proposal_id}/retract-vote/on-chain", response_model=ProposalRead)
async def retract_vote_on_chain(
    proposal_id: int,
    payload: RetractVoteOnChainAck,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProposalRead:
    """The new unvote — the other half of this whole update ("any user
    that vote and unvote you will have to use Gen token"). Reached once
    the frontend has already signed and sent a real NuanceGovernance.
    retract_vote transaction, which refunds the caller's exact staked GEN
    (see that contract method's own docstring). Deliberately allowed
    regardless of proposal.status, matching the contract side exactly —
    this is the voter's own money, not something forfeited by voting
    closing or by which way the decision went.
    """
    proposal = await _get_proposal_for_update_or_404(proposal_id, db)
    result = await db.execute(
        select(Vote).where(
            Vote.proposal_id == proposal_id, Vote.voter_address == current_user.wallet_address
        )
    )
    vote = result.scalar_one_or_none()
    if vote is None or vote.retracted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You have no active vote on this proposal."
        )

    _adjust_tally(proposal, vote.choice, -(vote.stake_amount or Decimal("0")))

    vote.retracted_at = datetime.now(timezone.utc)
    vote.retract_tx_hash = payload.tx_hash
    vote.stake_amount = Decimal("0")

    await db.commit()
    await db.refresh(proposal)

    eligible_voters = await _total_eligible_voters(db)
    return ProposalRead(**_proposal_fields(proposal, eligible_voters, user_vote=None))


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
    proposal = await _get_proposal_for_update_or_404(proposal_id, db)
    eligible_voters = await _total_eligible_voters(db)

    if proposal.status != ProposalStatus.ACTIVE:
        return ProposalRead(**_proposal_fields(proposal, eligible_voters, user_vote=None))

    # FIXED 2026-09-13 — an on-chain-linked proposal's real finalize is
    # services/genlayer_indexer.py::trigger_pending_proposal_finalizations,
    # automatic and unconditional once end_time passes — no manual trigger
    # exists or is needed. Without this check, calling this endpoint on
    # one used to silently do nothing (_finalize_if_due's own new guard
    # returns False for it) while still returning 200 with the proposal
    # unchanged at ACTIVE — indistinguishable from success.
    if proposal.on_chain_proposal_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This proposal finalizes automatically on-chain once voting ends — "
            "no manual trigger is available or needed.",
        )

    if datetime.now(timezone.utc) < _aware(proposal.end_time):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Voting is still open; ends at {proposal.end_time.isoformat()}.",
        )

    _finalize_if_due(proposal, eligible_voters)  # status is ACTIVE, off-chain, and past due — always True here

    await db.commit()
    await db.refresh(proposal)
    return ProposalRead(**_proposal_fields(proposal, eligible_voters, user_vote=None))


@router.post("/{proposal_id}/execute", response_model=ProposalRead)
async def execute_proposal(
    proposal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProposalRead:
    """Moves a PASSED proposal to EXECUTED — the formal "this decision has
    been enacted" marker. Not idempotent like finalize: a proposal can only
    be executed once, so a second call 400s rather than silently returning
    the same result, matching disputes.py's enforce_ruling precedent for
    the same "who did this and when" shape (executed_by/executed_at here,
    enforced_by/resolved_at there).

    No real on-chain effect is wired up yet (no treasury transfer, no
    parameter change) — see ROADMAP.md Part 3; this is deliberately scoped
    to just the status transition until there's a real effect to apply.
    """
    proposal = await _get_proposal_for_update_or_404(proposal_id, db)

    # Checked in this order so re-executing an already-executed proposal
    # reports "already executed" specifically, rather than the more
    # generic "not passed" (status has already moved to EXECUTED by then,
    # which would otherwise mask the more useful message).
    if proposal.executed_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Proposal already executed.")
    if proposal.status != ProposalStatus.PASSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only a passed proposal can be executed.",
        )

    proposal.status = ProposalStatus.EXECUTED
    proposal.executed_by = current_user.wallet_address
    proposal.executed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(proposal)

    eligible_voters = await _total_eligible_voters(db)
    return ProposalRead(**_proposal_fields(proposal, eligible_voters, user_vote=None))
