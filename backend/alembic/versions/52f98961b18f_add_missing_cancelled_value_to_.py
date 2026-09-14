"""add missing CANCELLED value to statuskey enum

Revision ID: 52f98961b18f
Revises: c69312f36442
Create Date: 2026-09-14 18:17:46.911702

Found live deploying to Render: services/genlayer_deploy.py::
retry_undeployed_escrows (the auto-deploy retry loop, part of the chain
indexer's background poll cycle) filters `Escrow.status_key !=
StatusKey.CANCELLED` — a real, used member of app/enums.py::StatusKey
(routers/escrows.py's own cancel_escrow_on_chain sets it). But the
baseline migration's Postgres `statuskey` type only ever listed the six
members that existed when it was written; CANCELLED was added to the
Python enum later with no follow-up migration widening the DB type to
match. Result: every poll cycle's query against a real Postgres raised
`InvalidTextRepresentationError: invalid input value for enum statuskey:
"CANCELLED"` — silently caught per-cycle (run_forever's own try/except),
so nothing crashed outright, but the retry loop never ran a single cycle
successfully.

Not caught by `alembic check` — confirmed live: SQLAlchemy/Alembic's
default autogenerate comparator diffs an Enum column by name only, not
its member list, so a Python enum that grows a value after its Postgres
type was created won't show up as drift on its own. Checked every other
native enum type this schema uses (chainstatus/proposalstatus/
votechoice/consensussubjecttype) against their Python enums the same way
— this is the only one with a gap.

ALTER TYPE ... ADD VALUE IF NOT EXISTS is safe inside Alembic's
transactional DDL on Postgres 12+ (this app targets 17) as long as the
new value isn't *used* in the same transaction, which this migration
doesn't do — it only adds it.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '52f98961b18f'
down_revision: Union[str, None] = 'c69312f36442'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE statuskey ADD VALUE IF NOT EXISTS 'CANCELLED'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE at all (removing an enum
    # value that rows might already reference isn't a safe/reversible
    # operation the way adding one is) — same reason baseline's own
    # downgrade() doesn't clean up the enum types it creates (see
    # d7e8f9a0b1c2's own follow-up fix). Downgrading past this revision
    # leaves the added value in place; harmless, since nothing downgrades
    # a live Postgres in this app's actual deploy path (Dockerfile.
    # backend's CMD only ever runs `upgrade head`).
    pass
