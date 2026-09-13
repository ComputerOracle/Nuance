"""governance on-chain linkage + GEN-staked voting

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-09-13 15:00:00.000000

Asked directly: "any user that vote and unvote you will have to use Gen
token ... like a real Governance." contracts/nuance_governance.py's
cast_vote is now payable (GEN staked = ballot weight) and a new
retract_vote (the unvote) refunds it — see that contract's own 2026-09-13
header for the full account. This migration is the backend half:

- proposals.total_for/total_against/total_abstain widen from a flat
  integer weight to Numeric(38, 18) — same batch_alter_table technique
  a48d0f47619d already used for escrows.total/milestones.amount, for the
  identical reason (SQLite has no ALTER COLUMN TYPE; Postgres tolerates
  batch mode fine). Value-compatible with every existing off-chain
  proposal's small integer tallies — nothing retroactively converts them
  to on-chain (confirmed directly: only new proposals go on-chain), this
  column just needs to be ABLE to hold a GEN wei amount for the ones that
  do.
- proposals gains on_chain_proposal_id/chain_status/on_chain_raw_status/
  on_chain_tx_hash/deploy_attempted_at — the same on-chain-linkage shape
  Dispute already has against the shared NuanceDisputeCourt registry,
  applied here against the shared NuanceGovernance registry.
- votes gains stake_amount/on_chain_tx_hash/retracted_at/retract_tx_hash
  — a real on-chain vote's GEN stake and its own on-chain-linkage/unvote
  tracking, entirely separate from the legacy voting_power column.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7e8f9a0b1c2'
down_revision: Union[str, None] = 'c6d7e8f9a0b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('proposals', schema=None) as batch_op:
        batch_op.alter_column(
            'total_for',
            existing_type=sa.Integer(),
            type_=sa.Numeric(precision=38, scale=18),
            existing_nullable=False,
        )
        batch_op.alter_column(
            'total_against',
            existing_type=sa.Integer(),
            type_=sa.Numeric(precision=38, scale=18),
            existing_nullable=False,
        )
        batch_op.alter_column(
            'total_abstain',
            existing_type=sa.Integer(),
            type_=sa.Numeric(precision=38, scale=18),
            existing_nullable=False,
        )
        batch_op.add_column(sa.Column('on_chain_proposal_id', sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                'chain_status',
                sa.String(),
                server_default='LEGACY_OFFCHAIN',
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column('on_chain_raw_status', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('on_chain_tx_hash', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('deploy_attempted_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('finalize_trigger_tx_hash', sa.String(), nullable=True))

    with op.batch_alter_table('votes', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('stake_amount', sa.Numeric(precision=38, scale=18), nullable=True)
        )
        batch_op.add_column(sa.Column('on_chain_tx_hash', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('retracted_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('retract_tx_hash', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('votes', schema=None) as batch_op:
        batch_op.drop_column('retract_tx_hash')
        batch_op.drop_column('retracted_at')
        batch_op.drop_column('on_chain_tx_hash')
        batch_op.drop_column('stake_amount')

    with op.batch_alter_table('proposals', schema=None) as batch_op:
        batch_op.drop_column('finalize_trigger_tx_hash')
        batch_op.drop_column('deploy_attempted_at')
        batch_op.drop_column('on_chain_tx_hash')
        batch_op.drop_column('on_chain_raw_status')
        batch_op.drop_column('chain_status')
        batch_op.drop_column('on_chain_proposal_id')
        batch_op.alter_column(
            'total_abstain',
            existing_type=sa.Numeric(precision=38, scale=18),
            type_=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            'total_against',
            existing_type=sa.Numeric(precision=38, scale=18),
            type_=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            'total_for',
            existing_type=sa.Numeric(precision=38, scale=18),
            type_=sa.Integer(),
            existing_nullable=False,
        )
