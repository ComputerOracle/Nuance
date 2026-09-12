"""Tests for services/genlayer_indexer.py's escrow contract_balance sync —
a real, serious gap found live: after a genuine on-chain cancel_escrow,
the creator reported the refunded GEN never reached their wallet, even
though get_escrow's own funded_amount had already dropped to 0. A direct
eth_getBalance against the deployed contract proved the GEN was still
sitting at the contract's own address — a confirmed, currently-open
GenLayer platform bug (genlayerlabs/genvm-manager#20): emit_transfer's
outbound message is recorded in the triggering transaction's receipt but
never actually executed on-chain. The contract's own funded_amount is
just in-contract bookkeeping the contract zeroes out unconditionally the
moment cancel_escrow/release_milestone runs — it cannot, on its own,
distinguish "genuinely refunded" from "recorded as refunded but the
platform never delivered it." contract_balance is the one field in this
app checked against the chain's real state instead of the contract's own
optimistic self-report — see Escrow.contract_balance's own docstring.

Covers:
  1. _apply_escrow_balance sets Escrow.contract_balance from a real
     "__native_balance__" read result.
  2. _apply_escrow_balance leaves contract_balance untouched (and doesn't
     crash) when the read itself failed.
  3. _build_read_batch includes one "__native_balance__" read per linked
     escrow, addressed at that escrow's own contract.
  4. The exact live scenario that surfaced this bug: funded_amount == 0
     (contract says "refunded") but contract_balance > 0 (the GEN never
     actually moved) are both representable at once — nothing in the sync
     path forces them to agree.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from decimal import Decimal

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-escrow-contract-balance-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.services.genlayer_indexer as genlayer_indexer  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.enums import StatusKey  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Escrow, Milestone, User  # noqa: E402

_CONTRACT_ADDRESS = "0xF00Dbabe00000000000000000000000000000099"


@pytest.fixture(scope="module", autouse=True)
def _init_schema():
    with TestClient(app):
        yield


async def _create_escrow(total: str = "2.00") -> int:
    async with AsyncSessionLocal() as db:
        creator = "0x" + "3" * 40
        counterparty = "0x" + "4" * 40
        for addr in (creator, counterparty):
            if await db.get(User, addr) is None:
                db.add(User(wallet_address=addr))
        escrow = Escrow(
            creator_address=creator,
            counterparty_address=counterparty,
            title="Contract-balance sync test escrow",
            total=Decimal(total),
            status_key=StatusKey.CANCELLED,
            contract_address=_CONTRACT_ADDRESS,
            funded_amount=Decimal("0"),  # the contract's own (possibly misleading) self-report
        )
        escrow.milestones.append(
            Milestone(
                name="Milestone 1",
                amount=Decimal(total),
                status_key=StatusKey.PENDING,
                criteria="Looks good.",
                order_index=0,
                on_chain_index=0,
            )
        )
        db.add(escrow)
        await db.commit()
        await db.refresh(escrow)
        return escrow.id


async def _get_escrow(escrow_id: int) -> Escrow:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Escrow).where(Escrow.id == escrow_id).options(selectinload(Escrow.milestones))
        )
        escrow = result.scalar_one_or_none()
        assert escrow is not None
        return escrow


# --- 1/2. _apply_escrow_balance --------------------------------------------


def test_apply_escrow_balance_sets_contract_balance():
    escrow_id = asyncio.run(_create_escrow())

    async def _run():
        escrow = await _get_escrow(escrow_id)
        assert escrow.contract_balance is None

        genlayer_indexer._apply_escrow_balance(
            escrow, {"ok": True, "result": "2000000000000000000"}
        )
        async with AsyncSessionLocal() as db:
            db.add(escrow)
            await db.commit()

        refetched = await _get_escrow(escrow_id)
        assert refetched.contract_balance == Decimal("2")

    asyncio.run(_run())


def test_apply_escrow_balance_leaves_balance_untouched_on_failed_read():
    escrow_id = asyncio.run(_create_escrow())

    async def _run():
        escrow = await _get_escrow(escrow_id)
        genlayer_indexer._apply_escrow_balance(
            escrow, {"ok": False, "error": "fetch failed"}
        )
        # Must not raise, and must not fabricate a value from nothing.
        assert escrow.contract_balance is None

    asyncio.run(_run())


# --- 3. _build_read_batch ---------------------------------------------------


def test_build_read_batch_includes_native_balance_per_linked_escrow():
    escrow_id = asyncio.run(_create_escrow())
    escrow = asyncio.run(_get_escrow(escrow_id))  # milestones eager-loaded

    reads = genlayer_indexer._build_read_batch([escrow], [], [])
    balance_reads = [r for r in reads if r["id"] == f"balance:{escrow_id}"]
    assert len(balance_reads) == 1
    assert balance_reads[0]["functionName"] == "__native_balance__"
    assert balance_reads[0]["address"] == _CONTRACT_ADDRESS


# --- 4. The exact live bug: funded_amount and contract_balance disagree ---


def test_cancelled_escrow_can_show_zero_funded_amount_but_nonzero_balance():
    """The precise, live-confirmed symptom: cancel_escrow already zeroed
    its own funded_amount, but the real GEN never left the contract
    (genlayerlabs/genvm-manager#20). Both fields must be able to hold
    their own, independently-sourced truth at once — this is what lets
    routers/escrows.py and the frontend tell "genuinely refunded" apart
    from "cancelled on-chain, refund stuck behind a platform bug"."""
    escrow_id = asyncio.run(_create_escrow(total="2.00"))

    async def _run():
        escrow = await _get_escrow(escrow_id)
        genlayer_indexer._apply_escrow_balance(
            escrow, {"ok": True, "result": "2000000000000000000"}
        )
        async with AsyncSessionLocal() as db:
            db.add(escrow)
            await db.commit()

        refetched = await _get_escrow(escrow_id)
        assert refetched.status_key == StatusKey.CANCELLED
        assert refetched.funded_amount == Decimal("0")  # the contract's own self-report
        assert refetched.contract_balance == Decimal("2")  # the real, undelivered balance

    asyncio.run(_run())
