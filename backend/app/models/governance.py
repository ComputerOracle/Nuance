"""Governance — SQLAlchemy async models. plan.md / ROADMAP.md Part 1.

A `Proposal` carries its own running tallies (`total_for`/`total_against`/
`total_abstain`) rather than requiring a `SELECT ... GROUP BY` over `Vote`
on every read. `Vote` is unique on `(proposal_id, voter_address)`, so
casting a second vote is always an *update* of that one row — the router
(routers/governance.py) is what actually moves a vote's weight out of its
old tally and into its new one in the same transaction; this module only
declares the shapes and the constraint that makes re-voting well-defined.

Row locking (ROADMAP.md Part 3 5.4): concurrent votes on the same
proposal read-modify-write `Proposal`'s tally columns — routers/
governance.py's write endpoints (cast_vote, finalize_proposal,
execute_proposal) fetch via `_get_proposal_for_update_or_404`, a
`SELECT ... FOR UPDATE`, specifically to close this race. A no-op on
SQLite (no error, no actual locking — fine given SQLite's own
effectively-serialized writes), a real row lock on Postgres.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.enums import ChainStatus, ProposalStatus, VoteChoice

# Same Numeric(38, 18) shape as models/core.py's own AssetAmount — GEN
# wei-precision Decimal, not a float. Not imported from core.py (that
# module doesn't export it as a public name) — duplicated here rather
# than adding a cross-import between the two model modules for one
# constant; keep the precision/scale in sync if either ever changes.
_GenAmount = Numeric(38, 18)


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str]
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(default="General")
    proposer_address: Mapped[str] = mapped_column(ForeignKey("users.wallet_address"))
    status: Mapped[ProposalStatus] = mapped_column(default=ProposalStatus.ACTIVE)

    start_time: Mapped[datetime]
    end_time: Mapped[datetime]

    # Percentages (0-100), not fractions — matches quorum_pct/pass_threshold_pct
    # naming already used in ROADMAP.md. Meaningful ONLY for a LEGACY_
    # OFFCHAIN proposal's own quorum check (_progress/_finalize_if_due,
    # routers/governance.py) — see quorum_threshold_gen below for why an
    # on-chain proposal can't reuse this value at all.
    quorum_threshold: Mapped[int] = mapped_column(default=20)
    # FIXED 2026-09-13 — a real, serious bug found live auditing
    # governance end-to-end: services/genlayer_indexer.py::
    # create_proposal_on_chain used to pass quorum_threshold above
    # straight through as NuanceGovernance.create_proposal's own
    # quorum_threshold argument — but that contract-side field is an
    # ABSOLUTE WEI TURNOUT threshold (see contracts/nuance_governance.py's
    # own header), while this column is a PERCENTAGE (1-100) of "every
    # wallet that's ever signed in," a concept that doesn't even exist
    # on-chain (GenVM has no wallet registry to be a percentage OF).
    # Passing "20" (meaning 20%) straight through made every on-chain
    # proposal's real quorum a trivial 20 wei — met by any single vote,
    # defeating quorum's entire purpose. This is the real, GEN-denominated
    # value used instead for an on-chain proposal; null for a
    # LEGACY_OFFCHAIN one, where it's meaningless. No UI can set this yet
    # (see ROADMAP.md/RUNBOOK.md — there's no create-proposal form in this
    # app at all, on- or off-chain; every existing proposal was created
    # via a direct API call) — routers/governance.py::create_proposal
    # applies a server-side default whenever a new proposal is about to
    # queue for on-chain creation.
    quorum_threshold_gen: Mapped[Decimal | None] = mapped_column(_GenAmount, default=None)
    pass_threshold: Mapped[int] = mapped_column(default=50)

    # FIXED 2026-09-13 — widened int -> Decimal (GEN wei-precision, same
    # shape as Escrow/Prediction's own amount columns) as part of real
    # GEN-staked voting (see contracts/nuance_governance.py's own header
    # and routers/governance.py's module docstring for the full account).
    # Still plain small integers for a LEGACY_OFFCHAIN proposal (never
    # retroactively converted — confirmed directly: only new proposals go
    # on-chain) — Decimal holds an integer weight like 3 exactly as well
    # as it holds 2.5 GEN, so this widening is value-compatible with
    # every existing off-chain proposal's tallies, not just new ones'.
    # For an on-chain-linked proposal (chain_status != LEGACY_OFFCHAIN),
    # these are synced from the real NuanceGovernance.get_proposal() read
    # (services/genlayer_indexer.py), not computed by routers/
    # governance.py's own _adjust_tally — that function only ever runs
    # for the off-chain path now (see that router's own updated guard).
    total_for: Mapped[Decimal] = mapped_column(_GenAmount, default=0)
    total_against: Mapped[Decimal] = mapped_column(_GenAmount, default=0)
    total_abstain: Mapped[Decimal] = mapped_column(_GenAmount, default=0)

    # Populated by POST /proposals/{id}/execute — mirrors Dispute's
    # enforced_by/resolved_at pair. A PASSED proposal has no on-chain
    # treasury/parameter effect wired up yet (ROADMAP.md Part 3); execute
    # is deliberately just the formal "this decision has been enacted"
    # status transition until a real effect exists to apply.
    executed_by: Mapped[str | None] = mapped_column(ForeignKey("users.wallet_address"), default=None)
    executed_at: Mapped[datetime | None] = mapped_column(default=None)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # --- On-chain linkage (2026-09-13) --------------------------------
    # Which NuanceGovernance.entries[] slot backs this proposal — null
    # for every proposal created before this update (see contract header
    # on why nothing retroactively converts) and, briefly, for a brand
    # new proposal whose background create_proposal_on_chain call hasn't
    # landed yet. Unlike Escrow/Prediction.contract_address (one deployed
    # instance per row), NuanceGovernance is a single shared registry —
    # every on-chain proposal lives at the same settings.
    # governance_contract_address, distinguished only by this id, exactly
    # the way Dispute.on_chain_dispute_id already works against the
    # shared NuanceDisputeCourt registry.
    on_chain_proposal_id: Mapped[int | None] = mapped_column(default=None)
    chain_status: Mapped[ChainStatus] = mapped_column(default=ChainStatus.LEGACY_OFFCHAIN)
    on_chain_raw_status: Mapped[str | None] = mapped_column(default=None)
    # The tx hash of the backend-triggered NuanceGovernance.create_proposal
    # call — create_proposal has no sender restriction on-chain (GenVM's
    # validator network judges nothing about who calls it), so, same
    # trust argument services/genlayer_indexer.py::trigger_pending_
    # adjudications/trigger_pending_market_resolutions already make,
    # firing this from the backend right after the off-chain row commits
    # is not a meaningfully different trust boundary than the proposer's
    # own wallet doing it — unlike cast_vote/retract_vote below, which
    # move real GEN and MUST be signed by the real voter's own wallet.
    on_chain_tx_hash: Mapped[str | None] = mapped_column(default=None)
    # Same deploy_attempted_at retry-cooldown pattern as Escrow/Prediction
    # — set right before the (slow, real) create_proposal_on_chain call,
    # read by a retry sweep to find proposals whose one shot failed or
    # never happened, without double-submitting one still in flight.
    deploy_attempted_at: Mapped[datetime | None] = mapped_column(default=None)
    # Mirrors Prediction.resolution_trigger_tx_hash exactly, same reason:
    # NuanceGovernance.finalize_proposal has no sender restriction (see
    # that contract's own source) but isn't idempotent to re-send blindly
    # (a second call after the first already landed just reverts,
    # spending gas for nothing) — services/genlayer_indexer.py::
    # trigger_pending_proposal_finalizations sets this the moment a
    # trigger is actually sent, and never re-sends once it's set.
    finalize_trigger_tx_hash: Mapped[str | None] = mapped_column(default=None)

    votes: Mapped[list["Vote"]] = relationship(
        back_populates="proposal",
        cascade="all, delete-orphan",
        order_by="Vote.created_at",
    )


class Vote(Base):
    __tablename__ = "votes"
    __table_args__ = (
        UniqueConstraint("proposal_id", "voter_address", name="uq_votes_proposal_voter"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id"))
    voter_address: Mapped[str] = mapped_column(ForeignKey("users.wallet_address"))
    choice: Mapped[VoteChoice]
    # Legacy off-chain weight (small int, e.g. 1-5 sybil-resistance
    # tiers — routers/governance.py::_voting_power). Untouched by, and
    # meaningless for, an on-chain vote — see stake_amount below for that
    # case's real weight instead of overloading this column's units.
    voting_power: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    # --- On-chain linkage (2026-09-13) --------------------------------
    # The real GEN staked by this ballot — only ever set for a vote cast
    # via POST /proposals/{id}/vote/on-chain (a real, wallet-signed,
    # payable NuanceGovernance.cast_vote call). Null for every legacy
    # off-chain vote, which has no GEN behind it at all — see
    # voting_power above for that case's own (unrelated-units) weight.
    stake_amount: Mapped[Decimal | None] = mapped_column(_GenAmount, default=None)
    on_chain_tx_hash: Mapped[str | None] = mapped_column(default=None)
    # Set once a real, wallet-signed NuanceGovernance.retract_vote call is
    # acknowledged — the unvote this whole update exists to add. Not a
    # deleted row: the (proposal_id, voter_address) unique constraint
    # means a later re-vote UPDATEs this same row back to active (clearing
    # this and retract_tx_hash) rather than inserting a second one, same
    # as the contract's own reuse-not-delete choice for its TreeMap entry
    # (see retract_vote's own docstring). A non-null value here — not
    # `choice`, which simply keeps whatever it last was — is the actual
    # "is this ballot currently active" signal for an on-chain vote.
    retracted_at: Mapped[datetime | None] = mapped_column(default=None)
    retract_tx_hash: Mapped[str | None] = mapped_column(default=None)

    proposal: Mapped["Proposal"] = relationship(back_populates="votes")
