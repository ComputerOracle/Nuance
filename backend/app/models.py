"""SQLAlchemy 2.0 async models — User, UserSettings, Escrow, Milestone,
DeliverableSubmission, ConsensusJob, Dispute, DisputeEvidence.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, ForeignKey, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.enums import ConsensusStage, ConsensusSubjectType, StatusKey

# Dollar amounts: 2 decimal places is plenty and keeps serialized values
# clean ("500.00" rather than the generic Numeric default's "500.0000000000").
Money = Numeric(12, 2)


class User(Base):
    """Identity = wallet address (lowercased). No password; see the auth prompt
    for the personal_sign + nonce verification flow.
    """

    __tablename__ = "users"

    wallet_address: Mapped[str] = mapped_column(primary_key=True)
    display_name: Mapped[str | None] = mapped_column(default=None)
    nonce: Mapped[str | None] = mapped_column(default=None)
    nonce_issued_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    settings: Mapped["UserSettings | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    created_escrows: Mapped[list["Escrow"]] = relationship(
        foreign_keys="[Escrow.creator_address]", back_populates="creator"
    )
    counterparty_escrows: Mapped[list["Escrow"]] = relationship(
        foreign_keys="[Escrow.counterparty_address]", back_populates="counterparty"
    )


class UserSettings(Base):
    __tablename__ = "user_settings"

    wallet_address: Mapped[str] = mapped_column(
        ForeignKey("users.wallet_address"), primary_key=True
    )
    notify_on: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_escalate_on: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="settings")


class Escrow(Base):
    __tablename__ = "escrows"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    creator_address: Mapped[str] = mapped_column(ForeignKey("users.wallet_address"))
    counterparty_address: Mapped[str] = mapped_column(ForeignKey("users.wallet_address"))
    title: Mapped[str]
    total: Mapped[Decimal] = mapped_column(Money)
    status_key: Mapped[StatusKey] = mapped_column(default=StatusKey.IN_PROGRESS)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    creator: Mapped["User"] = relationship(
        foreign_keys=[creator_address], back_populates="created_escrows"
    )
    counterparty: Mapped["User"] = relationship(
        foreign_keys=[counterparty_address], back_populates="counterparty_escrows"
    )
    milestones: Mapped[list["Milestone"]] = relationship(
        back_populates="escrow",
        order_by="Milestone.order_index",
        cascade="all, delete-orphan",
    )
    disputes: Mapped[list["Dispute"]] = relationship(
        back_populates="escrow",
        cascade="all, delete-orphan",
    )


class Milestone(Base):
    __tablename__ = "milestones"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    escrow_id: Mapped[int] = mapped_column(ForeignKey("escrows.id"))
    name: Mapped[str]
    amount: Mapped[Decimal] = mapped_column(Money)
    status_key: Mapped[StatusKey] = mapped_column(default=StatusKey.PENDING)
    criteria: Mapped[str] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(default=0)

    escrow: Mapped["Escrow"] = relationship(back_populates="milestones")
    submissions: Mapped[list["DeliverableSubmission"]] = relationship(
        back_populates="milestone",
        cascade="all, delete-orphan",
    )


class DeliverableSubmission(Base):
    __tablename__ = "deliverable_submissions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    milestone_id: Mapped[int] = mapped_column(ForeignKey("milestones.id"))
    wallet: Mapped[str] = mapped_column(ForeignKey("users.wallet_address"))
    text: Mapped[str] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(server_default=func.now())

    milestone: Mapped["Milestone"] = relationship(back_populates="submissions")


class ConsensusJob(Base):
    """One AI-validator-consensus run against a milestone submission or (once
    the disputes prompt lands) a piece of dispute evidence. `subject_id`
    points at `milestones.id` or `disputes.id` depending on `subject_type` —
    a polymorphic FK, so it's a plain int column rather than a real
    ForeignKey (there's no single table it always references).
    """

    __tablename__ = "consensus_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subject_type: Mapped[ConsensusSubjectType]
    subject_id: Mapped[int]
    stage: Mapped[int] = mapped_column(default=int(ConsensusStage.IDLE))

    # List of {name, vote, confidence, reasoning} dicts, one per validator
    validator_results: Mapped[list | None] = mapped_column(JSON, default=None)

    verdict_label: Mapped[str | None] = mapped_column(default=None)
    verdict_approved: Mapped[bool | None] = mapped_column(default=None)
    verdict_confidence: Mapped[int | None] = mapped_column(default=None)
    verdict_reasoning: Mapped[str | None] = mapped_column(Text, default=None)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(default=None)


class Dispute(Base):
    """A claim raised against an escrow (optionally a specific milestone).
    `opened_by_address` is a FK to `users.wallet_address`.
    """

    __tablename__ = "disputes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    escrow_id: Mapped[int] = mapped_column(ForeignKey("escrows.id"))
    milestone_id: Mapped[int | None] = mapped_column(ForeignKey("milestones.id"), default=None)
    opened_by_address: Mapped[str] = mapped_column(ForeignKey("users.wallet_address"))
    issue: Mapped[str] = mapped_column(Text)
    status_key: Mapped[StatusKey] = mapped_column(default=StatusKey.DISPUTED)

    # Populated by POST /disputes/{id}/enforce.
    ruling: Mapped[str | None] = mapped_column(Text, default=None)
    enforced_by: Mapped[str | None] = mapped_column(ForeignKey("users.wallet_address"), default=None)
    resolved_at: Mapped[datetime | None] = mapped_column(default=None)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    escrow: Mapped["Escrow"] = relationship(back_populates="disputes")
    opener: Mapped["User"] = relationship(foreign_keys=[opened_by_address])
    messages: Mapped[list["DisputeMessage"]] = relationship(
        back_populates="dispute",
        order_by="DisputeMessage.created_at",
        cascade="all, delete-orphan",
    )
    evidence: Mapped[list["DisputeEvidence"]] = relationship(
        back_populates="dispute",
        order_by="DisputeEvidence.created_at",
        cascade="all, delete-orphan",
    )


class DisputeMessage(Base):
    __tablename__ = "dispute_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dispute_id: Mapped[int] = mapped_column(ForeignKey("disputes.id"))
    sender_address: Mapped[str] = mapped_column(ForeignKey("users.wallet_address"))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    dispute: Mapped["Dispute"] = relationship(back_populates="messages")
    sender: Mapped["User"] = relationship(foreign_keys=[sender_address])


class DisputeEvidence(Base):
    __tablename__ = "dispute_evidence"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dispute_id: Mapped[int] = mapped_column(ForeignKey("disputes.id"))
    submitter_address: Mapped[str] = mapped_column(ForeignKey("users.wallet_address"))
    description: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    dispute: Mapped["Dispute"] = relationship(back_populates="evidence")
    submitter: Mapped["User"] = relationship(foreign_keys=[submitter_address])


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    resolution_date: Mapped[datetime]
    volume: Mapped[int] = mapped_column(default=0)
    status_key: Mapped[str] = mapped_column(default="open")
    outcome: Mapped[str | None] = mapped_column(Text, default=None)
    resolution_reasoning: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(default=None)

    positions: Mapped[list["PredictionPosition"]] = relationship(
        back_populates="prediction",
        cascade="all, delete-orphan",
        order_by="PredictionPosition.created_at",
    )


class PredictionPosition(Base):
    __tablename__ = "prediction_positions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    wallet_address: Mapped[str] = mapped_column(ForeignKey("users.wallet_address"))
    side: Mapped[str] = mapped_column(Text)
    amount: Mapped[int] = mapped_column(default=0)
    payout: Mapped[float | None] = mapped_column(default=0.0)
    status: Mapped[str] = mapped_column(Text, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    prediction: Mapped["Prediction"] = relationship(back_populates="positions")
    user: Mapped["User"] = relationship(foreign_keys=[wallet_address])


