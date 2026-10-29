"""Seeds mock disputes (plus the escrow each one was raised against, and a
piece of evidence) so the Next.js UI has something to show from
GET /disputes instead of an empty list.

Standalone script — run from backend/ with the venv active:

    python seed_disputes.py
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal, Base, engine
from app.enums import ChainStatus, ProposalStatus, StatusKey
from app.models import (
    Dispute,
    DisputeEvidence,
    DisputeMessage,
    Escrow,
    Milestone,
    Prediction,
    Proposal,
    User,
    UserSettings,
)


@dataclass
class PredictionSpec:
    title: str
    description: str
    category: str
    resolution_date: datetime
    volume: int
    status_key: str
    outcome: str | None = None


PREDICTION_SPECS = [
    PredictionSpec(
        title="Will GenLayer Season 1 distribute over 8,000,000 GLP across all weekly conversions before Season 2?",
        description="Resolves YES if total distributed GLP on portal.genlayer.foundation exceeds 8,000,000 GLP before Season 1 concludes. Resolves NO otherwise.",
        category="POINTS & REWARDS",
        resolution_date=datetime(2026, 11, 30, 23, 59, 0, tzinfo=timezone.utc),
        volume=95400,
        status_key="open",
    ),
    PredictionSpec(
        title="Will GenLayer's Intelligent Oracle maintain >= 97.0% resolution accuracy on the public Polymarket benchmark through Q4 2026?",
        description="Resolves YES if gym.genlayer.foundation/benchmarks/polymarket reports >= 97.0% resolution accuracy on addressable markets. Resolves NO otherwise.",
        category="INTELLIGENT ORACLE",
        resolution_date=datetime(2026, 12, 31, 23, 59, 0, tzinfo=timezone.utc),
        volume=142000,
        status_key="open",
    ),
    PredictionSpec(
        title="Will Exchange OS launch permissionless outcome market venues integrated with GenLayer on X Layer mainnet in 2026?",
        description="Resolves YES if OKX / X Layer announces live deployment of outcome market venues resolved by GenLayer Intelligent Oracle on mainnet before Dec 31, 2026.",
        category="EXCHANGE OS",
        resolution_date=datetime(2026, 12, 31, 23, 59, 0, tzinfo=timezone.utc),
        volume=68500,
        status_key="open",
    ),
    PredictionSpec(
        title="Did the GenLayer 'Bradbury' Testnet launch successfully in Q1 2026?",
        description="Resolves YES if Testnet Bradbury went live with AI consensus before April 1, 2026.",
        category="PROTOCOL",
        resolution_date=datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc),
        volume=25000,
        status_key="open",
    ),
]


@dataclass
class ProposalSpec:
    title: str
    description: str
    category: str
    days_active: int
    days_remaining: int
    quorum_threshold: int
    quorum_threshold_gen: Decimal
    pass_threshold: int
    total_for: Decimal
    total_against: Decimal
    total_abstain: Decimal
    status: ProposalStatus = ProposalStatus.ACTIVE


PROPOSAL_SPECS = [
    ProposalSpec(
        title="Expand the GenVM Validator Committee for Intelligent Oracles",
        description="Increase the default validator committee size from 5 to 11 for high-stakes prediction market resolutions and cross-contract dispute rulings, improving Byzantine fault tolerance and consensus resilience across Bradbury testnet.",
        category="Protocol",
        days_active=2,
        days_remaining=5,
        quorum_threshold=20,
        quorum_threshold_gen=Decimal("1.0"),
        pass_threshold=50,
        total_for=Decimal("4.5"),
        total_against=Decimal("0.8"),
        total_abstain=Decimal("0.2"),
    ),
    ProposalSpec(
        title="Allocate 50,000 GEN from Ecosystem Treasury to Fund Agent Tank Hackathon Grants",
        description="Authorize a treasury disbursement of 50,000 GEN to match developer bounties for AI agents building autonomous escrow and predictive market arbitration contracts on GenLayer.",
        category="Treasury",
        days_active=3,
        days_remaining=4,
        quorum_threshold=20,
        quorum_threshold_gen=Decimal("2.0"),
        pass_threshold=60,
        total_for=Decimal("8.2"),
        total_against=Decimal("1.5"),
        total_abstain=Decimal("0.5"),
    ),
    ProposalSpec(
        title="Standardize Natural Language Dispute Settlement Rules for Nuance Escrows",
        description="Ratify standard natural language milestone evaluation guidelines for GenLayer Internet Court validators, ensuring uniform interpretation of subjective delivery deliverables across all freelance and contractor escrows.",
        category="Governance",
        days_active=1,
        days_remaining=6,
        quorum_threshold=20,
        quorum_threshold_gen=Decimal("1.5"),
        pass_threshold=50,
        total_for=Decimal("3.2"),
        total_against=Decimal("0.4"),
        total_abstain=Decimal("0.1"),
    ),
    ProposalSpec(
        title="Deploy Uniswap V2 Outcome Token Liquidity Pools on Testnet Bradbury",
        description="Deploy automated market maker pools for conditional outcome tokens (YES/NO) minted by Nuance prediction markets, enabling secondary market liquidity prior to GenVM Intelligent Oracle settlement.",
        category="Integration",
        days_active=4,
        days_remaining=3,
        quorum_threshold=20,
        quorum_threshold_gen=Decimal("1.0"),
        pass_threshold=50,
        total_for=Decimal("6.1"),
        total_against=Decimal("3.2"),
        total_abstain=Decimal("0.0"),
    ),
]


@dataclass
class MessageSpec:
    sender_wallet: str
    content: str



@dataclass
class DisputeSpec:
    creator_wallet: str
    creator_name: str
    counterparty_wallet: str
    counterparty_name: str
    escrow_title: str
    escrow_total: str
    milestone_criteria: str
    issue: str
    status_key: StatusKey
    messages: list[MessageSpec]
    evidence_desc: str
    evidence_link: str | None = None
    ruling: str | None = None
    enforced_by: str | None = None


DISPUTE_SPECS = [
    DisputeSpec(
        creator_wallet="0x1111111111111111111111111111111111111111",
        creator_name="Alice (Client)",
        counterparty_wallet="0x2222222222222222222222222222222222222222",
        counterparty_name="Bob (Dev Studio)",
        escrow_title="Marketplace mobile app — QA milestone",
        escrow_total="2000.00",
        milestone_criteria="Zero P1 bugs across iOS/Android, docs delivered.",
        issue="Payment released before QA sign-off; P1 bugs remained open at handoff.",
        status_key=StatusKey.DISPUTED,
        messages=[
            MessageSpec(
                sender_wallet="0x1111111111111111111111111111111111111111",
                content="Hey Bob, our QA run failed on Android checkout with a crash bug. We can't approve milestone 1 yet.",
            ),
            MessageSpec(
                sender_wallet="0x2222222222222222222222222222222222222222",
                content="The crash only happens on rooted devices which was excluded from the brief. iOS builds are completely green.",
            ),
            MessageSpec(
                sender_wallet="0x1111111111111111111111111111111111111111",
                content="We reproduced on stock Pixel 8. Submitting the bug logs to the validators now.",
            ),
        ],
        evidence_desc="Bug tracker export and Sentry crash traces showing 4 open P1s at handoff on stock Pixel 8 devices.",
        evidence_link="https://github.com/example/nuance-app/issues/42",
    ),
    DisputeSpec(
        creator_wallet="0x2222222222222222222222222222222222222222",
        creator_name="Bob (Dev Studio)",
        counterparty_wallet="0x3333333333333333333333333333333333333333",
        counterparty_name="Charlie (Auditor)",
        escrow_title="Smart contract audit — vault module",
        escrow_total="1500.00",
        milestone_criteria="No critical/high findings unresolved.",
        issue="Static analysis report allegedly omits a known reentrancy finding.",
        status_key=StatusKey.IN_REVIEW,
        messages=[
            MessageSpec(
                sender_wallet="0x2222222222222222222222222222222222222222",
                content="The audit report you sent seems to have skipped the withdraw() hook reentrancy test.",
            ),
            MessageSpec(
                sender_wallet="0x3333333333333333333333333333333333333333",
                content="Reentrancy is mitigated by ReentrancyGuard transient storage. Slither flagged it as informational.",
            ),
        ],
        evidence_desc="Diff between the delivered report and the raw Slither/Aderyn analyzer outputs.",
        evidence_link="https://gist.github.com/example/audit-diff",
    ),
    DisputeSpec(
        creator_wallet="0x3333333333333333333333333333333333333333",
        creator_name="Charlie (Auditor)",
        counterparty_wallet="0x1111111111111111111111111111111111111111",
        counterparty_name="Alice (Client)",
        escrow_title="Brand identity for Solace Labs — brand guide",
        escrow_total="1700.00",
        milestone_criteria='Guide reads as "professional" per brand brief tone.',
        issue="Delivered brand guide did not match the agreed tone in the brief.",
        status_key=StatusKey.APPROVED,
        messages=[
            MessageSpec(
                sender_wallet="0x3333333333333333333333333333333333333333",
                content="Brand guide v2 has been completely revised with the requested enterprise corporate tone.",
            ),
            MessageSpec(
                sender_wallet="0x1111111111111111111111111111111111111111",
                content="Reviewed and validated by our team. Approving resolution.",
            ),
        ],
        evidence_desc="Side-by-side comparison against the brief's tone-of-voice section showing full alignment.",
        ruling="Evidence supported the claimant; guide revised and re-delivered.",
        enforced_by="0x3333333333333333333333333333333333333333",
    ),
]


async def _get_or_create_user(
    session: AsyncSession, wallet_address: str, display_name: str | None = None
) -> User:
    user = await session.get(User, wallet_address.lower())
    if user is None:
        user = User(wallet_address=wallet_address.lower(), display_name=display_name)
        user.settings = UserSettings(wallet_address=wallet_address.lower())
        session.add(user)
    elif display_name and not user.display_name:
        user.display_name = display_name
    return user


async def seed_disputes() -> None:
    # 1. Create tables if they don't exist yet.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        # 2. Seed disputes and escrows if not present
        dispute_count = await session.scalar(select(func.count(Dispute.id)))
        if dispute_count == 0:
            seeded_count = 0
            for spec in DISPUTE_SPECS:
                creator = await _get_or_create_user(
                    session, spec.creator_wallet, spec.creator_name
                )
                counterparty = await _get_or_create_user(
                    session, spec.counterparty_wallet, spec.counterparty_name
                )
                await session.flush()

                escrow = Escrow(
                    creator_address=creator.wallet_address,
                    counterparty_address=counterparty.wallet_address,
                    title=spec.escrow_title,
                    total=Decimal(spec.escrow_total),
                    status_key=spec.status_key,
                )
                session.add(escrow)
                await session.flush()

                milestone = Milestone(
                    escrow_id=escrow.id,
                    name="Milestone 1",
                    amount=Decimal(spec.escrow_total),
                    status_key=spec.status_key,
                    criteria=spec.milestone_criteria,
                    order_index=0,
                )
                session.add(milestone)
                await session.flush()

                dispute = Dispute(
                    escrow_id=escrow.id,
                    milestone_id=milestone.id,
                    opened_by_address=creator.wallet_address,
                    issue=spec.issue,
                    status_key=spec.status_key,
                    ruling=spec.ruling,
                    enforced_by=spec.enforced_by,
                )
                session.add(dispute)
                await session.flush()

                # Seed conversation messages
                for msg_spec in spec.messages:
                    session.add(
                        DisputeMessage(
                            dispute_id=dispute.id,
                            sender_address=msg_spec.sender_wallet.lower(),
                            content=msg_spec.content,
                        )
                    )

                # Seed evidence
                session.add(
                    DisputeEvidence(
                        dispute_id=dispute.id,
                        submitter_address=creator.wallet_address,
                        description=spec.evidence_desc,
                        link=spec.evidence_link,
                    )
                )
                seeded_count += 1
            print(f"Seeded {seeded_count} dispute(s).")
        else:
            print(f"Disputes already seeded ({dispute_count} existing).")

        # 3. Seed prediction markets if not present
        pred_count = await session.scalar(select(func.count(Prediction.id)))
        if pred_count == 0:
            for p_spec in PREDICTION_SPECS:
                session.add(
                    Prediction(
                        title=p_spec.title,
                        description=p_spec.description,
                        category=p_spec.category,
                        resolution_date=p_spec.resolution_date,
                        volume=p_spec.volume,
                        status_key=p_spec.status_key,
                        outcome=p_spec.outcome,
                    )
                )
            print(f"Seeded {len(PREDICTION_SPECS)} prediction market(s).")
        else:
            print(f"Predictions already seeded ({pred_count} existing).")

        # 4. Seed governance proposals if not present
        prop_count = await session.scalar(select(func.count(Proposal.id)))
        if prop_count == 0:
            proposer = await _get_or_create_user(
                session, "0x1111111111111111111111111111111111111111", "GenLayer DAO"
            )
            await session.flush()
            now = datetime.now(timezone.utc)
            for pr_spec in PROPOSAL_SPECS:
                session.add(
                    Proposal(
                        title=pr_spec.title,
                        description=pr_spec.description,
                        category=pr_spec.category,
                        proposer_address=proposer.wallet_address,
                        status=pr_spec.status,
                        start_time=now - timedelta(days=pr_spec.days_active),
                        end_time=now + timedelta(days=pr_spec.days_remaining),
                        quorum_threshold=pr_spec.quorum_threshold,
                        quorum_threshold_gen=pr_spec.quorum_threshold_gen,
                        pass_threshold=pr_spec.pass_threshold,
                        total_for=pr_spec.total_for,
                        total_against=pr_spec.total_against,
                        total_abstain=pr_spec.total_abstain,
                        chain_status=ChainStatus.LEGACY_OFFCHAIN,
                    )
                )
            print(f"Seeded {len(PROPOSAL_SPECS)} governance proposal(s).")
        else:
            print(f"Proposals already seeded ({prop_count} existing).")

        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed_disputes())



