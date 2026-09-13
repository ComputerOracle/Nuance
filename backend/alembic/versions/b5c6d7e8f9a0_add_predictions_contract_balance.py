"""add predictions.contract_balance and contract_balance_at_resolution

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-09-13 12:10:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5c6d7e8f9a0'
down_revision: Union[str, None] = 'a4b5c6d7e8f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('predictions', sa.Column('contract_balance', sa.Numeric(precision=38, scale=18), nullable=True))
    op.add_column(
        'predictions',
        sa.Column('contract_balance_at_resolution', sa.Numeric(precision=38, scale=18), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('predictions', 'contract_balance_at_resolution')
    op.drop_column('predictions', 'contract_balance')
