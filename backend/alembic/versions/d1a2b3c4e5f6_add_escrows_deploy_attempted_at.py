"""add escrows.deploy_attempted_at

Revision ID: d1a2b3c4e5f6
Revises: a48d0f47619d
Create Date: 2026-09-12 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1a2b3c4e5f6'
down_revision: Union[str, None] = 'a48d0f47619d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('escrows', sa.Column('deploy_attempted_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('escrows', 'deploy_attempted_at')
