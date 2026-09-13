"""Tests for services/genlayer_indexer.py's prediction contract_balance
sync — the predictions equivalent of test_escrow_contract_balance.py's own
gap and fix, added proactively rather than after a live incident.

Asked directly: "let the whole GEN tokens [be] distributed to the win[ners]
... handle it like a senior dev." The distribution MATH was already
correct on both sides — contracts/nuance_prediction_market.py's
claim_winnings() is real pari-mutuel, and services/payout.py's
calculate_prediction_payouts mirrors it exactly for display (see that
function's own docstring). The real risk is delivery, not math:
claim_winnings' payout leaves the contract via the exact same
emit_transfer() mechanism that Escrow.contract_balance's own docstring
already caught silently failing to deliver escrow refunds/payouts — a
confirmed, currently-open GenLayer platform bug
(genlayerlabs/genvm-manager#20). No on-chain prediction market had
actually resolved yet when this was written, so the bug hadn't visibly
struck a claim here — but nothing about claim_winnings' call shape differs
from cancel_escrow/release_milestone's, so this ships the same ground-
truth safeguard now rather than waiting for a second live incident.

Prediction.contract_balance_at_resolution (no escrow equivalent needed,
since escrows only ever have one creator to refund) is the piece specific
to a multi-claimant contract: a market has no single "total paid out"
counter of its own (total_yes_stake/total_no_stake never decrease on
claim), so comparing the live contract_balance against a snapshot taken
the instant the market resolved is the only way to know "has ANY real GEN
left this contract since resolution" without enumerating every bettor
address.

Covers:
  1. _apply_prediction_balance sets Prediction.contract_balance from a
     real "__native_balance__" read result.
  2. _apply_prediction_balance leaves contract_balance untouched (and
     doesn't crash) when the read itself failed.
  3. _build_read_batch includes one "__native_balance__" read per linked
     prediction, addressed at that market's own contract, keyed distinctly
     from escrows' own "balance:{id}" so the two can never collide on the
     same numeric id.
  4. _apply_prediction_view snapshots contract_balance_at_resolution the
     instant a market is first observed RESOLVED — using whatever balance
     this same cycle already read.
  5. The exact scenario this whole fix exists to detect: a market resolves
     with contract_balance_at_resolution == 3 GEN; a later cycle reads
     contract_balance still == 3 GEN (nothing left) — representable and
     distinguishable from a genuine payout (contract_balance drops).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-prediction-contract-balance-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.services.genlayer_indexer as genlayer_indexer  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Prediction  # noqa: E402

_CONTRACT_ADDRESS = "0xF00Dbabe0000000000000000000000000000AAAA"


@pytest.fixture(scope="module", autouse=True)
def _init_schema():
    with TestClient(app):
        yield


async def _create_prediction(
    *, status_key: str = "open", contract_address: str | None = _CONTRACT_ADDRESS
) -> int:
    async with AsyncSessionLocal() as db:
        prediction = Prediction(
            title="Will the payout actually arrive?",
            description="Test market for the contract_balance sync.",
            category="Test",
            status_key=status_key,
            resolution_date=datetime.now(timezone.utc) + timedelta(days=1),
            resolution_source_url="https://example.com/result",
            contract_address=contract_address,
        )
        db.add(prediction)
        await db.commit()
        await db.refresh(prediction)
        return prediction.id


async def _get_prediction(prediction_id: int) -> Prediction:
    async with AsyncSessionLocal() as db:
        prediction = await db.get(Prediction, prediction_id)
        assert prediction is not None
        return prediction


async def _get_prediction_with_positions(db, prediction_id: int) -> Prediction:
    """Eager-loads .positions — _apply_prediction_view's own call to
    services/payout.py::calculate_prediction_payouts reads
    prediction.positions, which a plain db.get() would otherwise lazy-load
    outside of an async-safe context (MissingGreenlet)."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(Prediction)
        .where(Prediction.id == prediction_id)
        .options(selectinload(Prediction.positions))
    )
    prediction = result.scalar_one_or_none()
    assert prediction is not None
    return prediction


# --- 1/2. _apply_prediction_balance -----------------------------------------


def test_apply_prediction_balance_sets_contract_balance():
    prediction_id = asyncio.run(_create_prediction())

    async def _run():
        prediction = await _get_prediction(prediction_id)
        assert prediction.contract_balance is None

        genlayer_indexer._apply_prediction_balance(
            prediction, {"ok": True, "result": "3000000000000000000"}
        )
        async with AsyncSessionLocal() as db:
            db.add(prediction)
            await db.commit()

        refetched = await _get_prediction(prediction_id)
        assert refetched.contract_balance == Decimal("3")

    asyncio.run(_run())


def test_apply_prediction_balance_leaves_balance_untouched_on_failed_read():
    prediction_id = asyncio.run(_create_prediction())

    async def _run():
        prediction = await _get_prediction(prediction_id)
        genlayer_indexer._apply_prediction_balance(
            prediction, {"ok": False, "error": "fetch failed"}
        )
        # Must not raise, and must not fabricate a value from nothing.
        assert prediction.contract_balance is None

    asyncio.run(_run())


# --- 3. _build_read_batch ----------------------------------------------------


def test_build_read_batch_includes_native_balance_per_linked_prediction():
    prediction_id = asyncio.run(_create_prediction())
    prediction = asyncio.run(_get_prediction(prediction_id))

    reads = genlayer_indexer._build_read_batch([], [], [prediction])
    balance_reads = [r for r in reads if r["id"] == f"balance:prediction:{prediction_id}"]
    assert len(balance_reads) == 1
    assert balance_reads[0]["functionName"] == "__native_balance__"
    assert balance_reads[0]["address"] == _CONTRACT_ADDRESS

    market_reads = [r for r in reads if r["id"] == f"prediction:{prediction_id}"]
    assert len(market_reads) == 1
    assert market_reads[0]["functionName"] == "get_market"


def test_prediction_balance_key_never_collides_with_escrow_balance_key():
    """The whole reason this uses "balance:prediction:{id}" instead of
    reusing escrows' bare "balance:{id}" — an escrow and a prediction with
    the same numeric id are two completely independent rows, and
    read_results is a single flat dict keyed by these strings in
    run_once. A collision would silently apply one row's real balance
    read to the other."""
    from app.models import Escrow

    prediction_id = asyncio.run(_create_prediction())
    prediction = asyncio.run(_get_prediction(prediction_id))
    # Construct (not persisted) an Escrow with the exact same numeric id —
    # only its id and contract_address matter for _build_read_batch.
    escrow = Escrow(
        id=prediction_id,
        creator_address="0x" + "1" * 40,
        counterparty_address="0x" + "2" * 40,
        title="Same id as the prediction above",
        total=Decimal("1"),
        status_key="IN_PROGRESS",
        contract_address="0xEscrowSameIdAsThePredictionAbove000000001",
    )
    escrow.milestones = []

    reads = genlayer_indexer._build_read_batch([escrow], [], [prediction])
    ids = [r["id"] for r in reads]
    assert len(ids) == len(set(ids)), f"duplicate read ids: {ids}"
    assert f"balance:{prediction_id}" in ids  # the escrow's own key
    assert f"balance:prediction:{prediction_id}" in ids  # the prediction's own key


# --- 4/5. _apply_prediction_view's resolution snapshot -----------------------


def test_resolution_snapshots_contract_balance_at_resolution():
    prediction_id = asyncio.run(_create_prediction(status_key="open"))

    async def _run():
        async with AsyncSessionLocal() as db:
            prediction = await _get_prediction_with_positions(db, prediction_id)
            # Same order run_once itself uses: balance applied first, so
            # the resolution snapshot below sees this cycle's fresh read.
            genlayer_indexer._apply_prediction_balance(
                prediction, {"ok": True, "result": "3000000000000000000"}
            )
            await genlayer_indexer._apply_prediction_view(
                db,
                prediction,
                {
                    "ok": True,
                    "result": {
                        "state": "RESOLVED",
                        "winning_outcome": "YES",
                        "total_yes_stake": "3000000000000000000",
                        "total_no_stake": "0",
                    },
                },
            )
            await db.commit()

        refetched = await _get_prediction(prediction_id)
        assert refetched.status_key == "RESOLVED"
        assert refetched.contract_balance == Decimal("3")
        assert refetched.contract_balance_at_resolution == Decimal("3")

    asyncio.run(_run())


def test_no_payout_delivered_is_representable_and_distinguishable_from_a_real_one():
    """The exact scenario this whole fix exists to detect: nothing has
    left the contract since resolution (contract_balance still equals the
    snapshot) vs. a genuine payout (contract_balance has dropped below
    it) — both must be cleanly representable, matching
    test_escrow_contract_balance.py's own "funded_amount vs
    contract_balance disagree" case for the identical underlying bug."""
    prediction_id = asyncio.run(_create_prediction(status_key="open"))

    async def _run():
        async with AsyncSessionLocal() as db:
            prediction = await _get_prediction_with_positions(db, prediction_id)
            genlayer_indexer._apply_prediction_balance(
                prediction, {"ok": True, "result": "3000000000000000000"}
            )
            await genlayer_indexer._apply_prediction_view(
                db,
                prediction,
                {
                    "ok": True,
                    "result": {
                        "state": "RESOLVED",
                        "winning_outcome": "YES",
                        "total_yes_stake": "3000000000000000000",
                        "total_no_stake": "0",
                    },
                },
            )
            await db.commit()

        # A later cycle: someone called claim_winnings (the tx itself
        # finalized), but the platform bug means the balance hasn't moved.
        async with AsyncSessionLocal() as db:
            prediction = await db.get(Prediction, prediction_id)
            genlayer_indexer._apply_prediction_balance(
                prediction, {"ok": True, "result": "3000000000000000000"}
            )
            await db.commit()

        stuck = await _get_prediction(prediction_id)
        assert stuck.contract_balance == stuck.contract_balance_at_resolution == Decimal("3")

        # Contrast: a genuine payout would show a real drop.
        async with AsyncSessionLocal() as db:
            prediction = await db.get(Prediction, prediction_id)
            genlayer_indexer._apply_prediction_balance(
                prediction, {"ok": True, "result": "1000000000000000000"}
            )
            await db.commit()

        delivered = await _get_prediction(prediction_id)
        assert delivered.contract_balance_at_resolution == Decimal("3")
        assert delivered.contract_balance == Decimal("1")
        assert delivered.contract_balance_at_resolution - delivered.contract_balance == Decimal("2")

    asyncio.run(_run())
