"""Governance request/response schemas. Pydantic V2 — see core.py's header.

`ProposalRead`'s progress fields (`turnout_pct`, `for_pct`, ...) aren't
ORM columns; routers/governance.py computes them fresh on every read and
constructs these models from a plain dict, rather than `model_validate`-ing
a `Proposal` row directly. This is the exact shape frozen for the Part 1
Sync Point — see fixtures/proposals.json for a live sample.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.enums import ChainStatus, ProposalStatus, VoteChoice


class ProposalCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    category: str = Field(default="General", max_length=60)
    voting_period_days: int = Field(default=7, ge=1, le=90)
    quorum_threshold: int = Field(default=20, ge=1, le=100)
    pass_threshold: int = Field(default=50, ge=1, le=100)


class VoteCreate(BaseModel):
    choice: VoteChoice

    @field_validator("choice", mode="before")
    @classmethod
    def _normalize_choice(cls, v: object) -> object:
        # Accept "FOR" / "For" / "for" alike — same defensive normalization
        # PredictionBetCreate.validate_side already does for bet sides.
        return v.strip().lower() if isinstance(v, str) else v


def _normalize_choice_value(v: object) -> object:
    return v.strip().lower() if isinstance(v, str) else v


class VoteOnChainAck(BaseModel):
    """The on-chain counterpart to VoteCreate — reached once components/
    app/genlayer-write-client.ts's castVoteOnChain has already signed and
    sent a real, payable NuanceGovernance.cast_vote transaction directly
    to the chain. See routers/governance.py::cast_vote_on_chain's own
    docstring for why this doesn't verify the hash is real (same
    reasoning OnChainBetAck's own docstring already gives for
    predictions)."""

    tx_hash: str
    choice: VoteChoice
    # GEN, arbitrary precision — unlike prediction bets (a fixed
    # BET_AMOUNTS_MILLI_GEN picklist), real governance voting has no
    # quantized amount; this is whatever the connected wallet actually
    # staked, read back off the transaction the frontend just sent.
    stake_amount: Decimal = Field(gt=0)

    @field_validator("choice", mode="before")
    @classmethod
    def _normalize_choice(cls, v: object) -> object:
        return _normalize_choice_value(v)


class RetractVoteOnChainAck(BaseModel):
    """The on-chain unvote's ack — reached once the frontend has already
    signed and sent a real NuanceGovernance.retract_vote transaction."""

    tx_hash: str


class VoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    proposal_id: int
    voter_address: str
    choice: VoteChoice
    voting_power: int
    created_at: datetime
    updated_at: datetime

    # --- On-chain linkage (2026-09-13) — see models/governance.py's own
    # Vote docstring. All null for a legacy off-chain vote.
    stake_amount: Decimal | None = None
    on_chain_tx_hash: str | None = None
    retracted_at: datetime | None = None
    retract_tx_hash: str | None = None


class ProposalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    category: str
    proposer_address: str
    status: ProposalStatus
    start_time: datetime
    end_time: datetime
    quorum_threshold: int
    pass_threshold: int
    # Decimal, not int, since 2026-09-13 — see models/governance.py's own
    # Proposal.total_for docstring on why this widening is value-
    # compatible with every existing off-chain proposal's small integer
    # tallies, not just new on-chain ones'.
    total_for: Decimal
    total_against: Decimal
    total_abstain: Decimal
    executed_by: str | None = None
    executed_at: datetime | None = None
    created_at: datetime

    # Computed by the router on every read — see module docstring.
    turnout_pct: float
    for_pct: float
    against_pct: float
    abstain_pct: float
    quorum_met: bool

    # The requesting wallet's own vote, if any and if authenticated.
    # Absent (null) on an anonymous request — not the same as "voted abstain".
    user_vote: VoteChoice | None = None
    # The requesting wallet's own currently-staked GEN behind user_vote —
    # only ever set alongside an on-chain vote (see Vote.stake_amount's
    # own docstring); null for a legacy off-chain vote, an anonymous
    # request, or no vote at all. What a real "Retract Vote" button shows
    # ("get back 2.5 GEN") before the user commits to the transaction.
    user_vote_stake_amount: Decimal | None = None

    # --- On-chain linkage (2026-09-13) — see models/governance.py's own
    # Proposal docstring. Null/LEGACY_OFFCHAIN for every proposal created
    # before this update, by design (nothing retroactively converts).
    on_chain_proposal_id: int | None = None
    chain_status: ChainStatus = ChainStatus.LEGACY_OFFCHAIN
    on_chain_tx_hash: str | None = None
    # True once this proposal is queued for on-chain creation (routers/
    # governance.py::create_proposal set Proposal.deploy_attempted_at
    # synchronously at creation time) but not linked yet
    # (on_chain_proposal_id still null) — mirrors Prediction.
    # isDeployingOnChain's exact purpose: the frontend shows "deploying"
    # instead of offering a bet/vote the backend will now refuse (see
    # cast_vote's own guard, which checks this same underlying field).
    # False for every proposal created before this update, by design.
    is_queued_for_on_chain: bool = False
    # The one global NuanceGovernance registry address (same value on
    # every row) — not per-proposal the way Escrow/Prediction.
    # contract_address are, since this is a single shared contract. Only
    # meaningful once on_chain_proposal_id is set; the frontend gates on
    # that, not on this being non-null (it's the same env-configured
    # value regardless of whether THIS proposal happens to be linked).
    governance_contract_address: str | None = None


class ProposalDetailRead(ProposalRead):
    votes: list[VoteRead] = []
