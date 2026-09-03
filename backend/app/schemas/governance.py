"""Governance request/response schemas. Pydantic V2 — see core.py's header.

`ProposalRead`'s progress fields (`turnout_pct`, `for_pct`, ...) aren't
ORM columns; routers/governance.py computes them fresh on every read and
constructs these models from a plain dict, rather than `model_validate`-ing
a `Proposal` row directly. This is the exact shape frozen for the Part 1
Sync Point — see fixtures/proposals.json for a live sample.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.enums import ProposalStatus, VoteChoice


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


class VoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    proposal_id: int
    voter_address: str
    choice: VoteChoice
    voting_power: int
    created_at: datetime
    updated_at: datetime


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
    total_for: int
    total_against: int
    total_abstain: int
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


class ProposalDetailRead(ProposalRead):
    votes: list[VoteRead] = []
