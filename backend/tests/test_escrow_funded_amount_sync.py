"""Tests for services/genlayer_indexer.py's escrow funded_amount sync — a
real gap found live: a fully-funded, real on-chain escrow (5 GEN
genuinely locked, confirmed via a direct get_escrow read against the live
deployed contract) showed nothing in the UI to that effect. The app only
ever tracked Escrow.funded_tx_hash ("a fund_escrow call was sent"), never
the contract's own actual funded_amount — this closes that gap by having
the indexer read get_escrow and mirror the real number back.

Covers:
  1. _wei_to_gen: exact round-trip with genlayer_deploy._gen_to_wei
     (never floating point), zero, and a value not evenly divisible.
  2. _apply_escrow_view sets Escrow.funded_amount from a real get_escrow
     result.
  3. _apply_escrow_view leaves funded_amount untouched (and doesn't
     crash) when the read itself failed.
  4. _build_read_batch includes one get_escrow read per linked escrow.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from decimal import Decimal

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-escrow-funded-amount-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.services.genlayer_deploy as genlayer_deploy  # noqa: E402
import app.services.genlayer_indexer as genlayer_indexer  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.enums import StatusKey  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Escrow, Milestone, User  # noqa: E402

_CONTRACT_ADDRESS = "0xF00Dbabe00000000000000000000000000000042"


@pytest.fixture(scope="module", autouse=True)
def _init_schema():
    with TestClient(app):
        yield


async def _create_escrow(total: str = "5.00") -> int:
    async with AsyncSessionLocal() as db:
        creator = "0x" + "1" * 40
        counterparty = "0x" + "2" * 40
        for addr in (creator, counterparty):
            if await db.get(User, addr) is None:
                db.add(User(wallet_address=addr))
        escrow = Escrow(
            creator_address=creator,
            counterparty_address=counterparty,
            title="Funded-amount sync test escrow",
            total=Decimal(total),
            status_key=StatusKey.IN_PROGRESS,
            contract_address=_CONTRACT_ADDRESS,
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


# --- 1. _wei_to_gen -------------------------------------------------------


def test_wei_to_gen_round_trips_with_gen_to_wei():
    for amount in ("5", "5.5", "0.000000000000000001", "123456.789"):
        wei = genlayer_deploy._gen_to_wei(Decimal(amount))
        assert genlayer_indexer._wei_to_gen(wei) == Decimal(amount)


def test_wei_to_gen_zero():
    assert genlayer_indexer._wei_to_gen(0) == Decimal("0.000000000000000000")


def test_wei_to_gen_exact_5_gen():
    # The exact live value confirmed against a real deployed contract
    # (get_escrow's own funded_amount) that surfaced this whole gap.
    assert genlayer_indexer._wei_to_gen(5_000_000_000_000_000_000) == Decimal("5")


# --- 2/3. _apply_escrow_view ----------------------------------------------


def test_apply_escrow_view_sets_funded_amount():
    escrow_id = asyncio.run(_create_escrow())

    async def _run():
        escrow = await _get_escrow(escrow_id)
        assert escrow.funded_amount is None

        await genlayer_indexer._apply_escrow_view(
            escrow,
            {
                "ok": True,
                "result": {
                    "creator": "0x" + "1" * 40,
                    "counterparty": "0x" + "2" * 40,
                    "funded_amount": "5000000000000000000",
                    "milestone_count": 1,
                    "status": "active",
                },
            },
        )
        async with AsyncSessionLocal() as db:
            db.add(escrow)
            await db.commit()

        refetched = await _get_escrow(escrow_id)
        assert refetched.funded_amount == Decimal("5")

    asyncio.run(_run())


def test_apply_escrow_view_leaves_amount_untouched_on_failed_read():
    escrow_id = asyncio.run(_create_escrow())

    async def _run():
        escrow = await _get_escrow(escrow_id)
        await genlayer_indexer._apply_escrow_view(
            escrow, {"ok": False, "error": "contract not found"}
        )
        # Must not raise, and must not fabricate a value from nothing.
        assert escrow.funded_amount is None

    asyncio.run(_run())


# --- 4. _build_read_batch --------------------------------------------------


def test_build_read_batch_includes_get_escrow_per_linked_escrow():
    escrow_id = asyncio.run(_create_escrow())
    escrow = asyncio.run(_get_escrow(escrow_id))  # milestones eager-loaded

    reads = genlayer_indexer._build_read_batch([escrow], [], [], [])
    escrow_reads = [r for r in reads if r["id"] == f"escrow:{escrow_id}"]
    assert len(escrow_reads) == 1
    assert escrow_reads[0]["functionName"] == "get_escrow"
    assert escrow_reads[0]["address"] == _CONTRACT_ADDRESS
