"""backend/app/services/genlayer_indexer.py — Part 2, Step 4: the chain
indexer (ROADMAP.md 4.5).

Mirrors on-chain GenVM state transitions back into this backend's own
database, so the frontend keeps reading fast, cached rows from Postgres/
SQLite instead of hitting the RPC directly on every page load — exactly
the "hybrid state" architecture ROADMAP.md 4.5 describes: writes go
straight from the frontend to the contract (once lib/chain-config.ts's
`writeContract` wiring lands — not done yet, see that section), reads for
display come from here.

--- What this file actually watches, precisely (not ROADMAP 4.5's
original simplified sketch) ---
Read contracts/nuance_escrow.py, nuance_dispute_court.py, and
nuance_prediction_market.py's real source before touching this file again
if any of this stops matching:

  - NuanceEscrow: ONE contract instance per escrow (holds every milestone
    for that agreement) -> Escrow.contract_address. A specific milestone
    inside it is addressed by a u256 index -> Milestone.on_chain_index
    (NOT the same number as Milestone.id/order_index).
  - NuanceDisputeCourt: a single SHARED REGISTRY for the whole app (one
    deployed address, settings.dispute_court_contract_address) holding
    every dispute keyed by a u256 dispute_id -> Dispute.on_chain_dispute_id.
  - NuancePredictionMarket: ONE contract instance per market ->
    Prediction.contract_address.

Every one of those linking columns is null by default and nothing else in
this repo sets them yet (a real per-escrow/per-market `deployContract`
call at creation time is separate, not-yet-built work — see
scripts/deploy.ts's header on its own bootstrap-instance caveat). That
means this indexer currently has nothing to do on a fresh checkout, by
design — it finds zero linked rows and logs that, rather than erroring.
`--link-demo` below exists specifically to prove it actually works
end-to-end against a real live contract in the meantime.

--- The chain-status vs. business-status split (read before changing
either) ---
nuance_dispute_court.py's own header says this explicitly and it applies
to all three contracts: GenVM's transaction consensus states (PENDING ->
... -> ACCEPTED -> FINALIZED, with an APPEAL_* window) are NOT the same
axis as a contract's own business state (a milestone's "approved"/
"disputed", a dispute's "resolved"/"dismissed"). This file tracks both,
on purpose, as separate columns:
  - chain_status / on_chain_raw_status — GenVM's transaction-level state
    for the most recent write this app is tracking against a row (via
    on_chain_tx_hash). Vocabulary: enums.ChainStatus, which mirrors
    lib/chain-status.ts's ChainStatus field-for-field so the two layers
    can't drift (see that enum's own docstring).
  - status_key / ruling / outcome / deliverable text — the contract's own
    current business state, read straight from its view methods
    (get_milestone/get_dispute/get_market) independent of any specific
    transaction. Reused via services.consensus._apply_verdict_to_state
    for milestones/disputes rather than re-deriving that cascade (advance
    next pending milestone, lock the escrow, etc.) a second time here.

--- Why a subprocess for the RPC leg ---
See genlayer_rpc.py's own header — no verified Python GenLayer SDK exists
in this repo; genlayer-js (via scripts/genlayer-read.ts) is the one
already-verified client.

Run it:
    python -m app.services.genlayer_indexer            # poll forever
    python -m app.services.genlayer_indexer --once      # one cycle, exit
    python -m app.services.genlayer_indexer --link-demo escrow 1
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db import AsyncSessionLocal, init_db
from app.enums import ChainStatus, ConsensusSubjectType, StatusKey
from app.models import DeliverableSubmission, Dispute, Escrow, Milestone, Prediction
from app.services import genlayer_rpc, genlayer_write

# Reused rather than re-derived: the exact cascade a verdict applies
# (advance the next pending milestone to in_progress, lock/unlock the
# parent escrow, distinguish a claimant's dispute being upheld vs.
# rejected) already exists and is exercised by the off-chain consensus
# path today. Soft-private (single underscore) but same package — an
# on-chain verdict reaching the identical end state as an off-chain one
# should run through the identical state machine, not a second
# hand-copied version of it that could drift.
from app.services.consensus import _apply_verdict_to_state

logger = logging.getLogger(__name__)
settings = get_settings()

_TERMINAL_CHAIN_STATUSES = {ChainStatus.FINALIZED, ChainStatus.CANCELED}
# GenVM's raw TransactionStatus values that lib/chain-status.ts's
# "decided" bucket folds an active appeal window into (see that file's
# own comment: "includes ACCEPTED and both APPEAL_* states"). Checked
# separately from the bucket itself so an appeal can be flagged
# specifically, not just observed as "still decided, not final yet" —
# ROADMAP.md 4.5's explicit ask.
_APPEAL_RAW_STATUSES = {"APPEAL_REVEALING", "APPEAL_COMMITTING"}


def is_under_appeal(raw_status: str | None) -> bool:
    return raw_status in _APPEAL_RAW_STATUSES


# --- Gather: which rows are actually on-chain right now --------------------


async def _load_linked_rows(
    db: AsyncSession,
) -> tuple[list[Escrow], list[Dispute], list[Prediction]]:
    escrows = (
        (
            await db.execute(
                select(Escrow)
                .where(Escrow.contract_address.is_not(None))
                .options(selectinload(Escrow.milestones).selectinload(Milestone.submissions))
            )
        )
        .scalars()
        .all()
    )
    disputes = (
        (await db.execute(select(Dispute).where(Dispute.on_chain_dispute_id.is_not(None))))
        .scalars()
        .all()
    )
    predictions = (
        (
            await db.execute(
                select(Prediction)
                .where(Prediction.contract_address.is_not(None))
                .options(selectinload(Prediction.positions))
            )
        )
        .scalars()
        .all()
    )
    return list(escrows), list(disputes), list(predictions)


async def _load_unresolved_disputes(db: AsyncSession) -> list[Dispute]:
    """Disputes routers/escrows.py's raise_dispute_on_chain already
    created (a real tx was sent), but whose on-chain id resolve_pending_
    dispute_ids hasn't matched yet — see that function's own docstring for
    why this is a separate, asynchronous step rather than something the
    ack endpoint can do synchronously. Deliberately not filtered by
    chain_status: a dispute that's still PROCESSING is included too (its
    tx status gets rechecked every cycle regardless of whether a match is
    possible yet)."""
    result = await db.execute(
        select(Dispute).where(
            Dispute.on_chain_tx_hash.is_not(None), Dispute.on_chain_dispute_id.is_(None)
        )
    )
    return list(result.scalars().all())


async def resolve_pending_dispute_ids(db: AsyncSession, unresolved: list[Dispute]) -> None:
    """Fills in Dispute.on_chain_dispute_id for rows raise_dispute_on_chain
    created without one — see Settings.dispute_id_scan_window's own
    comment for why genlayer-js can't just hand this back from the
    file_dispute transaction's receipt the way scripts/deploy.ts reads a
    deployed contract's address.

    Approach: once a tracked tx has actually reached the chain (past
    "processing" — no point scanning contract storage a still-in-flight
    write hasn't touched yet), read NuanceDisputeCourt's real
    get_dispute_count() and the last `dispute_id_scan_window` disputes,
    then match each unresolved local row to exactly one of them by
    (claimant, escrow_address, claim_statement) — the three fields
    file_dispute actually took as arguments, so a real match is a real
    match, not a guess. A tx that lands as CANCELED is logged and left
    alone permanently — it will never appear in the contract's history, so
    there's nothing to match against; that dispute stays without an
    on_chain_dispute_id (chain_status still communicates the failure).
    """
    if not unresolved:
        return
    if not settings.dispute_court_contract_address:
        logger.warning(
            "%d dispute(s) awaiting on-chain id resolution but "
            "DISPUTE_COURT_CONTRACT_ADDRESS isn't configured — skipping.",
            len(unresolved),
        )
        return

    tx_hashes = [d.on_chain_tx_hash for d in unresolved if d.on_chain_tx_hash]
    _, tx_results = await genlayer_rpc.read_and_check([], tx_hashes)

    matchable: list[Dispute] = []
    for dispute in unresolved:
        tx_result = tx_results.get(dispute.on_chain_tx_hash or "")
        if tx_result is None:
            continue  # RPC/subprocess-level failure this cycle — try again next cycle
        _apply_transaction_status(dispute, tx_result)
        if dispute.chain_status in (ChainStatus.DECIDED, ChainStatus.FINALIZED):
            matchable.append(dispute)
        elif dispute.chain_status == ChainStatus.CANCELED:
            logger.error(
                "file_dispute tx canceled for local dispute id=%s (tx=%s) — this "
                "dispute will never get an on_chain_dispute_id.",
                dispute.id,
                dispute.on_chain_tx_hash,
            )

    if not matchable:
        return

    count_reads, _ = await genlayer_rpc.read_and_check(
        [
            {
                "id": "count",
                "address": settings.dispute_court_contract_address,
                "functionName": "get_dispute_count",
                "args": [],
            }
        ],
        [],
    )
    count_item = count_reads.get("count")
    if count_item is None or not count_item.get("ok"):
        logger.warning(
            "get_dispute_count failed while resolving %d pending dispute id(s): %s",
            len(matchable),
            count_item.get("error") if count_item else "no response",
        )
        return
    dispute_count = count_item.get("result")
    if not isinstance(dispute_count, int) or dispute_count <= 0:
        return

    window_start = max(0, dispute_count - settings.dispute_id_scan_window)
    scan_ids = range(dispute_count - 1, window_start - 1, -1)
    scan_reads: list[genlayer_rpc.ReadRequest] = [
        {
            "id": f"scan:{i}",
            "address": settings.dispute_court_contract_address,
            "functionName": "get_dispute",
            "args": [i],
        }
        for i in scan_ids
    ]
    scan_results, _ = await genlayer_rpc.read_and_check(scan_reads, [])

    escrow_ids = {d.escrow_id for d in matchable}
    escrow_by_id = {
        e.id: e
        for e in (await db.execute(select(Escrow).where(Escrow.id.in_(escrow_ids)))).scalars().all()
    }

    # Each real on-chain dispute id can satisfy at most one local row —
    # claimed_ids stops two local rows from both matching the same one if
    # their claim text happened to collide (same claimant re-filing
    # identical wording, e.g.).
    claimed_ids: set[int] = set()
    for dispute in matchable:
        escrow = escrow_by_id.get(dispute.escrow_id)
        if escrow is None or not escrow.contract_address:
            continue
        claimant = dispute.opened_by_address.lower()
        escrow_addr = escrow.contract_address.lower()
        for i in scan_ids:
            if i in claimed_ids:
                continue
            item = scan_results.get(f"scan:{i}")
            if item is None or not item.get("ok"):
                continue
            onchain = item["result"]
            if (
                str(onchain.get("claimant", "")).lower() == claimant
                and str(onchain.get("escrow_address", "")).lower() == escrow_addr
                and str(onchain.get("claim_statement", "")) == dispute.issue
            ):
                dispute.on_chain_dispute_id = i
                claimed_ids.add(i)
                logger.info(
                    "Resolved local dispute id=%s -> on_chain_dispute_id=%s", dispute.id, i
                )
                break


def _build_read_batch(
    escrows: list[Escrow], disputes: list[Dispute], predictions: list[Prediction]
) -> list[genlayer_rpc.ReadRequest]:
    reads: list[genlayer_rpc.ReadRequest] = []
    for escrow in escrows:
        for milestone in escrow.milestones:
            if milestone.on_chain_index is None:
                continue
            reads.append(
                {
                    "id": f"milestone:{milestone.id}",
                    "address": escrow.contract_address,
                    "functionName": "get_milestone",
                    "args": [milestone.on_chain_index],
                }
            )

    if disputes and not settings.dispute_court_contract_address:
        logger.warning(
            "%d dispute(s) have on_chain_dispute_id set but "
            "DISPUTE_COURT_CONTRACT_ADDRESS isn't configured — skipping.",
            len(disputes),
        )
    elif settings.dispute_court_contract_address:
        for dispute in disputes:
            reads.append(
                {
                    "id": f"dispute:{dispute.id}",
                    "address": settings.dispute_court_contract_address,
                    "functionName": "get_dispute",
                    "args": [dispute.on_chain_dispute_id],
                }
            )

    for prediction in predictions:
        reads.append(
            {
                "id": f"prediction:{prediction.id}",
                "address": prediction.contract_address,
                "functionName": "get_market",
                "args": [],
            }
        )
    return reads


def _collect_pending_tx_hashes(
    escrows: list[Escrow], disputes: list[Dispute], predictions: list[Prediction]
) -> dict[str, tuple[str, int]]:
    """tx_hash -> (kind, row_id), for every row whose most recently tracked
    write hasn't reached a terminal chain_status yet."""
    hashes: dict[str, tuple[str, int]] = {}
    for escrow in escrows:
        for m in escrow.milestones:
            if m.on_chain_tx_hash and m.chain_status not in _TERMINAL_CHAIN_STATUSES:
                hashes[m.on_chain_tx_hash] = ("milestone", m.id)
    for d in disputes:
        if d.on_chain_tx_hash and d.chain_status not in _TERMINAL_CHAIN_STATUSES:
            hashes[d.on_chain_tx_hash] = ("dispute", d.id)
    for p in predictions:
        if p.on_chain_tx_hash and p.chain_status not in _TERMINAL_CHAIN_STATUSES:
            hashes[p.on_chain_tx_hash] = ("prediction", p.id)
    return hashes


def _find_row(
    kind: str,
    row_id: int,
    escrows: list[Escrow],
    disputes: list[Dispute],
    predictions: list[Prediction],
) -> Milestone | Dispute | Prediction | None:
    if kind == "milestone":
        for e in escrows:
            for m in e.milestones:
                if m.id == row_id:
                    return m
    elif kind == "dispute":
        for d in disputes:
            if d.id == row_id:
                return d
    elif kind == "prediction":
        for p in predictions:
            if p.id == row_id:
                return p
    return None


# --- Apply: transaction status (chain_status) -------------------------------


def _apply_transaction_status(
    row: Milestone | Dispute | Prediction, tx_result: genlayer_rpc.TransactionResult
) -> None:
    if not tx_result.get("ok"):
        logger.warning(
            "tx status check failed for %s id=%s: %s",
            type(row).__name__,
            row.id,
            tx_result.get("error"),
        )
        return

    bucket = tx_result.get("bucket") or ChainStatus.PROCESSING
    raw_status = tx_result.get("rawStatusName")
    row.chain_status = ChainStatus(bucket)
    row.on_chain_raw_status = raw_status

    if is_under_appeal(raw_status):
        # The "review alert" ROADMAP.md 4.5 asks for — there's no
        # notification/alerting system in this repo yet to hook into, so
        # this is the honest, buildable-now version of that: a loud,
        # greppable log line at WARNING, plus is_under_appeal() above as
        # the extension point once a real alert channel (email/Slack/a
        # websocket push) exists.
        logger.warning(
            "⚠ UNDER APPEAL — %s id=%s tx=%s raw_status=%s — needs review",
            type(row).__name__,
            row.id,
            row.on_chain_tx_hash,
            raw_status,
        )


# --- Apply: contract business state (status_key / ruling / outcome) --------


async def _apply_milestone_view(
    db: AsyncSession, milestone: Milestone, escrow: Escrow, result: genlayer_rpc.ReadResult
) -> None:
    if not result.get("ok"):
        logger.warning(
            "get_milestone failed for milestone id=%s: %s", milestone.id, result.get("error")
        )
        return
    m = result["result"]
    status = m.get("status")

    if status == "approved" and milestone.status_key != StatusKey.APPROVED:
        await _apply_verdict_to_state(
            db, ConsensusSubjectType.MILESTONE, milestone.id, True, str(m.get("reasoning", ""))
        )
    elif status == "disputed" and milestone.status_key != StatusKey.DISPUTED:
        await _apply_verdict_to_state(
            db, ConsensusSubjectType.MILESTONE, milestone.id, False, str(m.get("reasoning", ""))
        )
    # "pending"/"in_review" on-chain: nothing has been decided yet, leave
    # status_key as whatever it already is.

    deliverable_text = m.get("deliverable_text") or ""
    if deliverable_text and not any(s.text == deliverable_text for s in milestone.submissions):
        # Mirrors the DeliverableSubmission a legacy POST /escrows/{id}/
        # deliverable creates (routers/escrows.py) — a deliverable
        # submitted directly on-chain via submit_deliverable bypasses that
        # REST endpoint entirely (that's the point of the cutover), so
        # nothing else creates this row for an on-chain submission.
        db.add(
            DeliverableSubmission(
                milestone_id=milestone.id,
                wallet=escrow.counterparty_address,
                text=deliverable_text,
            )
        )


async def _apply_dispute_view(
    db: AsyncSession, dispute: Dispute, result: genlayer_rpc.ReadResult
) -> None:
    if not result.get("ok"):
        logger.warning("get_dispute failed for dispute id=%s: %s", dispute.id, result.get("error"))
        return
    d = result["result"]
    status = d.get("status")

    if status == "resolved":
        ruling = d.get("ruling")
        upheld = ruling == "favor_claimant"
        target_key = StatusKey.APPROVED if upheld else StatusKey.REJECTED
        if dispute.status_key != target_key:
            await _apply_verdict_to_state(
                db, ConsensusSubjectType.DISPUTE, dispute.id, upheld, str(d.get("reasoning", ""))
            )
    elif status == "dismissed" and dispute.status_key != StatusKey.REJECTED:
        # Not modeled by _apply_verdict_to_state (dismiss_dispute is a
        # claimant withdrawing, not an adjudicate_dispute verdict) — this
        # contract's own three states ("open"/"resolved"/"dismissed") map
        # onto backend/app/enums.py's narrower StatusKey vocabulary as:
        # dismissed -> REJECTED (the claim didn't succeed, same end state
        # a rejected verdict reaches), with a ruling string that says so
        # explicitly rather than reusing consensus-verdict reasoning text
        # nothing on-chain actually produced for this path.
        dispute.status_key = StatusKey.REJECTED
        dispute.ruling = "Claimant withdrew the dispute (dismissed on-chain, not adjudicated)."
        dispute.resolved_at = datetime.now(timezone.utc)


async def trigger_pending_adjudications(disputes: list[Dispute]) -> None:
    """Closes the gap flagged since raise_dispute_on_chain was built:
    filing a dispute on-chain (NuanceDisputeCourt.file_dispute) never got
    it a verdict, because nothing called adjudicate_dispute — a completely
    separate contract action. That function has no sender restriction at
    all (see contracts/nuance_dispute_court.py) — GenVM's validator
    network does the actual judging regardless of which address sends the
    call, so triggering it automatically here isn't a meaningfully
    different trust boundary than any other address doing so.

    Only ever considers disputes _load_linked_rows already resolved an
    on_chain_dispute_id for (an unresolved one has nothing to adjudicate
    yet) that are still DISPUTED in our own DB (a dispute _apply_dispute_view
    already flipped to APPROVED/REJECTED this same cycle needs no
    trigger) and haven't had one sent yet (adjudication_tx_hash null) —
    a successfully-sent trigger is never re-sent; a failed *send*
    (network/rate-limit, no tx hash back) leaves it null and is safe to
    retry next cycle, since nothing was actually submitted.
    """
    if not settings.dispute_court_contract_address:
        return

    candidates = [
        d
        for d in disputes
        if d.adjudication_tx_hash is None and d.status_key == StatusKey.DISPUTED
    ]
    for dispute in candidates:
        tx_hash = await genlayer_write.write_contract(
            settings.dispute_court_contract_address,
            "adjudicate_dispute",
            [dispute.on_chain_dispute_id],
        )
        if tx_hash is not None:
            dispute.adjudication_tx_hash = tx_hash
            logger.info(
                "Triggered adjudicate_dispute for dispute id=%s (on_chain_dispute_id=%s) tx=%s",
                dispute.id,
                dispute.on_chain_dispute_id,
                tx_hash,
            )


async def _apply_prediction_view(
    db: AsyncSession, prediction: Prediction, result: genlayer_rpc.ReadResult
) -> None:
    if not result.get("ok"):
        logger.warning(
            "get_market failed for prediction id=%s: %s", prediction.id, result.get("error")
        )
        return
    mk = result["result"]
    if mk.get("state") == "RESOLVED" and prediction.status_key != "RESOLVED":
        prediction.status_key = "RESOLVED"
        prediction.outcome = mk.get("winning_outcome")
        prediction.resolved_at = datetime.now(timezone.utc)
        prediction.resolution_reasoning = (
            "Resolved on-chain by NuancePredictionMarket.resolve_market (GenVM validator "
            "consensus). The contract's get_market view doesn't persist the resolving "
            "verdict's reasoning text, only the final state/outcome, so this field can't "
            "carry the actual on-chain reasoning the way the off-chain oracle's does."
        )
        # calculate_prediction_payouts is safe (in fact correct) to reuse
        # here, unlike it first looked: contracts/nuance_prediction_market.py's
        # own claim_winnings docstring says its pari-mutuel math is
        # deliberately "same math as backend/app/services/payout.py's
        # off-chain calculate_prediction_payouts" — so running it against
        # this market's PredictionPosition rows (which routers/predictions.py's
        # place_bet_on_chain mirrors from real on-chain bets — see that
        # endpoint's own docstring) produces a *display* figure that
        # genuinely matches what claim_winnings() would actually pay a
        # bettor on-chain, not a competing/fictional number. The REAL GEN
        # transfer still only ever happens via that pull-based on-chain
        # call — this is what "Won $X" shows in the UI, same as the
        # off-chain path already displays before anyone's clicked anything.
        from app.services.payout import calculate_prediction_payouts

        calculate_prediction_payouts(prediction)


async def trigger_pending_market_resolutions(predictions: list[Prediction]) -> None:
    """Closes the same gap trigger_pending_adjudications closes for
    disputes, for prediction markets: NuancePredictionMarket.resolve_market
    has no sender restriction at all (see that contract's own source) —
    GenVM's validator network does the actual judging regardless of which
    address sends the call, so triggering it automatically here isn't a
    meaningfully different trust boundary than any other address (or the
    existing off-chain "Resolve Market" button, for a market that weren't
    on-chain) doing so.

    Only considers already-linked markets (contract_address known — a
    market with none has nothing to resolve on-chain) that are still open
    per our own DB (status_key.lower() != "resolved" — a market
    _apply_prediction_view already flipped to RESOLVED this same cycle
    needs no trigger), whose off-chain resolution_date cutoff has actually
    passed (calling resolve_market before then would just fail on-chain —
    nuance_prediction_market.py's own header notes there's no verified
    on-chain clock, but the cutoff is still real information this app
    already tracks), and haven't had a trigger sent yet
    (resolution_trigger_tx_hash null) — a successfully-sent trigger is
    never re-sent; a failed *send* (network/rate-limit, no tx hash back)
    leaves it null and is safe to retry next cycle, since nothing was
    actually submitted.
    """
    now = datetime.now(timezone.utc)
    candidates = []
    for prediction in predictions:
        if prediction.resolution_trigger_tx_hash is not None:
            continue
        if prediction.status_key.lower() == "resolved":
            continue
        res_date = prediction.resolution_date
        if res_date.tzinfo is None:
            res_date = res_date.replace(tzinfo=timezone.utc)
        if now < res_date:
            continue
        candidates.append(prediction)

    for prediction in candidates:
        tx_hash = await genlayer_write.write_contract(
            prediction.contract_address, "resolve_market", []
        )
        if tx_hash is not None:
            prediction.resolution_trigger_tx_hash = tx_hash
            logger.info(
                "Triggered resolve_market for prediction id=%s (%s) tx=%s",
                prediction.id,
                prediction.contract_address,
                tx_hash,
            )


# --- One poll cycle ----------------------------------------------------------


async def run_once(db: AsyncSession) -> None:
    # Resolve any dispute ids still pending first — a row this fills in
    # becomes visible to _load_linked_rows below in the same cycle
    # (SQLAlchemy autoflushes the pending UPDATE before that SELECT runs),
    # so a freshly-resolved dispute gets its full get_dispute view-sync
    # this same pass rather than waiting a cycle.
    unresolved_disputes = await _load_unresolved_disputes(db)
    if unresolved_disputes:
        await resolve_pending_dispute_ids(db, unresolved_disputes)

    escrows, disputes, predictions = await _load_linked_rows(db)
    if not escrows and not disputes and not predictions:
        if unresolved_disputes:
            await db.commit()
            logger.info(
                "genlayer_indexer: no fully-linked rows yet; processed %d pending "
                "dispute id resolution(s) this cycle.",
                len(unresolved_disputes),
            )
        else:
            logger.info(
                "genlayer_indexer: no escrow/dispute/prediction is linked on-chain yet "
                "(contract_address / on_chain_dispute_id all null) — nothing to sync. "
                "See --link-demo to smoke-test against a real live contract."
            )
        return

    tx_hashes = _collect_pending_tx_hashes(escrows, disputes, predictions)
    reads = _build_read_batch(escrows, disputes, predictions)
    read_results, tx_results = await genlayer_rpc.read_and_check(reads, list(tx_hashes.keys()))

    for tx_hash, (kind, row_id) in tx_hashes.items():
        tx_result = tx_results.get(tx_hash)
        if tx_result is None:
            continue
        row = _find_row(kind, row_id, escrows, disputes, predictions)
        if row is not None:
            _apply_transaction_status(row, tx_result)

    # View-state resync for every linked row, not only ones with a pending
    # tx this process itself submitted — covers state that changed via a
    # call this app never tracked a hash for (someone calling the deployed
    # contract directly, e.g. through the block explorer or another client).
    for escrow in escrows:
        for milestone in escrow.milestones:
            if milestone.on_chain_index is None:
                continue
            result = read_results.get(f"milestone:{milestone.id}")
            if result is not None:
                await _apply_milestone_view(db, milestone, escrow, result)
    for dispute in disputes:
        result = read_results.get(f"dispute:{dispute.id}")
        if result is not None:
            await _apply_dispute_view(db, dispute, result)

    # After the view-sync above, so a dispute _apply_dispute_view just
    # resolved this same cycle (autoflushed, so status_key already
    # reflects it) is correctly skipped rather than adjudicated a second,
    # pointless time.
    await trigger_pending_adjudications(disputes)

    for prediction in predictions:
        result = read_results.get(f"prediction:{prediction.id}")
        if result is not None:
            await _apply_prediction_view(db, prediction, result)

    # Same ordering reasoning as trigger_pending_adjudications above — a
    # market _apply_prediction_view just resolved this cycle is correctly
    # skipped rather than resolved a second, pointless time.
    await trigger_pending_market_resolutions(predictions)

    await db.commit()


async def run_forever(interval_seconds: int | None = None) -> None:
    # This script has its own process lifetime, separate from FastAPI's —
    # it can't rely on main.py's lifespan having already run init_db() (it
    # may not have, if this is run before the server's ever started; see
    # that function's own docstring on why create_all + the sqlite column
    # patches both need to happen before any query below touches a column
    # this migration just added). A no-op once the schema is current.
    await init_db()
    interval = interval_seconds or settings.genlayer_indexer_poll_seconds
    logger.info("genlayer_indexer: starting, polling every %ss", interval)
    while True:
        try:
            # A fresh session per cycle — same reasoning services/
            # consensus.py's module docstring gives for run_consensus:
            # this loop outlives any single request/session.
            async with AsyncSessionLocal() as db:
                await run_once(db)
        except Exception:  # noqa: BLE001 — one bad cycle must not kill the loop
            logger.exception("genlayer_indexer: poll cycle failed")
        await asyncio.sleep(interval)


# --- Opt-in demo linking (manual smoke test) --------------------------------


async def link_demo(kind: str, row_id: int) -> None:
    """Points one real, existing DB row at the real bootstrap contract
    scripts/deploy.ts already deployed (ESCROW_CONTRACT_ADDRESS /
    PREDICTION_MARKET_CONTRACT_ADDRESS in backend/.env), so run_once above
    has something genuinely live to sync against on a fresh checkout
    instead of finding zero linked rows. Requires an explicit existing row
    id on purpose — never guesses at or creates one — so this can't
    silently overwrite seed/demo data. The bootstrap instance's own data
    (counterparty 0x1111..., "Bootstrap milestone") is fake (see
    deploy.ts's header); linking a real escrow to it is for proving the
    indexer's read/sync path works, not a real agreement.
    """
    await init_db()  # see run_forever's comment on why this can't be skipped
    async with AsyncSessionLocal() as db:
        if kind == "escrow":
            if not settings.escrow_contract_address:
                raise SystemExit("ESCROW_CONTRACT_ADDRESS is not set in backend/.env.")
            escrow = await db.get(Escrow, row_id)
            if escrow is None:
                raise SystemExit(f"No escrow with id={row_id}.")
            escrow.contract_address = settings.escrow_contract_address
            milestones = (
                (
                    await db.execute(
                        select(Milestone)
                        .where(Milestone.escrow_id == row_id)
                        .order_by(Milestone.order_index)
                    )
                )
                .scalars()
                .all()
            )
            if milestones:
                # The bootstrap contract has exactly one milestone, index 0
                # (see its __init__) — link this escrow's first milestone
                # to it; a second milestone here has nothing on-chain to
                # point at unless add_milestone was also called against
                # this exact deployed instance.
                milestones[0].on_chain_index = 0
                print(
                    f"Linked escrow id={row_id} -> {escrow.contract_address} "
                    f"(milestone id={milestones[0].id} -> on_chain_index=0)"
                )
            else:
                print(
                    f"Linked escrow id={row_id} -> {escrow.contract_address} "
                    "(no milestones on this escrow to link an index to)"
                )
        elif kind == "prediction":
            if not settings.prediction_market_contract_address:
                raise SystemExit("PREDICTION_MARKET_CONTRACT_ADDRESS is not set in backend/.env.")
            prediction = await db.get(Prediction, row_id)
            if prediction is None:
                raise SystemExit(f"No prediction with id={row_id}.")
            prediction.contract_address = settings.prediction_market_contract_address
            print(f"Linked prediction id={row_id} -> {prediction.contract_address}")
        else:
            raise SystemExit(f"Unknown --link-demo kind {kind!r} — expected 'escrow' or 'prediction'.")
        await db.commit()


# --- CLI ----------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Nuance's GenLayer chain indexer — mirrors on-chain escrow/"
        "dispute/prediction state into this backend's own database."
    )
    parser.add_argument(
        "--once", action="store_true", help="Run a single poll cycle and exit, instead of looping."
    )
    parser.add_argument(
        "--interval", type=int, default=None, help="Override the poll interval, in seconds."
    )
    parser.add_argument(
        "--link-demo",
        nargs=2,
        metavar=("KIND", "ID"),
        help="Point an existing escrow/prediction row (by id) at deploy.ts's live "
        "bootstrap contract, for an end-to-end smoke test. KIND is 'escrow' or "
        "'prediction'. Exits immediately after linking — does not also poll.",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = _parse_args()

    if args.link_demo:
        kind, row_id = args.link_demo
        asyncio.run(link_demo(kind, int(row_id)))
        return

    if args.once:

        async def _once() -> None:
            await init_db()  # see run_forever's comment
            async with AsyncSessionLocal() as db:
                await run_once(db)

        asyncio.run(_once())
        return

    asyncio.run(run_forever(args.interval))


if __name__ == "__main__":
    main()
