"""GET/POST /escrows, GET /escrows/{id} (+ WS/SSE live variants),
deliverable submission, release.

The AI-validator consensus step that normally follows a deliverable
submission (see plan.md section 4) lands with the consensus-engine prompt;
`submit_deliverable` here just records the submission and moves the
milestone to IN_REVIEW so that prompt has a real row to pick up.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db import AsyncSessionLocal, get_db
from app.dependencies import get_current_user, get_optional_current_user, require_user_with_scope
from app.enums import ChainStatus, ConsensusStage, ConsensusSubjectType, StatusKey
from app.models import (
    Asset,
    ConsensusJob,
    DeliverableSubmission,
    Dispute,
    DisputeEvidence,
    Escrow,
    Milestone,
    User,
    UserSettings,
)
from app.schemas import (
    DeliverableSubmissionCreate,
    DeliverableSubmissionRead,
    DisputeCreate,
    DisputeCreateRead,
    DisputeRead,
    EscrowCreate,
    EscrowRead,
    MilestoneRead,
    OnChainCancelAck,
    OnChainDisputeAck,
    OnChainFundAck,
    OnChainReleaseAck,
    OnChainSubmissionAck,
)
from app.services.consensus import run_consensus
from app.services.genlayer_deploy import deploy_escrow_contract
from app.services.realtime import format_sse, publish_escrow_update, subscribe_escrow_updates

router = APIRouter(prefix="/escrows", tags=["escrows"])
logger = logging.getLogger(__name__)
settings = get_settings()

DEFAULT_CRITERIA = "Deliverable meets the agreed brief."

ESCROW_POLL_INTERVAL_SECONDS = 3.0


async def _get_escrow_or_404(escrow_id: int, db: AsyncSession) -> Escrow:
    result = await db.execute(
        select(Escrow).where(Escrow.id == escrow_id).options(selectinload(Escrow.milestones), selectinload(Escrow.asset))
    )
    escrow = result.scalar_one_or_none()
    if escrow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Escrow not found.")
    return escrow


async def _get_escrow_for_update_or_404(escrow_id: int, db: AsyncSession) -> Escrow:
    """Same as _get_escrow_or_404, but holds a row lock on the Escrow for
    the rest of this transaction (ROADMAP.md Part 3 5.4's double-release
    race) — use for release_milestone specifically. Locking the parent
    Escrow row is enough to serialize concurrent release_milestone calls
    for the same escrow, even though the actual mutation is on one of its
    Milestone rows: a second concurrent call blocks on this same SELECT
    until the first transaction commits, and only then reads (already
    updated) milestone state — the milestone itself doesn't need its own
    separate lock. A no-op on SQLite, a real lock on Postgres, same as
    routers/governance.py's _get_proposal_for_update_or_404.
    """
    result = await db.execute(
        select(Escrow)
        .where(Escrow.id == escrow_id)
        .options(selectinload(Escrow.milestones), selectinload(Escrow.asset))
        .with_for_update()
    )
    escrow = result.scalar_one_or_none()
    if escrow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Escrow not found.")
    return escrow


async def _get_escrow_snapshot(escrow_id: int) -> dict | None:
    """Fresh session per call, same reasoning as routers/disputes.py's
    _list_messages_fresh — a WS/SSE connection's own SQLAlchemy identity
    map must never keep handing back a stale Escrow across ticks/publishes.
    None if the escrow doesn't exist (e.g. a bad id in the URL)."""
    async with AsyncSessionLocal() as db:
        escrow = (
            await db.execute(
                select(Escrow)
                .where(Escrow.id == escrow_id)
                .options(selectinload(Escrow.milestones), selectinload(Escrow.asset))
            )
        ).scalar_one_or_none()
        if escrow is None:
            return None
        return EscrowRead.model_validate(escrow).model_dump(mode="json")


async def _publish_escrow_snapshot(escrow_id: int) -> None:
    """Called after every commit that changes something an escrow's own
    detail view shows — see services/realtime.py::publish_escrow_update's
    own docstring for the full list of call sites and the gap this
    closes. Best-effort, same as every other publish in this codebase:
    a Redis hiccup here never fails the write that triggered it, a
    subscriber just falls back to its own polling tier instead."""
    snapshot = await _get_escrow_snapshot(escrow_id)
    if snapshot is not None:
        await publish_escrow_update(escrow_id, {"type": "escrow", "escrow": snapshot})


@router.websocket("/ws/{escrow_id}")
async def escrow_updates_ws(websocket: WebSocket, escrow_id: int) -> None:
    """Live counterpart to GET /escrows/{id} — added 2026-09-12 after a
    real gap found live: an already-open escrow detail view had no way to
    learn that a background auto-deploy had just linked a contract (or
    any other server-side change — funding, a milestone's consensus
    verdict landing, an on-chain sync from services/genlayer_indexer.py)
    short of a manual page reload. Same structure as routers/disputes.py's
    dispute_messages_ws: subscribe *before* the initial read (so nothing
    published in between is missed), Redis pub/sub when reachable, db
    polling unchanged otherwise. No terminal state here either — an
    escrow keeps changing for its whole lifetime, so this streams until
    the client disconnects.

    Unlike dispute messages (an append-only list, diffed by id), an
    escrow is one mutable record — every tick/publish sends the FULL
    current snapshot and the client just replaces its local copy, so
    there's no "new since last time" comparison to get wrong.
    """
    await websocket.accept()
    try:
        updates = await subscribe_escrow_updates(escrow_id)

        snapshot = await _get_escrow_snapshot(escrow_id)
        if snapshot is None:
            await websocket.send_json({"error": "Escrow not found."})
            await websocket.close(code=1008)
            return
        await websocket.send_json({"type": "escrow", "escrow": snapshot})

        if updates is not None:
            async for payload in updates:
                await websocket.send_json(payload)
            return

        # Redis unavailable — poll and only send when the snapshot has
        # actually changed (a plain string comparison of the serialized
        # JSON is enough here: there's no incrementing id to diff against
        # the way dispute messages has, and re-sending an identical
        # snapshot every tick would be pure waste, not a correctness
        # issue, but still worth skipping).
        last_sent = json.dumps(snapshot, sort_keys=True)
        while True:
            await asyncio.sleep(ESCROW_POLL_INTERVAL_SECONDS)
            fresh = await _get_escrow_snapshot(escrow_id)
            if fresh is None:
                await websocket.send_json({"error": "Escrow not found."})
                await websocket.close(code=1008)
                return
            serialized = json.dumps(fresh, sort_keys=True)
            if serialized != last_sent:
                await websocket.send_json({"type": "escrow", "escrow": fresh})
                last_sent = serialized
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 — never let a bad tick crash the server, just drop this connection
        logger.exception("Escrow updates WS tick failed for escrow %s", escrow_id)
        try:
            await websocket.close(code=1011)
        except RuntimeError:
            pass  # already closed


async def _escrow_updates_sse_events(escrow_id: int) -> AsyncIterator[str]:
    """SSE counterpart to escrow_updates_ws — see routers/consensus.py's
    _consensus_sse_events / routers/disputes.py's
    _dispute_messages_sse_events for why this is factored out as its own
    generator (directly testable) and ROADMAP.md Part 3 5.2 for why SSE
    exists as a fallback tier at all."""
    updates = await subscribe_escrow_updates(escrow_id)

    snapshot = await _get_escrow_snapshot(escrow_id)
    if snapshot is None:
        yield format_sse({"error": "Escrow not found."})
        return
    yield format_sse({"type": "escrow", "escrow": snapshot})

    if updates is not None:
        async for payload in updates:
            yield format_sse(payload)
        return

    last_sent = json.dumps(snapshot, sort_keys=True)
    while True:
        await asyncio.sleep(ESCROW_POLL_INTERVAL_SECONDS)
        fresh = await _get_escrow_snapshot(escrow_id)
        if fresh is None:
            yield format_sse({"error": "Escrow not found."})
            return
        serialized = json.dumps(fresh, sort_keys=True)
        if serialized != last_sent:
            yield format_sse({"type": "escrow", "escrow": fresh})
            last_sent = serialized


@router.get("/sse/{escrow_id}")
async def escrow_updates_sse(escrow_id: int) -> StreamingResponse:
    return StreamingResponse(
        _escrow_updates_sse_events(escrow_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _active_milestone(escrow: Escrow) -> Milestone | None:
    """First not-yet-APPROVED milestone by order_index — a stand-in for the
    frontend's `activeMilestoneIndex` (status.ts) until that logic is
    ported server-side verbatim. Deliberately EXCLUDES an approved
    milestone — right for "what's still open to submit a deliverable
    against," but NOT for release_milestone below, which needs the
    opposite (an approved milestone specifically) — see
    _releasable_milestone."""
    for milestone in escrow.milestones:
        if milestone.status_key != StatusKey.APPROVED:
            return milestone
    return None


def _releasable_milestone(escrow: Escrow) -> Milestone | None:
    """First milestone that's APPROVED and not yet released, by
    order_index. FIXED 2026-09-08 — release_milestone used to reuse
    _active_milestone for this, which explicitly EXCLUDES an approved
    milestone (see that function's own docstring) — meaning
    release_milestone 400'd on literally every real, consensus-approved
    milestone; the only way it ever returned 200 was calling it on a
    milestone that had never actually been approved by consensus at all
    (confirmed live: a fresh PENDING milestone released "successfully"
    with zero verdict ever having run). This is the real fix, not the
    same lookup repurposed."""
    for milestone in escrow.milestones:
        if milestone.status_key == StatusKey.APPROVED and milestone.released_at is None:
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
    query = select(Escrow).options(selectinload(Escrow.milestones), selectinload(Escrow.asset)).order_by(Escrow.created_at.desc())
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
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    # ROADMAP.md Part 4 6.1 — accepts either the normal browser JWT or an
    # X-Api-Key with the "escrow:create" scope, so a non-browser agent can
    # create an escrow without ever going through the nonce/personal_sign
    # flow. See app/dependencies.py::require_user_with_scope.
    current_user: User = Depends(require_user_with_scope("escrow:create")),
) -> Escrow:
    # Ensure counterparty user exists so foreign key is satisfied
    counterparty = await db.get(User, payload.counterparty_address)
    if counterparty is None:
        counterparty = User(wallet_address=payload.counterparty_address)
        counterparty.settings = UserSettings(wallet_address=payload.counterparty_address)
        db.add(counterparty)

    # ROADMAP.md Part 4 6.2 — resolved by symbol, not trusted as a raw id:
    # EscrowCreate.asset_symbol is a caller-friendly "GEN"/"USDC", looked
    # up against the real Asset row so an unknown/typo'd symbol 400s here
    # rather than either silently falling back to GEN or letting a bad
    # foreign key slip through to the database to fail on.
    asset_result = await db.execute(select(Asset).where(Asset.symbol == payload.asset_symbol))
    asset = asset_result.scalar_one_or_none()
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown asset '{payload.asset_symbol}'.",
        )

    escrow = Escrow(
        creator_address=current_user.wallet_address,
        counterparty_address=payload.counterparty_address,
        title=payload.title,
        total=payload.total,
        asset_id=asset.id,
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
    escrow.asset = asset  # already loaded above — avoids a lazy-load on the response

    # The actual Part 2 finish line: every new escrow gets a real deployed
    # NuanceEscrow instance automatically, not just ones manually linked
    # via `genlayer_indexer.py --link-demo`. Queued as a background task
    # (same pattern as run_consensus above) since a real Bradbury deploy
    # can take up to ~3 minutes — the 201 response returns immediately,
    # with contract_address still null; submitDeliverable/
    # escalateToDisputeCourt correctly stay on the legacy off-chain path
    # until services/genlayer_deploy.py's task actually links it.
    if settings.auto_deploy_escrow_contracts:
        background_tasks.add_task(deploy_escrow_contract, escrow.id)

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
    """FIXED 2026-09-12 — a real authorization gap found live: this
    endpoint never checked who was calling it at all. Any signed-in
    wallet — not the counterparty, not even a party to this escrow —
    could submit a "deliverable" for someone else's escrow, trigger real
    AI consensus, and move the milestone straight to APPROVED (payout-
    eligible). Confirmed live: the on-chain contract's own
    submit_deliverable has always enforced both of the checks added
    below (`gl.message.sender_address != self.counterparty` and
    `self.status != "active"` — contracts/nuance_escrow.py) — this
    off-chain sibling had neither, despite existing specifically so an
    off-chain escrow gets equivalent behavior to an on-chain one.
    """
    escrow = await _get_escrow_or_404(escrow_id, db)
    if current_user.wallet_address != escrow.counterparty_address:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the escrow counterparty can submit a deliverable.",
        )
    if escrow.status_key == StatusKey.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This escrow has been cancelled — no deliverable can be submitted.",
        )

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
    await _publish_escrow_snapshot(escrow_id)

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


@router.post(
    "/{escrow_id}/fund/on-chain",
    response_model=EscrowRead,
    status_code=status.HTTP_201_CREATED,
)
async def fund_escrow_on_chain(
    escrow_id: int,
    payload: OnChainFundAck,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Escrow:
    """Reached once components/app/genlayer-write-client.ts's
    fundEscrowOnChain has already signed and sent a real, *payable*
    NuanceEscrow.fund_escrow transaction — real GEN has already left the
    creator's wallet and now sits in the deployed contract's balance by
    the time this endpoint runs. Only the escrow creator may call
    fund_escrow on the contract itself (see that method's own source), so
    this endpoint enforces the same restriction rather than let anyone
    mark an escrow "funded." This does NOT verify the hash is real or
    read back the actual funded_amount — see OnChainFundAck's own
    docstring on why that's fine; it's UI bookkeeping (hide the "Fund
    Escrow" action), not the source of truth for whether the milestone
    can actually be released (release_milestone's own on-chain check
    against funded_amount is what actually matters).
    """
    escrow = await _get_escrow_or_404(escrow_id, db)
    if current_user.wallet_address != escrow.creator_address:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the escrow creator can fund this escrow.",
        )
    if escrow.contract_address is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This escrow isn't linked to a deployed contract yet — funding "
            "isn't available until auto-deploy finishes.",
        )

    escrow.funded_tx_hash = payload.tx_hash
    await db.commit()
    await db.refresh(escrow, attribute_names=["milestones"])
    await _publish_escrow_snapshot(escrow_id)
    return escrow


@router.post(
    "/{escrow_id}/cancel/on-chain",
    response_model=EscrowRead,
    status_code=status.HTTP_201_CREATED,
)
async def cancel_escrow_on_chain(
    escrow_id: int,
    payload: OnChainCancelAck,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Escrow:
    """Reached once components/app/genlayer-write-client.ts's
    cancelEscrowOnChain has already signed and sent a real
    NuanceEscrow.cancel_escrow transaction — the contract itself has
    already refunded whatever was locked back to the creator's wallet by
    the time this endpoint runs (see that contract method's own
    docstring). Only the escrow creator may call cancel_escrow on the
    contract itself, so this endpoint enforces the same restriction.

    Unlike fund/deliverable acks, this DOES immediately flip status_key —
    see OnChainCancelAck's own docstring on why that's safe here
    specifically (real enforcement lives entirely on the contract; this
    is local bookkeeping only, same trust level raise_dispute_on_chain's
    ack already uses elsewhere in this file).
    """
    escrow = await _get_escrow_or_404(escrow_id, db)
    if current_user.wallet_address != escrow.creator_address:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the escrow creator can cancel this escrow.",
        )
    if escrow.contract_address is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This escrow isn't linked to a deployed contract — nothing on-chain to cancel.",
        )
    if escrow.status_key == StatusKey.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This escrow has already been cancelled.",
        )

    escrow.status_key = StatusKey.CANCELLED
    escrow.cancelled_tx_hash = payload.tx_hash
    await db.commit()
    await db.refresh(escrow, attribute_names=["milestones"])
    await _publish_escrow_snapshot(escrow_id)
    return escrow


@router.post(
    "/{escrow_id}/deliverable/on-chain",
    response_model=MilestoneRead,
    status_code=status.HTTP_201_CREATED,
)
async def submit_deliverable_on_chain(
    escrow_id: int,
    payload: OnChainSubmissionAck,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Milestone:
    """The on-chain counterpart to submit_deliverable above — reached once
    components/app/genlayer-write-client.ts has already signed and sent a
    real `NuanceEscrow.submit_deliverable` transaction directly to the
    chain (see ROADMAP.md 4.6's verified writeContract pattern). This
    endpoint does NOT run consensus, queue a ConsensusJob, or touch
    deliverable text/reasoning — GenVM's own validator committee is
    already doing that job on the deployed contract. All this does is
    remember the tx hash so services/genlayer_indexer.py has something to
    poll; see OnChainSubmissionAck's own docstring on why that's safe even
    though nothing here verifies the hash is real.
    """
    escrow = await _get_escrow_or_404(escrow_id, db)
    if current_user.wallet_address != escrow.counterparty_address:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the escrow counterparty can submit a deliverable.",
        )
    if escrow.contract_address is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This escrow isn't linked to a deployed contract — use the "
            "off-chain POST /escrows/{id}/deliverable instead.",
        )

    milestone = _active_milestone(escrow)
    if milestone is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This escrow has no active milestone to submit against.",
        )
    if milestone.on_chain_index is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This milestone isn't linked to an index inside the deployed contract.",
        )

    milestone.on_chain_tx_hash = payload.tx_hash
    milestone.chain_status = ChainStatus.PROCESSING
    milestone.status_key = StatusKey.IN_REVIEW

    await db.commit()
    await db.refresh(milestone)
    await _publish_escrow_snapshot(escrow_id)
    return milestone


async def _default_dispute_issue(db: AsyncSession, milestone: Milestone) -> str:
    """Fallback claim text for raise_dispute when the caller doesn't
    supply one — the "Escalate to Internet Court" button (escrow-detail-
    view.tsx) fires with no form of its own, so this pulls the milestone's
    most recent AI verdict reasoning to explain what's actually being
    escalated, rather than leaving `issue` blank."""
    result = await db.execute(
        select(ConsensusJob)
        .where(
            ConsensusJob.subject_type == ConsensusSubjectType.MILESTONE,
            ConsensusJob.subject_id == milestone.id,
        )
        .order_by(ConsensusJob.created_at.desc())
        .limit(1)
    )
    job = result.scalars().first()
    if job is not None and job.verdict_reasoning:
        return f"Escalating AI Consensus verdict on '{milestone.name}': {job.verdict_reasoning}"
    return f"Escalating milestone '{milestone.name}' to Dispute Court review."


@router.post(
    "/{escrow_id}/dispute",
    response_model=DisputeCreateRead,
    status_code=status.HTTP_201_CREATED,
)
async def raise_dispute(
    escrow_id: int,
    payload: DisputeCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DisputeCreateRead:
    """Escalates the escrow's active milestone to a formal Dispute Court
    review. Not previously implemented anywhere in this backend — ROADMAP.md
    3.1's Part 1 checklist marks "GET/POST /disputes (implicit via escrow)"
    done, but no such endpoint, implicit or otherwise, actually existed;
    escrow-detail-view.tsx's "Escalate to Internet Court" button has been
    unwired since it was written. This is that missing endpoint, escrow-
    scoped to match the "implicit via escrow" framing rather than a bare
    POST /disputes.

    Either party to the escrow may open one — mirrors contracts/
    nuance_dispute_court.py's file_dispute (claimant is whoever calls it;
    the other party is derivable from the escrow, same as this repo's
    existing mapDispute on the frontend already does — no separate
    `respondent` field needed). Creates the Dispute row and an initial
    DisputeEvidence entry together, then queues the same AI-jury review
    submit_evidence already runs below — a claim with no supporting text
    isn't reviewable.
    """
    escrow = await _get_escrow_or_404(escrow_id, db)
    if current_user.wallet_address not in (escrow.creator_address, escrow.counterparty_address):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a party to this escrow can raise a dispute.",
        )

    milestone = _active_milestone(escrow)
    if milestone is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This escrow has no active milestone to dispute.",
        )

    existing = await db.execute(
        select(Dispute).where(
            Dispute.milestone_id == milestone.id, Dispute.status_key == StatusKey.DISPUTED
        )
    )
    if existing.scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This milestone already has an open dispute.",
        )

    issue = payload.issue or await _default_dispute_issue(db, milestone)

    dispute = Dispute(
        escrow_id=escrow.id,
        milestone_id=milestone.id,
        opened_by_address=current_user.wallet_address,
        issue=issue,
        status_key=StatusKey.DISPUTED,
    )
    db.add(dispute)
    await db.flush()  # populates dispute.id before the evidence row below references it

    db.add(
        DisputeEvidence(
            dispute_id=dispute.id,
            submitter_address=current_user.wallet_address,
            description=issue,
        )
    )

    # Queued synchronously, same pattern as submit_deliverable/submit_evidence
    # above, so the 201 response can hand back a real job id.
    job = ConsensusJob(
        subject_type=ConsensusSubjectType.DISPUTE,
        subject_id=dispute.id,
        stage=int(ConsensusStage.IDLE),
    )
    db.add(job)

    await db.commit()
    await db.refresh(dispute, attribute_names=["evidence", "messages"])
    await db.refresh(job)

    background_tasks.add_task(run_consensus, ConsensusSubjectType.DISPUTE, dispute.id, issue)

    return DisputeCreateRead.model_validate(dispute, from_attributes=True).model_copy(
        update={"consensus_job_id": job.id}
    )


@router.post(
    "/{escrow_id}/dispute/on-chain",
    response_model=DisputeRead,
    status_code=status.HTTP_201_CREATED,
)
async def raise_dispute_on_chain(
    escrow_id: int,
    payload: OnChainDisputeAck,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dispute:
    """The on-chain counterpart to raise_dispute above — reached once
    genlayer-write-client.ts has already signed and sent a real
    NuanceDisputeCourt.file_dispute transaction directly to the chain.

    Unlike submit_deliverable_on_chain (which updates an existing row),
    this CREATES the Dispute immediately, with on_chain_dispute_id left
    null — file_dispute assigns that id on-chain, and there's no cheap way
    to read a regular write call's return value back out of genlayer-js's
    receipt (see Settings.dispute_id_scan_window's own comment for why).
    services/genlayer_indexer.py's resolve_pending_dispute_ids fills it in
    asynchronously once the transaction lands, by matching (claimant,
    escrow_address, claim_statement) against the contract's own history —
    same "not a trust boundary" reasoning as OnChainSubmissionAck: nothing
    here verifies the hash is real, only the indexer reading actual chain
    state ever changes status_key/ruling.

    No ConsensusJob queued, no run_consensus — GenVM's own validator
    committee is the jury once adjudicate_dispute is actually called
    against this contract (a separate action from filing, not wired by
    this endpoint).
    """
    escrow = await _get_escrow_or_404(escrow_id, db)
    if current_user.wallet_address not in (escrow.creator_address, escrow.counterparty_address):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a party to this escrow can raise a dispute.",
        )
    if escrow.contract_address is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This escrow isn't linked to a deployed contract — use the "
            "off-chain POST /escrows/{id}/dispute instead.",
        )

    milestone = _active_milestone(escrow)
    if milestone is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This escrow has no active milestone to dispute.",
        )

    existing = await db.execute(
        select(Dispute).where(
            Dispute.milestone_id == milestone.id, Dispute.status_key == StatusKey.DISPUTED
        )
    )
    if existing.scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This milestone already has an open dispute.",
        )

    issue = payload.issue or await _default_dispute_issue(db, milestone)

    dispute = Dispute(
        escrow_id=escrow.id,
        milestone_id=milestone.id,
        opened_by_address=current_user.wallet_address,
        issue=issue,
        status_key=StatusKey.DISPUTED,
        on_chain_tx_hash=payload.tx_hash,
        chain_status=ChainStatus.PROCESSING,
    )
    db.add(dispute)
    await db.commit()
    await db.refresh(dispute, attribute_names=["evidence", "messages"])
    return dispute


@router.post("/{escrow_id}/release", response_model=EscrowRead)
async def release_milestone(
    escrow_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Escrow:
    """Legacy off-chain release — a pure DB write, no fund movement of any
    kind (there's nothing to move: an off-chain escrow's "collateral" was
    never actually locked anywhere on-chain to begin with). REJECTS an
    escrow linked to a deployed contract (below) — added 2026-09-11 after
    finding this endpoint was the ONLY thing the frontend's "Release
    Payment" button ever called, for every escrow, on-chain or not. For a
    real, funded on-chain escrow that meant clicking it just marked the
    milestone released_at in this DB with ZERO on-chain effect — the real
    GEN stayed locked in the contract, permanently unreachable, while the
    UI showed "Released ✓". See release_milestone_on_chain below, the fix.
    """
    escrow = await _get_escrow_for_update_or_404(escrow_id, db)
    if current_user.wallet_address != escrow.creator_address:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the escrow creator can release milestone funds.",
        )
    if escrow.contract_address is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This escrow is linked to a deployed contract — release the real funds "
            "via POST /escrows/{id}/release/on-chain instead.",
        )

    milestone = _releasable_milestone(escrow)
    if milestone is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No approved, unreleased milestone to release — either nothing has "
            "been approved by consensus yet, or it's already been released.",
        )

    milestone.released_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(escrow, attribute_names=["milestones"])
    await _publish_escrow_snapshot(escrow_id)
    return escrow


@router.post(
    "/{escrow_id}/release/on-chain",
    response_model=EscrowRead,
    status_code=status.HTTP_201_CREATED,
)
async def release_milestone_on_chain(
    escrow_id: int,
    payload: OnChainReleaseAck,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Escrow:
    """The on-chain counterpart to release_milestone above — reached once
    components/app/genlayer-write-client.ts's releaseMilestoneOnChain has
    already signed and sent a real, fund-moving NuanceEscrow.release_milestone
    transaction. Closes a real gap: nothing in this app called that method
    before 2026-09-11 (see OnChainReleaseAck's own docstring for the full
    incident) — a milestone approved on a funded on-chain escrow had its
    payout permanently stuck, since cancel_escrow is contract-gated to
    "no milestone ever approved."

    Same "not a trust boundary" shape as submit_deliverable_on_chain: this
    only remembers the tx hash for services/genlayer_indexer.py to poll.
    Milestone.released_at is set ONLY once the indexer reads real
    `released: true` back from the contract's own get_milestone (see
    _apply_milestone_view) — never here — so a caller reporting a bogus
    hash can make the indexer log a failed lookup, never fake a payout.
    """
    escrow = await _get_escrow_for_update_or_404(escrow_id, db)
    if current_user.wallet_address != escrow.creator_address:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the escrow creator can release milestone funds.",
        )
    if escrow.contract_address is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This escrow isn't linked to a deployed contract — use the "
            "off-chain POST /escrows/{id}/release instead.",
        )

    milestone = _releasable_milestone(escrow)
    if milestone is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No approved, unreleased milestone to release — either nothing has "
            "been approved by consensus yet, or it's already been released.",
        )
    if milestone.on_chain_index is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This milestone isn't linked to an index inside the deployed contract.",
        )

    milestone.on_chain_tx_hash = payload.tx_hash
    milestone.chain_status = ChainStatus.PROCESSING
    await db.commit()
    await db.refresh(escrow, attribute_names=["milestones"])
    await _publish_escrow_snapshot(escrow_id)
    return escrow

