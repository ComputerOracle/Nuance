"""add assets, api keys, webhooks; generalize escrow amounts

Revision ID: a48d0f47619d
Revises: eac90fe5a4f5
Create Date: 2026-09-08 22:12:34.557260

ROADMAP.md Part 4 6.1/6.2. Hand-corrected after the raw `--autogenerate`
output (kept below in git history/downgrade for reference) failed two
real checks before being trusted:

1. Ran as generated against a real SQLite target and hit
   `OperationalError: near "ALTER": syntax error` on
   `ALTER TABLE escrows ALTER COLUMN total TYPE ...` — SQLite has no
   ALTER COLUMN TYPE at all; Alembic's own fix for exactly this is
   `batch_alter_table` (recreates the table under the hood: new table,
   copy data, drop old, rename), which also degrades to a plain, direct
   ALTER on any dialect that *does* support it natively (Postgres
   included) — so wrapping every escrows/milestones column change in
   batch mode is the portable choice, not a SQLite-only workaround.
2. The raw output created `escrows.asset_id` (NOT NULL, server_default
   '1') and its FK to `assets.id` *before* any row existed in `assets` —
   fine on an empty table, but the FK's very first real validation
   (whatever row Postgres backfills existing escrows to under that
   default) would reference a row that doesn't exist yet. Seeding GEN as
   id=1 (and testnet USDC as id=2) between creating `assets` and touching
   `escrows` closes that ordering gap; see app/db.py's `_seed_assets` for
   why GEN specifically has to land as id 1, not just "some native asset".
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a48d0f47619d'
down_revision: Union[str, None] = 'eac90fe5a4f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'assets',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('symbol', sa.String(), nullable=False),
        sa.Column('decimals', sa.Integer(), nullable=False),
        sa.Column('contract_address', sa.String(), nullable=True),
        sa.Column('is_native', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('symbol'),
    )

    # Seeded here, not left to app/db.py's sqlite-only _seed_assets — this
    # is the path a real Postgres deployment actually takes (see that
    # function's own docstring: it's SQLite dev/test convenience only).
    # id=1/2 given explicitly so every existing/future escrows.asset_id
    # default of '1' unambiguously means GEN — see this file's own header.
    assets_table = sa.table(
        'assets',
        sa.column('id', sa.Integer),
        sa.column('symbol', sa.String),
        sa.column('decimals', sa.Integer),
        sa.column('contract_address', sa.String),
        sa.column('is_native', sa.Boolean),
    )
    op.bulk_insert(
        assets_table,
        [
            {'id': 1, 'symbol': 'GEN', 'decimals': 18, 'contract_address': None, 'is_native': True},
            {'id': 2, 'symbol': 'USDC', 'decimals': 6, 'contract_address': None, 'is_native': False},
        ],
    )

    op.create_table(
        'api_keys',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('key_id', sa.String(), nullable=False),
        sa.Column('secret_hash', sa.String(), nullable=False),
        sa.Column('wallet_address', sa.String(), nullable=False),
        sa.Column('scopes', sa.JSON(), nullable=False),
        sa.Column('label', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['wallet_address'], ['users.wallet_address']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key_id'),
    )
    op.create_table(
        'webhooks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('wallet_address', sa.String(), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('event_types', sa.JSON(), nullable=False),
        sa.Column('secret', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('last_delivered_at', sa.DateTime(), nullable=True),
        sa.Column('last_delivery_status', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['wallet_address'], ['users.wallet_address']),
        sa.PrimaryKeyConstraint('id'),
    )

    # Batch mode (see this file's own header, point 1) — portable across
    # SQLite (which requires it for a column type change) and Postgres
    # (which doesn't, but tolerates it fine).
    with op.batch_alter_table('escrows', schema=None) as batch_op:
        batch_op.add_column(sa.Column('asset_id', sa.Integer(), server_default='1', nullable=False))
        batch_op.alter_column(
            'total',
            existing_type=sa.NUMERIC(precision=12, scale=2),
            type_=sa.Numeric(precision=38, scale=18),
            existing_nullable=False,
        )
        batch_op.create_foreign_key('fk_escrows_asset_id_assets', 'assets', ['asset_id'], ['id'])

    with op.batch_alter_table('milestones', schema=None) as batch_op:
        batch_op.alter_column(
            'amount',
            existing_type=sa.NUMERIC(precision=12, scale=2),
            type_=sa.Numeric(precision=38, scale=18),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table('milestones', schema=None) as batch_op:
        batch_op.alter_column(
            'amount',
            existing_type=sa.Numeric(precision=38, scale=18),
            type_=sa.NUMERIC(precision=12, scale=2),
            existing_nullable=False,
        )

    with op.batch_alter_table('escrows', schema=None) as batch_op:
        batch_op.drop_constraint('fk_escrows_asset_id_assets', type_='foreignkey')
        batch_op.alter_column(
            'total',
            existing_type=sa.Numeric(precision=38, scale=18),
            type_=sa.NUMERIC(precision=12, scale=2),
            existing_nullable=False,
        )
        batch_op.drop_column('asset_id')

    op.drop_table('webhooks')
    op.drop_table('api_keys')
    op.drop_table('assets')
