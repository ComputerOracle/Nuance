"""Shared enums — imported by both models.py (SQLAlchemy columns) and
schemas.py (Pydantic fields) so the two layers can't drift apart.

Mirrors the frontend's components/app/types.ts:
  - StatusKey -> StatusKey
  - the escrow/dispute "view" concept has no backend equivalent (routing is
    frontend-only), everything else here is new state the frontend doesn't
    model explicitly today (ConsensusJob's subject_type / stage).
"""

from __future__ import annotations

from enum import IntEnum, StrEnum


class StatusKey(StrEnum):
    APPROVED = "approved"
    IN_REVIEW = "in_review"
    IN_PROGRESS = "in_progress"
    PENDING = "pending"
    DISPUTED = "disputed"


class ConsensusSubjectType(StrEnum):
    """What a ConsensusJob is adjudicating. Only MILESTONE is wired up by
    this prompt; DISPUTE is reserved for the disputes prompt so the column's
    allowed values don't need to change later."""

    MILESTONE = "milestone"
    DISPUTE = "dispute"


class ConsensusStage(IntEnum):
    """Mirrors the `stage` state machine already in nuance-app.tsx
    (submitDeliverable/submitEvidence) so the backend can drive the same
    ConsensusPanel UI via polling instead of the frontend's local timers.
    """

    IDLE = 0
    QUEUED = 1
    ANALYZING = 2
    DONE = 3


class ProposalStatus(StrEnum):
    """A governance proposal's lifecycle. finalize() (routers/governance.py)
    is the only thing that moves ACTIVE -> PASSED/REJECTED; EXECUTED is
    reserved for a future action that actually applies a passed proposal's
    effect (see ROADMAP.md Part 1) and isn't set by anything yet."""

    ACTIVE = "active"
    PASSED = "passed"
    REJECTED = "rejected"
    EXECUTED = "executed"


class VoteChoice(StrEnum):
    FOR = "for"
    AGAINST = "against"
    ABSTAIN = "abstain"
