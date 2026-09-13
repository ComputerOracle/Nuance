"""add proposals.quorum_threshold_gen

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-09-13 22:00:00.000000

Asked directly to audit the whole Governance feature for real bugs, the
same way the vote/unvote work was audited. Found live: services/
genlayer_indexer.py::create_proposal_on_chain was passing Proposal.
quorum_threshold (an off-chain PERCENTAGE, 1-100) straight through as
NuanceGovernance.create_proposal's own quorum_threshold argument — which
the contract treats as an ABSOLUTE WEI TURNOUT threshold. "20" (meaning
20%) became a real on-chain quorum of 20 wei, trivially met by any single
vote — silently defeating quorum for every on-chain proposal. This column
is the real, GEN-denominated value used instead; null for a
LEGACY_OFFCHAIN proposal, where it's meaningless.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8f9a0b1c2d3'
down_revision: Union[str, None] = 'd7e8f9a0b1c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'proposals',
        sa.Column('quorum_threshold_gen', sa.Numeric(precision=38, scale=18), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('proposals', 'quorum_threshold_gen')
