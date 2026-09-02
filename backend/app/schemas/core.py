"""Pydantic V2 request/response schemas.

Every model uses ConfigDict (not the V1 `class Config`) and field_validator
(not the V1 `@validator`) per the project's Pydantic V2 requirement.

Governance's schemas live in governance.py instead — see
app/schemas/__init__.py for the re-export that makes the split invisible
to every other importer.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.enums import ConsensusSubjectType, StatusKey

_WALLET_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def _normalize_wallet(v: str) -> str:
    """Shared by every DTO that accepts a wallet address: strips whitespace
    and lowercases it. Storage/lookups are lowercase throughout (User.wallet_
    address is the PK) so a checksummed and lowercased address for the same
    wallet always resolve to the same row."""
    v = v.strip()
    if not _WALLET_RE.match(v):
        raise ValueError("wallet_address must be a 0x-prefixed 40-hex-character address.")
    return v.lower()


# --- User & Settings --------------------------------------------------------


class UserSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    notify_on: bool = True
    auto_escalate_on: bool = False


class UserSettingsUpdate(BaseModel):
    notify_on: bool | None = None
    auto_escalate_on: bool | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    wallet_address: str
    display_name: str | None = None
    created_at: datetime
    settings: UserSettingsRead | None = None


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=100)


# --- Auth ---------------------------------------------------------------


class NonceRequest(BaseModel):
    wallet_address: str

    _normalize = field_validator("wallet_address")(_normalize_wallet)


class NonceResponse(BaseModel):
    nonce: str
    message: str


class VerifyRequest(BaseModel):
    wallet_address: str
    message: str
    signature: str

    _normalize = field_validator("wallet_address")(_normalize_wallet)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    wallet_address: str


# --- Milestone ----------------------------------------------------------


class MilestoneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    amount: Decimal
    status_key: StatusKey
    criteria: str
    order_index: int


# --- Escrow -------------------------------------------------------------


class EscrowCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    counterparty_address: str
    total: Decimal = Field(gt=0)
    criteria: str | None = Field(default=None, max_length=2000)

    _normalize_counterparty = field_validator("counterparty_address")(_normalize_wallet)

    @field_validator("criteria")
    @classmethod
    def default_criteria(cls, v: str | None) -> str | None:
        return v or None


class EscrowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creator_address: str
    counterparty_address: str
    title: str
    total: Decimal
    status_key: StatusKey
    created_at: datetime
    milestones: list[MilestoneRead] = []


# --- Deliverable submission -----------------------------------------------


class DeliverableSubmissionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=5000)

    @field_validator("text")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v:
            raise ValueError("Deliverable text can't be blank.")
        return v


class DeliverableSubmissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    milestone_id: int
    wallet: str
    text: str
    submitted_at: datetime
    consensus_job_id: int | None = None


# --- Consensus job --------------------------------------------------------


class ValidatorResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    vote: str
    confidence: int = Field(ge=0, le=100)
    reasoning: str
    # Which provider actually produced this verdict — "gemini" / "anthropic"
    # / "openai" on success, or "heuristic" if every configured provider
    # failed and the deterministic offline fallback answered instead.
    # Optional/nullable so older stored ConsensusJob rows (persisted before
    # this field existed) still deserialize cleanly.
    provider: str | None = None


class ConsensusJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject_type: ConsensusSubjectType
    subject_id: int
    stage: int
    validator_results: list[ValidatorResult] | None = None
    verdict_label: str | None = None
    verdict_approved: bool | None = None
    verdict_confidence: int | None = None
    verdict_reasoning: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class ConsensusVerdict(BaseModel):
    label: str
    approved: bool
    confidence: int
    reasoning: str


class ConsensusStatus(BaseModel):
    stage: int
    validator_results: list[ValidatorResult] | None = None
    verdict: ConsensusVerdict | None = None


# --- Dispute --------------------------------------------------------------


class DisputeMessageCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    content: str = Field(min_length=1, max_length=5000)

    @field_validator("content")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v:
            raise ValueError("Message content can't be blank.")
        return v


class DisputeMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dispute_id: int
    sender_address: str
    content: str
    created_at: datetime


class DisputeEvidenceCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    description: str = Field(min_length=1, max_length=5000)
    link: str | None = Field(default=None, max_length=1000)

    @field_validator("description")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v:
            raise ValueError("Evidence description can't be blank.")
        return v


class DisputeEvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dispute_id: int
    submitter_address: str
    description: str
    link: str | None = None
    created_at: datetime
    consensus_job_id: int | None = None


class DisputeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    escrow_id: int
    milestone_id: int | None = None
    opened_by_address: str
    issue: str
    status_key: StatusKey
    ruling: str | None = None
    enforced_by: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None
    messages: list[DisputeMessageRead] = []
    evidence: list[DisputeEvidenceRead] = []


class DisputeEnforceRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    approved: bool
    ruling: str | None = Field(default=None, max_length=2000)


# --- Prediction -----------------------------------------------------------


class PredictionPositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    prediction_id: int
    wallet_address: str
    side: str
    amount: int
    payout: float | None = 0.0
    status: str = "PENDING"
    created_at: datetime


class PredictionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    category: str
    resolution_date: datetime
    volume: int
    status_key: str
    outcome: str | None = None
    resolution_reasoning: str | None = None
    resolution_source_url: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None
    positions: list[PredictionPositionRead] = []


class PredictionBetCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    side: str
    amount: int = Field(gt=0, le=1_000_000)

    @field_validator("side")
    @classmethod
    def validate_side(cls, v: str) -> str:
        v_norm = v.strip().upper()
        if v_norm not in ("YES", "NO"):
            raise ValueError("Side must be 'YES' or 'NO'.")
        return v_norm


# --- Validator / Agent directories -----------------------------------------
#
# Both are computed on read from real history (ConsensusJob rows) — see
# routers/validators.py and routers/agents.py — not stored anywhere, so
# there's no *Create schema, only a read shape.


class ValidatorStatRead(BaseModel):
    name: str
    cases_judged: int
    accuracy_pct: float
    is_active: bool
    last_active_at: datetime | None = None


class AgentStatRead(BaseModel):
    wallet_address: str
    category: str
    cases_judged: int
    trust_score: int





