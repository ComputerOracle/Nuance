"""add governance_event_log

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-09-13 23:00:00.000000

Dedup ledger for services/governance_generator.py — the governance
equivalent of market_event_log, kept as a genuinely separate table (not a
shared one with a "kind" column) so the prediction and governance
generators, which both draw from the same underlying event stream, never
starve each other of source content — see GovernanceEventLog's own model
docstring for the full account.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9a0b1c2d3e4'
down_revision: Union[str, None] = 'e8f9a0b1c2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'governance_event_log',
        sa.Column('source_id', sa.String(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('outcome', sa.String(), nullable=False),
        sa.Column('proposal_id', sa.Integer(), nullable=True),
        sa.Column('processed_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['proposal_id'], ['proposals.id'], ),
        sa.PrimaryKeyConstraint('source_id'),
    )


def downgrade() -> None:
    op.drop_table('governance_event_log')
