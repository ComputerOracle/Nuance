"""Governance — SQLAlchemy async models. plan.md / ROADMAP.md Part 1.

A `Proposal` carries its own running tallies (`total_for`/`total_against`/
`total_abstain`) rather than requiring a `SELECT ... GROUP BY` over `Vote`
on every read. `Vote` is unique on `(proposal_id, voter_address)`, so
casting a second vote is always an *update* of that one row — the router
(routers/governance.py) is what actually moves a vote's weight out of its
old tally and into its new one in the same transaction; this module only
declares the shapes and the constraint that makes re-voting well-defined.

Known gap, matching this codebase's current maturity level elsewhere
(e.g. milestone release has no row-locking either): concurrent votes on
the same proposal read-modify-write `Proposal`'s tally columns with no
row lock. Fine for SQLite's effectively-serialized writes today; worth a
`SELECT ... FOR UPDATE` once this runs on Postgres (ROADMAP.md Part 3).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.enums import ProposalStatus, VoteChoice


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
    # naming already used in ROADMAP.md.
    quorum_threshold: Mapped[int] = mapped_column(default=20)
    pass_threshold: Mapped[int] = mapped_column(default=50)

    # Denormalized running tallies, in voting_power units (not vote counts —
    # they're the same thing today since DEFAULT_VOTING_POWER is fixed at 1,
    # see routers/governance.py, but this is what makes GEN-stake-weighted
    # voting a router-only change later instead of a schema one).
    total_for: Mapped[int] = mapped_column(default=0)
    total_against: Mapped[int] = mapped_column(default=0)
    total_abstain: Mapped[int] = mapped_column(default=0)

    # Populated by POST /proposals/{id}/execute — mirrors Dispute's
    # enforced_by/resolved_at pair. A PASSED proposal has no on-chain
    # treasury/parameter effect wired up yet (ROADMAP.md Part 3); execute
    # is deliberately just the formal "this decision has been enacted"
    # status transition until a real effect exists to apply.
    executed_by: Mapped[str | None] = mapped_column(ForeignKey("users.wallet_address"), default=None)
    executed_at: Mapped[datetime | None] = mapped_column(default=None)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

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
    voting_power: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    proposal: Mapped["Proposal"] = relationship(back_populates="votes")
