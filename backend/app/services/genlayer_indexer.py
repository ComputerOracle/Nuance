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
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db import AsyncSessionLocal, init_db
from app.enums import ChainStatus, ConsensusSubjectType, ProposalStatus, StatusKey
from app.models import AppState, DeliverableSubmission, Dispute, Escrow, Milestone, Prediction, Proposal
from app.services import genlayer_deploy, genlayer_rpc, genlayer_write

# Reused rather than re-derived: the exact cascade a verdict applies
# (advance the next pending milestone to in_progress, lock/unlock the
# parent escrow, distinguish a claimant's dispute being upheld vs.
# rejected) already exists and is exercised by the off-chain consensus
# path today. Soft-private (single underscore) but same package — an
# on-chain verdict reaching the identical end state as an off-chain one
# should run through the identical state machine, not a second
# hand-copied version of it that could drift.
from app.services.consensus import _apply_verdict_to_state

# routers/escrows.py doesn't import this module (genlayer_indexer), so this
# is a safe one-directional edge, not a cycle — see _publish_escrow_snapshot's
# own docstring for why this file needs it: an on-chain view-sync tick
# changes exactly the same escrow-visible fields a live-open detail view
# subscribes to (routers/escrows.py's escrow_updates_ws/sse).
from app.routers.escrows import _publish_escrow_snapshot

logger = logging.getLogger(__name__)
settings = get_settings()

_TERMINAL_CHAIN_STATUSES = {ChainStatus.FINALIZED, ChainStatus.CANCELED}
# Same value and reasoning as genlayer_deploy.py's own _DEPLOY_RETRY_
# COOLDOWN (a separate constant, not a cross-module reach into that
# private name — retry_uncreated_proposals below lives in this file, not
# genlayer_deploy.py, unlike its escrow/prediction counterparts): long
# enough that a real create_proposal call (subprocess + Bradbury
# consensus round) is comfortably done one way or the other before a
# retry could double-submit while the first attempt might still be
# in flight.
_PROPOSAL_CREATE_RETRY_COOLDOWN = timedelta(minutes=10)
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
) -> tuple[list[Escrow], list[Dispute], list[Prediction], list[Proposal]]:
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
    proposals = (
        (await db.execute(select(Proposal).where(Proposal.on_chain_proposal_id.is_not(None))))
        .scalars()
        .all()
    )
    return list(escrows), list(disputes), list(predictions), list(proposals)


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


async def _load_uncreated_proposal_ids(db: AsyncSession) -> list[Proposal]:
    """The proposals equivalent of _load_unresolved_disputes above:
    proposals whose create_proposal_on_chain call already sent a real tx,
    but whose on_chain_proposal_id resolve_pending_proposal_ids hasn't
    matched yet."""
    result = await db.execute(
        select(Proposal).where(
            Proposal.on_chain_tx_hash.is_not(None), Proposal.on_chain_proposal_id.is_(None)
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


async def resolve_pending_proposal_ids(db: AsyncSession, unresolved: list[Proposal]) -> None:
    """The proposals equivalent of resolve_pending_dispute_ids above — same
    gap (NuanceGovernance.create_proposal returns the real id, but
    genlayer-js can't surface a plain call's return value from its
    receipt), same fix: once a tracked creation tx has actually reached
    the chain, scan the last governance_proposal_id_scan_window on-chain
    proposals and match each unresolved local row by (proposer, title,
    category) — the fields create_proposal_on_chain actually passed, so a
    real match is a real match, not a guess."""
    if not unresolved:
        return
    if not settings.governance_contract_address:
        logger.warning(
            "%d proposal(s) awaiting on-chain id resolution but "
            "GOVERNANCE_CONTRACT_ADDRESS isn't configured — skipping.",
            len(unresolved),
        )
        return

    tx_hashes = [p.on_chain_tx_hash for p in unresolved if p.on_chain_tx_hash]
    _, tx_results = await genlayer_rpc.read_and_check([], tx_hashes)

    matchable: list[Proposal] = []
    for proposal in unresolved:
        tx_result = tx_results.get(proposal.on_chain_tx_hash or "")
        if tx_result is None:
            continue  # RPC/subprocess-level failure this cycle — try again next cycle
        _apply_transaction_status(proposal, tx_result)
        if proposal.chain_status in (ChainStatus.DECIDED, ChainStatus.FINALIZED):
            matchable.append(proposal)
        elif proposal.chain_status == ChainStatus.CANCELED:
            logger.error(
                "create_proposal tx canceled for local proposal id=%s (tx=%s) — this "
                "proposal will never get an on_chain_proposal_id.",
                proposal.id,
                proposal.on_chain_tx_hash,
            )

    if not matchable:
        return

    count_reads, _ = await genlayer_rpc.read_and_check(
        [
            {
                "id": "count",
                "address": settings.governance_contract_address,
                "functionName": "get_proposal_count",
                "args": [],
            }
        ],
        [],
    )
    count_item = count_reads.get("count")
    if count_item is None or not count_item.get("ok"):
        logger.warning(
            "get_proposal_count failed while resolving %d pending proposal id(s): %s",
            len(matchable),
            count_item.get("error") if count_item else "no response",
        )
        return
    proposal_count = count_item.get("result")
    if not isinstance(proposal_count, int) or proposal_count <= 0:
        return

    window_start = max(0, proposal_count - settings.governance_proposal_id_scan_window)
    scan_ids = range(proposal_count - 1, window_start - 1, -1)
    scan_reads: list[genlayer_rpc.ReadRequest] = [
        {
            "id": f"scan:{i}",
            "address": settings.governance_contract_address,
            "functionName": "get_proposal",
            "args": [i],
        }
        for i in scan_ids
    ]
    scan_results, _ = await genlayer_rpc.read_and_check(scan_reads, [])

    # Each real on-chain proposal id can satisfy at most one local row —
    # same collision guard resolve_pending_dispute_ids' own claimed_ids
    # gives disputes.
    claimed_ids: set[int] = set()
    for proposal in matchable:
        proposer = proposal.proposer_address.lower()
        for i in scan_ids:
            if i in claimed_ids:
                continue
            item = scan_results.get(f"scan:{i}")
            if item is None or not item.get("ok"):
                continue
            onchain = item["result"]
            if (
                str(onchain.get("proposer", "")).lower() == proposer
                and str(onchain.get("title", "")) == proposal.title
                and str(onchain.get("category", "")) == proposal.category
            ):
                proposal.on_chain_proposal_id = i
                claimed_ids.add(i)
                logger.info(
                    "Resolved local proposal id=%s -> on_chain_proposal_id=%s", proposal.id, i
                )
                break


def _build_read_batch(
    escrows: list[Escrow],
    disputes: list[Dispute],
    predictions: list[Prediction],
    proposals: list[Proposal],
) -> list[genlayer_rpc.ReadRequest]:
    reads: list[genlayer_rpc.ReadRequest] = []
    for escrow in escrows:
        # FIXED 2026-09-12 — a real gap found live: this batch read every
        # linked milestone's own state but never the escrow contract's own
        # get_escrow — the only place `funded_amount` (how much GEN is
        # actually locked right now, vs. funded_tx_hash's "a fund_escrow
        # call was sent") lives. One read per escrow, not per milestone.
        reads.append(
            {
                "id": f"escrow:{escrow.id}",
                "address": escrow.contract_address,
                "functionName": "get_escrow",
                "args": [],
            }
        )
        # FIXED 2026-09-12 — a real, serious gap found live: a cancelled
        # escrow's refund never reached the creator's wallet, even though
        # get_escrow's own funded_amount had already dropped to 0. Turned
        # out to be a confirmed, currently-open GenLayer platform bug
        # (genlayerlabs/genvm-manager#20) — emit_transfer's outbound value
        # is recorded in the receipt but never actually delivered on-chain
        # — so the contract's own bookkeeping can say "refunded"/"paid
        # out" while the GEN is still sitting at the contract's address.
        # "__native_balance__" is genlayer-read.ts's sentinel for a plain
        # eth_getBalance against this same address, folded into the same
        # batch/round-trip rather than a second subprocess call — see
        # Escrow.contract_balance's own docstring for the full account.
        reads.append(
            {
                "id": f"balance:{escrow.id}",
                "address": escrow.contract_address,
                "functionName": "__native_balance__",
                "args": [],
            }
        )
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
        # See Prediction.contract_balance's own docstring — same
        # "__native_balance__" sentinel, same reasoning as escrows' own
        # balance read above: claim_winnings' payout leaves this contract
        # via the identical emit_transfer() mechanism already confirmed
        # (genlayerlabs/genvm-manager#20) to sometimes never actually
        # deliver, despite the triggering transaction itself finalizing
        # cleanly. Folded into this same batch/round-trip, not a second
        # subprocess call.
        reads.append(
            {
                "id": f"balance:prediction:{prediction.id}",
                "address": prediction.contract_address,
                "functionName": "__native_balance__",
                "args": [],
            }
        )

    for proposal in proposals:
        reads.append(
            {
                "id": f"proposal:{proposal.id}",
                "address": settings.governance_contract_address,
                "functionName": "get_proposal",
                "args": [proposal.on_chain_proposal_id],
            }
        )
    # ONE shared balance read for the whole registry, not per-proposal —
    # unlike Escrow/Prediction (one deployed instance each), every
    # on-chain proposal lives at this same single address. See
    # AppState's own docstring: retract_vote's refund uses the identical
    # emit_transfer() mechanism already confirmed (genlayerlabs/
    # genvm-manager#20) to sometimes never actually deliver, so this is
    # the same ground-truth check, just keyed globally instead of per-row
    # since there's no single Proposal row to hang a per-instance balance
    # column off of.
    if proposals and settings.governance_contract_address:
        reads.append(
            {
                "id": "balance:governance",
                "address": settings.governance_contract_address,
                "functionName": "__native_balance__",
                "args": [],
            }
        )
    return reads


def _collect_pending_tx_hashes(
    escrows: list[Escrow],
    disputes: list[Dispute],
    predictions: list[Prediction],
    proposals: list[Proposal],
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
    for proposal in proposals:
        if proposal.on_chain_tx_hash and proposal.chain_status not in _TERMINAL_CHAIN_STATUSES:
            hashes[proposal.on_chain_tx_hash] = ("proposal", proposal.id)
    return hashes


def _find_row(
    kind: str,
    row_id: int,
    escrows: list[Escrow],
    disputes: list[Dispute],
    predictions: list[Prediction],
    proposals: list[Proposal],
) -> Milestone | Dispute | Prediction | Proposal | None:
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
    elif kind == "proposal":
        for proposal in proposals:
            if proposal.id == row_id:
                return proposal
    return None


# --- Apply: transaction status (chain_status) -------------------------------


def _apply_transaction_status(
    row: Milestone | Dispute | Prediction | Proposal, tx_result: genlayer_rpc.TransactionResult
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

# GEN has 18 decimals — same fact genlayer_deploy.py's own
# _WEI_PER_GEN_EXPONENT is pulled from (GENLAYER_BRADBURY.nativeCurrency.
# decimals, in genlayer-chain.ts). Duplicated as a plain constant here
# rather than importing genlayer_deploy's private one — this module
# already imports that one for retry_undeployed_escrows, but reaching
# into a leading-underscore name from a different module for one integer
# is worse than just restating the same well-known fact once more.
_WEI_PER_GEN_EXPONENT = 18


def _wei_to_gen(wei: int) -> Decimal:
    """Exact integer-wei -> Decimal-GEN conversion — the inverse of
    genlayer_deploy._gen_to_wei, same never-floating-point reasoning
    (string digit manipulation, not division, so this is immune to
    Decimal's ambient context precision same as that function is to
    float rounding). Used only for get_escrow's own real, on-chain
    funded_amount — see Escrow.funded_amount's own docstring on why this
    is the one field in this app actually verified against the contract,
    not just "an ack endpoint recorded a hash.\""""
    negative = wei < 0
    digits = str(abs(wei)).rjust(_WEI_PER_GEN_EXPONENT + 1, "0")
    whole, frac = digits[: -_WEI_PER_GEN_EXPONENT], digits[-_WEI_PER_GEN_EXPONENT:]
    value = Decimal(f"{whole}.{frac}")
    return -value if negative else value


async def _apply_escrow_view(escrow: Escrow, result: genlayer_rpc.ReadResult) -> None:
    """FIXED 2026-09-12 — a real gap found live: a fully-funded, real
    on-chain escrow (5 GEN genuinely locked, confirmed via a direct
    get_escrow read against the live contract) showed nothing in the UI
    to that effect — the app only ever tracked funded_tx_hash ("a
    fund_escrow call was sent"), never the contract's own actual
    funded_amount. This is the sync: escrow.funded_amount only ever
    reflects what get_escrow reports right now, the same "blockchain is
    authoritative, this app mirrors it" pattern every other on-chain
    field in this file already follows."""
    if not result.get("ok"):
        logger.warning("get_escrow failed for escrow id=%s: %s", escrow.id, result.get("error"))
        return
    raw_amount = result["result"].get("funded_amount")
    if raw_amount is None:
        return
    escrow.funded_amount = _wei_to_gen(int(raw_amount))


def _apply_escrow_balance(escrow: Escrow, result: genlayer_rpc.ReadResult) -> None:
    """The real, ground-truth check `_apply_escrow_view` above can't
    provide on its own — see Escrow.contract_balance's own docstring.
    `result["result"]` here is a plain wei string from genlayer-read.ts's
    "__native_balance__" sentinel (a real eth_getBalance), not anything
    the contract itself reports about its own state, unlike every other
    _apply_*_view function in this file."""
    if not result.get("ok"):
        logger.warning(
            "native balance check failed for escrow id=%s: %s", escrow.id, result.get("error")
        )
        return
    raw_balance = result.get("result")
    if raw_balance is None:
        return
    escrow.contract_balance = _wei_to_gen(int(raw_balance))


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

    # FIXED 2026-09-11 — this view-sync never looked at get_milestone's own
    # `released` field at all, even though it's been returned by the
    # contract from day one (see that method's own source). Paired with
    # nothing ever calling release_milestone in the first place (see
    # routers/escrows.py::release_milestone_on_chain, the other half of
    # this fix), an on-chain milestone's real payout had no way to ever be
    # reflected back into Milestone.released_at — the one field
    # _releasable_milestone/the frontend's "already released, hide the
    # button" check actually reads. Mirrors the same idempotent-overwrite
    # pattern every other field in this function already uses: only ever
    # sets it, never clears it, and only once (an already-set released_at
    # is left alone rather than overwritten with a fresh timestamp every
    # poll cycle).
    if m.get("released") and milestone.released_at is None:
        milestone.released_at = datetime.now(timezone.utc)

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


async def create_proposal_on_chain(proposal_id: int) -> None:
    """Asked directly: "any user that vote and unvote you will have to
    use Gen token ... like a real Governance." contracts/nuance_
    governance.py's cast_vote/retract_vote are now real, GEN-staked
    actions — but a vote needs an on-chain proposal_id to vote ON, so a
    Proposal has to exist on the shared NuanceGovernance registry before
    anyone can vote on it there at all.

    create_proposal has no sender restriction on-chain (GenVM's validator
    network judges nothing about who calls it — see that contract's own
    source) — same trust argument trigger_pending_adjudications/trigger_
    pending_market_resolutions above already make for their own backend-
    triggered calls, so firing this from the backend right after the
    off-chain row commits is not a meaningfully different trust boundary
    than the proposer's own wallet doing it. Unlike cast_vote/
    retract_vote, which move real GEN and MUST be signed by the real
    voter's own wallet from the browser.

    Fire-and-forget by design, same shape as genlayer_deploy.py's own
    deploy_* functions: records deploy_attempted_at immediately (before
    the real, slow call), then the real tx hash once sent — never the
    resulting on_chain_proposal_id itself, which resolve_pending_
    proposal_ids fills in later once the tx has actually landed (see that
    function's own docstring on why genlayer-js can't hand this back
    synchronously the way scripts/deploy.ts reads a deployed contract's
    address).
    """
    if not settings.governance_contract_address:
        logger.info(
            "Skipping on-chain proposal creation for id=%s — "
            "GOVERNANCE_CONTRACT_ADDRESS isn't configured.",
            proposal_id,
        )
        return

    async with AsyncSessionLocal() as db:
        proposal = await db.get(Proposal, proposal_id)
        if proposal is None:
            logger.warning("create_proposal_on_chain: proposal id=%s no longer exists.", proposal_id)
            return
        if proposal.on_chain_tx_hash is not None:
            return  # already sent — a duplicate/retry queue, not an error

        # Set BEFORE the actual (slow) write call below, and committed
        # immediately — same reasoning Escrow/Prediction.deploy_
        # attempted_at's own docstrings give: this is the guard retry_
        # uncreated_proposals reads to avoid double-submitting a real
        # create_proposal transaction while this exact attempt could
        # still be in flight. Not rolled back on failure further down: a
        # failed attempt still counts as "attempted," subject to the same
        # cooldown as any other attempt before being retried.
        proposal.deploy_attempted_at = datetime.now(timezone.utc)
        await db.commit()

        tx_hash = await genlayer_write.write_contract(
            settings.governance_contract_address,
            "create_proposal",
            [
                proposal.title,
                proposal.description,
                proposal.category,
                proposal.end_time.isoformat(),
                proposal.quorum_threshold,
                proposal.pass_threshold,
            ],
        )
        if tx_hash is None:
            logger.error(
                "Failed to send create_proposal for local proposal id=%s — will retry.",
                proposal_id,
            )
            return

        proposal.on_chain_tx_hash = tx_hash
        proposal.chain_status = ChainStatus.PROCESSING
        await db.commit()
        logger.info(
            "Sent create_proposal on-chain for proposal id=%s tx=%s", proposal_id, tx_hash
        )


async def retry_uncreated_proposals() -> None:
    """The proposals equivalent of genlayer_deploy.retry_undeployed_
    escrows/retry_undeployed_predictions — same one-shot-fire-and-forget
    gap, same fix: a transient failure sending create_proposal used to
    mean that proposal simply never went on-chain, permanently.

    Deliberately scoped to deploy_attempted_at IS NOT NULL (unlike
    escrows'/predictions' own retry sweeps, which also catch "never
    attempted at all" rows predating the feature) — confirmed directly:
    every proposal created before this update stays off-chain forever, on
    purpose, so this must never pick up a legacy row that never opted in.
    Every NEW proposal gets its first attempt queued immediately by
    routers/governance.py::create_proposal (which always sets deploy_
    attempted_at right away, same as create_escrow/create_prediction's
    own initial queue) — so "deploy_attempted_at set, but no on_chain_tx_
    hash yet" already means "a real attempt was made and failed," never
    "this legacy row was never supposed to be on-chain."
    """
    cutoff = datetime.now(timezone.utc) - _PROPOSAL_CREATE_RETRY_COOLDOWN
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Proposal.id).where(
                Proposal.on_chain_tx_hash.is_(None),
                Proposal.deploy_attempted_at.is_not(None),
                Proposal.deploy_attempted_at < cutoff,
            )
        )
        proposal_ids = [row[0] for row in result.all()]

    for proposal_id in proposal_ids:
        await create_proposal_on_chain(proposal_id)


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

        # See Prediction.contract_balance_at_resolution's own docstring —
        # captured the instant this market is first observed RESOLVED,
        # necessarily still the full pool (claim_winnings() rejects any
        # call before this point on the contract side). Whatever
        # contract_balance currently holds is safe to snapshot here even
        # if this exact cycle's own balance read failed (None) or is
        # slightly stale from an earlier cycle — either way it still
        # predates any possible claim.
        prediction.contract_balance_at_resolution = prediction.contract_balance


def _apply_prediction_balance(prediction: Prediction, result: genlayer_rpc.ReadResult) -> None:
    """The predictions equivalent of _apply_escrow_balance above — same
    ground-truth reasoning, same "__native_balance__" sentinel. See
    Prediction.contract_balance's own docstring for why this exists:
    claim_winnings()'s payout leaves the contract via the identical
    emit_transfer() call already confirmed (genlayerlabs/genvm-manager#20)
    to sometimes never actually deliver despite a clean FINALIZED receipt."""
    if not result.get("ok"):
        logger.warning(
            "native balance check failed for prediction id=%s: %s",
            prediction.id,
            result.get("error"),
        )
        return
    raw_balance = result.get("result")
    if raw_balance is None:
        return
    prediction.contract_balance = _wei_to_gen(int(raw_balance))


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


async def _apply_proposal_view(proposal: Proposal, result: genlayer_rpc.ReadResult) -> None:
    """Syncs a linked Proposal's business state from the real
    NuanceGovernance.get_proposal() read — status and the three wei-sum
    tallies (see Proposal.total_for's own 2026-09-13 docstring on why
    these are Decimal now, not the old flat integer weights). Never moves
    status backwards (passed/rejected -> active) — finalize_proposal on
    the contract side is itself one-way, same as routers/governance.py's
    own off-chain _finalize_if_due."""
    if not result.get("ok"):
        logger.warning("get_proposal failed for proposal id=%s: %s", proposal.id, result.get("error"))
        return
    p = result["result"]
    onchain_status = p.get("status")
    if onchain_status == "passed":
        proposal.status = ProposalStatus.PASSED
    elif onchain_status == "rejected":
        proposal.status = ProposalStatus.REJECTED
    # "active" needs no change either way.

    proposal.total_for = _wei_to_gen(int(p.get("total_for", 0)))
    proposal.total_against = _wei_to_gen(int(p.get("total_against", 0)))
    proposal.total_abstain = _wei_to_gen(int(p.get("total_abstain", 0)))


# AppState key for the shared NuanceGovernance registry's real native GEN
# balance — see _build_read_batch's own comment on why this is global
# (one shared contract, `balance:governance`) rather than a per-Proposal
# column the way Escrow/Prediction.contract_balance are.
_GOVERNANCE_BALANCE_STATE_KEY = "governance_contract_balance"


async def _apply_governance_balance(db: AsyncSession, result: genlayer_rpc.ReadResult) -> None:
    """The governance equivalent of _apply_escrow_balance/_apply_
    prediction_balance — same "__native_balance__" ground truth, same
    reason: retract_vote's refund leaves the contract via the identical
    emit_transfer() call already confirmed (genlayerlabs/genvm-manager#20)
    to sometimes never actually deliver despite a clean receipt. Written
    into AppState rather than a Proposal column since this is one number
    for the whole shared registry, not one per proposal."""
    if not result.get("ok"):
        logger.warning("native balance check failed for governance contract: %s", result.get("error"))
        return
    raw_balance = result.get("result")
    if raw_balance is None:
        return
    value = str(_wei_to_gen(int(raw_balance)))
    state = await db.get(AppState, _GOVERNANCE_BALANCE_STATE_KEY)
    if state is None:
        db.add(AppState(key=_GOVERNANCE_BALANCE_STATE_KEY, value=value))
    else:
        state.value = value


async def trigger_pending_proposal_finalizations(proposals: list[Proposal]) -> None:
    """Closes the same gap trigger_pending_adjudications/trigger_pending_
    market_resolutions close for disputes/predictions, for governance
    proposals: NuanceGovernance.finalize_proposal has no sender
    restriction at all (see that contract's own source) — the outcome is
    pure arithmetic over already-cast, already-on-chain votes, not a
    judgment call any particular sender could bias — so triggering it
    automatically here isn't a meaningfully different trust boundary than
    any other address doing so. Without this, an on-chain proposal would
    sit at the contract's own "active" forever past its end_time, even
    though _apply_proposal_view's DB sync would otherwise be waiting on
    exactly this call to ever observe "passed"/"rejected".

    Only considers already-linked proposals (on_chain_proposal_id known)
    whose off-chain end_time has actually passed (calling finalize_
    proposal before then would still succeed on-chain — there's no
    verified on-chain clock gating it either, same gap nuance_prediction_
    market.py's own header already flags — but firing it needlessly early
    would lock in a decision before real voters have had their full
    window) and haven't had a trigger sent yet (finalize_trigger_tx_hash
    null) — a successfully-sent trigger is never re-sent; a failed *send*
    leaves it null and is safe to retry next cycle, since nothing was
    actually submitted. Deliberately NOT gated on our own local `status`
    column (unlike predictions' status_key.lower() != "resolved" check) —
    _apply_proposal_view only ever learns "passed"/"rejected" from THIS
    same finalize_proposal call actually landing, so checking our own
    status here would be circular; finalize_trigger_tx_hash is the real
    "already handled" signal.
    """
    now = datetime.now(timezone.utc)
    candidates = []
    for proposal in proposals:
        if proposal.finalize_trigger_tx_hash is not None:
            continue
        end_time = proposal.end_time
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)
        if now < end_time:
            continue
        candidates.append(proposal)

    for proposal in candidates:
        tx_hash = await genlayer_write.write_contract(
            settings.governance_contract_address, "finalize_proposal", [proposal.on_chain_proposal_id]
        )
        if tx_hash is not None:
            proposal.finalize_trigger_tx_hash = tx_hash
            logger.info(
                "Triggered finalize_proposal for proposal id=%s (on_chain_proposal_id=%s) tx=%s",
                proposal.id,
                proposal.on_chain_proposal_id,
                tx_hash,
            )


# --- Fast, one-off sync for a single escrow ---------------------------------

# How long a real GenVM write call actually took to land, confirmed live
# against a real deployed escrow's fund_escrow transaction (see
# quick_sync_escrow's own docstring) — chosen to comfortably cover that,
# not a guess.
_QUICK_SYNC_MAX_ATTEMPTS = 12
_QUICK_SYNC_INTERVAL_SECONDS = 2.0


async def quick_sync_escrow(
    escrow_id: int,
    max_attempts: int = _QUICK_SYNC_MAX_ATTEMPTS,
    interval_seconds: float = _QUICK_SYNC_INTERVAL_SECONDS,
) -> None:
    """FIXED 2026-09-12 — found live: after funding a real escrow, the UI
    took as long as run_forever's own poll interval (15s by default) to
    show it, because nothing distinguished "a user is actively watching
    this specific escrow right after their own action" from "just sync
    everything on the usual cadence." Real dapps don't make you wait for
    a generic background sweep to notice your own transaction — this is
    that fix: a short-lived, fast-cadence poll of ONE escrow, queued as a
    background task right after routers/escrows.py's fund/cancel/submit/
    release-on-chain acks (the exact moments a user is watching for
    confirmation), reusing the same read-batch/view-apply/publish
    machinery run_once's own periodic sweep already uses — not a second,
    competing sync path.

    Stops the moment a poll actually changes something (the live WS/SSE
    channel has already pushed it by then via _publish_escrow_snapshot)
    or `max_attempts` is exhausted, whichever comes first — 12 attempts
    at 2s apart covers ~24s, comfortably past what a real fund_escrow
    transaction took to land end to end in a live test. Bounded and
    one-off: this never replaces run_once's own periodic sweep, which
    stays the catch-all for state that changes via any other path (a
    different browser session, someone calling the contract directly).
    """
    for _ in range(max_attempts):
        await asyncio.sleep(interval_seconds)

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Escrow)
                .where(Escrow.id == escrow_id)
                .options(selectinload(Escrow.milestones))
            )
            escrow = result.scalar_one_or_none()
            if escrow is None or escrow.contract_address is None:
                return

            reads = _build_read_batch([escrow], [], [], [])
            read_results, _ = await genlayer_rpc.read_and_check(reads, [])

            changed = False

            escrow_result = read_results.get(f"escrow:{escrow.id}")
            if escrow_result is not None:
                before = escrow.funded_amount
                await _apply_escrow_view(escrow, escrow_result)
                after = escrow.funded_amount
                # FOUND while testing this fix: the very first poll always
                # looked "changed" simply because `before` starts as None
                # (never synced yet) and any real read — even "still not
                # funded" (0) — differs from None, stopping after a single
                # attempt regardless of whether funding had actually
                # landed. Only the first-ever sync settling on zero is a
                # non-event; settling on zero *after* having been
                # something else (a real refund/cancel) still counts.
                first_sync_still_zero = before is None and after in (None, Decimal("0"))
                if after != before and not first_sync_still_zero:
                    changed = True

            # Same real-balance check run_once's own sweep does — see
            # _apply_escrow_balance's own docstring. Included in quick_sync
            # too so a cancel/release ack's fast poll can actually notice,
            # within its own ~24s window, that the platform bug above left
            # this escrow's refund/payout still sitting at the contract
            # instead of only ever reporting the (possibly misleading)
            # funded_amount transition as "done."
            balance_result = read_results.get(f"balance:{escrow.id}")
            if balance_result is not None:
                balance_before = escrow.contract_balance
                _apply_escrow_balance(escrow, balance_result)
                balance_after = escrow.contract_balance
                first_balance_sync_still_zero = balance_before is None and balance_after in (
                    None,
                    Decimal("0"),
                )
                if balance_after != balance_before and not first_balance_sync_still_zero:
                    changed = True

            for milestone in escrow.milestones:
                if milestone.on_chain_index is None:
                    continue
                milestone_result = read_results.get(f"milestone:{milestone.id}")
                if milestone_result is None:
                    continue
                before_state = (milestone.status_key, milestone.chain_status, milestone.released_at)
                await _apply_milestone_view(db, milestone, escrow, milestone_result)
                if (milestone.status_key, milestone.chain_status, milestone.released_at) != before_state:
                    changed = True

            await db.commit()

            if changed:
                await _publish_escrow_snapshot(escrow_id)
                return


# --- One poll cycle ----------------------------------------------------------


async def run_once(db: AsyncSession) -> None:
    # Retry any escrow whose auto-deploy failed or never ran — a real gap
    # fixed 2026-09-12 (see genlayer_deploy.retry_undeployed_escrows's own
    # docstring): deploy_escrow_contract used to be a one-shot fire-and-
    # forget task, so a transient RPC failure left an escrow off-chain
    # forever. Own session, own settings gate (same one create_escrow's
    # initial queue already checks) — genuinely independent of the
    # contract-linked-rows sync below, since an undeployed escrow has
    # nothing for _load_linked_rows to find in the first place. Gated off
    # entirely in tests the same way the initial auto-deploy already is
    # (tests/conftest.py forces auto_deploy_escrow_contracts False for the
    # whole suite) — an ordinary indexer test has no business firing a
    # real ~3-minute Bradbury deployment costing real testnet GEN.
    if settings.auto_deploy_escrow_contracts:
        await genlayer_deploy.retry_undeployed_escrows()

    # Same fix, same reasoning, for prediction markets — see
    # genlayer_deploy.retry_undeployed_predictions's own docstring (found
    # 2026-09-13 auditing "does every bet actually use real GEN"):
    # deploy_prediction_contract was equally a one-shot fire-and-forget
    # task, and several already-"open" (already bettable) markets predate
    # it running at all. Gated off in tests the same way (tests/
    # conftest.py forces auto_deploy_prediction_contracts False for the
    # whole suite) for the identical reason: no ordinary indexer test
    # should fire a real Bradbury deployment.
    if settings.auto_deploy_prediction_contracts:
        await genlayer_deploy.retry_undeployed_predictions()

    # Same fix, same reasoning, for governance proposals — see
    # retry_uncreated_proposals's own docstring. Gated off in tests the
    # same way (conftest.py forces auto_create_proposals_on_chain False
    # for the whole suite).
    if settings.auto_create_proposals_on_chain:
        await retry_uncreated_proposals()

    # Resolve any dispute/proposal ids still pending first — a row either
    # of these fills in becomes visible to _load_linked_rows below in the
    # same cycle (SQLAlchemy autoflushes the pending UPDATE before that
    # SELECT runs), so a freshly-resolved dispute/proposal gets its full
    # get_dispute/get_proposal view-sync this same pass rather than
    # waiting a cycle.
    unresolved_disputes = await _load_unresolved_disputes(db)
    if unresolved_disputes:
        await resolve_pending_dispute_ids(db, unresolved_disputes)
    uncreated_proposals = await _load_uncreated_proposal_ids(db)
    if uncreated_proposals:
        await resolve_pending_proposal_ids(db, uncreated_proposals)

    escrows, disputes, predictions, proposals = await _load_linked_rows(db)
    if not escrows and not disputes and not predictions and not proposals:
        if unresolved_disputes or uncreated_proposals:
            await db.commit()
            logger.info(
                "genlayer_indexer: no fully-linked rows yet; processed %d pending "
                "dispute id resolution(s) and %d pending proposal id resolution(s) "
                "this cycle.",
                len(unresolved_disputes),
                len(uncreated_proposals),
            )
        else:
            logger.info(
                "genlayer_indexer: no escrow/dispute/prediction/proposal is linked "
                "on-chain yet (contract_address / on_chain_dispute_id / "
                "on_chain_proposal_id all null) — nothing to sync. See --link-demo "
                "to smoke-test against a real live contract."
            )
        return

    tx_hashes = _collect_pending_tx_hashes(escrows, disputes, predictions, proposals)
    reads = _build_read_batch(escrows, disputes, predictions, proposals)
    read_results, tx_results = await genlayer_rpc.read_and_check(reads, list(tx_hashes.keys()))

    # Every escrow this cycle actually touched — published once, after the
    # single commit at the end of this function, rather than mid-cycle
    # (routers/escrows.py::escrow_updates_ws/sse subscribers must only ever
    # see committed state; publishing before commit could hand a fresh
    # session's read a row that then rolls back). Unconditional per row
    # touched, not a precise "did this field actually change" check — this
    # cycle only ever processes already-linked rows (bounded, not a hot
    # path), so the cost of an occasional redundant publish is trivial
    # next to the complexity of tracking every individual field flip.
    touched_escrow_ids: set[int] = set()

    for tx_hash, (kind, row_id) in tx_hashes.items():
        tx_result = tx_results.get(tx_hash)
        if tx_result is None:
            continue
        row = _find_row(kind, row_id, escrows, disputes, predictions, proposals)
        if row is not None:
            _apply_transaction_status(row, tx_result)
            if isinstance(row, (Milestone, Dispute)):
                touched_escrow_ids.add(row.escrow_id)

    # View-state resync for every linked row, not only ones with a pending
    # tx this process itself submitted — covers state that changed via a
    # call this app never tracked a hash for (someone calling the deployed
    # contract directly, e.g. through the block explorer or another client).
    for escrow in escrows:
        escrow_result = read_results.get(f"escrow:{escrow.id}")
        if escrow_result is not None:
            await _apply_escrow_view(escrow, escrow_result)
            touched_escrow_ids.add(escrow.id)
        balance_result = read_results.get(f"balance:{escrow.id}")
        if balance_result is not None:
            _apply_escrow_balance(escrow, balance_result)
            touched_escrow_ids.add(escrow.id)
        for milestone in escrow.milestones:
            if milestone.on_chain_index is None:
                continue
            result = read_results.get(f"milestone:{milestone.id}")
            if result is not None:
                await _apply_milestone_view(db, milestone, escrow, result)
                touched_escrow_ids.add(escrow.id)
    for dispute in disputes:
        result = read_results.get(f"dispute:{dispute.id}")
        if result is not None:
            await _apply_dispute_view(db, dispute, result)
            touched_escrow_ids.add(dispute.escrow_id)

    # After the view-sync above, so a dispute _apply_dispute_view just
    # resolved this same cycle (autoflushed, so status_key already
    # reflects it) is correctly skipped rather than adjudicated a second,
    # pointless time.
    await trigger_pending_adjudications(disputes)

    for prediction in predictions:
        # Balance applied BEFORE the view sync below on purpose: if this
        # cycle is the one where _apply_prediction_view first observes
        # RESOLVED, its contract_balance_at_resolution snapshot needs
        # whatever fresh balance this same cycle just read, not a stale
        # value from before.
        balance_result = read_results.get(f"balance:prediction:{prediction.id}")
        if balance_result is not None:
            _apply_prediction_balance(prediction, balance_result)
        result = read_results.get(f"prediction:{prediction.id}")
        if result is not None:
            await _apply_prediction_view(db, prediction, result)

    # Same ordering reasoning as trigger_pending_adjudications above — a
    # market _apply_prediction_view just resolved this cycle is correctly
    # skipped rather than resolved a second, pointless time.
    await trigger_pending_market_resolutions(predictions)

    for proposal in proposals:
        result = read_results.get(f"proposal:{proposal.id}")
        if result is not None:
            await _apply_proposal_view(proposal, result)

    # Same ordering reasoning as trigger_pending_adjudications/trigger_
    # pending_market_resolutions above — a proposal _apply_proposal_view
    # just flipped to passed/rejected this cycle needs no trigger (its
    # finalize_trigger_tx_hash is already set from whichever earlier
    # cycle actually sent it).
    await trigger_pending_proposal_finalizations(proposals)

    # One shared balance read for the whole registry (see _build_read_
    # batch's own comment) — applied once per cycle, not per proposal.
    governance_balance_result = read_results.get("balance:governance")
    if governance_balance_result is not None:
        await _apply_governance_balance(db, governance_balance_result)

    await db.commit()

    for escrow_id in touched_escrow_ids:
        await _publish_escrow_snapshot(escrow_id)


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
